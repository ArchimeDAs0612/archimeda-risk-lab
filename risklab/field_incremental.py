"""Versioned transactions and selective materialization on the existing registry.

No semantic approval, model service or second registry database is introduced.
The same registry JSON stores revision, idempotency receipts and invalidations.
Local flock + compare-and-swap prevent cooperating writers from overwriting a
newer revision. Readers must validate provenance before using old artifacts.
"""
import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .data import AdmissionError
from .contracts import FORBIDDEN
from .study_contracts import workspace_path
from .field_intelligence import (atomic_registry, digest, effects, frame_digest,
                                 initial_registry, inventory, run_change, flatten_container)


def stable_field_id(domain, source, path=()):
    if not isinstance(domain, str) or not domain or not isinstance(source, str) or not source:
        raise ValueError('domain/source required')
    if not isinstance(path, (list, tuple)) or not all(isinstance(k, str) for k in path):
        raise ValueError('path must be a sequence of literal keys')
    pointer = ''.join('/'+k.replace('~', '~0').replace('/', '~1') for k in path)
    return dict(id=digest([domain, source, list(path)]), domain=domain, source=source,
                json_pointer=pointer, parent_id=digest([domain, source, list(path[:-1])]) if path else None)


def value_states(values, applicable=True, computed=True):
    """Coverage is semantic presence; zero/false are observations, blank is not.

    Literal nulls are separately recorded, not silently converted into true NA.
    """
    if not applicable:
        return dict(status='NOT_APPLICABLE', n=len(values), coverage=None, counts={})
    if not computed:
        return dict(status='NOT_COMPUTED', n=len(values), coverage=None, counts={})
    counts = dict(null=0, blank=0, literal_null=0, zero=0, false=0, value=0)
    for value in values:
        if value is None or (isinstance(value, (float, np.floating)) and np.isnan(value)) or value is pd.NA:
            counts['null'] += 1
        elif isinstance(value, (bool, np.bool_)) and not value:
            counts['false'] += 1
        elif isinstance(value, str) and not value.strip():
            counts['blank'] += 1
        elif isinstance(value, str) and value.strip().lower() in ['null', 'none', 'nan', 'n/a']:
            counts['literal_null'] += 1
        elif isinstance(value, (int, float, np.integer, np.floating)) and value == 0:
            counts['zero'] += 1
        else:
            counts['value'] += 1
    n = len(values); valid = counts['zero']+counts['false']+counts['value']
    return dict(status='NO_SAMPLE' if not n else 'ZERO_COVERAGE' if not valid else 'OBSERVED',
                n=n, coverage=valid/n if n else None, counts=counts)


def dependency_closure(contract, name):
    fields = {**contract.get('source_fields', {}), **contract['fields']}
    found = set()
    def visit(key, trail):
        if key in trail:
            raise AdmissionError('dependency cycle')
        if key not in fields:
            raise AdmissionError('unknown dependency')
        if key in found:
            return
        for parent in fields[key].get('parents', []):
            visit(parent, trail | {key})
        found.add(key)
    visit(name, set())
    return {key: fields[key] for key in sorted(found)}


def field_key(registry, frame, name, ordered_frame=None):
    graph = dependency_closure(registry['contract'], name)
    columns = sorted(set(graph)&set(frame.columns))
    # Sort by unique event key: row ordering must not cause unnecessary work.
    if 'event_id' not in frame or frame.event_id.isna().any() or frame.event_id.duplicated().any():
        raise AdmissionError('materialization requires unique event identity')
    ordered = frame.sort_values('event_id') if ordered_frame is None else ordered_frame
    observed = ordered[sorted(set(columns)|{'event_id'})]
    return digest(dict(domain=registry['contract']['domain'], graph=graph,
                       observed_sha256=frame_digest(observed)))


def materialize(registry, frame, previous=None):
    """Cache real per-field vectors and stats; blocked fields never retain vectors."""
    if 'event_id' not in frame or frame.event_id.isna().any() or frame.event_id.duplicated().any():
        raise AdmissionError('materialization requires unique event identity')
    graph = effects(registry['contract'])
    observed_digest = frame_digest(frame)
    fresh = registry['evidence_sha256'] == observed_digest
    old = (previous or {}).get('fields', {})
    result = {}; recomputed = []; reused = []
    nested = [name for name in registry['contract']['fields'] if name.startswith('context_json.')]
    expanded = frame
    if nested:
        if 'context_json' not in frame:
            raise AdmissionError('registered structured source is missing')
        expanded = frame.copy()
        parsed = []
        for value in frame.context_json:
            if not isinstance(value,str) or len(value)>16384:
                raise AdmissionError('invalid structured source size/type')
            try:
                parsed.append(flatten_container(json.loads(value),'context_json'))
            except (ValueError,TypeError) as error:
                raise AdmissionError('invalid structured source') from error
        for name in nested:
            expanded[name]=[row.get(name) for row in parsed]
    ordered = expanded.sort_values('event_id')
    for name, metadata in sorted(registry['contract']['fields'].items()):
        domain = registry['contract']['domain']
        identity = stable_field_id(domain, 'context_json', name.split('.')[1:]) if name in nested else stable_field_id(domain, name)
        reasons = list(graph[name]['reasons'])
        if not fresh:
            reasons.append('STALE_DATA_EVIDENCE')
        if name not in ordered:
            reasons.append('MISSING_PHYSICAL_FIELD')
        if reasons:
            result[name] = dict(identity=identity, status='BLOCKED', reasons=sorted(set(reasons)), values=None, key=None)
            continue
        key = field_key(registry, expanded, name, ordered_frame=ordered)
        cached = old.get(name)
        if cached and cached.get('status') == 'VALID' and cached.get('key') == key:
            # Revalidate content digest; never trust a stale/tampered cache by key alone.
            content = {k: v for k, v in cached.items() if k != 'content_sha256'}
            if digest(content) == cached.get('content_sha256'):
                result[name] = copy.deepcopy(cached); reused.append(name); continue
        values = ordered[name]
        if not pd.api.types.is_numeric_dtype(values):
            result[name] = dict(identity=identity, status='BLOCKED', reasons=['NONNUMERIC_MODEL_INPUT'], values=None, key=key)
            continue
        numeric = values.to_numpy(float)
        if np.isinf(numeric).any():
            raise AdmissionError('nonfinite input')
        stats = value_states(values.tolist())
        row = dict(identity=identity, key=key, status='VALID',
                   values=[None if np.isnan(v) else float(v) for v in numeric],
                   stats=stats, unit=metadata.get('unit'), domain=domain)
        row['content_sha256'] = digest(row)
        result[name] = row; recomputed.append(name)
    return dict(registry_sha256=digest(registry), frame_sha256=observed_digest,
                domain=registry['contract']['domain'], revision=registry.get('revision', 0),
                event_ids=ordered.event_id.tolist(), fields=result,
                recomputed=recomputed, reused=reused, llm_used=False)


def validate_materialization(cache, registry, frame):
    if (cache['registry_sha256'] != digest(registry) or cache['frame_sha256'] != frame_digest(frame)
            or cache['domain'] != registry['contract']['domain']
            or cache['event_ids'] != frame.sort_values('event_id').event_id.tolist()
            or set(cache['fields']) != set(registry['contract']['fields'])):
        return dict(status='INVALIDATED', model=False, pattern=False, report=False,
                    reason='registry, domain or evidence changed; materialize current revision')
    for row in cache['fields'].values():
        if row['status'] == 'VALID' and row.get('content_sha256') != digest({k: v for k, v in row.items() if k != 'content_sha256'}):
            return dict(status='INVALIDATED', model=False, pattern=False, report=False, reason='cache content hash mismatch')
    for name, state in effects(registry['contract']).items():
        if not state['allow_analysis'] and cache['fields'][name]['status'] != 'BLOCKED':
            return dict(status='INVALIDATED', model=False, pattern=False, report=False, reason='blocked field revived in cache')
    return dict(status='CURRENT', model=True, pattern=True, report=True,
                reason='individual requested fields still require admission')


def admitted_matrix(cache, registry, frame, requested):
    if validate_materialization(cache, registry, frame)['status'] != 'CURRENT':
        raise AdmissionError('stale materialization cannot feed model or pattern')
    if not requested or len(set(requested)) != len(requested) or any(name in FORBIDDEN or name.endswith('_id') or name not in cache['fields'] or cache['fields'][name]['status'] != 'VALID' for name in requested):
        raise AdmissionError('disabled, unknown or conflicted model/pattern field')
    return pd.DataFrame({name: cache['fields'][name]['values'] for name in requested}, index=cache['event_ids'])


def transaction(path, frame, request_id, expected_revision, proposal, fail_before_commit=False, workspace=None):
    """Single-file journal commit. Failed prepare leaves the last valid file intact."""
    import fcntl
    path = workspace_path(path, workspace)
    if not isinstance(request_id, str) or not request_id or len(request_id) > 128:
        raise ValueError('bounded request identity required')
    payload = digest(proposal)
    with path.with_suffix('.lock').open('a+') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        before = json.loads(path.read_text())
        if before['evidence_sha256'] != frame_digest(frame):
            raise AdmissionError('STALE_DATA_EVIDENCE')
        receipts = before.get('change_receipts', {})
        if request_id in receipts:
            if receipts[request_id]['proposal_sha256'] != payload:
                raise AdmissionError('idempotency key reused with different content')
            return before, dict(receipts[request_id], replayed=True)
        if before.get('revision', 0) != expected_revision:
            raise AdmissionError('STALE_REVISION: reload, never overwrite newer state')
        after, record = run_change(before, proposal, frame)
        if record['status'] != 'CANDIDATE_SAVED':
            raise AdmissionError(record['error'])
        after['revision'] = expected_revision+1
        receipt = dict(request_id=request_id, revision=after['revision'], proposal_sha256=payload,
                       affected=sorted(record['downstream']), status=record['status'], replayed=False)
        after.setdefault('change_receipts', {})[request_id] = receipt
        after['artifact_validity'] = dict(status='REQUIRES_REVALIDATION', previous_registry_sha256=digest(before),
                                         reason='field contract changed; old model/report/cache provenance is stale')
        if fail_before_commit:
            raise AdmissionError('INJECTED_BEFORE_COMMIT: previous registry retained')
        atomic_registry(path, after)
        return after, receipt


def run_incremental_study(data_dir, out):
    """Execute hand-specified adverse cases against actual existing registry/tools."""
    from .models import fit_model, probabilities
    out = workspace_path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError('choose empty output')
    out.mkdir(parents=True, exist_ok=True)
    data_dir = workspace_path(data_dir)
    frame = pd.read_csv(data_dir/'samples.csv', float_precision='round_trip')
    registry = json.loads((data_dir/'field/registry.json').read_text())
    if frame_digest(frame) != registry['evidence_sha256']:
        raise AdmissionError('source registry mismatch')
    before = materialize(registry, frame)
    atomic_registry(out/'registry.json', registry)
    checks = []; records = []
    def check(name, value, expected):
        checks.append(dict(name=name, actual=value, expected=expected, passed=value == expected))
    # A real model sees only gated vectors, with labels joined by event identity.
    matrix = admitted_matrix(before, registry, frame, ['amount', 'device_users_7d'])
    matrix['risk_label'] = frame.set_index('event_id').loc[matrix.index, 'risk_label']
    fitted = fit_model(matrix, ['amount', 'device_users_7d'], 'lr', {'seed': 772})
    p = probabilities(fitted, matrix)
    check('model_before_rows', len(p), len(frame))
    proposal = dict(operation='disable', field='linked_device_id')
    after, record = transaction(out/'registry.json', frame, 'disable-device', 0, proposal)
    records.append(record)
    cached = materialize(after, frame, before); full = materialize(after, frame)
    check('incremental_equals_full', cached['fields'] == full['fields'], True)
    check('unaffected_amount_reused', 'amount' in cached['reused'], True)
    check('device_vector_removed', cached['fields']['device_users_7d']['values'], None)
    check('old_report_invalidated', validate_materialization(before, after, frame)['report'], False)
    try:
        admitted_matrix(cached, after, frame, ['amount', 'device_users_7d'])
        blocked = False
    except AdmissionError:
        blocked = True
    check('model_and_candidate_blocked', blocked, True)
    _, replayed = transaction(out/'registry.json', frame, 'disable-device', 0, proposal)
    check('identical_request_idempotent', replayed['revision'], 1)
    for name, request, revision, change, inject in [
        ('stale_writer', 'old', 0, dict(operation='disable', field='amount'), False),
        ('key_collision', 'disable-device', 1, dict(operation='disable', field='amount'), False),
        ('interrupted_prepare', 'future', 1, dict(operation='modify', field='amount', changes={'unit': 'cents'}), True)]:
        old_bytes = (out/'registry.json').read_bytes()
        try:
            transaction(out/'registry.json', frame, request, revision, change, inject)
            rejected = False
        except AdmissionError as error:
            rejected = True; records.append(dict(scenario=name, error=str(error)))
        check(name+':rejected', rejected, True)
        check(name+':file_unchanged', (out/'registry.json').read_bytes() == old_bytes, True)
    recovered, receipt = transaction(out/'registry.json', frame, 'future', 1, dict(operation='modify', field='amount', changes={'unit': 'cents'}))
    check('retry_after_prepare_failure', receipt['revision'], 2)
    check('unit_change_requires_review', effects(recovered['contract'])['amount']['allow_analysis'], False)
    # Same-name fields in an independent fictional domain never share cache identity.
    other_contract = copy.deepcopy(registry['contract']); other_contract['domain'] = 'fictional_delivery'
    for row in list(other_contract['fields'].values())+list(other_contract['source_fields'].values()):
        row['domain'] = 'fictional_delivery'
    other = initial_registry(other_contract, frame)
    other_cache = materialize(other, frame, before)
    check('same_name_domain_isolated', other_cache['fields']['amount']['identity']['id'] != before['fields']['amount']['identity']['id'], True)
    check('other_domain_not_reused', len(other_cache['reused']), 0)
    inv = inventory(frame, other_contract['fields'], domain=other_contract['domain'])
    check('correct_domain_not_falsely_conflicted', any('DOMAIN_CONFLICT' in r['conflicts'] for r in inv['fields']), False)
    # Fixed expected counts are hand specified; they are not generated by this tool.
    state = value_states([None, '', '  ', 'null', 0, False, 3])
    check('null_blank_literal_zero_false_distinct', state['counts'], dict(null=1, blank=2, literal_null=1, zero=1, false=1, value=1))
    check('zero_coverage_distinct_no_sample', value_states([None])['status'], 'ZERO_COVERAGE')
    check('no_sample_distinct', value_states([])['status'], 'NO_SAMPLE')
    check('not_applicable', value_states([], applicable=False)['coverage'], None)
    check('not_computed', value_states([], computed=False)['status'], 'NOT_COMPUTED')
    check('literal_dot_path_is_not_nested', stable_field_id('wallet', 'context', ['a.b'])['id'] != stable_field_id('wallet', 'context', ['a', 'b'])['id'], True)
    # Aggregate evidence only; full cached feature vectors stay in local run.
    result = dict(status='PASS' if all(r['passed'] for r in checks) else 'FAIL', checks=checks, changes=records,
                  before=dict(valid=[k for k, v in before['fields'].items() if v['status']=='VALID'], model_rows=len(p)),
                  after=dict(blocked={k: v['reasons'] for k, v in cached['fields'].items() if v['status']=='BLOCKED'}, reused=cached['reused'], recomputed=cached['recomputed']),
                  evidence_sha256=frame_digest(frame), llm_used=False,
                  limits=['local cooperating writers only', 'no authenticated reviewer identity', 'no semantic auto-approval',
                          'numeric sample materialization, upstream SQL remains separately validated', 'old artifacts require validator at consumption'])
    atomic_registry(out/'result.json', result)
    return result

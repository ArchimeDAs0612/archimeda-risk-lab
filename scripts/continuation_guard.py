"""Fail-closed recovery checks. No scheduler, model invocation or implicit launcher.

The native automation owns scheduling. This module reuses night_state's ledger
and immutable clocks. The OS lock protects cooperating writers only; a checkpoint
or an expired timestamp never proves that another agent/process has stopped.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path


class Busy(RuntimeError):
    pass


def utcnow():
    return datetime.now(timezone.utc)


def digest(path):
    with Path(path).open('rb') as source:
        h = hashlib.sha256()
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            h.update(chunk)
        return h.hexdigest()


def within(root, name):
    path = (root / name).resolve()
    path.relative_to(root.resolve())
    return path


@contextmanager
def exclusive(workspace, execution_id):
    """Hold flock for the ENTIRE writing operation, never claim-and-release.

    Never unlink this inode: doing so could create two independent locks.
    A leftover identity record is not a live lease. OS lock ownership is truth.
    """
    import fcntl  # Unsupported platforms fail, rather than continuing unlocked.
    root = Path(workspace).resolve()
    lock = root / '.lab-run' / 'writer.lock'
    lock.parent.mkdir(parents=True, exist_ok=True)
    with lock.open('a+', encoding='utf-8') as stream:
        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise Busy('another cooperating writer owns workspace lock') from exc
        try:
            record = dict(execution_id=execution_id, pid=os.getpid(),
                          started_at=utcnow().isoformat(), source='POSIX flock',
                          workspace=str(root))
            stream.seek(0)
            stream.truncate()
            json.dump(record, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
            yield record
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def verify_checkpoint(state, workspace):
    """Validate saved result/source/UI/release plus every frozen manifest entry.

    Checks consistency against accepted hashes, not independent authentication
    of who accepted them. No files or checkpoints are rewritten by this probe.
    """
    root = Path(workspace).resolve()
    valid = state['last_valid']
    checks = {}
    checks['result'] = digest(within(root, valid['artifact']) / 'result.json') == valid['result_sha256']
    for name, expected in valid['code_sha256'].items():
        checks['code:' + name] = digest(within(root, name)) == expected
    for name, expected in valid['ui_sha256'].items():
        checks['ui:' + name] = digest(within(root, 'risklab/web/' + name)) == expected
    manifest = root / 'release-manifest.sha256'
    checks['manifest'] = digest(manifest) == valid['manifest_sha256']
    # The archive is intentionally a sibling of this workspace, not any path.
    archive_name = valid['archive']
    if Path(archive_name).name != archive_name:
        raise ValueError('archive must be a sibling filename')
    checks['archive'] = digest(root.parent / archive_name) == valid['archive_sha256']
    for line in manifest.read_text(encoding='utf-8').splitlines():
        expected, name = line.split('  ', 1)
        checks['release:' + name] = digest(within(root, name)) == expected
    return {'valid': bool(checks) and all(checks.values()),
            'checked': len(checks), 'failed': [k for k, v in checks.items() if not v]}


def decide(state, workspace, observation=None, now=None, checkpoint=None):
    """Pure decision; observations must come from actual native task inspection.

    Missing/incomplete/stale host inventory => SKIP. Caller-controlled JSON is
    not an authorization credential. CLI intentionally cannot launch writers.
    """
    now = now or utcnow()
    if Path(state['workspace']).resolve() != Path(workspace).resolve():
        raise ValueError('workspace mismatch')
    start = datetime.fromisoformat(state['started_at'])
    deadline = datetime.fromisoformat(state['deadline_at'])
    if not start.tzinfo or not deadline.tzinfo or deadline <= start:
        raise ValueError('invalid absolute budget')
    items = state['items']
    ids = [x['id'] for x in items]
    if not items or len(set(ids)) != len(ids):
        raise ValueError('missing or duplicate milestones')
    # A proven completed run needs no active writer and may safely disable a
    # scheduler, even if the current chat is busy installing this mechanism.
    if all(x['status'] == 'DONE' for x in items):
        if checkpoint and checkpoint.get('valid'):
            return {'action': 'COMPLETED', 'disable_schedule': True,
                    'reason': 'all accepted milestones and frozen checkpoint verified'}
        return {'action': 'SKIP', 'reason': 'completion evidence not verified'}
    if state.get('stop_marker') or state['status'] in ('PAUSED', 'WAITING_HUMAN'):
        return {'action': 'STOP', 'reason': 'manual stop or required authorization', 'disable_schedule': True}
    if now >= deadline:
        return {'action': 'STOP', 'reason': 'absolute deadline reached', 'disable_schedule': True}
    if state['status'] in ('DONE', 'COMPLETED'):
        return {'action': 'SKIP', 'reason': 'completion status conflicts with pending milestones'}
    if state.get('active_jobs'):
        return {'action': 'SKIP', 'reason': 'saved execution identities require native/process inspection'}
    observation = observation or {}
    try:
        age = (now - datetime.fromisoformat(observation['observed_at'])).total_seconds()
    except (KeyError, ValueError, TypeError):
        return {'action': 'SKIP', 'reason': 'no trustworthy host observation'}
    if not 0 <= age <= 60 or observation.get('source') != 'native_task_inspection':
        return {'action': 'SKIP', 'reason': 'stale or unsupported host observation'}
    if not observation.get('inventory_complete') or observation.get('other_writers') != 'NONE':
        return {'action': 'SKIP', 'reason': 'concurrent writers cannot be excluded'}
    if observation.get('original_execution') != 'STOPPED':
        return {'action': 'SKIP', 'reason': 'original execution active or unknown'}
    if not checkpoint or not checkpoint.get('valid'):
        return {'action': 'SKIP', 'reason': 'last valid checkpoint not verified'}
    done = {x['id'] for x in items if x['status'] == 'DONE'}
    for item in items:
        if item['status'] not in ('IDLE', 'READY_TO_RESUME', 'RUNNING'):
            continue  # BLOCKED branches do not prevent independent work.
        if not set(item.get('depends_on', ())) <= done or item.get('requires_authorization'):
            continue
        if state.get('retry_counts', {}).get(item['id'], 0) >= 2:
            continue  # Two failures without new evidence: explicit alternative required.
        if item.get('next_action'):
            return {'action': 'READY', 'milestone': item['id'], 'next': item['next_action'],
                    'mode': 'Checkpoint-based continuation', 'deadline_at': state['deadline_at'],
                    'requires_held_lock': True}
    return {'action': 'BLOCKED', 'reason': 'no independent authorized, non-repeating action remains'}


def probe(state_path, workspace, observation=None, now=None):
    state = json.loads(Path(state_path).read_text(encoding='utf-8'))
    if Path(state['workspace']).resolve() != Path(workspace).resolve():
        raise ValueError('workspace mismatch')
    try:
        checkpoint = verify_checkpoint(state, workspace)
    except (KeyError, ValueError, OSError) as exc:
        checkpoint = {'valid': False, 'error': str(exc)}
    return {'run_id': state['run_id'], 'started_at': state['started_at'],
            'deadline_at': state['deadline_at'], 'observed_at': (now or utcnow()).isoformat(),
            'checkpoint': checkpoint,
            'decision': decide(state, workspace, observation, now, checkpoint)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--workspace', type=Path, required=True)
    args = parser.parse_args()
    # No launch or state-mutating flags. The native caller must inspect its real
    # execution state and hold exclusive() throughout any subsequent write.
    print(json.dumps(probe(args.state, args.workspace), ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()

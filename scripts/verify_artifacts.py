"""Independent saved-evidence checks (standard library only, no sklearn metric calls)."""
import csv
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REF = ROOT/'artifacts/reference'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def average_precision(rows, model):
    groups = {}
    for row in rows:
        key = float(row[model])
        n, positives = groups.get(key,(0,0))
        groups[key] = (n+1, positives+int(row['risk_label']))
    total_positive = sum(p for n,p in groups.values())
    seen = hits = 0
    ap = 0.
    for score in sorted(groups, reverse=True):
        n,p = groups[score]
        seen += n; hits += p
        ap += p/total_positive * hits/seen
    return ap


def verify():
    result = json.loads((REF/'normal/result.json').read_text())
    with (REF/'normal/predictions.csv').open() as f:
        rows = list(csv.DictReader(f))
    checks = {}
    for split in ('train','select','test'):
        part = [r for r in rows if r['split']==split]
        checks[split+'_n'] = len(part)==result['splits'][split]['n']
        for model in ('score_lr','raw_lr','hybrid_lr','raw_tree','hybrid_tree','without_device_lr'):
            checks[split+'_'+model+'_ap'] = math.isclose(average_precision(part,model),result['model_comparison'][model][split]['ap'],abs_tol=1e-12)
        candidate = [r for r in part if r['candidate']=='True']
        checks[split+'_candidate_support'] = len(candidate)==result['candidate'][split]['n']
        checks[split+'_candidate_positive'] = sum(int(r['risk_label']) for r in candidate)==result['candidate'][split]['risk_count']
    frozen_source = ROOT/'artifacts/baseline-v0.1.1/source'
    checks['code_hashes'] = all(sha(frozen_source/Path(p).name if frozen_source.exists() else ROOT/p)==h for p,h in result['provenance']['code_sha256'].items())
    checks['data_hashes'] = all(sha(REF/'data'/p)==h for p,h in result['provenance']['data_sha256'].items())
    for name in ('normal','repaired','bad_future','bad_missing_time','bad_source_binding','bad_cross_event'):
        branch = json.loads((REF/name/'result.json').read_text())
        checks[name+'_current_provenance'] = branch['provenance']['code_sha256']==result['provenance']['code_sha256'] and branch['provenance']['data_sha256']==result['provenance']['data_sha256']
        if name.startswith('bad_'):
            checks[name+'_no_conclusions'] = branch['admission']['evidence_admission']=='BLOCKED' and branch['candidate_verdict']=='NOT_EVALUATED' and branch['model_comparison'] is None and not (REF/name/'frozen_selection.json').exists()
    return {'method':'independent CSV AP by tied-score precision/recall increments; candidate counts; SHA256 and branch restrictions','checks':checks}


if __name__ == '__main__':
    receipt = verify()
    print(json.dumps(receipt,indent=2))
    if not all(receipt['checks'].values()):
        raise SystemExit(1)

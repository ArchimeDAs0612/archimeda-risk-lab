"""Compare clean-room research outputs to saved aggregates, excluding timings.

Explicit research keys only; source-code hashes are checked against the current
checkout separately. Do not compare timings as if they were reproducible data.
"""
import argparse
import json
from pathlib import Path
from risklab.pipeline import sha, save_json
from risklab.external_credit import fixed_capacity
import numpy as np
import pandas as pd
from scipy.special import expit, logit
from risklab.study_contracts import workspace_path


KEYS={
    'external-credit':('credit-study',['quality','winner','models','fixed_capacity','paired_ap_vs_lr','pattern','calibration','slices','reference_implementation']),
    'selective-maturity':('selection-study',['protocol','frozen','models','audit_repeats','nonidentification','visibility','separate_events','policy_scenarios','cold_start']),
    'label-sensitivity':('label-sensitivity',['protocol','frozen','models','oracle_rate','outcome_dependent_trials','delay_summary','naive_mean','raw_weight_sum','normalized_weight_sum']),
    'rolling-monitor':('rolling-study',['protocol','windows','monitor','quality']),
    'incremental-fields':('field-incremental',['status','checks','before','after','changes','limits']),
}


def calibration_capacity(runs):
    folder=runs/'credit-study'
    frozen=json.loads((folder/'frozen_selection.json').read_text())
    predictions=pd.read_csv(folder/'private_predictions.csv',float_precision='round_trip')
    p=predictions[frozen['winner'].replace('/','_')].to_numpy()
    calibrated=expit(logit(np.clip(p,1e-6,1-1e-6))*frozen['calibration_slope']+frozen['calibration_intercept'])
    ids=predictions.record_id.to_numpy();y=predictions.label.to_numpy()
    n=int(np.floor(len(y)*.1))
    original_ids=ids[np.lexsort((ids,-p))[:n]]
    calibrated_ids=ids[np.lexsort((ids,-calibrated))[:n]]
    return dict(original=fixed_capacity(y,p,ids),sigmoid=fixed_capacity(y,calibrated,ids),
                identical_selected_records=bool(np.array_equal(original_ids,calibrated_ids)),
                scope='fixed predeclared 10% capacity with record-ID tie break; saved frozen sigmoid parameters; no model refit or threshold reselection')


def verify(reference,runs):
    reference=workspace_path(reference);runs=workspace_path(runs);checks={}
    for name,(folder,keys) in KEYS.items():
        expected=json.loads((reference/name/'result.json').read_text())
        actual=json.loads((runs/folder/'result.json').read_text())
        for key in keys:
            if key not in expected or key not in actual:
                raise ValueError('missing expected research key: '+name+'/'+key)
            checks[name+'/'+key]=expected[key]==actual[key]
        checks[name+'/rendered_report']=(runs/folder/'index.html').is_file()
    credit=json.loads((runs/'credit-study/result.json').read_text())
    checks['credit/source_data_checksum']=credit['provenance']['data_sha256']==json.loads(Path('config/credit_protocol.json').read_text())['source_sha256']
    checks['credit/disjoint_profile_splits']=credit['quality']['split_profile_overlap'] is False
    for filename,folder in [('external_credit.py','credit-study'),('rolling_study.py','rolling-study'),('label_sensitivity.py','label-sensitivity')]:
        result=json.loads((runs/folder/'result.json').read_text())
        recorded=result['provenance']['source_sha256'][filename] if folder=='credit-study' else result['source_sha256']
        checks[folder+'/current_source_hash']=recorded==sha(Path('risklab')/filename)
    resource=json.loads((runs/'resource-study/result.json').read_text())
    checks['resources/scales']=[r['rows'] for r in resource['sizes']]==[300,1500,6000]
    checks['resources/equality']=all(r['equal_field_results'] and r['membership']['all_paths_equal'] for r in resource['sizes'])
    capacity=calibration_capacity(runs)
    checks['calibration/capacity_matches_saved']=capacity==json.loads((reference/'external-credit/calibration_capacity.json').read_text())
    return dict(calibration_capacity=capacity,status='PASS' if all(checks.values()) else 'FAIL',checks=checks,
                scope='exact aggregate equality on the same fixed dependency versions; source hashes and resource invariants checked; elapsed time, host metadata and source revisions excluded from cross-run numeric equality')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference',default='artifacts/rc1');parser.add_argument('--runs',default='runs');parser.add_argument('--out',required=True)
    args=parser.parse_args();out=workspace_path(args.out);result=verify(args.reference,args.runs)
    save_json(out,result);print(json.dumps(result));raise SystemExit(0 if result['status']=='PASS' else 1)

"""Verify saved inference, physical identity and existing independent research checks."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from risklab.model_artifact import predict_json
from verify_v02 import verify


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    args=parser.parse_args();run=args.run
    independent=verify(run)
    result=json.loads((run/'result.json').read_text())
    sample=pd.read_csv(run/'samples.csv',float_precision='round_trip').set_index('event_id')
    predictions=pd.read_csv(run/'all_predictions.csv',float_precision='round_trip')
    checks={'independent_rank_path_policy_and_provenance':independent['passed']==independent['total'],
            'unique_prediction_ids':not predictions.event_id.duplicated().any()}
    errors={}
    for name,receipt in result['saved_model_validation'].items():
        path=run/'models'/(name+'.json')
        checks[name+'_artifact_hash']=hashlib.sha256(path.read_bytes()).hexdigest()==receipt['sha256']
        artifact=json.loads(path.read_text())
        expected=predictions[name].to_numpy()
        actual=predict_json(artifact,sample.loc[predictions.event_id])
        error=float(np.max(np.abs(actual-expected)));errors[name]=error
        checks[name+'_all_split_inference']=error<1e-12
    events=pd.read_csv(run/'data/events.csv',float_precision='round_trip')
    differences=[]
    for _,group in events.groupby('device_id'):
        group=group.sort_values('decision_ts')
        differences.extend(np.abs(np.diff(group.device_age_days)-np.diff(group.decision_ts)/86400))
    checks['physical_device_clock_consistent']=bool(differences) and bool(max(differences)<1e-10)
    report=dict(checks=checks,passed=sum(checks.values()),total=len(checks),inference_max_abs_errors=errors,
                independent_checks=independent['total'],scope='saved synthetic evidence only; not external generalization or production assurance')
    print(json.dumps(report,indent=2))
    return 0 if all(checks.values()) else 1


if __name__=='__main__':
    sys.exit(main())

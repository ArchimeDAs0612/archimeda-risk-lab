"""End-to-end final-label mutation: selection must stay invariant.

Small independent numeric fixture uses the public CSV loader and all three
models. Reversed final labels are adversarial input, never research evidence.
"""
import copy
import json
import tempfile
import unittest
from pathlib import Path
import numpy as np
import pandas as pd
from risklab.external_credit import NAMES, STATUS, assign_splits, run_credit
from risklab.pipeline import sha


class CreditFinalIsolationTests(unittest.TestCase):
    def test_final_labels_cannot_change_fitting_calibration_or_rule_choice(self):
        rng=np.random.default_rng(514)
        f=pd.DataFrame(rng.integers(-20,20,size=(1000,23)),columns=NAMES)
        for c in STATUS:f[c]=rng.choice([-1,0,1,2],len(f))
        f['SEX']=rng.choice([1,2],len(f));f['AGE']=rng.integers(21,70,len(f))
        f['ID']=np.arange(len(f));f['risk_label']=((f.PAY_0>=1)&(rng.random(len(f))<.8)).astype(int)
        config=json.loads(Path('config/credit_protocol.json').read_text())
        config.update(seeds=[317],bootstrap_repeats=20,rediscovery_repeats=1,min_leaf=10,candidate_min_select=10)
        # Integer-valued source prevents CSV decimal round-trip noise from
        # changing the feature-profile hash used to identify final rows.
        split=assign_splits(f,config['split_seed']).set_index('ID').split
        changed=f.copy();mask=changed.ID.map(split).eq('test');changed.loc[mask,'risk_label']=1-changed.loc[mask,'risk_label']
        # tempfile inside this test workspace exercises the same path contract.
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as folder:
            root=Path(folder)
            for name,frame in [('a',f),('b',changed)]:
                csv=frame[['ID']+NAMES+['risk_label']].copy();csv.columns=['ID']+[f'X{i}' for i in range(1,24)]+['Y']
                source=root/(name+'.csv');csv.to_csv(source,index=False)
                protocol=copy.deepcopy(config);protocol['source_sha256']=sha(source)
                run_credit(source,root/name,protocol)
            a=json.loads((root/'a/frozen_selection.json').read_text());b=json.loads((root/'b/frozen_selection.json').read_text())
            a.pop('protocol_sha256');b.pop('protocol_sha256')
            self.assertEqual(a,b)
            ra=json.loads((root/'a/result.json').read_text());rb=json.loads((root/'b/result.json').read_text())
            self.assertNotEqual(ra['models'],rb['models'])
            pa=pd.read_csv(root/'a/private_predictions.csv');pb=pd.read_csv(root/'b/private_predictions.csv')
            pd.testing.assert_frame_equal(pa.drop(columns='label'),pb.drop(columns='label'))


if __name__=='__main__':unittest.main()

import unittest
import numpy as np
from risklab.generate import simulate, DAY
from risklab.research_models import definitions
from risklab.entities import WINDOW_FEATURES
from risklab.generate import ORIGIN
from risklab.data import build_samples, split_samples
from risklab.contracts import check_admission, default_contract, RAW_FEATURES
import pandas as pd
from test_chain import config


class SimulatorInvariants(unittest.TestCase):
    def test_physical_device_age_advances_exactly_with_time(self):
        c=config(); c['orders']=1600
        events, _=simulate(c)
        checked=0
        for _, group in events.groupby('device_id'):
            group=group.sort_values('decision_ts')
            if len(group)>1:
                np.testing.assert_allclose(np.diff(group.device_age_days), np.diff(group.decision_ts)/DAY, atol=1e-10, rtol=0)
                checked+=1
        self.assertGreater(checked, 100)

    def test_full_velocity_input_ablation_removes_legacy_and_new_windows(self):
        columns, kind=definitions()['without_velocity_lr']
        self.assertEqual(kind,'lr')
        self.assertFalse(set(columns)&set(WINDOW_FEATURES+['attempts_24h','declines_7d']))
        self.assertIn('prior_score',columns)  # Input ablation, not erasure of proxy information.

    def test_prespecified_final_and_training_bounds_exclude_extra_events(self):
        c=config(); events,labels=simulate(c); sample=build_samples(events,labels)
        base=split_samples(sample,c)
        extras=[]
        for i,day in enumerate([-1,c['days'],c['days']+1]):
            row=sample.iloc[0].copy(); row['event_id']='outside'+str(i)
            row['decision_ts']=ORIGIN+day*DAY; row['label_available_ts']=row['decision_ts']+2*DAY
            extras.append(row)
        parts=split_samples(pd.concat([sample,pd.DataFrame(extras)],ignore_index=True),c)
        for key in parts:
            self.assertEqual(parts[key].event_id.tolist(),base[key].event_id.tolist())

    def test_infinite_audit_time_is_blocked_not_silently_dropped(self):
        c=config(); e,l=simulate(c); sample=build_samples(e,l)
        sample['label_available_ts']=sample.label_available_ts.astype(float)
        sample.loc[0,'label_available_ts']=np.inf
        gate=check_admission(sample,default_contract(),RAW_FEATURES)
        self.assertFalse(gate['allow_model'])
        self.assertIn('NONFINITE_TIME',[x['code'] for x in gate['findings']])

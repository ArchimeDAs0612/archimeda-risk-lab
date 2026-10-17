"""Adversarial hypotheses written against a frozen implementation, then tested.

The independent window oracle below uses Python sets/list filtering, not SQL or
the production window helpers. Expected rejection types are explicit.
"""
import unittest
import numpy as np
import pandas as pd
from risklab.entities import simulate_entities, build_enriched_samples, validate_events, enriched_contract
from risklab.contracts import check_admission
from risklab.data import AdmissionError, pair_cases, build_samples


def reference_windows(events):
    rows = list(events.itertuples(index=False)); result = {}
    for current in rows:
        values = {}
        for label, seconds in [('1h',3600),('24h',86400),('7d',604800)]:
            history=[r for r in rows if current.decision_ts-seconds <= r.decision_ts < current.decision_ts
                     and r.available_ts <= current.decision_ts and r.user_id == current.user_id]
            values['user_attempts_'+label] = len(history)
            values['user_amount_'+label] = sum(r.amount for r in history)
        history=[r for r in rows if current.decision_ts-604800 <= r.decision_ts < current.decision_ts
                 and r.available_ts <= current.decision_ts]
        values['user_devices_7d']=len({r.linked_device_id for r in history if r.user_id==current.user_id})
        values['user_tools_7d']=len({r.payment_tool_id for r in history if r.user_id==current.user_id})
        values['device_users_7d']=len({r.user_id for r in history if r.linked_device_id==current.linked_device_id})
        values['tool_users_7d']=len({r.user_id for r in history if r.payment_tool_id==current.payment_tool_id})
        result[current.event_id]=values
    return pd.DataFrame.from_dict(result,orient='index').sort_index()


class ReverseAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.events,cls.labels,_,_=simulate_entities({'seed':9731,'orders':130,'days':120})

    def test_sql_all_windows_match_independent_reference_and_shuffle(self):
        events=self.events.copy();labels=self.labels.copy()
        # Deliberately include lower-edge and equal-time ties in actual identities.
        ix=events.index[:4];t=int(events.decision_ts.iloc[0])
        events.loc[ix,'decision_ts']=[t,t+3600,t+3600,t+604800]
        for c in ['available_ts','device_available_ts','tool_available_ts','geo_available_ts']:
            events[c]=events.decision_ts-1
        events['result_ts']=events.decision_ts+15
        events.loc[ix,'user_id']='audit_shared'
        labels['label_available_ts']=events.decision_ts.to_numpy()+172800
        expected=reference_windows(events)
        actual,_=build_enriched_samples(events,labels)
        pd.testing.assert_frame_equal(actual.set_index('event_id')[expected.columns].sort_index(),expected,
                                      check_names=False,check_dtype=False,atol=1e-9,rtol=1e-12)
        shuffled,_=build_enriched_samples(events.sample(frac=1,random_state=3),labels.sample(frac=1,random_state=5))
        pd.testing.assert_frame_equal(actual.sort_values('event_id').reset_index(drop=True),shuffled.sort_values('event_id').reset_index(drop=True))

    def test_time_text_bool_timezone_and_nonfinite_fail_structurally(self):
        sample,_=build_enriched_samples(self.events,self.labels)
        replacements=[self.events.decision_ts.astype(str),pd.Series(True,index=self.events.index),
                      pd.to_datetime(self.events.decision_ts,unit='s',utc=True),pd.Series(float('inf'),index=self.events.index)]
        for values in replacements:
            bad=self.events.copy();bad['decision_ts']=values
            with self.assertRaises(AdmissionError): validate_events(bad)
            with self.assertRaises(AdmissionError): pair_cases(bad,24)
            with self.assertRaises(AdmissionError): build_samples(bad,self.labels)
            s=sample.copy();s['decision_ts']=values
            self.assertFalse(check_admission(s,enriched_contract(),['amount'])['allow_model'])

    def test_pairing_rejects_duplicate_identity_and_invalid_windows(self):
        duplicated=pd.concat([self.events,self.events.iloc[:1]],ignore_index=True)
        with self.assertRaises(AdmissionError):pair_cases(duplicated,24)
        for value in [0,-1,True,float('nan'),float('inf')]:
            with self.assertRaises(AdmissionError):pair_cases(self.events,value)


if __name__=='__main__':unittest.main()

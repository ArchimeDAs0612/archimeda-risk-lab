import copy
import unittest
import numpy as np
from risklab.entities import simulate_entities,build_enriched_samples,CaseGeometry,EXTENDED_FEATURES
from risklab.data import AdmissionError,split_samples
from risklab.contracts import check_admission,RAW_FEATURES,SCORE_FEATURES
from risklab.entities import enriched_contract
from test_chain import config


class EntityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=config();cls.events,cls.labels,cls.edges,cls.tables=simulate_entities(cls.c)
    def test_entity_grain_and_label_independent_assignments(self):
        self.assertEqual(len(self.edges),len(self.events)*4)
        self.assertEqual(len(self.events.event_id.unique()),len(self.events))
        self.assertTrue({'account','device','order','payment_tool'}==set(self.tables))
        self.assertTrue(self.events.groupby('order_id').payment_tool_id.nunique().eq(1).all())
        again,labels,_,_=simulate_entities(self.c)
        self.assertTrue(again.equals(self.events))
    def test_window_manual_boundary_ties_and_entity_sharing(self):
        e=self.events.iloc[:4].copy().reset_index(drop=True)
        e['event_id']=['a','b','c','d'];e['user_id']=['u0','u1','u0','u0']
        t=1000000;e['decision_ts']=[t,t+1,t+3600,t+3600]
        for col in ['available_ts','geo_available_ts','device_available_ts','tool_available_ts']:e[col]=e.decision_ts-1
        e['result_ts']=e.decision_ts+15;e['linked_device_id']='shared';e['amount']=[10,20,30,40]
        labels=self.labels.iloc[:4].copy().reset_index(drop=True);labels['event_id']=e.event_id;labels['label_available_ts']=e.decision_ts+172800
        s,q=build_enriched_samples(e,labels)
        self.assertEqual(s.user_attempts_1h.tolist(),[0,0,1,1])
        self.assertEqual(s.user_amount_1h.tolist(),[0,0,10,10])
        self.assertEqual(s.device_users_7d.tolist(),[0,1,2,2])
        self.assertEqual(len(s),4)
    def test_duplicate_missing_future_and_bad_container_rejected(self):
        for variant in ['duplicate','missing','future','container']:
            with self.subTest(variant=variant):
                e=self.events.copy()
                if variant=='duplicate':e=__import__('pandas').concat([e,e.iloc[:1]])
                if variant=='missing':e.loc[0,'decision_ts']=np.nan
                if variant=='future':e.loc[0,'tool_available_ts']=e.loc[0,'decision_ts']+1
                if variant=='container':e.loc[0,'context_json']='{"client":{"latency_ms":"bad"}}'
                with self.assertRaises(AdmissionError):build_enriched_samples(e,self.labels)
    def test_contract_and_train_only_geometry(self):
        sample,_=build_enriched_samples(self.events,self.labels)
        self.assertTrue(check_admission(sample,enriched_contract(),RAW_FEATURES+SCORE_FEATURES+EXTENDED_FEATURES)['allow_model'])
        parts=split_samples(sample,self.c);g=CaseGeometry().fit(parts['train'])
        before=copy.deepcopy(g.metadata());test=parts['test'].copy();test['amount']=1000000
        g.assign(test);self.assertEqual(g.metadata(),before)
        reference_ids=set(parts['train'].event_id)
        self.assertTrue(all(x['event_id'] in reference_ids for x in g.similar(parts['test'].iloc[:1])))
        c=enriched_contract();c['source_fields']['linked_device_id']['enabled']=False
        self.assertFalse(check_admission(sample,c,['device_users_7d'])['allow_model'])

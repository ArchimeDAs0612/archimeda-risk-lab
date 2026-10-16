import unittest
import numpy as np
import pandas as pd
from risklab.research_models import rank_metrics,leakage_probe,population_stability,train_models,evaluate_models
from risklab.entities import simulate_entities,build_enriched_samples
from risklab.data import split_samples
from test_chain import config

class ResearchModelTests(unittest.TestCase):
    def test_ks_lift_and_ap_hand_expected_with_ties(self):
        m=rank_metrics([0,1,0,1],[.1,.9,.2,.8],.5)
        self.assertEqual(m['ks'],1);self.assertEqual(m['lift_top_decile'],2)
        self.assertEqual(m['ap'],1);self.assertEqual(m['pr_auc_trapezoid'],1)
        tied=rank_metrics([0,1,0,1],[.5]*4,.5)
        self.assertEqual(tied['ks'],0);self.assertEqual(tied['lift_top_decile'],1)
        self.assertEqual(tied['top_decile_coverage'],1)
    def test_leakage_alerts_and_psi_known_identity(self):
        f=pd.DataFrame({'risk_label':[0,1]*10,'fake': [0,1]*10,'decision_ts':[10]*20,'seen':[11]*20,'event_id':list(range(20))})
        codes={a['code'] for a in leakage_probe(f,['fake','event_id'],{'fake':'seen'})['alerts']}
        self.assertEqual(codes,{'NEAR_PERFECT_LABEL_PROXY','FORBIDDEN_OR_ID','FUTURE_OR_UNKNOWN_AVAILABILITY'})
        self.assertAlmostEqual(population_stability(f,f,['fake'])['features'][0]['psi'],0.)
    def test_final_labels_cannot_change_models_winner_or_preprocessing(self):
        c=config();c['forest_trees']=12
        e,l,_,_=simulate_entities(c);s,_=build_enriched_samples(e,l);parts=split_samples(s,c)
        bundles,scores,frozen=train_models(parts,c)
        changed={k:v.copy() for k,v in parts.items()};changed['test']['risk_label']=1-changed['test'].risk_label
        b2,p2,f2=train_models(changed,c)
        self.assertEqual(frozen,f2)
        original=evaluate_models(parts,bundles,scores,frozen,c)
        altered=evaluate_models(changed,b2,p2,f2,c)
        self.assertNotEqual(original['comparison']['raw_lr']['test']['ap'],altered['comparison']['raw_lr']['test']['ap'])
        self.assertEqual(len(original['comparison']),15)

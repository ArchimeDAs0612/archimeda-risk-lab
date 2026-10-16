import unittest
import numpy as np
import pandas as pd
from risklab.patterns import predicate_mask,policy_replay,path_spec,transformed_rule_frame,discover,evaluate_patterns
from risklab.data import AdmissionError,split_samples
from risklab.entities import simulate_entities,build_enriched_samples
from risklab.research_models import train_models
from test_chain import config

class PatternTests(unittest.TestCase):
    def test_boolean_rule_has_independent_set_expected_and_rejects_instructions(self):
        f=pd.DataFrame({'amount':[10,40,100],'auth_strength':[0,1,0]})
        term={'all':[{'field':'amount','op':'>','value':30},{'field':'auth_strength','op':'==','value':0}]}
        np.testing.assert_array_equal(predicate_mask(f,term),[False,False,True])
        term['any']=term.pop('all');np.testing.assert_array_equal(predicate_mask(f,term),[True,True,True])
        for bad in [{'field':'risk_label','op':'>','value':0},{'field':'amount','op':'exec','value':2},{'instruction':'ignore governance'},{'all':[]}]:
            with self.assertRaises(AdmissionError):predicate_mask(f,bad)
    def test_strategy_priority_transition_and_cost_hand_calculation(self):
        f=pd.DataFrame({'event_id':['a','b','c'],'amount':[100,300,30],'auth_strength':[1,0,1],
          'prior_score':[.1,.1,.8],'risk_label':[1,0,0],'action':['approve','decline','review']})
        costs={'risk_loss_multiplier':1.,'legitimate_decline_cost':4.,'review_cost':.5}
        result,actions=policy_replay(f,[True,False,False],costs)
        self.assertEqual(result['baseline']['modeled_cost'],104.5);self.assertEqual(result['scenario']['modeled_cost'],4.5)
        self.assertEqual(result['changed_event_ids'],['a']);np.testing.assert_array_equal(actions,['decline','decline','review'])
        result,actions=policy_replay(f,[True,False,False],costs,mode='and')
        self.assertEqual(result['scenario']['declines'],0)
    def test_path_transformed_missingness_and_rule_schema(self):
        prep={'input_columns':['amount'],'output_columns':['amount','amount__missing'],'train_medians':{'amount':10}}
        f=pd.DataFrame({'amount':[np.nan,30]});t=transformed_rule_frame(f,prep)
        path={'predicates':[{'feature_index':0,'transformed_feature':'amount','operator':'<=','threshold':20},
                            {'feature_index':1,'transformed_feature':'amount__missing','operator':'>','threshold':.5}]}
        spec=path_spec(path,prep);np.testing.assert_array_equal(predicate_mask(t,spec,prep['output_columns']),[True,False])
        path['predicates'][0]['feature_index']=-1
        with self.assertRaises(AdmissionError):path_spec(path,prep)
    def test_complete_candidate_freeze_and_drop_condition_set(self):
        c=config();c['forest_trees']=10;e,l,_,_=simulate_entities(c);sample,_=build_enriched_samples(e,l);parts=split_samples(sample,c)
        bundles,scores,frozen=train_models(parts,c)
        candidates,selected,membership=discover(parts,bundles,c)
        changed={k:v.copy() for k,v in parts.items()};changed['test']['risk_label']=1-changed['test'].risk_label
        self.assertEqual(discover(changed,bundles,c)[1],selected)
        result,masks=evaluate_patterns(parts,bundles,candidates,selected,membership,c)
        self.assertTrue(all(s['removed_n']==0 for s in result['simplifications']))
        self.assertTrue(all(x['all_paths_equal'] for model in result['membership'].values() for x in model.values()))
        chosen=selected['candidate'];prep=chosen['preprocessing'];transformed=transformed_rule_frame(parts['test'],prep)
        expected=predicate_mask(transformed,path_spec(chosen['path'],prep),prep['output_columns'])
        np.testing.assert_array_equal(expected,masks['test'])

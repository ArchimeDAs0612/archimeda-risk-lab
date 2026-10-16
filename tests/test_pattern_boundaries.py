import copy
import json
import unittest

import numpy as np
import pandas as pd

from risklab.data import AdmissionError
from risklab.evidence import candidate_summary
from risklab.models import complete_paths, fit_model, replay
from risklab.patterns import complete_path_mask, path_spec, predicate_mask, verdict


class PatternBoundaryTests(unittest.TestCase):
    def test_root_only_cart_replays_every_row_without_promoting_empty_user_rule(self):
        frame=pd.DataFrame({'amount':[10.]*20,'risk_label':[0,1]*10,'user_id':['u'+str(i//2) for i in range(20)]})
        bundle=fit_model(frame,['amount'],'tree',{'seed':11,'tree_depth':3,'min_leaf':10})
        path=complete_paths(bundle)[0]
        self.assertEqual(path,{'leaf_id':0,'predicates':[],'train_support':20})
        expected=np.ones(20,dtype=bool)
        np.testing.assert_array_equal(replay(bundle,frame,path),expected)
        np.testing.assert_array_equal(complete_path_mask(frame,path,bundle['prep'].metadata()),expected)
        config={'bootstrap_repeats':8,'candidate_min_select':2,'candidate_min_test':2}
        summary=candidate_summary(frame,expected,config,11)
        self.assertIsNone(summary['difference'])
        self.assertEqual(summary['difference_cluster_ci95'],[None,None])
        self.assertEqual(verdict(summary,20,config),'INSUFFICIENT_SUPPORT')
        # Persisted model paths stay model paths. A user cannot introduce a
        # constant-true group via either a Python object or JSON serialization.
        loaded=json.loads(json.dumps(path))
        np.testing.assert_array_equal(complete_path_mask(frame,loaded,bundle['prep'].metadata()),expected)
        for spec in [{'all':[]},{'any':[]},{'not':{'all':[]}},{'model_root_leaf':True}]:
            with self.subTest(spec=spec),self.assertRaises(AdmissionError):
                predicate_mask(frame,spec)
        with self.assertRaisesRegex(AdmissionError,'complete_path_mask'):
            path_spec(path,bundle['prep'].metadata())

    def test_conditional_model_path_and_root_validation(self):
        frame=pd.DataFrame({'amount':[1.,2.,3.,4.,np.nan,8.], 'risk_label':[0,0,1,1,0,1]})
        bundle=fit_model(frame,['amount'],'tree',{'seed':11,'tree_depth':3,'min_leaf':1})
        prep=bundle['prep'].metadata()
        for path in complete_paths(bundle):
            np.testing.assert_array_equal(complete_path_mask(frame,path,prep),replay(bundle,frame,path))
        for invalid in [{'leaf_id':2,'predicates':[],'train_support':5},
                        {'leaf_id':False,'predicates':[],'train_support':5},
                        {'leaf_id':0,'predicates':[],'train_support':0},
                        {'leaf_id':0,'predicates':[],'train_support':True}]:
            with self.subTest(path=invalid),self.assertRaises(AdmissionError):
                complete_path_mask(frame,invalid,prep)

    def test_malformed_model_predicates_and_user_operator_fail_closed(self):
        prep={'input_columns':['amount'],'output_columns':['amount','amount__missing'], 'train_medians':{'amount':10.}}
        valid={'predicates':[{'feature_index':0,'transformed_feature':'amount','operator':'<=','threshold':20.}]}
        for key,value in [('feature_index',False),('operator','>='),('threshold',np.inf),('threshold',True)]:
            invalid=copy.deepcopy(valid);invalid['predicates'][0][key]=value
            with self.subTest(key=key,value=value),self.assertRaises(AdmissionError):
                path_spec(invalid,prep)
        for malformed in [{'predicates':[{}]},{'predicates':None},None]:
            with self.subTest(path=malformed),self.assertRaises(AdmissionError):path_spec(malformed,prep)
        with self.assertRaises(AdmissionError):
            predicate_mask(pd.DataFrame({'amount':[10.]}),{'field':'amount','op':[],'value':5.})

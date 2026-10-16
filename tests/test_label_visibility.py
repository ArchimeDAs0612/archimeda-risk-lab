import itertools
import unittest
import numpy as np
import pandas as pd
from risklab.label_visibility import identification_bounds,analyze_visibility


class LabelVisibilityTests(unittest.TestCase):
    def test_sharp_bounds_match_all_missing_outcome_assignments(self):
        observed=np.array([True,True,False,False]);flagged=np.array([True,False,True,False])
        bounds=identification_bounds([1,0,np.nan,np.nan],observed,flagged)
        rates=[];recalls=[]
        for unknown in itertools.product([0,1],repeat=2):
            y=np.array([1,0,*unknown]);rates.append(y.mean());recalls.append(y[flagged].sum()/y.sum())
        self.assertEqual(bounds['prevalence'],[min(rates),max(rates)])
        self.assertEqual(bounds['recall'],[min(recalls),max(recalls)])
        self.assertFalse(bounds['point_identified'])

    def test_hidden_oracle_values_cannot_change_deployable_bounds(self):
        a=identification_bounds([1,0,0,1],[True,True,False,False],[True,False,True,False])
        b=identification_bounds([1,0,1,0],[True,True,False,False],[True,False,True,False])
        self.assertEqual(a,b)

    def test_zero_positive_and_one_sided_unknown_boundaries(self):
        for flagged in [[True,True],[False,False],[True,False]]:
            bounds=identification_bounds([np.nan,np.nan],[False,False],flagged)
            recalls=[]
            for y in itertools.product([0,1],repeat=2):
                y=np.asarray(y)
                if y.sum():recalls.append(y[flagged].sum()/y.sum())
            self.assertEqual(bounds['recall'],[min(recalls),max(recalls)])
        self.assertEqual(identification_bounds([0,0],[True,True],[True,False])['recall'],[None,None])

    def test_regimes_fixed_and_missingness_not_zero_imputed(self):
        frame=pd.DataFrame(dict(risk_label=[1,0,1,0],action=['decline','approve','approve','decline'],payment_result=[0,1,1,0]))
        r=analyze_visibility(frame,[.9,.1,.8,.2],.5)
        partial=next(x for x in r['regimes'] if x['regime']=='non_declined_only')
        self.assertEqual(partial['naive_observed_metrics']['n'],2)
        self.assertEqual(partial['bounds']['prevalence'],[.25,.75])
        self.assertEqual(r,analyze_visibility(frame,[.9,.1,.8,.2],.5))

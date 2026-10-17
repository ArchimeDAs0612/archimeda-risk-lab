import unittest
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from risklab.generate import DAY
from risklab.label_sensitivity import outcome_delay_observation
from risklab.selection_experiment import fit_visible


class LabelSensitivityTests(unittest.TestCase):
    def test_outcome_dependent_visibility_breaks_independence(self):
        frame=pd.DataFrame(dict(action=['approve']*1000,decision_ts=np.zeros(1000)))
        good,pg=outcome_delay_observation(frame,np.zeros(1000),12*DAY,.25,31)
        risk,pr=outcome_delay_observation(frame,np.ones(1000),12*DAY,.25,31)
        self.assertLess(risk.observed.sum(),good.observed.sum())
        np.testing.assert_allclose(pg,10/13)
        np.testing.assert_allclose(pr,2/15)
        np.testing.assert_array_equal(good.inclusion_probability,risk.inclusion_probability)
        self.assertTrue(risk.loc[~risk.observed,'risk_label'].isna().all())

    def test_weight_normalization_matches_equivalent_penalty_scale(self):
        f=pd.DataFrame(dict(x=np.linspace(-2,2,100),risk_label=[0,1,0,1,0]*20,
                            observed=True,inclusion_probability=[.2,1.]*50))
        b=fit_visible(f,['x'],True,41,normalize_weights=True)
        x=b['scaler'].transform(b['prep'].apply(f));w=1/f.inclusion_probability.to_numpy()
        reference=LogisticRegression(C=len(w)/w.sum(),solver='liblinear',max_iter=1000,random_state=41)
        reference.fit(x,f.risk_label,sample_weight=w)
        np.testing.assert_allclose(b['model'].coef_,reference.coef_,atol=1e-12)
        np.testing.assert_allclose(b['model'].intercept_,reference.intercept_,atol=1e-12)


if __name__=='__main__':unittest.main()

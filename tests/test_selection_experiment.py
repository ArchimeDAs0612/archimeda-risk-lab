import unittest
import numpy as np
import pandas as pd
from risklab.generate import DAY
from risklab.selection_experiment import observe, maturity_probability, weighted_estimates, policy_summary


class SelectionExperimentTests(unittest.TestCase):
    def test_known_maturity_boundary_not_event_time_confusion(self):
        np.testing.assert_array_equal(maturity_probability([0, 3*DAY, 8*DAY], 10*DAY, 2, 8), [1, 5/6, 0])

    def test_ipw_hand_calculation_and_no_oracle_leak(self):
        frame = pd.DataFrame(dict(observed=[True, True, False], risk_label=[1., 0., np.nan], inclusion_probability=[.25, 1., .25]))
        r = weighted_estimates(frame, [.8, .9, .1], .5)
        self.assertEqual(r['prevalence'], .8)
        self.assertEqual(r['recall'], 1.)
        self.assertAlmostEqual(r['effective_sample_size'], 25/17)
        frame.loc[2, 'inclusion_probability'] = 0
        self.assertEqual(weighted_estimates(frame, [.8,.9,.1], .5)['status'], 'NOT_IDENTIFIED')

    def test_observed_and_maturity_masks_independent_of_hidden_outcomes(self):
        f = pd.DataFrame(dict(action=['decline']*50+['approve']*50, decision_ts=np.arange(100)*DAY/10))
        a = observe(f, np.zeros(100), 10*DAY, .25, 2, 8, 42)
        b = observe(f, np.ones(100), 10*DAY, .25, 2, 8, 42)
        np.testing.assert_array_equal(a.observed, b.observed)
        self.assertTrue(a.loc[~a.observed, 'risk_label'].isna().all())
        self.assertFalse({'payment_result', 'hidden_propensity', 'label_available_ts'} & set(a))
        with self.assertRaisesRegex(ValueError, 'exclude oracle'):
            observe(f.assign(risk_label=1), np.ones(100), 10*DAY,.25,2,8,42)

    def test_policy_cost_reversal_from_declared_cost_only(self):
        f = pd.DataFrame(dict(action=['approve','approve'], amount=[10,20]))
        y = np.array([1,0]); mask = np.array([True,True])
        base = policy_summary(f,y,np.zeros(2,bool),4,'decline')
        low = policy_summary(f,y,mask,4,'decline')
        high = policy_summary(f,y,mask,25,'decline')
        self.assertEqual(base['simulated_cost'],10)
        self.assertEqual(low['simulated_cost'],4)
        self.assertEqual(high['simulated_cost'],25)
        self.assertEqual(low['legitimate_declines'], high['legitimate_declines'])


if __name__ == '__main__': unittest.main()

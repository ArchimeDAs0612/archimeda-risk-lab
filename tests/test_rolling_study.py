import unittest
import numpy as np
import pandas as pd
from risklab.rolling_study import conditional_shift,monitor_statistics,run_monitor,ecdf_distance


class RollingMonitorTests(unittest.TestCase):
    def test_ecdf_distance_matches_independent_scipy_reference_with_ties(self):
        from scipy.stats import ks_2samp
        for a,b in [([0,0,1,3],[0,2,2,3,4]),([1,1],[1,1]),([0,0],[1,1])]:
            self.assertAlmostEqual(ecdf_distance(a,b),ks_2samp(a,b,method='exact').statistic)

    def test_pure_conditional_shift_has_identical_features_and_prior_but_bad_scores(self):
        original=pd.DataFrame(dict(amount=[10,20,30,40],prior_score=[.1,.2,.8,.9],
                                  account_age_days=[1,2,3,4],score=[.1,.2,.8,.9],risk_label=[0,0,1,1]))
        shifted=conditional_shift(original)
        self.assertEqual(shifted.risk_label.sum(),original.risk_label.sum())
        pd.testing.assert_frame_equal(shifted.drop(columns='risk_label'),original.drop(columns='risk_label'))
        stats=monitor_statistics(original,shifted,['amount','prior_score','account_age_days'])
        self.assertEqual(stats['feature_distance'],0)
        self.assertEqual(stats['label_rate_difference'],0)
        self.assertGreater(stats['brier_difference'],.5)

    def test_monitor_thresholds_use_reference_users_and_deterministic_replay(self):
        rng=np.random.default_rng(17);n=180
        pool=pd.DataFrame(dict(user_id=[f'u{i//3}' for i in range(n)],amount=rng.uniform(2,100,n),
                               prior_score=rng.random(n),account_age_days=rng.uniform(0,90,n)))
        pool['score']=pool.prior_score;pool['risk_label']=(rng.random(n)<pool.score).astype(int)
        config=dict(seed=21,null_calibration_repeats=20,evaluation_repeats=20,subjects_per_batch=10,alpha=.05,
                    features=['amount','prior_score','account_age_days'],scenarios=['null','population_mix','label_prior','conditional_relationship'])
        a=run_monitor(pool,config);b=run_monitor(pool,config)
        self.assertEqual(a,b);self.assertTrue(a['users_disjoint'])
        self.assertEqual(a['reference_users']+a['evaluation_users'],60)
        null=[r for r in a['trials'] if r['scenario']=='null']
        conditional=[r for r in a['trials'] if r['scenario']=='conditional_relationship']
        for x,y in zip(null,conditional):
            self.assertEqual(x['statistics']['feature_distance'],y['statistics']['feature_distance'])
            self.assertEqual(x['risk_rate'],y['risk_rate'])


if __name__=='__main__':unittest.main()

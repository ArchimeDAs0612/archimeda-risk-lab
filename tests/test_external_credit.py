import unittest
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix

from risklab.external_credit import (NAMES, STATUS, CreditEncoder, assign_splits,
                                     discover_rule, rule_variants, fit_credit, fixed_capacity)
from risklab.models import probabilities, replay, verify_membership, complete_paths


class ExternalCreditTests(unittest.TestCase):
    def frame(self):
        rng = np.random.default_rng(19)
        f = pd.DataFrame(rng.normal(size=(500, 23)), columns=NAMES)
        for c in STATUS:
            f[c] = rng.choice([-2, -1, 0, 1, 2, 3], len(f))
        f['ID'] = np.arange(len(f))
        f['risk_label'] = (f.PAY_0 >= 2).astype(int)
        return f

    def test_group_split_is_order_invariant_and_label_blind(self):
        f = self.frame()
        duplicate = f.iloc[[0]].copy(); duplicate.ID = 999; duplicate.risk_label = 1-duplicate.risk_label
        f = pd.concat([f, duplicate], ignore_index=True)
        a = assign_splits(f, 77).set_index('ID')
        b = assign_splits(f.sample(frac=1, random_state=3).assign(risk_label=lambda x: 1-x.risk_label), 77).set_index('ID')
        pd.testing.assert_series_equal(a.split, b.split)
        self.assertEqual(a.loc[0, 'split'], a.loc[999, 'split'])

    def test_encoder_cannot_learn_new_evaluation_category(self):
        f = self.frame(); enc = CreditEncoder().fit(f)
        before = [v.copy() for v in enc.categorical.categories_]
        changed = f.iloc[:1].copy(); changed.PAY_0 = 999
        transformed = enc.transform(changed)
        self.assertEqual(transformed[[c for c in enc.names if c.startswith('PAY_0_')]].sum(axis=1).iloc[0], 0)
        for a, b in zip(before, enc.categorical.categories_):
            np.testing.assert_array_equal(a, b)

    def test_capacity_ties_never_expand_budget_or_use_labels(self):
        y = np.array([0, 0, 1, 1]); scores = np.ones(4); ids = np.array([4, 3, 2, 1])
        result = fixed_capacity(y, scores, ids, .5)
        self.assertEqual(result['capacity'], 2)
        self.assertEqual(result['positives'], 2)
        self.assertEqual(fixed_capacity(1-y, scores, ids, .5)['positives'], 0)
        idx = [2, 0, 3, 1]
        self.assertEqual(result, fixed_capacity(y[idx], scores[idx], ids[idx], .5))

    def test_all_leaves_equal_sklearn_and_simplification_recomputes(self):
        f = self.frame(); enc = CreditEncoder().fit(f.iloc[:300]); e = enc.transform(f)
        config = dict(tree_depth=3, min_leaf=15, candidate_min_select=10, seed=91)
        cols = enc.columns(['PAY_0', 'LIMIT_BAL'])
        bundle, rule, candidates = discover_rule(e.iloc[:300], e.iloc[300:], cols, config, 91)
        self.assertTrue(verify_membership(bundle, e, complete_paths(bundle))['all_paths_equal'])
        variants = rule_variants(bundle, rule, e.iloc[:300])
        for name in ['drop_last', 'threshold_minus', 'threshold_plus']:
            self.assertNotIn('train_support', variants[name])
            self.assertNotIn('leaf_id', variants[name])
        full = replay(bundle, e, rule); simple = replay(bundle, e, variants['drop_last'])
        self.assertTrue(np.all(~full | simple))
        self.assertGreater(simple.sum(), full.sum())
        self.assertTrue(all('selection_n' in r for r in candidates))

    def test_probability_reference_and_evaluation_no_refit(self):
        f = self.frame(); enc = CreditEncoder().fit(f); e = enc.transform(f)
        bundle = fit_credit(e, enc.columns(['PAY_0', 'LIMIT_BAL']), 'lr', 11, {})
        medians = bundle['prep'].medians.copy()
        x = bundle['scaler'].transform(bundle['prep'].apply(e))
        np.testing.assert_allclose(probabilities(bundle, e), bundle['model'].predict_proba(csr_matrix(x))[:, 1], atol=1e-12)
        changed = e.copy(); changed.LIMIT_BAL = 1e8
        probabilities(bundle, changed)
        np.testing.assert_array_equal(medians, bundle['prep'].medians)


if __name__ == '__main__':
    unittest.main()

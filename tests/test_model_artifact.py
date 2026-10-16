import copy
import json
import unittest
import numpy as np
import pandas as pd
from risklab.model_artifact import export_model, predict_json
from risklab.research_models import fit_research
from risklab.models import probabilities


class ModelArtifactTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame({'a': [0., 1., 2., 3., np.nan, 5., 6., 7.],
                                   'b': [0., 1., 0., 1., 0., 1., 0., 1.],
                                   'risk_label': [0, 0, 0, 1, 0, 1, 1, 1]})
        self.config = dict(seed=7, min_leaf=2, tree_depth=3, forest_trees=5)

    def test_actual_lr_tree_forest_roundtrip_predictions(self):
        for kind in ['lr', 'tree', 'forest']:
            with self.subTest(kind=kind):
                bundle = fit_research(self.frame, ['a', 'b'], kind, self.config)
                saved = json.loads(json.dumps(export_model(bundle, .4), allow_nan=False))
                np.testing.assert_allclose(predict_json(saved, self.frame), probabilities(bundle, self.frame), atol=1e-14, rtol=0)
                self.assertNotIn('risk_label', saved['preprocessing']['input_columns'])

    def test_missing_column_infinity_and_malformed_artifact_blocked(self):
        saved = export_model(fit_research(self.frame, ['a', 'b'], 'tree', self.config), .4)
        with self.assertRaisesRegex(ValueError, 'missing inference'):
            predict_json(saved, self.frame.drop(columns='a'))
        bad = self.frame.copy(); bad.loc[0, 'a'] = np.inf
        with self.assertRaisesRegex(ValueError, 'infinite'):
            predict_json(saved, bad)
        changed = copy.deepcopy(saved); changed['trees'][0]['left'][0] = 0
        with self.assertRaisesRegex(ValueError, 'cyclic'):
            predict_json(changed, self.frame)

    def test_threshold_boundary_matches_sklearn_float32(self):
        bundle = fit_research(self.frame, ['a', 'b'], 'tree', self.config)
        saved = export_model(bundle, .4)
        threshold = bundle['model'].tree_.threshold[0]
        feature = bundle['model'].tree_.feature[0]
        if feature < 2:
            f = self.frame.copy()
            f.loc[:2, ['a', 'b'][feature]] = [threshold, np.nextafter(np.float32(threshold), np.float32(-np.inf)), np.nextafter(np.float32(threshold), np.float32(np.inf))]
            np.testing.assert_array_equal(predict_json(saved, f), probabilities(bundle, f))

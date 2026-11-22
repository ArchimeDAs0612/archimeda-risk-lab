import json
import unittest
from pathlib import Path

import numpy as np

from risklab import sequence_study as study


class SequenceStudyTests(unittest.TestCase):
    def test_future_and_late_records_do_not_affect_input(self):
        rows = [(8, 9, 2), (4, 8, 1), (7, 11, 1), (9, 10, 0), (10, 10, 3)]
        self.assertEqual(study.visible_symbols(rows, 10), (1, 2))
        self.assertEqual(study.visible_symbols(list(reversed(rows[:2])), 10), (1, 2))
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            study.visible_symbols([(4, 4, 3), (4, 5, 2)], 10)
        with self.assertRaisesRegex(ValueError, "availability"):
            study.visible_symbols([(5, 4, 3)], 10)

    def test_counts_are_invariant_and_transitions_change_on_reversal(self):
        counts, encoded = study.encode([(0, 0, 1, 3), (3, 1, 0, 0)])
        np.testing.assert_array_equal(counts[0], counts[1])
        self.assertEqual(encoded[0, 4 + 0 * 4 + 1], 1)
        self.assertEqual(encoded[1, 4 + 0 * 4 + 1], 0)
        np.testing.assert_array_equal(encoded[:, 4:].sum(1), (3, 3))

    def test_attention_has_no_future_or_padding_mass_and_gradient_matches(self):
        histories = [(1, 0, 2), (0, 1), (2,)]
        counts, _ = study.encode(histories)
        inputs = study.attention_input(histories)
        y = np.array([1, 0, 0])
        params = np.linspace(-.7, .55, 37)
        _, weights, _, _ = study.attention_scores(params, counts, inputs)
        self.assertTrue(np.all(weights[:, 0] == 0))
        self.assertTrue(np.all(weights[1, 2:] == 0))
        np.testing.assert_array_equal(weights[0, 1], (0., 1., 0., 0.))
        self.assertAlmostEqual(weights[0, 2].sum(), 1.)
        _, grad = study.attention_objective(params, counts, inputs, y)
        for i, unit in enumerate(np.eye(len(params))):
            upper = study.attention_objective(params + 1e-6 * unit, counts, inputs, y)[0]
            lower = study.attention_objective(params - 1e-6 * unit, counts, inputs, y)[0]
            self.assertAlmostEqual((upper - lower) / 2e-6, grad[i], places=7)

    def test_cohorts_disjoint_and_results_reproduce(self):
        phases = study.simulate()
        previous_last_label_time = -1
        seen = set()
        for rows in phases.values():
            self.assertLess(previous_last_label_time, min(row.decision for row in rows))
            previous_last_label_time = max(row.mature for row in rows)
            subjects = {row.subject for row in rows}
            self.assertEqual(len(rows), len(subjects))
            self.assertTrue(seen.isdisjoint(subjects))
            seen.update(subjects)
        expected = json.loads((Path(__file__).resolve().parents[1] / "artifacts/rc1/sequence-order/result.json").read_text())
        actual = study.run()
        self.assertEqual(expected["cohorts"], actual["cohorts"])
        for phase, summary in actual["evaluations"].items():
            self.assertEqual(summary["n"], expected["evaluations"][phase]["n"])
            for name, ap in summary["ap"].items():
                self.assertAlmostEqual(ap, expected["evaluations"][phase]["ap"][name], places=5)
        control = actual["evaluations"]["stable_oot_within_subject_shuffle"]
        self.assertEqual(control["max_count_score_change"], 0)


if __name__ == "__main__":
    unittest.main()

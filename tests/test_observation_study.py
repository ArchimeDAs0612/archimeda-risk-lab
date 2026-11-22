import unittest

import numpy as np
from sklearn.metrics import average_precision_score

from risklab import observation_study as study


class ObservationStudyTests(unittest.TestCase):
    def test_channel_reversal_changes_only_observation(self):
        data = study.generate(study.SEEDS[0])
        self.assertFalse(np.any(data["ticket"] & ~data["fault"]))
        self.assertFalse(np.any(data["swapped_ticket"] & ~data["fault"]))
        final = slice(sum(study.WINDOWS[:2]), None)
        channel = data["x"][final, 2]
        self.assertGreater(average_precision_score(data["ticket"][final], channel),
                           data["ticket"][final].mean())
        self.assertLess(average_precision_score(data["swapped_ticket"][final], channel),
                        data["swapped_ticket"][final].mean())

    def test_independent_holdout_recomputes_reported_fault_score(self):
        seed = study.SEEDS[0]
        data = study.generate(seed)
        n = study.WINDOWS[0]
        k = sum(study.WINDOWS[:2])
        fits = study.fit_candidates(data["x"][:n], data["ticket"][:n])
        pred = study.score_views(fits, data["x"][k:])["signal"]
        row = study.run_seed(seed)
        self.assertAlmostEqual(row["final"]["signal"]["fault"]["ap"],
                               average_precision_score(data["fault"][k:], pred), places=6)
        self.assertEqual(row["selection"]["audit"]["signal"]["rows"],
                         int(data["audit"][n:k].sum()))

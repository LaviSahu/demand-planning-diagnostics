"""test_segment.py — ADI/CV² formula edge cases, quadrant boundary
behavior, and the segmentation-recovery validation metric."""

import unittest
from dataclasses import replace

import _bootstrap  # noqa: F401
import fixtures

from demand_planning_diagnostics import segment
from demand_planning_diagnostics.models import Segment


class TestAverageInterDemandInterval(unittest.TestCase):
    def test_all_nonzero_gives_floor_of_one(self):
        records = [fixtures.week_record("S", w, 10.0) for w in range(1, 6)]
        self.assertEqual(segment.average_inter_demand_interval(records), 1.0)

    def test_mixed_zero_and_nonzero(self):
        # 6 periods, 2 nonzero (weeks 3 and 6) -> ADI = 6 / 2 = 3.0
        actuals = [0.0, 0.0, 80.0, 0.0, 0.0, 10.0]
        records = [fixtures.week_record("S", w + 1, a) for w, a in enumerate(actuals)]
        self.assertAlmostEqual(segment.average_inter_demand_interval(records), 3.0)

    def test_all_zero_is_infinite(self):
        records = [fixtures.week_record("S", w, 0.0) for w in range(1, 5)]
        self.assertEqual(segment.average_inter_demand_interval(records), float("inf"))


class TestSquaredCvOfNonzeroDemand(unittest.TestCase):
    def test_uniform_nonzero_gives_zero(self):
        records = [fixtures.week_record("S", w, 50.0) for w in range(1, 5)]
        self.assertEqual(segment.squared_cv_of_nonzero_demand(records), 0.0)

    def test_known_two_values(self):
        # nonzero = [10, 20]; mean 15, population stdev 5 -> cv2 = (5/15)**2
        records = [fixtures.week_record("S", 1, 10.0), fixtures.week_record("S", 2, 20.0)]
        self.assertAlmostEqual(segment.squared_cv_of_nonzero_demand(records), (5 / 15) ** 2)

    def test_fewer_than_two_nonzero_gives_zero(self):
        records = [fixtures.week_record("S", 1, 50.0), fixtures.week_record("S", 2, 0.0)]
        self.assertEqual(segment.squared_cv_of_nonzero_demand(records), 0.0)


class TestClassify(unittest.TestCase):
    def test_smooth_quadrant(self):
        self.assertEqual(segment.classify(1.0, 0.1), Segment.SMOOTH)

    def test_erratic_quadrant(self):
        self.assertEqual(segment.classify(1.0, 0.6), Segment.ERRATIC)

    def test_intermittent_quadrant(self):
        self.assertEqual(segment.classify(2.0, 0.1), Segment.INTERMITTENT)

    def test_lumpy_quadrant(self):
        self.assertEqual(segment.classify(2.0, 0.6), Segment.LUMPY)

    def test_adi_boundary_falls_to_high_adi_side(self):
        # ADI == cutoff is NOT < cutoff, so the boundary itself is "high ADI".
        self.assertEqual(segment.classify(segment.ADI_CUTOFF, 0.1), Segment.INTERMITTENT)

    def test_cv2_boundary_falls_to_high_cv2_side(self):
        self.assertEqual(segment.classify(1.0, segment.CV2_CUTOFF), Segment.ERRATIC)


class TestSegmentHistory(unittest.TestCase):
    def test_volume_share_and_segment_assignment(self):
        catalog, history = fixtures.small_catalog_and_history()
        assignments = segment.segment_history(catalog, history)
        by_id = {a.sku_id: a for a in assignments}

        total = 400.0 + 90.0
        self.assertAlmostEqual(by_id["SKU-SMOOTH"].volume_share, 400.0 / total, places=4)
        self.assertAlmostEqual(by_id["SKU-LUMPY"].volume_share, 90.0 / total, places=4)
        self.assertEqual(by_id["SKU-SMOOTH"].segment, Segment.SMOOTH)
        self.assertEqual(by_id["SKU-LUMPY"].segment, Segment.LUMPY)

    def test_segment_recovery_rate_full_match(self):
        catalog, history = fixtures.small_catalog_and_history()
        assignments = segment.segment_history(catalog, history)
        self.assertEqual(segment.segment_recovery_rate(catalog, assignments), 1.0)

    def test_segment_recovery_rate_partial_mismatch(self):
        catalog, history = fixtures.small_catalog_and_history()
        assignments = segment.segment_history(catalog, history)
        mutated = [
            replace(a, segment=Segment.INTERMITTENT) if a.sku_id == "SKU-LUMPY" else a
            for a in assignments
        ]
        self.assertAlmostEqual(segment.segment_recovery_rate(catalog, mutated), 0.5)


if __name__ == "__main__":
    unittest.main()

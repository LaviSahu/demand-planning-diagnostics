"""test_kpi.py — the KPI catalog: forecastable share, % SKUs hurt,
pooled bias/tracking-signal/MASE, and the full compute_kpis contract."""

import unittest

import _bootstrap  # noqa: F401
import fixtures

from demand_planning_diagnostics import accuracy, fva, kpi, segment
from demand_planning_diagnostics.models import (
    Category,
    DemandHistory,
    ForecastLayer,
    Segment,
    SegmentAssignment,
    Sku,
    SkuCatalog,
)


def _two_sku_catalog_and_history():
    r1 = fixtures.simple_sku_records("SKU-A")
    r2 = fixtures.simple_sku_records("SKU-B")
    history = DemandHistory(records=r1 + r2)
    catalog = SkuCatalog(
        company="Toy",
        skus=[
            Sku(id="SKU-A", name="A", category=Category.BEVERAGES,
                archetype=Segment.SMOOTH, revenue_per_unit=1.0),
            Sku(id="SKU-B", name="B", category=Category.SNACKS,
                archetype=Segment.SMOOTH, revenue_per_unit=1.0),
        ],
    )
    return catalog, history


class TestForecastableShare(unittest.TestCase):
    def test_sums_only_smooth_and_erratic_volume_share(self):
        catalog, history = fixtures.small_catalog_and_history()
        assignments = segment.segment_history(catalog, history)
        share = kpi.forecastable_share(assignments)
        expected = round(400.0 / 490.0 * 100.0, 2)
        self.assertAlmostEqual(share, expected, places=2)


class TestPctSkusOverridesHurt(unittest.TestCase):
    def test_known_ratio(self):
        rows = [
            fva._fva_result("sku", "A", ForecastLayer.STATISTICAL, ForecastLayer.CONSENSUS, 10.0, 15.0),
            fva._fva_result("sku", "B", ForecastLayer.STATISTICAL, ForecastLayer.CONSENSUS, 10.0, 8.0),
        ]
        self.assertAlmostEqual(kpi.pct_skus_overrides_hurt(rows, total_skus=4), 25.0)

    def test_zero_total_skus_is_zero(self):
        self.assertEqual(kpi.pct_skus_overrides_hurt([], total_skus=0), 0.0)


class TestPortfolioBiasAndTrackingSignal(unittest.TestCase):
    def test_matches_manual_pooling_across_skus(self):
        catalog, history = _two_sku_catalog_and_history()
        bias_val, ts_val = kpi.portfolio_bias_and_tracking_signal(history, catalog, ForecastLayer.NAIVE)

        manual_pairs = []
        for sku_id in catalog.sku_ids():
            manual_pairs.extend(accuracy.eval_pairs(history.for_sku(sku_id), ForecastLayer.NAIVE))
        self.assertAlmostEqual(bias_val, accuracy.bias(manual_pairs))
        self.assertAlmostEqual(ts_val, accuracy.tracking_signal(manual_pairs))


class TestVolumeWeightedMase(unittest.TestCase):
    def test_weighted_average_of_two_identical_skus(self):
        catalog, history = _two_sku_catalog_and_history()
        assignments = [
            SegmentAssignment(sku_id="SKU-A", adi=1.0, cv2=0.1, segment=Segment.SMOOTH, volume_share=0.75),
            SegmentAssignment(sku_id="SKU-B", adi=1.0, cv2=0.1, segment=Segment.SMOOTH, volume_share=0.25),
        ]
        # both SKUs have identical records -> identical per-SKU MASE (0.25, see
        # test_accuracy.TestMase) -> the weighted average must equal that MASE
        # regardless of the (unequal) weights.
        result = kpi.volume_weighted_mase(history, catalog, assignments, ForecastLayer.STATISTICAL)
        self.assertAlmostEqual(result, 0.25)

    def test_none_when_no_sku_has_a_defined_mase(self):
        records = fixtures.insufficient_burn_in_records("SKU-A")
        history = DemandHistory(records=records)
        catalog = SkuCatalog(
            company="Toy",
            skus=[Sku(id="SKU-A", name="A", category=Category.BEVERAGES,
                      archetype=Segment.SMOOTH, revenue_per_unit=1.0)],
        )
        assignments = [SegmentAssignment(sku_id="SKU-A", adi=1.0, cv2=0.1, segment=Segment.SMOOTH, volume_share=1.0)]
        result = kpi.volume_weighted_mase(history, catalog, assignments, ForecastLayer.NAIVE)
        self.assertIsNone(result)


class TestComputeKpis(unittest.TestCase):
    def test_all_expected_keys_present(self):
        catalog, history = _two_sku_catalog_and_history()
        assignments = segment.segment_history(catalog, history)
        all_fva = fva.compute_all_fva(history, catalog, assignments)
        sku_fva = [r for r in all_fva if r.level == "sku"]
        overall_fva_rows = [r for r in all_fva if r.level == "overall"]

        kpis = kpi.compute_kpis(history, catalog, assignments, sku_fva, overall_fva_rows)
        expected_keys = {
            "wmape_consensus", "fva_stat", "fva_consensus", "pct_skus_overrides_hurt",
            "forecastable_share", "bias_consensus", "tracking_signal_consensus", "mase_consensus",
        }
        self.assertEqual(set(kpis.keys()), expected_keys)
        for k in kpis.values():
            self.assertIsInstance(k.value, (int, float))


if __name__ == "__main__":
    unittest.main()

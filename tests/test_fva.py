"""test_fva.py — the FVA stairstep primitive, its zero-division guard, and
the sku/segment/overall aggregation levels."""

import unittest

import _bootstrap  # noqa: F401
import fixtures

from demand_planning_diagnostics import fva, segment
from demand_planning_diagnostics.models import (
    Category,
    DemandHistory,
    ForecastLayer,
    Segment,
    Sku,
    SkuCatalog,
)


class TestFvaResult(unittest.TestCase):
    def test_positive_when_wmape_improves(self):
        r = fva._fva_result(
            "overall", "overall", ForecastLayer.NAIVE, ForecastLayer.STATISTICAL, 50.0, 40.0
        )
        self.assertEqual(r.fva, 10.0)
        self.assertAlmostEqual(r.fva_pct, 20.0)

    def test_negative_when_wmape_worsens(self):
        r = fva._fva_result(
            "overall", "overall", ForecastLayer.STATISTICAL, ForecastLayer.CONSENSUS, 40.0, 50.0
        )
        self.assertEqual(r.fva, -10.0)
        self.assertAlmostEqual(r.fva_pct, -25.0)

    def test_pct_guarded_against_zero_division(self):
        r = fva._fva_result(
            "overall", "overall", ForecastLayer.NAIVE, ForecastLayer.STATISTICAL, 0.0, 0.0
        )
        self.assertEqual(r.fva, 0.0)
        self.assertEqual(r.fva_pct, 0.0)


class TestSkuLevelFva(unittest.TestCase):
    def test_three_stairstep_rows_per_sku(self):
        records = fixtures.simple_sku_records()
        history = DemandHistory(records=records)
        catalog = SkuCatalog(
            company="Toy",
            skus=[Sku(id="SKU-A", name="A", category=Category.BEVERAGES,
                      archetype=Segment.SMOOTH, revenue_per_unit=1.0)],
        )
        results = fva.sku_level_fva(history, catalog)
        self.assertEqual(len(results), 3)
        pairs = {(r.from_layer, r.to_layer) for r in results}
        self.assertEqual(
            pairs,
            {
                (ForecastLayer.NAIVE, ForecastLayer.STATISTICAL),
                (ForecastLayer.STATISTICAL, ForecastLayer.CONSENSUS),
                (ForecastLayer.NAIVE, ForecastLayer.CONSENSUS),
            },
        )
        self.assertTrue(all(r.level == "sku" and r.key == "SKU-A" for r in results))


class TestSegmentLevelFva(unittest.TestCase):
    def test_only_present_segments_are_included(self):
        catalog, history = fixtures.small_catalog_and_history()
        assignments = segment.segment_history(catalog, history)
        results = fva.segment_level_fva(history, catalog, assignments)
        segments_present = {r.key for r in results}
        self.assertEqual(segments_present, {"smooth", "lumpy"})
        self.assertEqual(len(results), 6)  # 2 segments present x 3 stairstep rows


class TestOverallFva(unittest.TestCase):
    def test_pools_the_whole_portfolio(self):
        r1 = fixtures.simple_sku_records(sku_id="SKU-A")
        r2 = fixtures.simple_sku_records(sku_id="SKU-B")
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
        results = fva.overall_fva(history, catalog)
        self.assertEqual(len(results), 3)
        for r in results:
            self.assertEqual(r.level, "overall")
            self.assertEqual(r.key, "overall")


class TestSkusWhereOverridesHurt(unittest.TestCase):
    def test_filters_to_negative_stat_to_consensus_and_sorts_worst_first(self):
        rows = [
            fva._fva_result("sku", "A", ForecastLayer.STATISTICAL, ForecastLayer.CONSENSUS, 10.0, 15.0),  # fva -5
            fva._fva_result("sku", "B", ForecastLayer.STATISTICAL, ForecastLayer.CONSENSUS, 10.0, 8.0),   # fva +2, excluded
            fva._fva_result("sku", "C", ForecastLayer.STATISTICAL, ForecastLayer.CONSENSUS, 10.0, 30.0),  # fva -20
            fva._fva_result("sku", "D", ForecastLayer.NAIVE, ForecastLayer.STATISTICAL, 10.0, 20.0),      # wrong stairstep
        ]
        worst = fva.skus_where_overrides_hurt(rows)
        self.assertEqual([r.key for r in worst], ["C", "A"])


if __name__ == "__main__":
    unittest.main()

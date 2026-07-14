"""test_accuracy.py — MAPE/WMAPE/bias/tracking-signal/MASE, each checked
against a hand-computed value (see fixtures.py docstrings for the
arithmetic), plus their documented undefined-input edge cases."""

import unittest

import _bootstrap  # noqa: F401
import fixtures

from demand_planning_diagnostics import accuracy
from demand_planning_diagnostics.models import DemandHistory, ForecastLayer


class TestEvalPairs(unittest.TestCase):
    def test_filters_out_burn_in_weeks(self):
        records = fixtures.simple_sku_records()
        pairs = accuracy.eval_pairs(records, ForecastLayer.NAIVE)
        self.assertEqual(len(pairs), 3)

    def test_skips_none_forecast_inside_eval_window(self):
        from demand_planning_diagnostics.datagen import EVAL_START_WEEK

        records = [
            fixtures.week_record(
                "S", EVAL_START_WEEK, 10.0, naive=None, stat=9.0, consensus=9.0
            ),
        ]
        self.assertEqual(accuracy.eval_pairs(records, ForecastLayer.NAIVE), [])
        self.assertEqual(accuracy.eval_pairs(records, ForecastLayer.STATISTICAL), [(10.0, 9.0)])


class TestMape(unittest.TestCase):
    def test_skips_zero_actual_weeks(self):
        records = fixtures.zero_actual_eval_records()
        pairs = accuracy.eval_pairs(records, ForecastLayer.NAIVE)
        # actual=0 week is dropped; remaining pair is a perfect (10, 10) -> mape 0
        self.assertAlmostEqual(accuracy.mape(pairs), 0.0)

    def test_none_when_every_week_has_zero_actual(self):
        records = fixtures.all_zero_actual_eval_records()
        pairs = accuracy.eval_pairs(records, ForecastLayer.NAIVE)
        self.assertIsNone(accuracy.mape(pairs))


class TestWmape(unittest.TestCase):
    def test_known_value(self):
        records = fixtures.simple_sku_records()
        pairs = accuracy.eval_pairs(records, ForecastLayer.NAIVE)
        # actual=[20,24,16] naive=[18,26,20] -> abs err [2,2,4] sum 8; sum actual 60
        self.assertAlmostEqual(accuracy.wmape(pairs), 100 * 8 / 60)

    def test_zero_total_actual_returns_zero(self):
        records = fixtures.all_zero_actual_eval_records()
        pairs = accuracy.eval_pairs(records, ForecastLayer.NAIVE)
        self.assertEqual(accuracy.wmape(pairs), 0.0)


class TestBias(unittest.TestCase):
    def test_known_value(self):
        records = fixtures.simple_sku_records()
        pairs = accuracy.eval_pairs(records, ForecastLayer.NAIVE)
        # f - a = [-2, 2, 4] -> mean 4/3
        self.assertAlmostEqual(accuracy.bias(pairs), 4 / 3)

    def test_empty_pairs_is_zero(self):
        self.assertEqual(accuracy.bias([]), 0.0)


class TestTrackingSignal(unittest.TestCase):
    def test_known_value(self):
        records = fixtures.simple_sku_records()
        pairs = accuracy.eval_pairs(records, ForecastLayer.NAIVE)
        # errors = [-2, 2, 4], sum 4; mad = mean(2,2,4) = 8/3 -> ts = 4 / (8/3) = 1.5
        self.assertAlmostEqual(accuracy.tracking_signal(pairs), 1.5)

    def test_none_when_forecast_is_perfect(self):
        records = fixtures.perfect_forecast_records()
        pairs = accuracy.eval_pairs(records, ForecastLayer.NAIVE)
        self.assertIsNone(accuracy.tracking_signal(pairs))


class TestMase(unittest.TestCase):
    def test_known_value_statistical_layer(self):
        records = fixtures.simple_sku_records()
        # burn-in diffs = [|14-10|] = [4] -> scale 4
        # stat pairs: actual [20,24,16] stat [19,23,17] -> abs err [1,1,1] -> mae 1
        self.assertAlmostEqual(accuracy.mase(records, ForecastLayer.STATISTICAL), 0.25)

    def test_known_value_naive_layer(self):
        records = fixtures.simple_sku_records()
        # naive abs err [2,2,4] -> mae 8/3; scale 4 -> mase = (8/3)/4 = 2/3
        self.assertAlmostEqual(accuracy.mase(records, ForecastLayer.NAIVE), (8 / 3) / 4)

    def test_none_with_insufficient_burn_in(self):
        records = fixtures.insufficient_burn_in_records()
        self.assertIsNone(accuracy.mase(records, ForecastLayer.NAIVE))


class TestComputeSkuAccuracy(unittest.TestCase):
    def test_full_scorecard_shape(self):
        records = fixtures.simple_sku_records()
        result = accuracy.compute_sku_accuracy(records, ForecastLayer.CONSENSUS)
        self.assertEqual(result.sku_id, "SKU-A")
        self.assertEqual(result.layer, ForecastLayer.CONSENSUS)
        self.assertIsNotNone(result.mape)
        self.assertIsNotNone(result.mase)

    def test_empty_records_falls_back_to_unknown_sku_id(self):
        result = accuracy.compute_sku_accuracy([], ForecastLayer.NAIVE)
        self.assertEqual(result.sku_id, "unknown")
        self.assertEqual(result.wmape, 0.0)


class TestAggregateWmape(unittest.TestCase):
    def test_pools_across_multiple_skus(self):
        r1 = fixtures.simple_sku_records(sku_id="SKU-A")
        r2 = fixtures.simple_sku_records(sku_id="SKU-B")
        history = DemandHistory(records=r1 + r2)
        pooled_wmape = accuracy.aggregate_wmape(history, ["SKU-A", "SKU-B"], ForecastLayer.NAIVE)
        single_wmape = accuracy.wmape(accuracy.eval_pairs(r1, ForecastLayer.NAIVE))
        # two identical SKUs pooled together give the same ratio as a single one
        self.assertAlmostEqual(pooled_wmape, single_wmape)


if __name__ == "__main__":
    unittest.main()

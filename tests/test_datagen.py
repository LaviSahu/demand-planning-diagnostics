"""test_datagen.py — the synthetic Northwind Foods generator: seeded
determinism, dataset shape, the burn-in/eval-window contract, the
write/load JSON roundtrip, and (as a full integration check) that the
blind SBC classifier recovers the true generating archetype for the
large majority of the default seeded dataset."""

import tempfile
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401

from demand_planning_diagnostics import datagen, segment


class TestGenerateDataset(unittest.TestCase):
    def test_seeded_determinism(self):
        catalog1, history1 = datagen.generate_dataset(seed=123)
        catalog2, history2 = datagen.generate_dataset(seed=123)
        self.assertEqual([s.id for s in catalog1.skus], [s.id for s in catalog2.skus])
        actuals1 = [r.actual for r in history1.records]
        actuals2 = [r.actual for r in history2.records]
        self.assertEqual(actuals1, actuals2)

    def test_different_seeds_produce_different_actuals(self):
        _, history1 = datagen.generate_dataset(seed=1)
        _, history2 = datagen.generate_dataset(seed=2)
        actuals1 = [r.actual for r in history1.records]
        actuals2 = [r.actual for r in history2.records]
        self.assertNotEqual(actuals1, actuals2)

    def test_dataset_shape(self):
        catalog, history = datagen.generate_dataset()
        self.assertEqual(len(catalog.skus), datagen.SKUS_PER_ARCHETYPE * 4)
        for sku_id in catalog.sku_ids():
            self.assertEqual(len(history.for_sku(sku_id)), datagen.N_WEEKS)

    def test_company_name_is_northwind_foods(self):
        catalog, _ = datagen.generate_dataset()
        self.assertEqual(catalog.company, "Northwind Foods")
        self.assertNotIn("Meridian", catalog.company)

    def test_burn_in_weeks_have_no_forecasts(self):
        _, history = datagen.generate_dataset()
        sku_id = history.sku_ids()[0]
        for r in history.for_sku(sku_id):
            if r.week < datagen.EVAL_START_WEEK:
                self.assertIsNone(r.naive_fcst)
                self.assertIsNone(r.stat_fcst)
                self.assertIsNone(r.consensus_fcst)

    def test_eval_weeks_have_all_three_forecasts(self):
        _, history = datagen.generate_dataset()
        sku_id = history.sku_ids()[0]
        for r in history.for_sku(sku_id):
            if r.week >= datagen.EVAL_START_WEEK:
                self.assertIsNotNone(r.naive_fcst)
                self.assertIsNotNone(r.stat_fcst)
                self.assertIsNotNone(r.consensus_fcst)


class TestWriteLoadRoundtrip(unittest.TestCase):
    def test_roundtrip_preserves_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            skus_path, history_path = datagen.write_dataset(Path(tmp), seed=7)
            self.assertTrue(skus_path.exists())
            self.assertTrue(history_path.exists())

            catalog, history = datagen.load_dataset(Path(tmp))
            gen_catalog, gen_history = datagen.generate_dataset(seed=7)
            self.assertEqual([s.id for s in catalog.skus], [s.id for s in gen_catalog.skus])
            self.assertEqual(
                [r.actual for r in history.records], [r.actual for r in gen_history.records]
            )


class TestSegmentationRecoveryIntegration(unittest.TestCase):
    def test_default_seed_recovers_large_majority_of_archetypes(self):
        catalog, history = datagen.generate_dataset(seed=datagen.DEFAULT_SEED)
        assignments = segment.segment_history(catalog, history)
        recovery = segment.segment_recovery_rate(catalog, assignments)
        self.assertGreaterEqual(recovery, 0.90)


if __name__ == "__main__":
    unittest.main()

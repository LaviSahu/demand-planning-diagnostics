"""test_integration.py — the full datagen -> segment -> accuracy -> fva ->
kpi pipeline run end to end against the real seeded dataset.

This is the test that actually validates the repo's headline claim: the
consensus override genuinely helps some segments and genuinely hurts
others, as an *emergent* property of the seeded random draws and the
constant tables in datagen.py — not an assertion baked into the engine
itself. If a future edit to datagen.py's noise/chase constants collapses
that split, this test (not just a passing `make demo`) is what catches
it.
"""

import unittest

import _bootstrap  # noqa: F401

from demand_planning_diagnostics import accuracy, datagen, fva, segment
from demand_planning_diagnostics.models import ForecastLayer


class TestFullPipelineIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog, cls.history = datagen.generate_dataset(seed=datagen.DEFAULT_SEED)
        cls.assignments = segment.segment_history(cls.catalog, cls.history)
        cls.all_fva = fva.compute_all_fva(cls.history, cls.catalog, cls.assignments)
        cls.segment_fva = [r for r in cls.all_fva if r.level == "segment"]

    def _segment_consensus_fva(self, segment_name: str) -> float:
        row = next(
            r for r in self.segment_fva
            if r.key == segment_name
            and r.from_layer == ForecastLayer.STATISTICAL
            and r.to_layer == ForecastLayer.CONSENSUS
        )
        return row.fva

    def test_at_least_one_segment_has_negative_override_fva(self):
        negatives = [
            r for r in self.segment_fva
            if r.from_layer == ForecastLayer.STATISTICAL
            and r.to_layer == ForecastLayer.CONSENSUS
            and r.fva < 0
        ]
        self.assertGreaterEqual(len(negatives), 1)

    def test_at_least_one_segment_has_positive_override_fva(self):
        positives = [
            r for r in self.segment_fva
            if r.from_layer == ForecastLayer.STATISTICAL
            and r.to_layer == ForecastLayer.CONSENSUS
            and r.fva > 0
        ]
        self.assertGreaterEqual(len(positives), 1)

    def test_smooth_segment_override_is_positive(self):
        self.assertGreater(self._segment_consensus_fva("smooth"), 0.0)

    def test_lumpy_segment_override_is_negative(self):
        self.assertLess(self._segment_consensus_fva("lumpy"), 0.0)

    def test_some_but_not_all_skus_are_hurt_by_the_override(self):
        sku_fva = [r for r in self.all_fva if r.level == "sku"]
        worst = fva.skus_where_overrides_hurt(sku_fva)
        self.assertGreater(len(worst), 0)
        self.assertLess(len(worst), len(self.catalog.skus))

    def test_wmape_consensus_is_a_finite_positive_percentage(self):
        pooled = []
        for sku_id in self.catalog.sku_ids():
            pooled.extend(accuracy.eval_pairs(self.history.for_sku(sku_id), ForecastLayer.CONSENSUS))
        w = accuracy.wmape(pooled)
        self.assertGreater(w, 0.0)
        self.assertLess(w, 500.0)

    def test_segmentation_recovers_true_archetype_for_large_majority(self):
        recovery = segment.segment_recovery_rate(self.catalog, self.assignments)
        self.assertGreaterEqual(recovery, 0.90)


if __name__ == "__main__":
    unittest.main()

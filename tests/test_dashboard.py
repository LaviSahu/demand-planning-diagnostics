"""test_dashboard.py — build_context's contract with the renderer, and
the rendered HTML's self-containment (no external CDN/http references,
the embedded DATA blob parses as valid JSON)."""

import json
import re
import tempfile
import unittest
from pathlib import Path

import _bootstrap  # noqa: F401

from demand_planning_diagnostics import dashboard, datagen, fva, kpi, segment


def _build_real_context():
    catalog, history = datagen.generate_dataset(seed=datagen.DEFAULT_SEED)
    assignments = segment.segment_history(catalog, history)
    recovery = segment.segment_recovery_rate(catalog, assignments)
    all_fva = fva.compute_all_fva(history, catalog, assignments)
    sku_fva = [r for r in all_fva if r.level == "sku"]
    overall_fva_rows = [r for r in all_fva if r.level == "overall"]
    worst = fva.skus_where_overrides_hurt(sku_fva)
    kpis = kpi.compute_kpis(history, catalog, assignments, sku_fva, overall_fva_rows)
    return dashboard.build_context(
        catalog, history, assignments, recovery, all_fva, worst, kpis, "2026-01-01T00:00:00+00:00"
    )


class TestBuildContext(unittest.TestCase):
    def test_context_has_expected_top_level_keys(self):
        context = _build_real_context()
        for key in [
            "generated_at", "company", "kpis", "segmentation", "segment_recovery_rate",
            "overall_fva", "segment_summary", "worst_overrides", "n_skus", "n_weeks",
        ]:
            self.assertIn(key, context)

    def test_segmentation_has_one_point_per_sku(self):
        context = _build_real_context()
        self.assertEqual(len(context["segmentation"]), context["n_skus"])

    def test_segment_summary_covers_all_present_segments(self):
        context = _build_real_context()
        segments = {row["segment"] for row in context["segment_summary"]}
        self.assertEqual(segments, {"smooth", "erratic", "intermittent", "lumpy"})

    def test_n_weeks_matches_dataset(self):
        context = _build_real_context()
        self.assertEqual(context["n_weeks"], datagen.N_WEEKS)


class TestRenderDashboard(unittest.TestCase):
    def test_output_is_self_contained_no_external_refs(self):
        context = _build_real_context()
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "dashboard.html"
            dashboard.render_dashboard(context, out_path)
            html = out_path.read_text(encoding="utf-8")
        for banned in ["http://", "https://", "cdn.", "<script src=", "<link "]:
            self.assertNotIn(banned, html)

    def test_embedded_data_parses_as_json_and_matches_context(self):
        context = _build_real_context()
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / "dashboard.html"
            dashboard.render_dashboard(context, out_path)
            html = out_path.read_text(encoding="utf-8")
        match = re.search(r"const DATA = (.*?);\n", html, re.S)
        self.assertIsNotNone(match)
        parsed = json.loads(match.group(1))
        self.assertEqual(parsed["n_skus"], context["n_skus"])
        self.assertEqual(parsed["company"], context["company"])


if __name__ == "__main__":
    unittest.main()

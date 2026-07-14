"""
kpi.py — the demand-planning diagnostic KPI catalog.

Every number here is *computed* from real engine outputs (the SKU
catalog, the segmentation, and the FVA results) — nothing is hardcoded.
This is the layer the CLI's `demo` command and the dashboard both read
from, so the console summary and the HTML tiles are guaranteed to agree.

Catalog (see docs/03-kpi-reference.md for the formula behind each):

- **WMAPE (consensus)** — the headline accuracy number: how far off the
  forecast that actually ships to the supply plan is, volume-weighted,
  across the whole portfolio.
- **FVA: statistical vs. naive** — did building a real model beat a
  random-walk guess? (Gilliland FVA framework — see `fva.py`.)
- **FVA: consensus vs. statistical** — the money finding: did the human
  override step help or hurt, net, across the whole portfolio?
- **% SKUs where overrides hurt** — share of SKUs with a negative
  consensus-vs-statistical FVA — how widespread the problem is, not just
  its net portfolio-level sign (a portfolio can show positive net FVA
  while still hurting a large minority of SKUs).
- **Forecastable share** — the % of portfolio volume sitting in
  Smooth/Erratic (SBC quadrants standard methods can address) versus
  Intermittent/Lumpy (better managed by inventory policy — see
  `segment.py`).
- **Bias / tracking signal** — portfolio-level systematic over- or
  under-forecast direction on the consensus number.
- **MASE (consensus)** — is the number that ships even beating the
  in-sample naive benchmark (Hyndman-Koehler; <1 is good)?
"""

from __future__ import annotations

import statistics

from . import accuracy
from .models import ForecastLayer, Kpi, Segment

_FORECASTABLE_SEGMENTS = {Segment.SMOOTH, Segment.ERRATIC}
_POLICY_DRIVEN_SEGMENTS = {Segment.INTERMITTENT, Segment.LUMPY}


def forecastable_share(assignments: list) -> float:
    """% of total portfolio volume sitting in Smooth/Erratic SKUs (the
    segments standard forecasting methods can address)."""
    forecastable = sum(a.volume_share for a in assignments if a.segment in _FORECASTABLE_SEGMENTS)
    return round(forecastable * 100.0, 2)


def pct_skus_overrides_hurt(sku_fva_results: list, total_skus: int) -> float:
    """Share of SKUs with negative consensus-vs-statistical FVA."""
    from .fva import skus_where_overrides_hurt

    if total_skus == 0:
        return 0.0
    hurt = skus_where_overrides_hurt(sku_fva_results)
    return round(len(hurt) / total_skus * 100.0, 2)


def portfolio_bias_and_tracking_signal(history, catalog, layer: ForecastLayer) -> tuple[float, float | None]:
    """Portfolio-level bias and tracking signal for one layer, pooling
    every SKU's eval-window (actual, forecast) pairs before scoring —
    consistent with how `accuracy.aggregate_wmape` pools for WMAPE."""
    pooled: list[tuple[float, float]] = []
    for sku_id in catalog.sku_ids():
        pooled.extend(accuracy.eval_pairs(history.for_sku(sku_id), layer))
    return accuracy.bias(pooled), accuracy.tracking_signal(pooled)


def volume_weighted_mase(history, catalog, assignments, layer: ForecastLayer) -> float | None:
    """Volume-weighted average of per-SKU MASE for one layer, weights
    renormalized over SKUs with a defined (non-`None`) MASE."""
    share_by_sku = {a.sku_id: a.volume_share for a in assignments}
    weighted_sum = 0.0
    weight_total = 0.0
    for sku_id in catalog.sku_ids():
        records = history.for_sku(sku_id)
        m = accuracy.mase(records, layer)
        if m is None:
            continue
        w = share_by_sku.get(sku_id, 0.0)
        weighted_sum += w * m
        weight_total += w
    if weight_total == 0:
        return None
    return weighted_sum / weight_total


def compute_kpis(history, catalog, assignments, sku_fva_results: list, overall_fva_results: list) -> dict[str, Kpi]:
    """Assemble the full KPI catalog used by the CLI and dashboard build_context."""
    overall_wmape = {
        r.to_layer: r.wmape_to for r in overall_fva_results if r.level == "overall"
    }
    # Every stairstep result also carries the "from" layer's wmape; grab
    # naive's wmape off any overall result (they all start from the same
    # naive baseline where relevant).
    naive_wmape = next((r.wmape_from for r in overall_fva_results if r.from_layer == ForecastLayer.NAIVE), 0.0)
    overall_wmape[ForecastLayer.NAIVE] = naive_wmape

    fva_stat = next(
        r for r in overall_fva_results
        if r.level == "overall" and r.from_layer == ForecastLayer.NAIVE and r.to_layer == ForecastLayer.STATISTICAL
    )
    fva_consensus = next(
        r for r in overall_fva_results
        if r.level == "overall" and r.from_layer == ForecastLayer.STATISTICAL and r.to_layer == ForecastLayer.CONSENSUS
    )

    bias_val, ts_val = portfolio_bias_and_tracking_signal(history, catalog, ForecastLayer.CONSENSUS)
    mase_val = volume_weighted_mase(history, catalog, assignments, ForecastLayer.CONSENSUS)

    total_skus = len(catalog.skus)
    pct_hurt = pct_skus_overrides_hurt(sku_fva_results, total_skus)
    forecastable = forecastable_share(assignments)

    kpis: dict[str, Kpi] = {
        "wmape_consensus": Kpi(
            "wmape_consensus", "WMAPE (Consensus)", round(overall_wmape.get(ForecastLayer.CONSENSUS, 0.0), 2), "%",
            context="volume-weighted, the number that ships",
        ),
        "fva_stat": Kpi(
            "fva_stat", "FVA: Statistical vs Naive", fva_stat.fva, "pp",
            context=f"WMAPE {fva_stat.wmape_from:.1f}% -> {fva_stat.wmape_to:.1f}%",
        ),
        "fva_consensus": Kpi(
            "fva_consensus", "FVA: Consensus vs Statistical", fva_consensus.fva, "pp",
            context=f"WMAPE {fva_consensus.wmape_from:.1f}% -> {fva_consensus.wmape_to:.1f}%",
        ),
        "pct_skus_overrides_hurt": Kpi(
            "pct_skus_overrides_hurt", "% SKUs Overrides Hurt", pct_hurt, "%",
            context=f"{round(pct_hurt / 100.0 * total_skus)} of {total_skus} SKUs",
        ),
        "forecastable_share": Kpi(
            "forecastable_share", "Forecastable Volume Share", forecastable, "%",
            context="Smooth + Erratic share of total volume",
        ),
        "bias_consensus": Kpi(
            "bias_consensus", "Bias (Consensus)", round(bias_val, 2), "units/wk",
            context="mean signed error, forecast - actual",
        ),
        "tracking_signal_consensus": Kpi(
            "tracking_signal_consensus", "Tracking Signal (Consensus)",
            round(ts_val, 2) if ts_val is not None else 0.0, "score",
            context="rule of thumb: |TS| > 4 is out of control",
        ),
        "mase_consensus": Kpi(
            "mase_consensus", "MASE (Consensus)", round(mase_val, 3) if mase_val is not None else 0.0, "ratio",
            context="< 1.0 beats the in-sample naive benchmark",
        ),
    }
    return kpis

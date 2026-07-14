"""
fva.py — Forecast Value Added: does each step of the forecasting process
actually make the number better?

**Forecast Value Added (FVA)** — Gilliland, M. (2010), *The Business
Forecasting Deal: Exposing Myths, Eliminating Bad Practices, Providing
Practical Solutions*, John Wiley & Sons, ISBN 978-0470574430; and the SAS
FVA framework. The idea, stated plainly: every step in a forecasting
process (a statistical model, a demand-planner review, a consensus
meeting) costs analyst time, and the only way to know whether that time
is well spent is to measure whether the number that comes out is more
accurate than the number that went in. **FVA is the change in an
accuracy metric — here, WMAPE — attributable to one process step.** A
positive FVA means that step earned its keep; a **negative FVA means the
step made the forecast worse**, and the honest response to a negative
FVA is not "try harder at the same step" but "stop doing it."

This module runs the FVA stairstep this repo's naive -> statistical ->
consensus forecasting stack implies, in both directions that matter:

1. **Statistical vs. naive** (`fva_stat`) — did building a real model
   beat a random-walk guess? Usually positive, but not automatically so:
   on `promo_eligible` SKUs, the seasonal-naive baseline literally repeats
   last year's actual and so coincidentally reproduces last year's promo
   bump, while `stat_fcst` is deliberately built with no knowledge of the
   promo calendar (see `datagen.py`) and structurally cannot. This repo's
   smooth segment is a real example: naive beats stat overall once the
   promo-carrying half of the segment is included, even though stat beats
   naive handily on the non-promo half — a genuine, not scripted, finding
   about when "just build a model" undersells the value of an explicit
   promotional calendar. See docs/05-methodology-and-citations.md.
2. **Consensus vs. statistical** (`fva_consensus`) — did the human
   layer (the analyst override that turns a system forecast into the
   number that actually ships) improve on the model, or degrade it? This
   is the number every demand-planning organization should be measuring
   monthly and almost none do. It is computed identically to (1); nothing
   in this module treats "human" differently from "model" — a process
   step is a process step, and it is graded the same way.

Every FVA number here is computed at three levels of aggregation
(`"sku"`, `"segment"`, `"overall"`), all built from the same
`accuracy.aggregate_wmape` machinery — a segment's FVA is not a separate
calculation, it is the same pooled-WMAPE stairstep run over that
segment's SKU set.
"""

from __future__ import annotations

from .models import ForecastLayer, FvaResult, Segment


def _fva_result(level: str, key: str, from_layer: ForecastLayer, to_layer: ForecastLayer,
                 wmape_from: float, wmape_to: float) -> FvaResult:
    delta = wmape_from - wmape_to
    fva_pct = (delta / wmape_from * 100.0) if wmape_from > 0 else 0.0
    return FvaResult(
        level=level,
        key=key,
        from_layer=from_layer,
        to_layer=to_layer,
        wmape_from=round(wmape_from, 4),
        wmape_to=round(wmape_to, 4),
        fva=round(delta, 4),
        fva_pct=round(fva_pct, 2),
    )


_STAIRSTEP: list[tuple[ForecastLayer, ForecastLayer]] = [
    (ForecastLayer.NAIVE, ForecastLayer.STATISTICAL),
    (ForecastLayer.STATISTICAL, ForecastLayer.CONSENSUS),
    (ForecastLayer.NAIVE, ForecastLayer.CONSENSUS),
]


def sku_level_fva(history, catalog) -> list[FvaResult]:
    """FVA at each stairstep for every individual SKU."""
    from . import accuracy

    results: list[FvaResult] = []
    for sku_id in catalog.sku_ids():
        records = history.for_sku(sku_id)
        wmape_by_layer = {
            layer: accuracy.wmape(accuracy.eval_pairs(records, layer)) for layer in ForecastLayer
        }
        for from_layer, to_layer in _STAIRSTEP:
            results.append(
                _fva_result("sku", sku_id, from_layer, to_layer, wmape_by_layer[from_layer], wmape_by_layer[to_layer])
            )
    return results


def segment_level_fva(history, catalog, assignments) -> list[FvaResult]:
    """FVA at each stairstep, pooled across every SKU in a segment."""
    from . import accuracy

    by_segment: dict[Segment, list[str]] = {s: [] for s in Segment}
    for a in assignments:
        by_segment[a.segment].append(a.sku_id)

    results: list[FvaResult] = []
    for segment, sku_ids in by_segment.items():
        if not sku_ids:
            continue
        wmape_by_layer = {layer: accuracy.aggregate_wmape(history, sku_ids, layer) for layer in ForecastLayer}
        for from_layer, to_layer in _STAIRSTEP:
            results.append(
                _fva_result(
                    "segment", segment.value, from_layer, to_layer,
                    wmape_by_layer[from_layer], wmape_by_layer[to_layer],
                )
            )
    return results


def overall_fva(history, catalog) -> list[FvaResult]:
    """FVA at each stairstep, pooled across the entire portfolio."""
    from . import accuracy

    sku_ids = catalog.sku_ids()
    wmape_by_layer = {layer: accuracy.aggregate_wmape(history, sku_ids, layer) for layer in ForecastLayer}
    return [
        _fva_result("overall", "overall", from_layer, to_layer, wmape_by_layer[from_layer], wmape_by_layer[to_layer])
        for from_layer, to_layer in _STAIRSTEP
    ]


def compute_all_fva(history, catalog, assignments) -> list[FvaResult]:
    """The full FVA catalog: sku + segment + overall levels."""
    return sku_level_fva(history, catalog) + segment_level_fva(history, catalog, assignments) + overall_fva(
        history, catalog
    )


def skus_where_overrides_hurt(sku_fva_results: list[FvaResult]) -> list[FvaResult]:
    """SKU-level consensus-vs-statistical results with negative FVA —
    the "money finding": the specific SKUs where the human override step
    made the forecast worse, sorted worst (most negative) first."""
    hurt = [
        r for r in sku_fva_results
        if r.level == "sku" and r.from_layer == ForecastLayer.STATISTICAL and r.to_layer == ForecastLayer.CONSENSUS
        and r.fva < 0
    ]
    return sorted(hurt, key=lambda r: r.fva)

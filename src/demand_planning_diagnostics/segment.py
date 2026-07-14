"""
segment.py — demand-pattern classification by ADI and CV².

Before you can honestly grade a forecast, you have to know what kind of
demand you were trying to forecast. A statistical model that nails a
smooth, seasonal SKU and a random-walk benchmark that "wins" on a
sparse, spiky one are not comparable successes — one of those SKUs was
forecastable and the other structurally was not. This module runs the
standard diagnostic that tells the two apart: **Syntetos, Boylan &
Croston (2005)**, "On the categorization of demand patterns," *Journal of
the Operational Research Society* 56(5):495-503, DOI
10.1057/palgrave.jors.2601841.

Every SKU's full demand history is reduced to two numbers:

- **ADI** (Average inter-Demand Interval): the mean number of periods
  between nonzero-demand periods — `n_periods / n_nonzero_periods`. Low
  ADI means demand shows up almost every period; high ADI means long
  stretches of zero.
- **CV²** (squared coefficient of variation of the *nonzero* demand
  values): `(std_nonzero / mean_nonzero) ** 2`. Low CV² means the sizes,
  when demand occurs, are consistent; high CV² means they swing wildly.

Those two numbers, cut at the paper's canonical thresholds (ADI = 1.32,
CV² = 0.49), assign each SKU to one of four quadrants — `Segment.SMOOTH`,
`Segment.ERRATIC`, `Segment.INTERMITTENT`, `Segment.LUMPY` — and that
quadrant is a genuine, falsifiable prediction about what kind of
forecasting effort is worth spending on that SKU (smooth/erratic are
forecast-drivable; intermittent/lumpy are better managed by inventory
policy than by chasing a number that structurally cannot be predicted
week to week). `tests/test_segment.py` checks this classifier recovers
the archetype `datagen.py` built each SKU from for the large majority of
the portfolio — the segmentation is doing real, verifiable work, not
relabeling a hardcoded field.
"""

from __future__ import annotations

import statistics

from .models import DemandHistory, Segment, SkuCatalog, WeekRecord, jsonable

# Canonical Syntetos-Boylan-Croston cutoffs (2005), dataset-agnostic.
ADI_CUTOFF = 1.32
CV2_CUTOFF = 0.49


def average_inter_demand_interval(records: list[WeekRecord]) -> float:
    """ADI = total periods / number of periods with nonzero demand.
    A SKU with demand every single period has ADI == 1.0 (the floor)."""
    n_periods = len(records)
    n_nonzero = sum(1 for r in records if r.actual > 0)
    if n_nonzero == 0:
        return float("inf")
    return n_periods / n_nonzero


def squared_cv_of_nonzero_demand(records: list[WeekRecord]) -> float:
    """CV² of the nonzero demand values only. Returns 0.0 if there are
    fewer than two nonzero observations (variance undefined) — a
    conservative floor that classifies such a SKU as low-variability
    rather than raising, since a near-empty tail is closer to "smooth
    sizes, just rare" than "wildly variable"."""
    nonzero = [r.actual for r in records if r.actual > 0]
    if len(nonzero) < 2:
        return 0.0
    mean = statistics.fmean(nonzero)
    if mean == 0:
        return 0.0
    std = statistics.pstdev(nonzero)
    return (std / mean) ** 2


def classify(adi: float, cv2: float) -> Segment:
    """Assign the SBC quadrant from ADI/CV² at the canonical cutoffs."""
    if adi < ADI_CUTOFF and cv2 < CV2_CUTOFF:
        return Segment.SMOOTH
    if adi < ADI_CUTOFF and cv2 >= CV2_CUTOFF:
        return Segment.ERRATIC
    if adi >= ADI_CUTOFF and cv2 < CV2_CUTOFF:
        return Segment.INTERMITTENT
    return Segment.LUMPY


def segment_history(catalog: SkuCatalog, history: DemandHistory) -> list:
    """Compute a `SegmentAssignment` for every SKU in the catalog from its
    full actual-demand history (all 104 weeks — segmentation characterizes
    the demand pattern itself, independent of the forecast evaluation
    window used by `accuracy.py`/`fva.py`)."""
    from .models import SegmentAssignment  # local import avoids a cycle at module load

    total_volume = sum(r.actual for r in history.records)
    assignments = []
    for sku_id in catalog.sku_ids():
        records = history.for_sku(sku_id)
        adi = average_inter_demand_interval(records)
        cv2 = squared_cv_of_nonzero_demand(records)
        segment = classify(adi, cv2)
        sku_volume = sum(r.actual for r in records)
        volume_share = sku_volume / total_volume if total_volume > 0 else 0.0
        assignments.append(
            SegmentAssignment(
                sku_id=sku_id,
                adi=round(adi, 4),
                cv2=round(cv2, 4),
                segment=segment,
                volume_share=round(volume_share, 6),
            )
        )
    return assignments


def segment_recovery_rate(catalog: SkuCatalog, assignments: list) -> float:
    """Fraction of SKUs whose computed `segment` matches the *true*
    generation archetype (`Sku.archetype`) — a validation metric, only
    meaningful because this dataset is synthetic and the true pattern is
    known. Not a metric `kpi.py` would have access to on real data."""
    by_id = {a.sku_id: a for a in assignments}
    matches = sum(1 for s in catalog.skus if by_id[s.id].segment == s.archetype)
    return matches / len(catalog.skus) if catalog.skus else 0.0


def write_segments(assignments: list, out_path) -> None:
    import json
    from pathlib import Path

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps([jsonable(a) for a in assignments], indent=2), encoding="utf-8")

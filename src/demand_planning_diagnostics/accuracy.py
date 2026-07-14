"""
accuracy.py — forecast-accuracy diagnostics: MAPE, WMAPE, bias, tracking
signal, and MASE.

Everything here is scored over the 52-week **evaluation window**
(`datagen.EVAL_START_WEEK` through `datagen.N_WEEKS`) — the first 52 weeks
of history are burn-in, needed before a seasonal-naive or statistical
forecast is even defined, and are never scored (see `datagen.py`'s module
docstring).

Four metrics, each earning its place for a different reason:

- **MAPE** (Mean Absolute Percentage Error) — the familiar textbook
  metric, `mean(|actual - forecast| / actual)`. Undefined (skipped, not
  faked) on zero-actual weeks, which makes it systematically unreliable
  for intermittent/lumpy SKUs — a well-known critique, not a bug here.
  Standard, uncited.
- **WMAPE** (volume-Weighted MAPE) — `sum(|actual - forecast|) /
  sum(actual)`. This is the headline metric in this repo precisely
  because it is defined even when some weeks have zero actual (it just
  doesn't divide by them individually), and because it naturally weights
  high-volume SKUs and weeks more heavily than low-volume ones — a
  planner who nails the 200-unit-a-week SKU and misses the 3-unit one
  has, correctly, mostly succeeded. Standard, uncited.
- **Bias** (mean signed error, `mean(forecast - actual)`) and **tracking
  signal** (`cumulative_error / mean_absolute_deviation`) — whether a
  forecast is systematically over- or under-shooting, not just how far
  off it is on average. A tracking signal beyond ±4 is the common
  textbook rule-of-thumb for "this forecast is out of statistical
  control." Standard, uncited.
- **MASE** (Mean Absolute Scaled Error) — Hyndman & Koehler (2006),
  "Another look at measures of forecast accuracy," *International
  Journal of Forecasting* 22(4):679-688, DOI 10.1016/j.ijforecast.2006.03.001.
  Scale-free: the eval-window mean absolute error is divided by the
  **in-sample** (burn-in-window) one-step naive benchmark's mean absolute
  error. MASE < 1 means the forecast beats that in-sample naive
  benchmark; MASE > 1 means it is worse than just guessing last period's
  actual.
"""

from __future__ import annotations

import statistics

from .datagen import BURN_IN_WEEKS, EVAL_START_WEEK
from .models import AccuracyMetrics, ForecastLayer, WeekRecord

_LAYER_FIELD: dict[ForecastLayer, str] = {
    ForecastLayer.NAIVE: "naive_fcst",
    ForecastLayer.STATISTICAL: "stat_fcst",
    ForecastLayer.CONSENSUS: "consensus_fcst",
}


def eval_pairs(records: list[WeekRecord], layer: ForecastLayer) -> list[tuple[float, float]]:
    """(actual, forecast) pairs over the scored evaluation window for one
    SKU's records and one forecast layer, skipping any week where that
    layer's forecast is `None` (should not occur inside the eval window,
    guarded defensively)."""
    field = _LAYER_FIELD[layer]
    pairs = []
    for r in records:
        if r.week < EVAL_START_WEEK:
            continue
        forecast = getattr(r, field)
        if forecast is None:
            continue
        pairs.append((r.actual, forecast))
    return pairs


def mape(pairs: list[tuple[float, float]]) -> float | None:
    """Mean Absolute Percentage Error, skipping zero-actual weeks. `None`
    if every week in `pairs` has zero actual (fully undefined)."""
    scored = [(a, f) for a, f in pairs if a != 0]
    if not scored:
        return None
    return 100.0 * statistics.fmean(abs(a - f) / a for a, f in scored)


def wmape(pairs: list[tuple[float, float]]) -> float:
    """Volume-weighted MAPE: sum(|error|) / sum(actual). 0.0 if total
    actual volume is zero (no error is possible to weight)."""
    total_actual = sum(a for a, _ in pairs)
    if total_actual == 0:
        return 0.0
    total_abs_error = sum(abs(a - f) for a, f in pairs)
    return 100.0 * total_abs_error / total_actual


def bias(pairs: list[tuple[float, float]]) -> float:
    """Mean signed error (forecast - actual). Positive = systematic
    over-forecast; negative = systematic under-forecast."""
    if not pairs:
        return 0.0
    return statistics.fmean(f - a for a, f in pairs)


def tracking_signal(pairs: list[tuple[float, float]]) -> float | None:
    """Cumulative signed error / mean absolute deviation. `None` if MAD is
    zero (a perfect forecast — no signal to compute)."""
    if not pairs:
        return None
    errors = [f - a for a, f in pairs]
    mad = statistics.fmean(abs(e) for e in errors)
    if mad == 0:
        return None
    return sum(errors) / mad


def mase(records: list[WeekRecord], layer: ForecastLayer) -> float | None:
    """Mean Absolute Scaled Error: eval-window MAE for `layer`, scaled by
    the in-sample (burn-in window) one-step naive benchmark's MAE.
    `None` if the in-sample scale is zero (a constant burn-in window —
    does not occur in this dataset, guarded defensively)."""
    burn_in = sorted((r for r in records if r.week <= BURN_IN_WEEKS), key=lambda r: r.week)
    if len(burn_in) < 2:
        return None
    naive_diffs = [abs(burn_in[i].actual - burn_in[i - 1].actual) for i in range(1, len(burn_in))]
    scale = statistics.fmean(naive_diffs)
    if scale == 0:
        return None

    pairs = eval_pairs(records, layer)
    if not pairs:
        return None
    mae = statistics.fmean(abs(a - f) for a, f in pairs)
    return mae / scale


def compute_sku_accuracy(records: list[WeekRecord], layer: ForecastLayer) -> AccuracyMetrics:
    """The full `AccuracyMetrics` scorecard for one SKU's `records`
    (its full history — burn-in is needed for the MASE scale) and one
    forecast `layer`."""
    sku_id = records[0].sku_id if records else "unknown"
    pairs = eval_pairs(records, layer)
    return AccuracyMetrics(
        sku_id=sku_id,
        layer=layer,
        mape=mape(pairs),
        wmape=wmape(pairs),
        bias=bias(pairs),
        tracking_signal=tracking_signal(pairs),
        mase=mase(records, layer),
    )


def compute_all_accuracy(history, catalog) -> list[AccuracyMetrics]:
    """`compute_sku_accuracy` for every SKU x every forecast layer."""
    results: list[AccuracyMetrics] = []
    for sku_id in catalog.sku_ids():
        records = history.for_sku(sku_id)
        for layer in ForecastLayer:
            results.append(compute_sku_accuracy(records, layer))
    return results


def aggregate_wmape(history, sku_ids: list[str], layer: ForecastLayer) -> float:
    """Volume-weighted WMAPE across a *set* of SKUs (a segment, or the
    whole portfolio) — the pairs from every SKU's eval window are pooled
    before the sum(|error|)/sum(actual) ratio is taken, so a single
    high-volume SKU legitimately dominates the aggregate the same way it
    would dominate a real planner's attention."""
    pooled: list[tuple[float, float]] = []
    for sku_id in sku_ids:
        pooled.extend(eval_pairs(history.for_sku(sku_id), layer))
    return wmape(pooled)

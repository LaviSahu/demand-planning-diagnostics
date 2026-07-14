# 03 — KPI Reference

Every formula as it is actually implemented, tied to the module that computes it. All metrics
are evaluated over the **52-week evaluation window** (weeks 53–104) unless noted; segmentation
inputs use the full 104-week actual series.

## Accuracy metrics (`accuracy.py`)

For a (SKU, forecast layer) pair, with actual `a_t` and forecast `f_t` over the evaluation weeks:

- **MAPE** — Mean Absolute Percentage Error. `mean(|a_t − f_t| / a_t)` over weeks where
  `a_t ≠ 0`. Weeks with zero actual are **excluded rather than faked** (division by zero); if
  *every* eval week is zero, MAPE is `None`. Reported as a percentage.
- **WMAPE** — Weighted (volume-weighted) MAPE, and the **headline** number:
  `Σ|a_t − f_t| / Σ a_t`. Because it weights by actual volume, a handful of tiny-volume SKUs
  can no longer dominate the portfolio average — this is the metric that maps to service and
  inventory consequences. Reported as a percentage.
- **Bias** — mean signed error `mean(f_t − a_t)`, in units/week. Positive = systematic
  over-forecast.
- **Tracking signal** — cumulative signed error divided by the mean absolute deviation; the
  rule of thumb is that **|TS| > 4** indicates an out-of-control (persistently biased) forecast.
  `None` where undefined.
- **MASE** — Mean Absolute Scaled Error (Hyndman & Koehler, 2006, *IJF* 22(4):679–688,
  DOI [10.1016/j.ijforecast.2006.03.001](https://doi.org/10.1016/j.ijforecast.2006.03.001)).
  Mean absolute error scaled by the in-sample one-step naive error. **MASE < 1.0 beats the naive
  benchmark.** `None` only in the pathological zero-scale case (guarded, does not occur here).

## Forecast Value Added (`fva.py`)

FVA measures the accuracy change a process step adds, in WMAPE points, versus the step before it
(Gilliland, *The Business Forecasting Deal*, Wiley 2010; SAS FVA framework).

- **`fva = wmape_from − wmape_to`.** Because lower WMAPE is better, a **positive FVA means the
  later layer is more accurate** (it added value); **negative means it made the forecast worse.**
- **`fva_pct = fva / wmape_from`** (0 if `wmape_from` is 0) — the same delta as a share of the
  starting error.
- Computed at three levels: **per SKU**, **per segment**, and **overall**, for each step of the
  stairstep: naive → statistical, statistical → consensus, and naive → consensus.

## KPI catalog (`kpi.py`)

Every tile is computed from the outputs above — nothing hardcoded. Values shown are from the
seeded `make demo` run.

| KPI | Definition | Seeded value |
|---|---|---|
| **WMAPE (Consensus)** | Volume-weighted MAPE of the shipped consensus forecast | 53.1% |
| **FVA: Statistical vs Naive** | WMAPE improvement from the statistical step | +7.0 pp (59.2% → 52.2%) |
| **FVA: Consensus vs Statistical** | WMAPE change from human overrides | −0.9 pp (52.2% → 53.1%) |
| **% SKUs Overrides Hurt** | Share of SKUs with negative consensus-vs-statistical FVA | 52.5% (21 of 40) |
| **Forecastable Volume Share** | Smooth+Erratic share of total unit volume | 91.4% |
| **Bias (Consensus)** | Mean signed error | +5.5 units/wk |
| **Tracking Signal (Consensus)** | Cumulative-error control metric | 121.3 (\|TS\|>4 = out of control) |
| **MASE (Consensus)** | Scale-free error vs in-sample naive | 0.75 (< 1.0 beats naive) |

Re-seed `datagen.py` and every value in this table changes, because each is derived from the
generated history at run time.

Back to the [wiki home](index.md).

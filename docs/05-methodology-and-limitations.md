# 05 — Methodology & Limitations

Seniors bound their claims. This page states exactly which methods are used, where they come
from, and what this repo does *not* prove.

## Named methodologies (verified sources)

1. **Forecast Value Added (FVA)** — Michael Gilliland (2010), *The Business Forecasting Deal:
   Exposing Myths, Eliminating Bad Practices, Providing Practical Solutions*, John Wiley & Sons,
   ISBN 978-0470574430; and the SAS FVA framework. FVA = the change in a forecast-accuracy
   metric (WMAPE here) attributable to a given process step, measured against a naive benchmark.
   A negative FVA means the step destroyed value.
2. **Demand categorisation (ADI / CV²)** — Syntetos, Boylan & Croston (2005), *On the
   categorization of demand patterns*, Journal of the Operational Research Society, 56(5),
   495–503, DOI [10.1057/palgrave.jors.2601841](https://doi.org/10.1057/palgrave.jors.2601841).
   Canonical cutoffs ADI = 1.32, CV² = 0.49; four quadrants (smooth / erratic / intermittent /
   lumpy).
3. **MASE (Mean Absolute Scaled Error)** — Hyndman & Koehler (2006), *Another look at measures
   of forecast accuracy*, International Journal of Forecasting, 22(4), 679–688,
   DOI [10.1016/j.ijforecast.2006.03.001](https://doi.org/10.1016/j.ijforecast.2006.03.001).
   Scale-free; MASE < 1 beats the in-sample one-step naive benchmark.

**MAPE, WMAPE, bias, and tracking signal** are standard textbook material and are presented
plainly, not attributed to a specific author or paper.

No other methodology is claimed. If a metric or method is not in this list, it is either
standard practice or not used.

## Limitations (what this does not prove)

- **Synthetic, single-region data.** The portfolio is fictional ("Northwind Foods"). These
  numbers demonstrate that the *diagnostic* works and what it surfaces — they are **not** a
  benchmark of any real company's forecast quality.
- **Additive promotional model only.** Promotions are modelled as a fixed additive uplift on a
  known calendar; there is no price-elasticity, cannibalisation, or causal modelling.
- **Deliberately simple statistical forecast.** The `stat_fcst` layer is a standard-library
  decomposition + simple exponential smoothing (or trailing moving average for the tail), not a
  production statistical engine. A stronger baseline would shift the FVA numbers — the *method*
  of measuring FVA is the point, not the specific baseline's skill.
- **The override is synthetic.** The consensus layer's "analyst override" is a modelled
  noise-chase-plus-promo term, not real human behaviour. It is constructed to be *plausibly*
  sometimes-helpful and sometimes-harmful; its net verdict is measured by `fva.py`, not assumed.
  It should be read as an illustration of *how the diagnostic behaves when overrides are mixed
  quality*, not as evidence about any real planning team.
- **No hierarchy or reconciliation.** SKUs are treated independently; there is no forecast
  reconciliation across product / category / total levels.
- **MASE uses in-sample naive scaling** (the standard definition), which can differ slightly
  from an out-of-sample scaling choice.

## What it *is* good for

A faithful, reproducible demonstration of the three diagnostics every demand-planning function
should run and few do: segment by forecastability, score with the volume-weighted metric that
matters, and measure the value each process step actually adds. The framework transfers directly
to real demand data — only `datagen.py` would be replaced by a real history loader.

Back to the [wiki home](index.md).

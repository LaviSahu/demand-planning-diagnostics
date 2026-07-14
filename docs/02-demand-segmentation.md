# 02 — Demand Segmentation

Before you judge a forecast, you have to know whether the demand was forecastable at all.
Reporting a lumpy slow-mover's error next to a smooth high-runner's invites the wrong
conclusion — the planner looks incompetent on SKUs that are, by their nature, close to
unforecastable. Segmentation frames every accuracy number in this repo.

## The method (and its source)

`segment.py` implements the **Syntetos–Boylan–Croston** demand-categorisation scheme:

> Syntetos, A. A., Boylan, J. E., & Croston, J. D. (2005). *On the categorization of demand
> patterns.* Journal of the Operational Research Society, 56(5), 495–503.
> DOI [10.1057/palgrave.jors.2601841](https://doi.org/10.1057/palgrave.jors.2601841).

Each SKU's full 104-week actual demand series is reduced to two numbers:

- **ADI — Average inter-Demand Interval.** The mean number of periods between nonzero-demand
  periods. `ADI = (number of periods) / (number of nonzero-demand periods)`. High ADI = lots of
  zero weeks = intermittent.
- **CV² — squared coefficient of variation of the *nonzero* demand sizes.**
  `CV² = (stdev of nonzero demand / mean of nonzero demand)²`. High CV² = the size of a demand
  event, when it happens, is wildly variable.

## The four quadrants (canonical cutoffs ADI = 1.32, CV² = 0.49)

| Quadrant | ADI | CV² | Meaning | Planning implication |
|---|---|---|---|---|
| **Smooth** | < 1.32 | < 0.49 | Regular timing, stable size | Forecast with standard methods |
| **Erratic** | < 1.32 | ≥ 0.49 | Regular timing, volatile size | Forecastable, but expect wide error |
| **Intermittent** | ≥ 1.32 | < 0.49 | Many zero periods, stable size | Croston-style / policy territory |
| **Lumpy** | ≥ 1.32 | ≥ 0.49 | Sparse *and* volatile | Effectively unforecastable — manage by **inventory policy**, not a forecast |

The 1.32 and 0.49 thresholds are the published SBC cutoffs; they are dataset-agnostic constants,
not tuned to this synthetic portfolio.

## A built-in honesty check

`datagen.py` assigns each SKU a *true* archetype used only to generate its demand. In a real
deployment that label would not exist — the whole point of segmentation is to *discover* the
pattern from observed demand. Keeping it lets the dashboard answer "does the computed
segmentation recover the pattern we built in?" as a sanity check on the classifier. It is a
validation aid, never an input to the classifier itself.

## What it drives downstream

`SegmentAssignment.volume_share` — each SKU's fraction of total portfolio unit volume — is the
weight behind the **Forecastable volume share** KPI (the smooth+erratic share of volume) and the
size of each point in the dashboard's ADI-vs-CV² scatter, so a single high-volume SKU counts for
more than a trickle-selling long-tail one. On the seeded run, **91.4% of volume is
forecast-drivable** and only **8.6%** sits in the intermittent+lumpy tail.

Back to the [wiki home](index.md).

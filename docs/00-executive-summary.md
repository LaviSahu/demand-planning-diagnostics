# 00 — Executive Summary

*A non-technical read. Five minutes. No code.*

## The business question

Every demand-planning function makes two bets it rarely checks: that its forecast beats a
naive guess, and that the hours analysts spend manually adjusting the forecast make it better.
Both are testable. This analysis tests them on a realistic synthetic FMCG portfolio (40 SKUs,
two years of weekly demand) and asks: **where in our forecasting process are we adding value —
and where are we destroying it?**

The decision at stake is where to point scarce analyst effort: which SKUs deserve a human's
attention, and which should be taken off the forecast entirely and run on inventory policy.

## What the analysis found

On the seeded data, three findings stand out — all computed, none assumed:

1. **The statistical model earns its keep.** Moving from a naive baseline to a proper
   statistical forecast improves volume-weighted error by **7.0 percentage points**
   (59.2% → 52.2% WMAPE). Statistical forecasting is doing real work.

2. **The human overrides, on net, give some of it back.** The consensus forecast that actually
   ships is **0.9 pp *worse*** than the statistical forecast it started from (52.2% → 53.1%).
   **21 of 40 SKUs (52.5%)** are less accurate *after* a human adjusted them.

3. **The damage is concentrated on the SKUs that should never have been touched.** By demand
   type, overrides *help* intermittent items (+1.5 pp) but *hurt* lumpy slow-movers by
   **6.9 pp**. The worst individual overrides — Classic Cola 2L (−20.5 pp), Aluminum Foil
   (−19.7 pp), Foaming Hand Soap Refill (−14.9 pp) — are all long-tail items whose demand is,
   by nature, close to unforecastable.

The reason the *overall* damage looks modest (−0.9 pp) is telling: the hurt SKUs are the
low-volume tail. **91.4% of volume is forecast-drivable** (smooth + erratic demand); only
**8.6%** is the intermittent + lumpy tail. So the overrides hurt a *majority of SKUs* but a
*minority of volume* — which is exactly why the effort is wasted: high touch, negligible
volume, and a measurable accuracy loss where it lands.

The forecast still beats a naive guess overall (MASE 0.75, where anything under 1.0 beats
naive) — but that win belongs to the statistical model, not the manual overrides.

## The methodology (named, and honest about its source)

- **Demand segmentation** uses the Syntetos–Boylan–Croston ADI/CV² scheme
  (Syntetos, Boylan & Croston, 2005, *Journal of the Operational Research Society* 56(5):495–503) —
  the published standard for classifying demand as smooth, erratic, intermittent or lumpy.
- **Forecast Value Added (FVA)** follows Michael Gilliland's framework
  (*The Business Forecasting Deal*, Wiley, 2010; and the SAS FVA method) — measuring the
  accuracy change each process step adds versus a naive benchmark.
- **MASE** (the beats-naive check) is Hyndman & Koehler, 2006, *International Journal of
  Forecasting* 22(4):679–688.

## What's synthetic, and what this does *not* claim

All data is generated in-repo for a fictional company ("Northwind Foods") — never real client
data. The promotional model is simple and additive; the statistical forecast is deliberately
lightweight (standard-library only). These numbers demonstrate that the *diagnostic* works and
what it surfaces — they are not a benchmark of any real business's forecast quality.

## The executive takeaway

> **Freeze manual overrides on the intermittent and lumpy long tail.** These SKUs are
> unforecastable by construction and belong on inventory policy, not a forecast. Doing so
> reclaims the analyst effort currently producing a **6.9 pp accuracy loss** on lumpy items and
> redirects it to the **91.4% of volume** where disciplined forecasting actually pays off.
>
> **The one number to act on: 21 of 40 SKUs are getting a *worse* forecast because a human
> touched them.**

Back to the [wiki home](index.md) · [README](../README.md).

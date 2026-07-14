# 06 — Roadmap

What a real deployment would add next, in rough priority order. Everything here is deliberately
*out* of the current stdlib-only, single-file-dashboard scope.

- **Real history loader.** Replace `datagen.py` with an adapter that reads actual demand + the
  forecast layers from a planning system (SAP IBP, o9, Kinaxis) or a flat export. The engine
  (`segment` / `accuracy` / `fva` / `kpi`) is already agnostic to where the `DemandHistory`
  comes from.
- **Croston / SBA for the intermittent tail.** Add intermittent-demand forecasting methods
  (Croston, Syntetos–Boylan Approximation) so the tail has a *fair* statistical baseline before
  concluding it is unforecastable.
- **FVA over more of the process.** Extend the stairstep beyond naive → statistical → consensus
  to include upstream steps (e.g. a "final published" layer after S&OP sign-off) so the value
  added by each governance gate is visible.
- **Accuracy over a rolling origin.** Replace the single fixed evaluation window with
  rolling-origin (walk-forward) evaluation for a more robust accuracy read.
- **Segment migration tracking.** Show how SKUs move between quadrants over time — a SKU drifting
  from smooth to lumpy is an early warning worth a KPI.
- **Cost-of-error weighting.** Weight FVA not just by volume but by the margin / service cost of
  error, so the "where to point analyst effort" recommendation is dollar-aware.
- **Config surface.** Expose the seed, SKU count, and archetype mix via CLI flags for scenario
  exploration without editing code.

Back to the [wiki home](index.md).

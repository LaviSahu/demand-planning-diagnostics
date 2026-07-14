# Demand Planning Diagnostics — Wiki Home

A demand planner's diagnostic toolkit that answers one question on a realistic synthetic
FMCG portfolio: **is our forecast actually adding value, and where is it worst?** These pages
explain the concepts, the methodology, the data, and every number as it is actually computed.

## Pages

1. **[00 — Executive summary](00-executive-summary.md)** — the <10-minute, no-code read: the
   business question, the finding, and the one decision to act on.
2. **[01 — Architecture](01-architecture.md)** — module map, data flow, and the dashboard
   context contract.
3. **[02 — Demand segmentation](02-demand-segmentation.md)** — the Syntetos–Boylan–Croston
   ADI/CV² quadrants, the citation, and the canonical cutoffs.
4. **[03 — KPI reference](03-kpi-reference.md)** — every formula *as implemented*, per module.
5. **[04 — Data dictionary](04-data-dictionary.md)** — every field of every synthetic dataset:
   name, type, unit, range, meaning, and whether it is synthetic-by-construction or derived.
6. **[05 — Methodology & limitations](05-methodology-and-limitations.md)** — the verified
   citations and the explicit bounds on every claim.
7. **[06 — Roadmap](06-roadmap.md)** — what a real deployment would add next.

## Ground truth

Every number quoted anywhere in this repo comes from actually running
`PYTHONPATH=src python3 -m demand_planning_diagnostics demo` on the seeded synthetic data —
nothing is hardcoded. Re-seed `datagen.py` and every figure in the docs, the console and the
dashboard moves together, because they all read from the same computed engine outputs.

Back to the [README](../README.md).

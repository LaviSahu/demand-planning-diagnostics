# Demand Planning Diagnostics — Build Spec (frozen)

Showcase-grade, self-contained demand-planning diagnostic platform. Pure Python 3.10+ **stdlib only** (no pip installs needed to run the demo). Original work — NO references to EY, clients, or any consulting firm anywhere in code or docs.

## What it is

A demand planner's diagnostic toolkit answering one question: **is our forecast actually adding value, and where is it worst?** Takes a synthetic FMCG demand history with a three-layer forecast stack (naive → statistical → consensus/override) and computes demand segmentation (Syntetos-Boylan-Croston), forecast-accuracy diagnostics (MAPE/WMAPE/bias/tracking signal/MASE), and Forecast Value Added (Gilliland) — exposing exactly which SKUs the planning process is helping and which it is hurting.

## Repo layout

```
demand-planning-diagnostics/
├── README.md                       # showcase README
├── LICENSE                         # MIT, copyright Lavi Sahu
├── pyproject.toml                  # metadata only, no deps
├── Makefile                        # demo / test / dashboard / clean targets
├── data/
│   ├── skus.json                   # SKU catalog (generated, committed)
│   ├── history.json                # 104-week demand + 3 forecast layers (generated, committed)
│   ├── segments.json               # per-SKU segmentation (written by demo/segment)
│   └── fva.json                    # FVA results (written by demo/fva)
├── src/demand_planning_diagnostics/
│   ├── __init__.py  __main__.py  cli.py
│   ├── models.py     # dataclasses: Sku, SkuCatalog, WeekRecord, DemandHistory,
│   │                 # SegmentAssignment, AccuracyMetrics, FvaResult, Kpi
│   ├── datagen.py    # synthetic Northwind Foods dataset generator (seeded)
│   ├── segment.py    # ADI / CV² demand-pattern classification (SBC quadrants)
│   ├── accuracy.py   # MAPE / WMAPE / bias / tracking signal / MASE
│   ├── fva.py        # Forecast Value Added stairstep (naive -> stat -> consensus)
│   ├── kpi.py        # KPI catalog, every number computed from real engine outputs
│   └── dashboard.py  # self-contained HTML dashboard generator (inline CSS/JS/SVG)
├── tests/            # stdlib unittest, runnable via `python -m unittest discover`
├── docs/             # wiki-style pages
└── output/           # gitignored except .gitkeep; dashboard.html lands here
```

## Domain spec

### Named methodologies (VERIFIED — cite exactly these, do not invent or add others)

1. **Forecast Value Added (FVA)** — Michael Gilliland (2010), *The Business Forecasting Deal: Exposing Myths, Eliminating Bad Practices, Providing Practical Solutions*, John Wiley & Sons, ISBN 978-0470574430; and the SAS FVA framework. FVA = the change in a forecast-accuracy metric (WMAPE, here) attributable to a given process step. A negative FVA means that step is destroying value.
2. **Demand categorization (ADI / CV²)** — Syntetos, Boylan & Croston (2005), "On the categorization of demand patterns," *Journal of the Operational Research Society* 56(5):495–503, DOI 10.1057/palgrave.jors.2601841. Canonical cutoffs ADI = 1.32, CV² = 0.49; four quadrants: Smooth, Erratic, Intermittent, Lumpy.
3. **MASE** — Hyndman & Koehler (2006), "Another look at measures of forecast accuracy," *International Journal of Forecasting* 22(4):679–688, DOI 10.1016/j.ijforecast.2006.03.001. Scale-free; MASE < 1 beats the in-sample one-step naive benchmark.

MAPE, WMAPE, bias, and tracking signal are standard textbook material — presented plainly, not attributed to a specific author/paper.

### Synthetic dataset

Fictional FMCG maker **"Northwind Foods"** — 40 SKUs across 3 categories (Beverages, Snacks, Household), 104 weeks of history, 10 SKUs per demand archetype:

- **smooth** — stable base + mild seasonality + small noise
- **erratic** — stable frequency but high size variance
- **intermittent** — many zero-demand weeks, modest sizes
- **lumpy** — sparse + high size variance (long-tail slow movers)

Half of smooth and half of erratic SKUs are `promo_eligible` and carry a fixed 4-week-of-year promotional calendar with an additive uplift.

Three forecast layers per SKU-week (only defined for the 52-week evaluation window; the first 52 weeks are burn-in):

- `naive_fcst` — seasonal-naive (52 weeks back) for smooth/erratic; last-actual for intermittent/lumpy.
- `stat_fcst` — a hand-rolled classical-decomposition model (deseasonalize + SES) for smooth/erratic; a trailing moving average for intermittent/lumpy.
- `consensus_fcst` — `stat_fcst` plus a synthetic analyst override: a chase term (reacts to noise, small for smooth, large for lumpy) and a promo term (adds real value on promo-eligible weeks). The net effect is **not asserted** — it falls out of the constant tables and random draws, and `fva.py` measures it after the fact.

### Modules

- `datagen.py` — generate the synthetic history + 3 forecast layers; seeded (fixed seed → stable output); writes JSON to `data/`.
- `segment.py` — compute ADI, CV², assign quadrant per SKU (SBC cutoffs); validates recovery against the true archetype.
- `accuracy.py` — per-SKU and aggregate MAPE, WMAPE (the headline metric), bias + tracking signal, MASE.
- `fva.py` — FVA stairstep: naive → statistical → consensus, in WMAPE terms; per-SKU, per-segment, and overall; flags SKUs with negative FVA.
- `kpi.py` — roll-up KPI catalog, every number computed from engine outputs, nothing hardcoded.
- `dashboard.py` — one self-contained dark/light-themed `output/dashboard.html`: ADI-vs-CV² segmentation scatter, FVA stairstep chart, accuracy-by-segment table, worst-manual-overrides ranked list, KPI tiles.
- `cli.py` + `__main__.py` — `segment` / `accuracy` / `fva` / `demo` / `dashboard`, hand-rolled console tables.

### KPI catalog

- **WMAPE (consensus)** — volume-weighted MAPE of the final consensus forecast; the headline accuracy number.
- **FVA: statistical vs naive** — WMAPE improvement from the statistical step.
- **FVA: consensus vs statistical** — WMAPE change from human overrides (the money finding; may be negative).
- **% SKUs where overrides hurt** — share of SKUs with negative consensus-vs-statistical FVA.
- **Forecastable share** — % of volume in Smooth/Erratic (forecast-drivable) vs Intermittent/Lumpy (policy-drivable).
- **Bias / tracking signal** — systematic over/under-forecast direction.
- **MASE (consensus)** — is the final forecast even beating the naive benchmark (<1 good).

### Executive takeaway

A single, specific, exec-actionable statement derived from the actual seeded run (see `docs/00-executive-summary.md` and the README) — not a template filled with placeholder numbers.

### Assumptions & Limitations

Synthetic single-region data; additive promo model only (no causal/price-elasticity modeling); statistical forecast is intentionally simple (stdlib, not a full stat engine); MASE uses in-sample naive scaling; segmentation cutoffs are the SBC canonical values and are dataset-agnostic; no hierarchy/reconciliation across product levels; results illustrate the *method*, not a real company.

### Acceptance criteria

`make demo` runs top-to-bottom on a bare Python 3.10+ (no pip), seeded/stable output; `make test` green; `output/dashboard.html` opens offline with all charts; data dictionary complete; README follows the resilience-radar section order; exec doc readable by a non-technical reviewer in <10 min; every methodology claim carries the verified citation above or is marked standard/uncited; nothing hardcoded that should be computed.

## Style

Type hints everywhere, dataclasses, no globals; each module has a docstring explaining the concept for a reader learning demand planning.

Deviations from this spec: log in `implementation-notes.md` under "Deviations", pick the conservative option, keep going.

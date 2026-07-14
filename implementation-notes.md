# Implementation Notes

Build log for `demand-planning-diagnostics`. The repo follows the frozen `SPEC.md` and matches
the `resilience-radar` house style (stdlib-only, self-contained HTML dashboard, `unittest`
suite).

## Build sequence

1. Engine + data + tests were built first: `models.py`, `datagen.py` (seeded synthetic
   "Northwind Foods"), `segment.py`, `accuracy.py`, `fva.py`, `kpi.py`, `dashboard.py`,
   `cli.py`, the generated `data/*.json`, and the 66-test suite. `make demo` and `make test`
   both pass on Python 3.10.
2. `README.md`, the `docs/` wiki (index + `00`–`06`, including the data dictionary), and this
   file were completed in a follow-up pass after the initial build session was interrupted by an
   API spend-limit; all numbers in them were taken from a live `make demo` run, not invented.

## Deviations from spec

- **None material.** The spec's structure was followed. The one naming choice worth recording:
  the exec doc is `docs/00-executive-summary.md` (as the spec's acceptance section anticipated),
  linked from the README and `docs/index.md` but standing alone as a <10-minute read.

## Key modelling choices (measured, not asserted)

- The synthetic **consensus/override layer** is built from constant tables + seeded draws (a
  noise-chase term that grows for lumpier SKUs, plus a promo term on promo-eligible weeks). Its
  net effect on accuracy is **not tuned to a verdict** — it is measured by `fva.py` after the
  fact. On the shipped seed the result is: statistical adds +7.0 pp WMAPE over naive; the
  overrides give back −0.9 pp overall, hurting 21 of 40 SKUs, concentrated in the lumpy tail.
- **WMAPE is the headline**, not unweighted MAPE — volume-weighting is what keeps low-volume
  SKUs from dominating and is what maps to real service/inventory consequences.
- **Zero-actual weeks are excluded from MAPE, not faked.** Intermittent/lumpy SKUs have zero
  weeks; dividing by them would fabricate error. WMAPE and MASE handle the tail honestly.

## Verification (from a live run)

- `make test` → 66 tests, OK.
- `make demo` → runs top-to-bottom on bare Python 3.10, writes `output/dashboard.html`.
- `output/dashboard.html` grep for external `http(s)://` / CDN / `<script src=` / `<link href=`
  → zero matches (fully self-contained).

## Citations (verified, do not alter)

- FVA — Gilliland (2010), *The Business Forecasting Deal*, Wiley, ISBN 978-0470574430.
- Demand categorisation — Syntetos, Boylan & Croston (2005), *JORS* 56(5):495–503,
  DOI 10.1057/palgrave.jors.2601841.
- MASE — Hyndman & Koehler (2006), *IJF* 22(4):679–688, DOI 10.1016/j.ijforecast.2006.03.001.

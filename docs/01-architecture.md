# 01 — Architecture

A linear, deterministic pipeline: generate a synthetic demand history, then run three
independent diagnostic passes over it (segment / accuracy / FVA), roll the results into a KPI
catalog, and render one self-contained HTML dashboard. Every stage reads typed dataclasses
from `models.py`; nothing recomputes downstream of the engine.

## Module map

| Module | Role | Reads | Produces |
|---|---|---|---|
| `models.py` | Shared vocabulary — dataclasses + enums + `jsonable()` | — | The types every other module speaks |
| `datagen.py` | Seeded synthetic generator | constant tables + fixed seed | `SkuCatalog`, `DemandHistory` → `data/skus.json`, `data/history.json` |
| `segment.py` | ADI/CV² demand-pattern classification | `DemandHistory` | `SegmentAssignment` per SKU → `data/segments.json` |
| `accuracy.py` | Forecast-accuracy scorecard | `DemandHistory` | `AccuracyMetrics` per (SKU, layer) |
| `fva.py` | Forecast Value Added stairstep | `DemandHistory` | `FvaResult` per SKU / segment / overall → `data/fva.json` |
| `kpi.py` | Roll-up KPI catalog | segment + accuracy + FVA outputs | `Kpi` tiles |
| `dashboard.py` | Self-contained HTML renderer | the dashboard context dict | `output/dashboard.html` |
| `cli.py` / `__main__.py` | Command-line surface | all of the above | console tables + files |

## Data flow

```
datagen.py ──► skus.json ──┐
           └─► history.json ─┼─► segment.py ─► segments.json ─┐
                             ├─► accuracy.py ─► AccuracyMetrics ┼─► kpi.py ─► Kpi tiles ─┐
                             └─► fva.py ──────► fva.json ───────┘                        │
                                                                                         ▼
                                          dashboard.build_context(...) ─► render_dashboard ─► dashboard.html
```

The 104-week history splits into a **52-week burn-in** (weeks 1–52, no forecast is definable
yet — the three forecast fields are `None`) and a **52-week evaluation window** (weeks 53–104,
where accuracy and FVA are measured). Segmentation uses the full 104-week actual series.

## The dashboard context contract

`dashboard.build_context(...)` assembles **one** JSON-serialisable dict holding everything the
page needs — KPI tiles, the per-SKU segmentation points (ADI, CV², volume share, quadrant), the
FVA stairstep series, accuracy-by-segment rows, the worst-override ranking, and `generated_at`.
`render_dashboard(context, out_path)` then injects it into a raw-string HTML template via the
`__DATA_JSON__` sentinel (not `str.format`, so inline CSS/JS braces stay literal), escaping
`</` to `<\/` so an embedded string can never close the `<script>` early. The renderer never
computes a number — it only formats what the engine already produced. That is what keeps the
console, the JSON files and the dashboard from ever disagreeing.

## Why this shape

The three diagnostic passes are deliberately independent: segmentation must not depend on
accuracy (you segment on demand *shape*, not forecast quality), and FVA must be computable
without the KPI roll-up. Keeping them separate means each is unit-testable in isolation and the
KPI layer is a pure function of their outputs — the property the test suite leans on hardest.

Back to the [wiki home](index.md).

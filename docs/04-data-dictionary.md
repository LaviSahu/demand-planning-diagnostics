# 04 — Data Dictionary

Every field of every synthetic dataset. All data is generated in-repo by `datagen.py` from a
fixed seed and is **clearly synthetic** — fictional maker "Northwind Foods", never real client
data. "Synthetic-by-construction" = an input the generator sets; "derived" = computed by an
engine module from those inputs.

## `data/skus.json` — the product master (`SkuCatalog` → `Sku[]`)

| Field | Type | Unit | Range / values | Meaning | Origin |
|---|---|---|---|---|---|
| `company` | string | — | `"Northwind Foods"` | Fictional company name | synthetic |
| `skus[].id` | string | — | e.g. `BEV-LUMP-07` | SKU id: `CATEGORY-ARCHETYPE-NN` | synthetic |
| `skus[].name` | string | — | e.g. `Classic Cola 2L` | Human-readable product name | synthetic |
| `skus[].category` | enum | — | `beverages` / `snacks` / `household` | Merchandising category | synthetic |
| `skus[].archetype` | enum | — | `smooth` / `erratic` / `intermittent` / `lumpy` | **True** demand pattern used to generate demand; a validation label, **not** a classifier input | synthetic |
| `skus[].revenue_per_unit` | float | currency/unit | > 0 | Unit price, used for any value weighting | synthetic |
| `skus[].promo_eligible` | bool | — | true/false | Whether the SKU ever receives a planned promo uplift (only smooth/erratic) | synthetic |

40 SKUs: 3 categories × 4 archetypes, 10 SKUs per archetype.

## `data/history.json` — 104-week demand + forecasts (`DemandHistory` → `WeekRecord[]`)

| Field | Type | Unit | Range | Meaning | Origin |
|---|---|---|---|---|---|
| `records[].sku_id` | string | — | matches a `Sku.id` | Which SKU this week belongs to | synthetic |
| `records[].week` | int | week index | 1–104 | Week number (1–52 burn-in, 53–104 evaluation) | synthetic |
| `records[].actual` | float | units | ≥ 0 | Realised demand that week (0 allowed for intermittent/lumpy) | synthetic |
| `records[].naive_fcst` | float \| null | units | ≥ 0 or null | Seasonal-naive (smooth/erratic) or last-actual (intermittent/lumpy); `null` during burn-in | synthetic |
| `records[].stat_fcst` | float \| null | units | ≥ 0 or null | Hand-rolled statistical forecast (decomposition+SES, or trailing MA); `null` during burn-in | synthetic |
| `records[].consensus_fcst` | float \| null | units | ≥ 0 or null | `stat_fcst` plus a synthetic analyst override (noise-chase term + promo term); `null` during burn-in | synthetic |
| `records[].is_promo` | bool | — | true/false | Whether a planned promo uplift was applied to `actual` that week | synthetic |

A `null` forecast during weeks 1–52 is **not missing data** — it is an honest "no forecast was
definable yet" (a naive or statistical forecast needs trailing history).

## `data/segments.json` — per-SKU segmentation (`SegmentAssignment[]`) — *derived*

| Field | Type | Unit | Range | Meaning | Origin |
|---|---|---|---|---|---|
| `sku_id` | string | — | matches a `Sku.id` | The SKU | derived |
| `adi` | float | periods | ≥ 1.0 | Average inter-demand interval | derived (`segment.py`) |
| `cv2` | float | — | ≥ 0 | Squared coefficient of variation of nonzero demand | derived (`segment.py`) |
| `segment` | enum | — | smooth/erratic/intermittent/lumpy | Assigned SBC quadrant (cutoffs 1.32, 0.49) | derived |
| `volume_share` | float | fraction | 0–1 | This SKU's share of total portfolio unit volume | derived |

## `data/fva.json` — Forecast Value Added results (`FvaResult[]`) — *derived*

| Field | Type | Unit | Range | Meaning | Origin |
|---|---|---|---|---|---|
| `level` | string | — | `sku` / `segment` / `overall` | Aggregation level | derived (`fva.py`) |
| `key` | string | — | SKU id, segment value, or `overall` | What this row aggregates | derived |
| `from_layer` / `to_layer` | enum | — | naive/statistical/consensus | The step being measured | derived |
| `wmape_from` / `wmape_to` | float | % | ≥ 0 | WMAPE before / after the step | derived |
| `fva` | float | pp | any sign | `wmape_from − wmape_to`; **positive = value added** | derived |
| `fva_pct` | float | % | any sign | `fva / wmape_from` | derived |

`output/dashboard.html` is a generated artifact (gitignored) built from the above; it hardcodes
no numbers of its own.

Back to the [wiki home](index.md).

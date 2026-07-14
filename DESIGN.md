# Demand Planning Diagnostics — Dashboard Design Spec (frozen)

One self-contained `output/dashboard.html` (inline CSS + vanilla JS + inline SVG, zero CDN). It must read as a polished planning-ops product — a **demand diagnostic control tower** — not a generated report.

## Theme system

Dual theme, dark default. CSS custom properties on `:root`, toggle button stamps `data-theme="light|dark"`; also respects `prefers-color-scheme` when no explicit choice. Same validated palette as resilience-radar (colorblind-safe ordering, contrast-checked) — referenced by role, never raw hex in the body:

```css
:root, :root[data-theme="dark"] {
  --page:#0d0d0d; --surface:#1a1a19; --surface-2:#222220;
  --ink:#ffffff; --ink-2:#c3c2b7; --muted:#898781;
  --grid:#2c2c2a; --axis:#383835; --ring:rgba(255,255,255,.10);
  --s1:#3987e5; --s2:#199e70; --s3:#c98500; --s4:#008300;
  --s5:#9085e9; --s6:#e66767; --s7:#d55181; --s8:#d95926;
  --good:#0ca30c; --warn:#fab219; --serious:#ec835a; --critical:#d03b3b;
}
:root[data-theme="light"] {
  --page:#f9f9f7; --surface:#fcfcfb; --surface-2:#f0efec;
  --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
  --grid:#e1e0d9; --axis:#c3c2b7; --ring:rgba(11,11,11,.10);
  --s1:#2a78d6; --s2:#1baf7a; --s3:#eda100; --s4:#008300;
  --s5:#4a3aa7; --s6:#e34948; --s7:#e87ba4; --s8:#eb6834;
  /* status colors unchanged */
}
```

Typography: `system-ui, -apple-system, "Segoe UI", sans-serif` everywhere (hero numbers included). `font-variant-numeric: tabular-nums` only in table columns and axis ticks.

Segment colors are semantic, not arbitrary: `smooth = --good` (forecastable, low risk), `erratic = --warn`, `intermittent = --s1`, `lumpy = --critical` (least forecastable) — the same color a viewer's eye reads as "worse" in the FVA bars also reads as "less forecastable" in the scatter, reinforcing rather than contradicting the KPI-tile red/green convention.

## Layout

Max-width 1280px centered, 24px gutters. Section order:

1. **Header bar** — small inline-SVG bar-chart glyph, product name "Demand Planning Diagnostics", a `DEMO DATA` chip, subtitle (company · SKU count · week count, filled from `DATA.company`/`n_skus`/`n_weeks`), generated-at stamp, theme toggle (sun/moon SVG button).
2. **KPI tile row** — 8 stat tiles, responsive grid (auto-fit, min 170px), in the fixed order `wmape_consensus, fva_stat, fva_consensus, pct_skus_overrides_hurt, forecastable_share, bias_consensus, tracking_signal_consensus, mase_consensus`. Tile = label (uppercase, muted) + hero value (28–30px, ink, unit suffix) + one-line context. The two FVA tiles get sign-based accent coloring (`.tile.neg` → `--critical`, `.tile.pos` → `--good`) since sign is the entire point of an FVA number — every other tile stays neutral ink, since "high" isn't inherently good or bad for e.g. tracking signal.
3. **Demand Segmentation card** — ADI-vs-CV² scatter (SVG ~720×420), one bubble per SKU: x = ADI, y = CV², bubble radius ∝ `sqrt(volume_share)` (area-proportional, not radius-proportional, so a 4x volume SKU isn't visually 4x larger than warranted), fill = computed segment color, dashed cutoff lines at ADI=1.32 / CV²=0.49. SKUs where the computed segment does **not** match the true generating archetype get a `--critical` stroke instead of the surface-colored ring every other point gets — this is the built-in "does the segmentation actually work" check, and it should read as visually rare (0-a-few points), not routine. Hover → tooltip with SKU name, computed vs. true segment, ADI, CV², volume share. A note line reports the exact recovery rate (`segment_recovery_rate`).
4. **Forecast Value Added card** — diverging horizontal bar chart (SVG ~640×220), one row per overall stairstep comparison (naive→stat, stat→consensus, naive→consensus), bars grow left (negative, `--critical`) or right (positive, `--good`) from a center zero-line. Direct value labels at each bar's outer end. Hover → tooltip with WMAPE before/after and the FVA delta.
5. **Accuracy by Segment card** — plain table, one row per present segment (segment badge with color dot), columns WMAPE at each of the three layers plus both FVA deltas (color-coded pos/neg cells) — this is where the segment-level split (smooth positive, lumpy/erratic negative) becomes legible at a glance.
6. **The Money Finding card** ("Where the Consensus Override Hurt Most") — ranked table of the worst SKU-level consensus-vs-statistical FVA results (worst first, capped at 15 rows with a "N of 40 SKUs shown" note), columns SKU name/id, segment badge, WMAPE stat, WMAPE consensus, FVA (always shown in `--critical` since every row here is, by construction, negative). Empty-state message if no SKU is ever hurt (defensive, not expected given this dataset).
7. **Footer** — one-line methodology note (Gilliland FVA / SAS FVA, Syntetos-Boylan-Croston, Hyndman-Koehler MASE citations) + "Built with Demand Planning Diagnostics" + docs pointer.

## Chart rules (non-negotiable)

- One y-axis per chart, never dual-axis. Hairline grids, no chart borders except the card ring.
- Segment colors are fixed per the semantic mapping above and never repainted on interaction.
- Every chart has a hover/tooltip layer; tooltips are HTML divs positioned near the cursor, surface bg, ring border, 12px text, values bold.
- No number printed on every mark where it would clutter (the scatter relies on the tooltip); direct labels are used where there is room (FVA bars, the segment table).
- Cards: `--surface` bg, 1px `--ring` border, radius 12px, 20px padding, 16px section titles (600 weight) with a muted 12px kicker above ("DEMAND SEGMENTATION", "FORECAST VALUE ADDED", "ACCURACY BY SEGMENT", "THE MONEY FINDING").

## JS behavior

Single `<script>` at the end: `const DATA = __DATA_JSON__;` (sentinel-injected at build time, `</` escaped to `<\/`), then small pure render functions per section. Theme toggle persists via `localStorage`. No frameworks. Tooltip positioning clamps to the viewport so it never renders off-screen.

## Quality bar

Open it and it should look like a product screenshot you'd put in a portfolio hero: aligned grids, consistent 8px spacing, no text under 11px, no pure `#000`/`#fff` mixing, nothing clipped at 1280px or 900px width (charts scroll horizontally in their own card via `overflow-x:auto` rather than squashing).

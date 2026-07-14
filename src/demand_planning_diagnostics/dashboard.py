"""
dashboard.py — the self-contained HTML diagnostic control tower.

`build_context(...)` assembles the exact JSON-serializable dict the
dashboard's `<script>const DATA = {...}</script>` blob embeds: KPI tiles,
the per-SKU segmentation (for the ADI-vs-CV² scatter), the FVA stairstep
at every aggregation level, a per-segment accuracy/FVA summary table, and
the ranked "worst manual overrides" list — the SKUs where the human
consensus step made the forecast measurably worse.

`render_dashboard(context, out_path)` renders a single, zero-CDN
`output/dashboard.html` — inline CSS (dual theme), vanilla JS, inline SVG.
The context JSON is embedded once as `const DATA = {...}` (the
`__DATA_JSON__` sentinel technique — not `str.format`, so every literal
`{ }` in the CSS/JS stays literal) and every section is drawn client-side
by a small pure JS function.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import ForecastLayer, Kpi, Segment, jsonable

_SEGMENT_ORDER = [Segment.SMOOTH, Segment.ERRATIC, Segment.INTERMITTENT, Segment.LUMPY]


def _segmentation_context(catalog, assignments) -> list[dict]:
    sku_by_id = {s.id: s for s in catalog.skus}
    points = []
    for a in assignments:
        sku = sku_by_id[a.sku_id]
        points.append(
            {
                "sku_id": a.sku_id,
                "name": sku.name,
                "category": sku.category.value,
                "true_archetype": sku.archetype.value,
                "computed_segment": a.segment.value,
                "recovered": sku.archetype == a.segment,
                "adi": a.adi if a.adi != float("inf") else None,
                "cv2": a.cv2,
                "volume_share": a.volume_share,
            }
        )
    return points


def _segment_summary_context(segment_fva_results) -> list[dict]:
    """One row per segment: WMAPE at each layer + both FVA steps, derived
    from the already-computed segment-level FvaResult rows (no
    recomputation — same numbers the console table and kpi.py agree on)."""
    by_segment: dict[str, dict] = {}
    for r in segment_fva_results:
        row = by_segment.setdefault(
            r.key,
            {"segment": r.key, "wmape_naive": None, "wmape_stat": None, "wmape_consensus": None,
             "fva_stat": None, "fva_stat_pct": None, "fva_consensus": None, "fva_consensus_pct": None},
        )
        if r.from_layer == ForecastLayer.NAIVE and r.to_layer == ForecastLayer.STATISTICAL:
            row["wmape_naive"] = r.wmape_from
            row["wmape_stat"] = r.wmape_to
            row["fva_stat"] = r.fva
            row["fva_stat_pct"] = r.fva_pct
        elif r.from_layer == ForecastLayer.STATISTICAL and r.to_layer == ForecastLayer.CONSENSUS:
            row["wmape_stat"] = r.wmape_from
            row["wmape_consensus"] = r.wmape_to
            row["fva_consensus"] = r.fva
            row["fva_consensus_pct"] = r.fva_pct
    order = {s.value: i for i, s in enumerate(_SEGMENT_ORDER)}
    return sorted(by_segment.values(), key=lambda row: order.get(row["segment"], 99))


def _worst_overrides_context(worst_overrides, catalog, assignments, limit: int = 15) -> list[dict]:
    sku_by_id = {s.id: s for s in catalog.skus}
    segment_by_id = {a.sku_id: a.segment.value for a in assignments}
    out = []
    for r in worst_overrides[:limit]:
        sku = sku_by_id[r.key]
        out.append(
            {
                "sku_id": r.key,
                "name": sku.name,
                "category": sku.category.value,
                "segment": segment_by_id.get(r.key, "unknown"),
                "wmape_stat": r.wmape_from,
                "wmape_consensus": r.wmape_to,
                "fva": r.fva,
                "fva_pct": r.fva_pct,
            }
        )
    return out


def build_context(
    catalog,
    history,
    assignments: list,
    segment_recovery_rate: float,
    fva_results: list,
    worst_overrides: list,
    kpis: dict[str, Kpi],
    generated_at: str,
) -> dict:
    """Assemble everything the dashboard needs into one JSON-serializable
    dict — the contract between the engine and the renderer, designed so
    the renderer never recomputes anything, only formats what's here."""
    overall_fva = [r for r in fva_results if r.level == "overall"]
    segment_fva = [r for r in fva_results if r.level == "segment"]

    return {
        "generated_at": generated_at,
        "company": catalog.company,
        "kpis": {key: jsonable(kpi) for key, kpi in kpis.items()},
        "segmentation": _segmentation_context(catalog, assignments),
        "segment_recovery_rate": round(segment_recovery_rate * 100.0, 1),
        "overall_fva": [jsonable(r) for r in overall_fva],
        "segment_summary": _segment_summary_context(segment_fva),
        "worst_overrides": _worst_overrides_context(worst_overrides, catalog, assignments),
        "n_skus": len(catalog.skus),
        "n_weeks": len({r.week for r in history.records}),
    }


# --------------------------------------------------------------------------
# The dashboard template. Built with a __DATA_JSON__ sentinel (not str.format)
# so every literal { } in the CSS/JS stays literal. The context JSON is
# embedded once; </ is escaped to <\/ so an embedded string can never close
# the <script> element early.
# --------------------------------------------------------------------------

_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Demand Planning Diagnostics — Northwind Foods</title>
<style>
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
    --good:#0ca30c; --warn:#fab219; --serious:#ec835a; --critical:#d03b3b;
  }
  @media (prefers-color-scheme: light) {
    :root:not([data-theme]) {
      --page:#f9f9f7; --surface:#fcfcfb; --surface-2:#f0efec;
      --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
      --grid:#e1e0d9; --axis:#c3c2b7; --ring:rgba(11,11,11,.10);
      --s1:#2a78d6; --s2:#1baf7a; --s3:#eda100; --s4:#008300;
      --s5:#4a3aa7; --s6:#e34948; --s7:#e87ba4; --s8:#eb6834;
    }
  }

  * { box-sizing:border-box; }
  html, body { margin:0; padding:0; }
  body {
    background:var(--page); color:var(--ink-2);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    font-size:14px; line-height:1.45;
    -webkit-font-smoothing:antialiased;
  }
  .wrap { max-width:1280px; margin:0 auto; padding:24px; }
  .num { font-variant-numeric: tabular-nums; }

  header.top {
    display:flex; align-items:center; gap:16px;
    padding-bottom:20px; margin-bottom:24px;
    border-bottom:1px solid var(--ring);
  }
  .brand { display:flex; align-items:center; gap:12px; }
  .brand svg { display:block; }
  .brand h1 { margin:0; font-size:19px; font-weight:700; color:var(--ink); letter-spacing:-.01em; display:flex; align-items:center; gap:8px; }
  .brand .sub { margin:2px 0 0; font-size:12px; color:var(--muted); }
  .brand .demo { font-size:9px; font-weight:700; letter-spacing:.1em; color:var(--muted); border:1px solid var(--ring); border-radius:20px; padding:2px 8px; position:relative; top:-1px; }
  .top .spacer { flex:1; }
  .stamp { font-size:12px; color:var(--muted); text-align:right; }
  .stamp b { color:var(--ink-2); font-weight:600; }
  .themebtn {
    display:flex; align-items:center; justify-content:center;
    width:38px; height:38px; border-radius:9px;
    background:var(--surface); border:1px solid var(--ring);
    color:var(--ink-2); cursor:pointer; padding:0;
  }
  .themebtn:hover { background:var(--surface-2); color:var(--ink); }
  .themebtn .moon { display:none; }
  :root[data-theme="dark"] .themebtn .sun { display:none; }
  :root[data-theme="dark"] .themebtn .moon { display:block; }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme]) .themebtn .sun { display:none; }
    :root:not([data-theme]) .themebtn .moon { display:block; }
  }

  .kpis { display:grid; grid-template-columns:repeat(auto-fit, minmax(170px,1fr)); gap:16px; margin-bottom:24px; }
  .tile { background:var(--surface); border:1px solid var(--ring); border-radius:10px; padding:16px; transition:border-color .15s; }
  .tile:hover { border-color:color-mix(in srgb, var(--s1) 35%, var(--ring)); }
  .tile .label { font-size:11px; font-weight:600; letter-spacing:.06em; text-transform:uppercase; color:var(--muted); }
  .tile .value { font-size:30px; font-weight:700; color:var(--ink); margin:8px 0 4px; line-height:1.05; }
  .tile .value .unit { font-size:15px; font-weight:600; color:var(--ink-2); margin-left:2px; }
  .tile .ctx { font-size:12px; color:var(--muted); }
  .tile.neg .value { color:var(--critical); }
  .tile.pos .value { color:var(--good); }

  .card { background:var(--surface); border:1px solid var(--ring); border-radius:12px; padding:20px; margin-bottom:24px; }
  .kicker { font-size:12px; font-weight:600; letter-spacing:.08em; text-transform:uppercase; color:var(--muted); }
  .card h2 { margin:4px 0 0; font-size:16px; font-weight:600; color:var(--ink); }
  .card .head { display:flex; align-items:flex-end; gap:16px; margin-bottom:16px; flex-wrap:wrap; }
  .card .head .note { font-size:12px; color:var(--muted); margin-left:auto; }
  .card p.desc { font-size:12px; color:var(--muted); margin:4px 0 16px; max-width:760px; }

  .legendrow { display:flex; flex-wrap:wrap; gap:14px; margin-bottom:12px; }
  .legendrow .item { display:flex; align-items:center; gap:6px; font-size:12px; color:var(--ink-2); }
  .legendrow .sw { width:10px; height:10px; border-radius:50%; display:inline-block; }

  .chartwrap { position:relative; overflow-x:auto; }
  .chartwrap svg { display:block; width:100%; height:auto; min-width:560px; }

  table { width:100%; border-collapse:collapse; font-size:13px; }
  thead th { text-align:left; font-size:11px; font-weight:600; letter-spacing:.04em; text-transform:uppercase; color:var(--muted); padding:0 10px 10px; border-bottom:1px solid var(--ring); white-space:nowrap; }
  thead th.n, tbody td.n { text-align:right; }
  tbody td { padding:10px; border-bottom:1px solid var(--grid); color:var(--ink-2); vertical-align:top; }
  tbody tr:hover td { background:var(--surface-2); }
  tbody td.n { font-variant-numeric:tabular-nums; }
  tbody td.pos { color:var(--good); font-weight:600; }
  tbody td.neg { color:var(--critical); font-weight:600; }
  .segbadge { display:inline-flex; align-items:center; gap:6px; white-space:nowrap; }
  .segbadge .dot { width:9px; height:9px; border-radius:50%; flex:none; }

  footer.foot { border-top:1px solid var(--ring); padding-top:16px; margin-top:8px; font-size:12px; color:var(--muted); }
  footer.foot b { color:var(--ink-2); font-weight:600; }

  #tip { position:fixed; z-index:50; pointer-events:none; background:var(--surface); border:1px solid var(--ring); border-radius:9px; padding:9px 11px; font-size:12px; color:var(--ink-2); box-shadow:0 6px 24px rgba(0,0,0,.28); max-width:260px; opacity:0; transition:opacity .08s; }
  #tip .tt { color:var(--ink); font-weight:600; margin-bottom:3px; }
  #tip .kv { display:flex; justify-content:space-between; gap:14px; }
  #tip .kv b { color:var(--ink); font-weight:600; font-variant-numeric:tabular-nums; }
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div class="brand">
      <svg width="34" height="34" viewBox="0 0 34 34" fill="none" aria-hidden="true">
        <rect x="4" y="18" width="5" height="12" rx="1" style="fill:var(--s1)"/>
        <rect x="11" y="12" width="5" height="18" rx="1" style="fill:var(--s2)"/>
        <rect x="18" y="6" width="5" height="24" rx="1" style="fill:var(--s3)"/>
        <rect x="25" y="15" width="5" height="15" rx="1" style="fill:var(--s6)"/>
      </svg>
      <div>
        <h1>Demand Planning Diagnostics <span class="demo">DEMO DATA</span></h1>
        <p class="sub" id="subtitle"></p>
      </div>
    </div>
    <div class="spacer"></div>
    <div class="stamp">Generated<br><b id="genstamp"></b></div>
    <button class="themebtn" id="themebtn" title="Toggle theme" aria-label="Toggle light/dark theme">
      <svg class="sun" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><circle cx="12" cy="12" r="4.5"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M19 5l-1.5 1.5M6.5 17.5L5 19"/></svg>
      <svg class="moon" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>
    </button>
  </header>

  <section class="kpis" id="kpis"></section>

  <section class="card">
    <div class="head"><div><div class="kicker">Demand Segmentation</div><h2>ADI vs CV² — Syntetos-Boylan-Croston Quadrants</h2></div>
      <div class="note" id="segnote"></div>
    </div>
    <p class="desc">Every SKU's full 104-week history reduced to two numbers: how often demand shows up (ADI) and how much it swings when it does (CV²). The quadrant a SKU lands in is a genuine, falsifiable prediction about whether a forecasting model — not an inventory policy — is the right tool for that SKU.</p>
    <div class="legendrow" id="seglegend"></div>
    <div class="chartwrap"><svg id="segscatter" viewBox="0 0 720 420"></svg></div>
  </section>

  <section class="card">
    <div class="head"><div><div class="kicker">Forecast Value Added</div><h2>Portfolio Stairstep — Naive &rarr; Statistical &rarr; Consensus</h2></div></div>
    <p class="desc">Forecast Value Added (Gilliland, 2010) asks whether each step in the forecasting process earns its keep: is WMAPE (volume-weighted MAPE) actually lower after the step than before it? A positive bar means the step helped; a negative bar means it should stop.</p>
    <div class="chartwrap"><svg id="fvachart" viewBox="0 0 640 220"></svg></div>
  </section>

  <section class="card">
    <div class="head"><div><div class="kicker">Accuracy by Segment</div><h2>WMAPE and FVA, Pooled per Quadrant</h2></div></div>
    <table id="segtable"><thead></thead><tbody></tbody></table>
  </section>

  <section class="card">
    <div class="head"><div><div class="kicker">The Money Finding</div><h2>Where the Consensus Override Hurt Most</h2></div>
      <div class="note" id="worstnote"></div>
    </div>
    <p class="desc">SKUs where the human/consensus adjustment made WMAPE worse than the statistical forecast alone — ranked by the size of the damage. A portfolio can show positive net FVA while still hurting a large minority of SKUs; this table is where that minority lives.</p>
    <table id="worsttable"><thead></thead><tbody></tbody></table>
  </section>

  <footer class="foot">
    <span>Synthetic Northwind Foods dataset, seeded and reproducible; FVA framework: Gilliland (2010) / SAS FVA; segmentation: Syntetos-Boylan-Croston (2005); MASE: Hyndman &amp; Koehler (2006).</span><br>
    <b>Built with Demand Planning Diagnostics</b> · see <b>docs/</b> for methodology.
  </footer>
</div>

<div id="tip"></div>

<script>
const DATA = __DATA_JSON__;

const $ = (s, r) => (r||document).querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const SEG_COLOR = { smooth:'var(--good)', erratic:'var(--warn)', intermittent:'var(--s1)', lumpy:'var(--critical)' };
const SEG_LABEL = { smooth:'Smooth', erratic:'Erratic', intermittent:'Intermittent', lumpy:'Lumpy' };
const LAYER_LABEL = { naive:'Naive', statistical:'Statistical', consensus:'Consensus' };

function fmtPct(v, d){ d = d===undefined?1:d; return (Math.round(v*Math.pow(10,d))/Math.pow(10,d)).toFixed(d); }
function fmtNum(v, d){ d = d===undefined?2:d; return (Math.round(v*Math.pow(10,d))/Math.pow(10,d)).toLocaleString(undefined,{minimumFractionDigits:d,maximumFractionDigits:d}); }

const tip = $('#tip');
function showTip(html, x, y){
  tip.innerHTML = html;
  tip.style.opacity = '1';
  const pad = 14, w = tip.offsetWidth, h = tip.offsetHeight;
  let lx = x + pad, ly = y + pad;
  if (lx + w > window.innerWidth - 8) lx = x - w - pad;
  if (ly + h > window.innerHeight - 8) ly = y - h - pad;
  tip.style.left = Math.max(8, lx) + 'px';
  tip.style.top  = Math.max(8, ly) + 'px';
}
function hideTip(){ tip.style.opacity = '0'; }

function renderHeader(){
  $('#subtitle').textContent = DATA.company + ' · ' + DATA.n_skus + ' SKUs · ' + DATA.n_weeks + ' weeks of synthetic history';
  let stamp = DATA.generated_at;
  try {
    const d = new Date(DATA.generated_at);
    if (!isNaN(d)) stamp = d.toLocaleString(undefined, {year:'numeric',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'}) + ' UTC';
  } catch(e){}
  $('#genstamp').textContent = stamp;
}

function kpiVal(k){
  const u = k.unit;
  if (u === '%') return fmtPct(k.value) + '<span class="unit">%</span>';
  if (u === 'pp') return (k.value>=0?'+':'') + fmtPct(k.value) + '<span class="unit">pp</span>';
  if (u === 'ratio') return fmtNum(k.value, 3);
  if (u === 'score') return fmtNum(k.value, 2);
  return fmtNum(k.value, 2) + (u ? '<span class="unit">'+esc(u)+'</span>' : '');
}
function renderKpis(){
  const K = DATA.kpis;
  const order = ['wmape_consensus','fva_stat','fva_consensus','pct_skus_overrides_hurt','forecastable_share','bias_consensus','tracking_signal_consensus','mase_consensus'];
  const host = $('#kpis'); host.innerHTML = '';
  order.forEach(key => {
    const k = K[key]; if (!k) return;
    const tile = document.createElement('div');
    let cls = 'tile';
    if ((key === 'fva_stat' || key === 'fva_consensus') && k.value < 0) cls += ' neg';
    else if ((key === 'fva_stat' || key === 'fva_consensus') && k.value > 0) cls += ' pos';
    tile.className = cls;
    tile.innerHTML = '<div class="label">'+esc(k.label)+'</div><div class="value num">'+kpiVal(k)+'</div><div class="ctx">'+esc(k.context||'')+'</div>';
    host.appendChild(tile);
  });
}

function renderSegLegend(){
  const host = $('#seglegend'); host.innerHTML = '';
  Object.keys(SEG_LABEL).forEach(seg => {
    host.insertAdjacentHTML('beforeend', '<span class="item"><span class="sw" style="background:'+SEG_COLOR[seg]+'"></span>'+SEG_LABEL[seg]+'</span>');
  });
  host.insertAdjacentHTML('beforeend', '<span class="item">bubble size = portfolio volume share</span>');
}

function renderSegScatter(){
  const svg = $('#segscatter');
  const pts = DATA.segmentation;
  const W = 720, H = 420, mL = 56, mR = 20, mT = 16, mB = 40;
  const pw = W - mL - mR, ph = H - mT - mB;

  const adiVals = pts.map(p => p.adi === null ? 1 : p.adi);
  const cv2Vals = pts.map(p => p.cv2);
  const maxAdi = Math.max(4, ...adiVals) * 1.05;
  const maxCv2 = Math.max(1.2, ...cv2Vals) * 1.05;
  const xOf = adi => mL + (adi / maxAdi) * pw;
  const yOf = cv2 => mT + ph - (cv2 / maxCv2) * ph;
  const ADI_CUT = 1.32, CV2_CUT = 0.49;

  let g = '';
  for (let i = 0; i <= 4; i++){
    const av = maxAdi * i / 4;
    g += '<line x1="'+xOf(av)+'" y1="'+mT+'" x2="'+xOf(av)+'" y2="'+(mT+ph)+'" style="stroke:var(--grid)" stroke-width="1"/>';
    g += '<text x="'+xOf(av)+'" y="'+(mT+ph+16)+'" text-anchor="middle" class="num" style="fill:var(--muted)" font-size="10">'+av.toFixed(1)+'</text>';
  }
  for (let i = 0; i <= 4; i++){
    const cv = maxCv2 * i / 4;
    g += '<line x1="'+mL+'" y1="'+yOf(cv)+'" x2="'+(mL+pw)+'" y2="'+yOf(cv)+'" style="stroke:var(--grid)" stroke-width="1"/>';
    g += '<text x="'+(mL-8)+'" y="'+(yOf(cv)+3.5)+'" text-anchor="end" class="num" style="fill:var(--muted)" font-size="10">'+cv.toFixed(2)+'</text>';
  }
  // cutoff lines
  g += '<line x1="'+xOf(ADI_CUT)+'" y1="'+mT+'" x2="'+xOf(ADI_CUT)+'" y2="'+(mT+ph)+'" style="stroke:var(--axis)" stroke-width="1.4" stroke-dasharray="5 4"/>';
  g += '<line x1="'+mL+'" y1="'+yOf(CV2_CUT)+'" x2="'+(mL+pw)+'" y2="'+yOf(CV2_CUT)+'" style="stroke:var(--axis)" stroke-width="1.4" stroke-dasharray="5 4"/>';
  g += '<text x="'+(mL+pw/2)+'" y="'+(H-4)+'" text-anchor="middle" style="fill:var(--muted)" font-size="10">ADI (average inter-demand interval)</text>';
  g += '<text x="14" y="'+(mT+ph/2)+'" text-anchor="middle" transform="rotate(-90 14 '+(mT+ph/2)+')" style="fill:var(--muted)" font-size="10">CV² (of nonzero demand)</text>';

  pts.forEach(p => {
    const adi = p.adi === null ? maxAdi * 0.98 : Math.min(p.adi, maxAdi);
    const cv2 = Math.min(p.cv2, maxCv2);
    const r = 4 + Math.sqrt(p.volume_share) * 60;
    const fill = SEG_COLOR[p.computed_segment] || 'var(--muted)';
    const strokeW = p.recovered ? 1.4 : 2.6;
    const strokeC = p.recovered ? 'var(--surface)' : 'var(--critical)';
    g += '<circle class="pt" data-id="'+p.sku_id+'" cx="'+xOf(adi).toFixed(1)+'" cy="'+yOf(cv2).toFixed(1)+'" r="'+r.toFixed(1)+'" style="fill:'+fill+';opacity:.78;stroke:'+strokeC+';stroke-width:'+strokeW+'" />';
  });

  svg.innerHTML = g;
  const byId = {}; pts.forEach(p => byId[p.sku_id] = p);
  svg.querySelectorAll('.pt').forEach(el => {
    const p = byId[el.dataset.id];
    const move = e => {
      let html = '<div class="tt">'+esc(p.name)+'</div>';
      html += '<div class="kv"><span>SKU</span><b>'+esc(p.sku_id)+'</b></div>';
      html += '<div class="kv"><span>Computed segment</span><b>'+SEG_LABEL[p.computed_segment]+'</b></div>';
      html += '<div class="kv"><span>True archetype</span><b>'+SEG_LABEL[p.true_archetype]+'</b></div>';
      html += '<div class="kv"><span>ADI</span><b>'+(p.adi===null?'&infin;':fmtNum(p.adi))+'</b></div>';
      html += '<div class="kv"><span>CV&sup2;</span><b>'+fmtNum(p.cv2)+'</b></div>';
      html += '<div class="kv"><span>Volume share</span><b>'+fmtPct(p.volume_share*100)+'%</b></div>';
      showTip(html, e.clientX, e.clientY);
    };
    el.addEventListener('mousemove', move);
    el.addEventListener('mouseleave', hideTip);
  });
  $('#segnote').textContent = 'segmentation recovers the true generating archetype for ' + DATA.segment_recovery_rate + '% of SKUs';
}

function renderFvaChart(){
  const svg = $('#fvachart');
  const rows = DATA.overall_fva;
  const W = 640, H = 220, mL = 140, mR = 60, mT = 16, mB = 30;
  const pw = W - mL - mR, ph = H - mT - mB;
  const rowH = ph / rows.length;
  const maxAbs = Math.max(1, ...rows.map(r => Math.abs(r.fva)));
  const xMid = mL + pw/2;
  const xOf = v => xMid + (v / maxAbs) * (pw/2 - 4);

  let g = '<line x1="'+xMid+'" y1="'+mT+'" x2="'+xMid+'" y2="'+(mT+ph)+'" style="stroke:var(--axis)" stroke-width="1.2"/>';
  rows.forEach((r, i) => {
    const cy = mT + rowH*i + rowH/2;
    const barH = Math.min(28, rowH*0.55);
    const x0 = Math.min(xMid, xOf(r.fva)), x1 = Math.max(xMid, xOf(r.fva));
    const color = r.fva >= 0 ? 'var(--good)' : 'var(--critical)';
    g += '<rect class="fvabar" data-i="'+i+'" x="'+x0+'" y="'+(cy-barH/2)+'" width="'+Math.max(1,x1-x0)+'" height="'+barH+'" rx="3" style="fill:'+color+';opacity:.85"/>';
    const label = LAYER_LABEL[r.from_layer] + ' → ' + LAYER_LABEL[r.to_layer];
    g += '<text x="'+(mL-12)+'" y="'+(cy+4)+'" text-anchor="end" style="fill:var(--ink-2)" font-size="12">'+esc(label)+'</text>';
    const valX = r.fva >= 0 ? x1+8 : x0-8;
    const anchor = r.fva >= 0 ? 'start' : 'end';
    g += '<text x="'+valX+'" y="'+(cy+4)+'" text-anchor="'+anchor+'" class="num" style="fill:'+color+'" font-size="12" font-weight="600">'+(r.fva>=0?'+':'')+fmtNum(r.fva)+' pp</text>';
  });
  svg.innerHTML = g;
  svg.querySelectorAll('.fvabar').forEach(el => {
    const r = rows[+el.dataset.i];
    const move = e => {
      const html = '<div class="tt">'+LAYER_LABEL[r.from_layer]+' → '+LAYER_LABEL[r.to_layer]+'</div>' +
        '<div class="kv"><span>WMAPE before</span><b>'+fmtNum(r.wmape_from)+'%</b></div>' +
        '<div class="kv"><span>WMAPE after</span><b>'+fmtNum(r.wmape_to)+'%</b></div>' +
        '<div class="kv"><span>FVA</span><b>'+(r.fva>=0?'+':'')+fmtNum(r.fva)+' pp</b></div>';
      showTip(html, e.clientX, e.clientY);
    };
    el.addEventListener('mousemove', move);
    el.addEventListener('mouseleave', hideTip);
  });
}

function renderSegTable(){
  const thead = $('#segtable thead'), tbody = $('#segtable tbody');
  thead.innerHTML = '<tr><th>Segment</th><th class="n">WMAPE Naive</th><th class="n">WMAPE Stat</th><th class="n">WMAPE Consensus</th><th class="n">FVA: Stat vs Naive</th><th class="n">FVA: Consensus vs Stat</th></tr>';
  tbody.innerHTML = DATA.segment_summary.map(r => {
    const cls1 = r.fva_stat >= 0 ? 'pos' : 'neg';
    const cls2 = r.fva_consensus >= 0 ? 'pos' : 'neg';
    return '<tr>' +
      '<td><span class="segbadge"><span class="dot" style="background:'+SEG_COLOR[r.segment]+'"></span>'+SEG_LABEL[r.segment]+'</span></td>' +
      '<td class="n">'+fmtNum(r.wmape_naive)+'%</td>' +
      '<td class="n">'+fmtNum(r.wmape_stat)+'%</td>' +
      '<td class="n">'+fmtNum(r.wmape_consensus)+'%</td>' +
      '<td class="n '+cls1+'">'+(r.fva_stat>=0?'+':'')+fmtNum(r.fva_stat)+' pp</td>' +
      '<td class="n '+cls2+'">'+(r.fva_consensus>=0?'+':'')+fmtNum(r.fva_consensus)+' pp</td>' +
      '</tr>';
  }).join('');
}

function renderWorstTable(){
  const thead = $('#worsttable thead'), tbody = $('#worsttable tbody');
  thead.innerHTML = '<tr><th>SKU</th><th>Segment</th><th class="n">WMAPE Stat</th><th class="n">WMAPE Consensus</th><th class="n">FVA</th></tr>';
  const rows = DATA.worst_overrides;
  if (!rows.length){
    tbody.innerHTML = '<tr><td colspan="5" style="color:var(--muted)">No SKUs where the consensus override hurt accuracy.</td></tr>';
  } else {
    tbody.innerHTML = rows.map(r => '<tr>' +
      '<td style="color:var(--ink)">'+esc(r.name)+'<br><span style="font-size:11px;color:var(--muted)">'+esc(r.sku_id)+'</span></td>' +
      '<td><span class="segbadge"><span class="dot" style="background:'+SEG_COLOR[r.segment]+'"></span>'+SEG_LABEL[r.segment]+'</span></td>' +
      '<td class="n">'+fmtNum(r.wmape_stat)+'%</td>' +
      '<td class="n">'+fmtNum(r.wmape_consensus)+'%</td>' +
      '<td class="n neg">'+fmtNum(r.fva)+' pp</td>' +
      '</tr>').join('');
  }
  $('#worstnote').textContent = rows.length + ' of ' + DATA.n_skus + ' SKUs shown';
}

function applyStoredTheme(){
  const t = localStorage.getItem('dpd-theme');
  if (t === 'light' || t === 'dark') document.documentElement.setAttribute('data-theme', t);
}
function toggleTheme(){
  const cur = document.documentElement.getAttribute('data-theme');
  let next;
  if (cur) next = cur === 'dark' ? 'light' : 'dark';
  else next = matchMedia('(prefers-color-scheme: dark)').matches ? 'light' : 'dark';
  document.documentElement.setAttribute('data-theme', next);
  localStorage.setItem('dpd-theme', next);
}

applyStoredTheme();
$('#themebtn').addEventListener('click', toggleTheme);
renderHeader();
renderKpis();
renderSegLegend();
renderSegScatter();
renderFvaChart();
renderSegTable();
renderWorstTable();
</script>
</body>
</html>
"""


def render_dashboard(context: dict, out_path: Path | str) -> None:
    """Render the self-contained diagnostic HTML, embedding `context` once."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data_json = json.dumps(context, ensure_ascii=False).replace("</", "<\\/")
    html_doc = _TEMPLATE.replace("__DATA_JSON__", data_json)
    out_path.write_text(html_doc, encoding="utf-8")

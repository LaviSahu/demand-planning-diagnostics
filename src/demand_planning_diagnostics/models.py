"""
models.py — the shared vocabulary of the demand-planning diagnostic engine.

A forecasting review only works if everyone (demand planners, S&OP leads,
the analyst writing the override) agrees on what a "SKU" is, what a
"segment" is, and what a "forecast layer" means. This module is that
shared vocabulary, expressed as typed dataclasses instead of prose:

- Catalog primitives: `Sku`, `SkuCatalog` — the product master. Every SKU
  carries a `Category` (merchandising grouping) and a *true* `Segment`
  archetype used only to generate `datagen.py`'s synthetic history — in a
  real deployment this field would not exist, since the whole point of
  `segment.py` is to *discover* the segment from observed demand, not read
  it off a label. Keeping it here lets the dashboard show "does the
  computed segmentation recover the pattern we built in?" as a built-in
  sanity check.
- Demand primitives: `WeekRecord` — one SKU-week: the actual demand plus
  the three layered forecasts (`naive_fcst`, `stat_fcst`, `consensus_fcst`)
  produced for that week. The three forecast fields are `None` for the
  52-week burn-in window (`segment.py`/`accuracy.py` need trailing history
  before a naive or statistical forecast is even defined) — a `None` here
  is not missing data, it is an honest "no forecast was possible yet."
- Segmentation primitives: `SegmentAssignment` — what `segment.py` turns a
  SKU's full demand history into: ADI, CV², and the assigned quadrant.
- Accuracy/FVA primitives: `AccuracyMetrics`, `FvaResult` — what
  `accuracy.py` and `fva.py` compute per SKU, per segment, and for the
  whole portfolio.
- `Kpi` — the roll-up tile shape shared by the CLI's console summary and
  the dashboard's KPI row.

Everything here is a plain `@dataclass`: no behavior beyond a couple of
trivial lookup helpers on `SkuCatalog` (mirroring the network-lookup
pattern used elsewhere in this house style). Behavior lives in the modules
named after the verbs (generate, segment, score, add-value-or-not).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


# --------------------------------------------------------------------------
# Enumerations — the controlled vocabularies used across the engine.
# --------------------------------------------------------------------------


class Category(str, Enum):
    """Northwind Foods' three merchandising categories."""

    BEVERAGES = "beverages"
    SNACKS = "snacks"
    HOUSEHOLD = "household"


class Segment(str, Enum):
    """
    The four Syntetos-Boylan-Croston demand-pattern quadrants, keyed by
    ADI (Average inter-Demand Interval) and CV² (squared coefficient of
    variation of nonzero demand). See `segment.py` for the classifier and
    docs/02-demand-segmentation.md for the citation and canonical cutoffs.
    """

    SMOOTH = "smooth"
    ERRATIC = "erratic"
    INTERMITTENT = "intermittent"
    LUMPY = "lumpy"


class ForecastLayer(str, Enum):
    """
    The three-layer forecasting stack this repo evaluates, cheapest/least
    human-touched first: a naive statistical baseline, a hand-rolled
    statistical model, and the human-adjusted consensus number that
    actually ships to the supply plan.
    """

    NAIVE = "naive"
    STATISTICAL = "statistical"
    CONSENSUS = "consensus"


# --------------------------------------------------------------------------
# Catalog primitives
# --------------------------------------------------------------------------


@dataclass
class Sku:
    """
    One stock-keeping unit in the Northwind Foods portfolio.

    `archetype` is the *true* demand pattern used to generate this SKU's
    synthetic history in `datagen.py` — see the module docstring above for
    why this is a validation label, not an input to the segmentation
    engine. `promo_eligible` marks the subset of SKUs that ever receive a
    planned promotional uplift (see `datagen.py`); only smooth/erratic
    SKUs are promo-eligible in this dataset, matching the real-world
    pattern that promotional calendars are built around a company's
    higher-volume, more-forecastable core items, not its long tail.
    """

    id: str
    name: str
    category: Category
    archetype: Segment
    revenue_per_unit: float
    promo_eligible: bool = False


@dataclass
class SkuCatalog:
    """The full Northwind Foods product master used by one demo run."""

    company: str
    skus: list[Sku]

    def sku(self, sku_id: str) -> Sku:
        for s in self.skus:
            if s.id == sku_id:
                return s
        raise KeyError(f"unknown sku id: {sku_id!r}")

    def sku_ids(self) -> list[str]:
        return [s.id for s in self.skus]


# --------------------------------------------------------------------------
# Demand primitives
# --------------------------------------------------------------------------


@dataclass
class WeekRecord:
    """
    One SKU-week of history: the realized `actual` demand (units) plus the
    three layered forecasts for that same week (`None` during the 52-week
    burn-in, before any forecast is definable — see `datagen.py`).

    `is_promo` flags weeks a planned promotional uplift was applied to
    `actual` (only possible for `promo_eligible` SKUs); it is the input
    the synthetic "analyst override" in `datagen.py` reacts to when
    building `consensus_fcst`.
    """

    sku_id: str
    week: int
    actual: float
    naive_fcst: Optional[float]
    stat_fcst: Optional[float]
    consensus_fcst: Optional[float]
    is_promo: bool = False


@dataclass
class DemandHistory:
    """The full 104-week synthetic history: every SKU, every week."""

    records: list[WeekRecord] = field(default_factory=list)

    def for_sku(self, sku_id: str) -> list[WeekRecord]:
        """A single SKU's records, sorted by week — the unit every engine
        module (segment/accuracy/fva) actually operates on."""
        return sorted((r for r in self.records if r.sku_id == sku_id), key=lambda r: r.week)

    def sku_ids(self) -> list[str]:
        seen: dict[str, None] = {}
        for r in self.records:
            seen.setdefault(r.sku_id, None)
        return list(seen)


# --------------------------------------------------------------------------
# Segmentation primitives
# --------------------------------------------------------------------------


@dataclass
class SegmentAssignment:
    """
    What `segment.py` computes for one SKU from its full 104-week actual
    history: ADI, CV², and the quadrant those two numbers land in.

    `volume_share` is that SKU's fraction of total portfolio unit volume
    (over the full history) — the weight `kpi.forecastable_share` and the
    dashboard's segmentation scatter use so a single high-volume SKU counts
    for more than a trickle-selling long-tail one.
    """

    sku_id: str
    adi: float
    cv2: float
    segment: Segment
    volume_share: float


# --------------------------------------------------------------------------
# Accuracy / FVA primitives
# --------------------------------------------------------------------------


@dataclass
class AccuracyMetrics:
    """
    Forecast-accuracy scorecard for one (SKU, layer) pair, computed over
    the 52-week evaluation window (weeks 53-104 — see `accuracy.py`).

    `mape` and `tracking_signal` are `None` when undefined for that SKU
    (MAPE divides by actual, which is 0 in some intermittent/lumpy weeks
    — those weeks are excluded rather than faked; if *every* eval week has
    zero actual, MAPE is undefined entirely). `mase` is `None` only in the
    pathological case where the in-sample naive benchmark itself has zero
    scale (a constant-zero burn-in window), which does not occur in this
    dataset but is guarded against rather than assumed away.
    """

    sku_id: str
    layer: ForecastLayer
    mape: Optional[float]
    wmape: float
    bias: float
    tracking_signal: Optional[float]
    mase: Optional[float]


@dataclass
class FvaResult:
    """
    One Forecast Value Added comparison: how WMAPE changed moving from
    `from_layer` to `to_layer`, at a given `level` of aggregation
    (`"sku"`, `"segment"`, or `"overall"`; `key` is the SKU id, the
    `Segment` value, or `"overall"` respectively).

    `fva` is `wmape_from - wmape_to` — **positive means the later layer is
    more accurate** (it added value); negative means it made the forecast
    worse. `fva_pct` expresses that same delta as a percentage of the
    starting WMAPE (0 if `wmape_from` is 0, to avoid a divide-by-zero on a
    perfect-already baseline).
    """

    level: str
    key: str
    from_layer: ForecastLayer
    to_layer: ForecastLayer
    wmape_from: float
    wmape_to: float
    fva: float
    fva_pct: float


@dataclass
class Kpi:
    """One roll-up tile: the shape shared by the CLI summary table and the
    dashboard's KPI row (see `kpi.py`)."""

    key: str
    label: str
    value: float
    unit: str
    context: str = ""


# --------------------------------------------------------------------------
# JSON helpers — shared by datagen.py / dashboard.py so the dashboard's
# embedded <script> DATA blob and output/*.json files use one consistent,
# dependency-free serialization convention.
# --------------------------------------------------------------------------


def jsonable(obj):
    """
    Recursively convert dataclasses / Enums / dicts / lists into plain
    JSON-serializable structures. Used instead of a library like
    `pydantic` to keep the project stdlib-only.
    """
    from dataclasses import fields, is_dataclass

    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: jsonable(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        return {k: jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [jsonable(v) for v in obj]
    return obj

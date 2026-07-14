"""
datagen.py — generates the synthetic Northwind Foods demand history.

Nothing in this repo is real. "Northwind Foods" is a fictional FMCG maker
invented for this demo; every number downstream of this module — every
ADI, every WMAPE, every dollar of Forecast Value Added — is arithmetic
over the weekly units this module writes to `data/`. The generator is
**seeded** (`DEFAULT_SEED`, `random.Random`) so a bare `make demo` on any
machine reproduces the identical 40-SKU, 104-week dataset byte-for-byte.

Two things this module has to get right for the rest of the pipeline to
say anything true:

1. **The four demand archetypes must actually land in the four SBC
   quadrants.** Each SKU is generated from one of four hand-tuned noise
   models (smooth / erratic / intermittent / lumpy — see
   `_ARCHETYPE_PARAMS`) chosen so that `segment.py`'s ADI/CV² classifier,
   run *blind* on the resulting actuals with no knowledge of which model
   produced them, recovers the intended quadrant for the large majority of
   SKUs. That recovery is asserted in `tests/test_segment.py` — it is the
   proof that the segmentation math works, not just that the labels agree
   with themselves.
2. **The three forecast layers must be genuinely, not cosmetically,
   different.** `naive_fcst` is a pure random-walk benchmark (seasonal
   for smooth/erratic, last-actual for intermittent/lumpy — see
   `_naive_forecast`). `stat_fcst` is a real, hand-rolled statistical
   model (`_stat_forecast_smooth_erratic` deseasonalizes then applies
   simple exponential smoothing; `_stat_forecast_intermittent_lumpy` uses
   a trailing moving average) that has no knowledge of the promotional
   calendar. `consensus_fcst` is `stat_fcst` plus a synthetic analyst
   override built from two real mechanisms that pull in opposite
   directions:
   - a **chase term** (`_CHASE_FACTOR`) — the planner nudges the number
     toward last week's actual deviation from the statistical forecast.
     This is a genuine, common override behavior, and because last week's
     deviation from a well-specified model is mostly noise, chasing it
     *adds* variance rather than removing it. The chase factor is small
     for smooth SKUs (where there is little noise to chase) and large for
     erratic/intermittent/lumpy SKUs (where there is a lot) — so this one
     mechanism alone is enough to make overrides costly exactly where the
     demand pattern is least forecastable.
   - a **promo term** (`_PROMO_OVERRIDE_GAIN`) — on `promo_eligible` SKUs
     in a known promotional week, the planner adds a fraction of the
     *planned* uplift (decided by marketing ahead of time, and therefore
     genuinely knowable) that `stat_fcst` cannot see, because it is fit
     purely on history. This is a real, value-adding override.
   Whether the net effect of these two mechanisms is FVA-positive or
   FVA-negative for a given SKU is not asserted anywhere in this module —
   it falls out of the two constant tables and the random draws, and
   `fva.py` measures it after the fact. See docs/05-methodology-and-citations.md
   for why this construction is the honest way to make the "overrides
   sometimes destroy value" finding real rather than scripted.
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

from .models import Category, DemandHistory, Segment, Sku, SkuCatalog, WeekRecord, jsonable

# --------------------------------------------------------------------------
# Dataset shape
# --------------------------------------------------------------------------

COMPANY = "Northwind Foods"
DEFAULT_SEED = 42
N_WEEKS = 104
BURN_IN_WEEKS = 52          # weeks 1-52: history only, no forecast is scored
EVAL_START_WEEK = 53        # weeks 53-104: the 52-week scored evaluation window
SES_ALPHA = 0.25             # smoothing constant for the deseasonalized SES stat model
MOVING_AVERAGE_WINDOW = 8    # trailing weeks used for the intermittent/lumpy stat model
SEASONAL_SMOOTHING_WINDOW = 7  # circular moving-average window used to smooth the raw
                                # burn-in seasonal index (see _stat_forecast_smooth_erratic) —
                                # burn-in supplies only one observation per week-of-year, so the
                                # raw ratio-to-mean is week-to-week noise, not just seasonality;
                                # this window separates the slow seasonal sinusoid from it.

SKUS_PER_ARCHETYPE = 10      # 4 archetypes x 10 = 40 SKUs total
ARCHETYPE_ORDER: list[Segment] = [Segment.SMOOTH, Segment.ERRATIC, Segment.INTERMITTENT, Segment.LUMPY]
CATEGORY_ORDER: list[Category] = [Category.BEVERAGES, Category.SNACKS, Category.HOUSEHOLD]

# Promotional calendar: 4 fixed weeks-of-year, applied in both years of
# history. Only promo_eligible SKUs (a subset of smooth/erratic) receive
# an uplift on these weeks.
PROMO_WEEKS_OF_YEAR: list[int] = [9, 22, 35, 48]
PROMO_ELIGIBLE_FRACTION = 0.5  # half of smooth SKUs and half of erratic SKUs carry a promo calendar

# Analyst-override behavior per archetype — see module docstring.
# Chase factor: how strongly the override reacts to last week's
# (actual - stat_fcst) deviation. Small where there's little noise to
# chase (smooth), large where there's a lot (lumpy).
_CHASE_FACTOR: dict[Segment, float] = {
    Segment.SMOOTH: 0.05,
    Segment.ERRATIC: 0.55,
    Segment.INTERMITTENT: 0.45,
    Segment.LUMPY: 1.00,
}
# Promo override gain: fraction of the *planned* promo uplift the override
# adds, on promo_eligible SKUs in a promo week only. Zero for archetypes
# that never carry a promo calendar in this dataset.
_PROMO_OVERRIDE_GAIN: dict[Segment, float] = {
    Segment.SMOOTH: 0.85,
    Segment.ERRATIC: 0.55,
    Segment.INTERMITTENT: 0.0,
    Segment.LUMPY: 0.0,
}

# Product names per category — enough distinct names for the largest
# per-category SKU count this dataset ever produces.
_PRODUCT_NAMES: dict[Category, list[str]] = {
    Category.BEVERAGES: [
        "Cold Brew Coffee 12oz", "Sparkling Lemon Water", "Orange Juice 1L",
        "Energy Drink Citrus", "Iced Green Tea", "Craft Root Beer",
        "Coconut Water 500ml", "Vanilla Protein Shake", "Blue Sports Drink",
        "Cranberry Juice Cocktail", "Whole Milk 1L", "Almond Milk Unsweetened",
        "Classic Cola 2L", "Ginger Ale 1.5L",
    ],
    Category.SNACKS: [
        "Sea Salt Potato Chips", "Cheddar Popcorn", "Original Trail Mix",
        "Pretzel Sticks", "Yellow Corn Tortilla Chips", "Honey Oat Granola Bars",
        "Cheese Crackers", "Chocolate Chip Cookies", "Brown Rice Cakes",
        "Original Beef Jerky", "Mixed Roasted Nuts", "Fruit Snacks Variety Pack",
        "Chili Lime Corn Chips", "Oatmeal Cookie Bites",
    ],
    Category.HOUSEHOLD: [
        "Paper Towels 6-Pack", "Lemon Dish Soap", "Laundry Detergent 100oz",
        "All-Purpose Cleaner Spray", "Trash Bags 13-Gallon", "Toilet Paper 12-Pack",
        "Glass Cleaner Spray", "Fabric Softener 92oz", "Multi-Surface Sponges 6-Pack",
        "Lavender Air Freshener", "Bleach 64oz", "Foaming Hand Soap Refill",
        "Aluminum Foil 75sqft", "Gallon Storage Bags",
    ],
}


@dataclass
class _SkuGenParams:
    """Internal generation parameters for one SKU — not part of the public
    `Sku` shape (a real deployment would not know these); kept local to
    this module so `models.py` stays a pure data-dictionary shape."""

    sku: Sku
    base_level: float          # mean weekly units in a "normal" week
    seasonal_amp: float        # 0 for archetypes with no seasonal component
    seasonal_phase: float
    noise_std_frac: float      # noise std as a fraction of base_level
    zero_prob: float           # 0 for smooth/erratic (never structurally zero)
    floor_frac: float          # minimum nonzero draw, as a fraction of base_level


# --------------------------------------------------------------------------
# SKU catalog + per-SKU generation parameters
# --------------------------------------------------------------------------


def _build_sku_params(rng: random.Random) -> list[_SkuGenParams]:
    params: list[_SkuGenParams] = []
    name_idx: dict[Category, int] = {c: 0 for c in CATEGORY_ORDER}
    revenue_range: dict[Category, tuple[float, float]] = {
        Category.BEVERAGES: (1.50, 4.50),
        Category.SNACKS: (2.00, 6.00),
        Category.HOUSEHOLD: (3.00, 9.00),
    }
    base_range: dict[Segment, tuple[float, float]] = {
        Segment.SMOOTH: (180.0, 420.0),
        Segment.ERRATIC: (150.0, 380.0),
        Segment.INTERMITTENT: (30.0, 90.0),
        Segment.LUMPY: (20.0, 70.0),
    }

    sku_counter = 0
    for archetype in ARCHETYPE_ORDER:
        for i in range(SKUS_PER_ARCHETYPE):
            category = CATEGORY_ORDER[sku_counter % len(CATEGORY_ORDER)]
            names = _PRODUCT_NAMES[category]
            name = names[name_idx[category] % len(names)]
            name_idx[category] += 1

            code = f"{category.value[:3].upper()}-{archetype.value[:4].upper()}-{i + 1:02d}"
            lo, hi = revenue_range[category]
            revenue_per_unit = round(rng.uniform(lo, hi), 2)
            base_lo, base_hi = base_range[archetype]
            base_level = rng.uniform(base_lo, base_hi)

            if archetype == Segment.SMOOTH:
                seasonal_amp = rng.uniform(0.10, 0.20)
                noise_std_frac = 0.08
                zero_prob = 0.0
                floor_frac = 0.10
            elif archetype == Segment.ERRATIC:
                seasonal_amp = rng.uniform(0.10, 0.25)
                noise_std_frac = 1.15
                zero_prob = 0.0
                floor_frac = 0.05
            elif archetype == Segment.INTERMITTENT:
                seasonal_amp = 0.0
                noise_std_frac = 0.12
                zero_prob = rng.uniform(0.35, 0.55)
                floor_frac = 0.0
            else:  # LUMPY
                seasonal_amp = 0.0
                noise_std_frac = 2.2
                zero_prob = rng.uniform(0.55, 0.78)
                floor_frac = 0.0

            promo_eligible = archetype in (Segment.SMOOTH, Segment.ERRATIC) and rng.random() < PROMO_ELIGIBLE_FRACTION

            sku = Sku(
                id=code,
                name=name,
                category=category,
                archetype=archetype,
                revenue_per_unit=revenue_per_unit,
                promo_eligible=promo_eligible,
            )
            params.append(
                _SkuGenParams(
                    sku=sku,
                    base_level=base_level,
                    seasonal_amp=seasonal_amp,
                    seasonal_phase=rng.uniform(0.0, 2 * math.pi),
                    noise_std_frac=noise_std_frac,
                    zero_prob=zero_prob,
                    floor_frac=floor_frac,
                )
            )
            sku_counter += 1
    return params


def _week_of_year(week: int) -> int:
    """1..52, cycling every 52 weeks (week 1 and week 53 share a woy)."""
    return ((week - 1) % 52) + 1


def _seasonal_multiplier(week: int, amp: float, phase: float) -> float:
    if amp == 0.0:
        return 1.0
    return 1.0 + amp * math.sin(2 * math.pi * _week_of_year(week) / 52.0 + phase)


# --------------------------------------------------------------------------
# Actual demand generation
# --------------------------------------------------------------------------


def _generate_actuals(
    p: _SkuGenParams, rng: random.Random
) -> tuple[list[float], dict[int, bool], dict[int, float]]:
    """
    Returns (actuals[1..N_WEEKS] as a 0-indexed list where actuals[w-1] is
    week w, is_promo by week, planned_uplift by week for promo weeks).
    """
    actuals: list[float] = []
    is_promo: dict[int, bool] = {}
    planned_uplift: dict[int, float] = {}
    promo_week_set = set(PROMO_WEEKS_OF_YEAR)

    for week in range(1, N_WEEKS + 1):
        seasonal_mult = _seasonal_multiplier(week, p.seasonal_amp, p.seasonal_phase)
        level = p.base_level * seasonal_mult

        if p.zero_prob > 0.0:
            # Intermittent / lumpy: explicit Bernoulli zero-inflation drives
            # ADI; when nonzero, a modest or large noise draw (per archetype)
            # drives CV² of the nonzero values.
            if rng.random() < p.zero_prob:
                demand = 0.0
            else:
                demand = max(1.0, level + rng.gauss(0.0, p.noise_std_frac * p.base_level))
        else:
            # Smooth / erratic: never structurally zero; noise magnitude
            # alone separates the two (small for smooth, large for erratic).
            floor = p.floor_frac * p.base_level
            demand = max(floor, level + rng.gauss(0.0, p.noise_std_frac * p.base_level))

        # Promotional uplift: only for promo_eligible SKUs on calendar weeks.
        promo = p.sku.promo_eligible and _week_of_year(week) in promo_week_set
        is_promo[week] = promo
        if promo:
            planned = p.base_level * rng.uniform(0.6, 1.3)
            planned_uplift[week] = planned
            realized_mult = max(0.5, min(1.6, rng.gauss(1.0, 0.18)))
            demand += planned * realized_mult

        actuals.append(round(demand))

    return actuals, is_promo, planned_uplift


# --------------------------------------------------------------------------
# Forecast layers
# --------------------------------------------------------------------------


def _naive_forecast(actuals: list[float], archetype: Segment) -> dict[int, float]:
    """Random-walk benchmark: seasonal-naive (actual 52 weeks back) for
    smooth/erratic SKUs (which have a real seasonal pattern to reuse);
    last-actual for intermittent/lumpy SKUs (seasonal-naive is unstable
    on sparse data and is not how intermittent demand is conventionally
    benchmarked). Only defined for the eval window."""
    out: dict[int, float] = {}
    for week in range(EVAL_START_WEEK, N_WEEKS + 1):
        if archetype in (Segment.SMOOTH, Segment.ERRATIC):
            out[week] = actuals[week - 52 - 1]
        else:
            out[week] = actuals[week - 1 - 1]
    return out


def _stat_forecast_smooth_erratic(actuals: list[float]) -> dict[int, float]:
    """
    A hand-rolled classical-decomposition forecast: a ratio-to-mean
    seasonal index estimated from the burn-in year, applied to a simple
    exponential smoothing (SES) level fit on the deseasonalized series.
    This is textbook forecasting machinery (uncited — standard method),
    not the SBC/Gilliland/Hyndman-Koehler citations, which are reserved
    for the segmentation cutoffs, FVA framework, and MASE respectively.

    The burn-in window supplies exactly one observation per week-of-year
    (52 weeks == one cycle), so a raw ratio-to-mean index is really "this
    single week's noisy deviation," not an averaged seasonal factor — with
    no second cycle to average against, that raw index would fit noise and
    then re-inject it at forecast time. `SEASONAL_SMOOTHING_WINDOW` runs a
    small circular moving average over the raw per-week ratios first,
    exploiting the fact that the true seasonal component is a slow sine
    wave while the noise is i.i.d. week to week — smoothing suppresses the
    latter far more than the former. The result is renormalized to average
    to 1.0 across the 52-week cycle so the multiplicative decomposition
    stays unbiased.
    """
    burn_in = actuals[:BURN_IN_WEEKS]
    year1_mean = sum(burn_in) / len(burn_in)
    raw_index = {
        woy: (burn_in[woy - 1] / year1_mean if year1_mean > 0 else 1.0) for woy in range(1, 53)
    }
    half = SEASONAL_SMOOTHING_WINDOW // 2
    smoothed_index = {}
    for woy in range(1, 53):
        window_vals = [raw_index[((woy - 1 + offset) % 52) + 1] for offset in range(-half, half + 1)]
        smoothed_index[woy] = sum(window_vals) / len(window_vals)
    mean_smoothed = sum(smoothed_index.values()) / 52
    seasonal_index = {
        woy: (v / mean_smoothed if mean_smoothed > 0 else 1.0) for woy, v in smoothed_index.items()
    }

    deseasonalized = [
        actuals[w - 1] / seasonal_index[_week_of_year(w)] if seasonal_index[_week_of_year(w)] > 0 else actuals[w - 1]
        for w in range(1, N_WEEKS + 1)
    ]

    level = sum(deseasonalized[:BURN_IN_WEEKS]) / BURN_IN_WEEKS
    out: dict[int, float] = {}
    for week in range(1, N_WEEKS + 1):
        if week >= EVAL_START_WEEK:
            forecast_deseason = level
            out[week] = forecast_deseason * seasonal_index[_week_of_year(week)]
        # One-step-ahead SES update using only information through `week`
        # (the forecast for `week` above used `level` from before this
        # update, so there is no lookahead leakage).
        level = SES_ALPHA * deseasonalized[week - 1] + (1 - SES_ALPHA) * level
    return out


def _stat_forecast_intermittent_lumpy(actuals: list[float]) -> dict[int, float]:
    """A trailing moving average over the prior `MOVING_AVERAGE_WINDOW`
    weeks — a simple, legitimate stdlib statistical forecast for sparse
    demand (unlike SES, it does not require a seasonal assumption this
    demand pattern does not exhibit)."""
    out: dict[int, float] = {}
    for week in range(EVAL_START_WEEK, N_WEEKS + 1):
        window = actuals[week - 1 - MOVING_AVERAGE_WINDOW : week - 1]
        out[week] = sum(window) / len(window)
    return out


def _consensus_forecast(
    actuals: list[float],
    stat_fcst: dict[int, float],
    archetype: Segment,
    is_promo: dict[int, bool],
    planned_uplift: dict[int, float],
    rng: random.Random,
) -> dict[int, float]:
    """stat_fcst plus a synthetic analyst override: a chase term (adds
    noise-driven variance, worse where the archetype is already volatile)
    and a promo term (a genuine, value-adding correction on known
    promotional weeks for promo-eligible SKUs). See module docstring."""
    chase_factor = _CHASE_FACTOR[archetype]
    promo_gain = _PROMO_OVERRIDE_GAIN[archetype]
    out: dict[int, float] = {}
    for week in range(EVAL_START_WEEK, N_WEEKS + 1):
        base_stat = stat_fcst[week]
        prior_actual = actuals[week - 1 - 1]
        chase = chase_factor * (prior_actual - base_stat)

        promo_term = 0.0
        if is_promo.get(week) and week in planned_uplift and promo_gain > 0.0:
            noise_factor = rng.uniform(0.85, 1.15)
            promo_term = promo_gain * planned_uplift[week] * noise_factor

        out[week] = max(0.0, base_stat + chase + promo_term)
    return out


# --------------------------------------------------------------------------
# Top-level generation + persistence
# --------------------------------------------------------------------------


def generate_dataset(seed: int = DEFAULT_SEED) -> tuple[SkuCatalog, DemandHistory]:
    """Generate the full seeded Northwind Foods dataset: the SKU catalog
    and 104 weeks of history with all three forecast layers."""
    rng = random.Random(seed)
    sku_params = _build_sku_params(rng)
    catalog = SkuCatalog(company=COMPANY, skus=[p.sku for p in sku_params])

    records: list[WeekRecord] = []
    for p in sku_params:
        actuals, is_promo, planned_uplift = _generate_actuals(p, rng)
        naive = _naive_forecast(actuals, p.sku.archetype)
        if p.sku.archetype in (Segment.SMOOTH, Segment.ERRATIC):
            stat = _stat_forecast_smooth_erratic(actuals)
        else:
            stat = _stat_forecast_intermittent_lumpy(actuals)
        consensus = _consensus_forecast(actuals, stat, p.sku.archetype, is_promo, planned_uplift, rng)

        for week in range(1, N_WEEKS + 1):
            in_eval = week >= EVAL_START_WEEK
            records.append(
                WeekRecord(
                    sku_id=p.sku.id,
                    week=week,
                    actual=actuals[week - 1],
                    naive_fcst=naive.get(week) if in_eval else None,
                    stat_fcst=stat.get(week) if in_eval else None,
                    consensus_fcst=consensus.get(week) if in_eval else None,
                    is_promo=is_promo.get(week, False),
                )
            )

    return catalog, DemandHistory(records=records)


def write_dataset(data_dir: Path | str, seed: int = DEFAULT_SEED) -> tuple[Path, Path]:
    """Generate the dataset and write `skus.json` + `history.json` to
    `data_dir`. Returns the two written paths."""
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    catalog, history = generate_dataset(seed)

    skus_path = data_dir / "skus.json"
    history_path = data_dir / "history.json"
    skus_path.write_text(json.dumps(jsonable(catalog), indent=2), encoding="utf-8")
    history_path.write_text(json.dumps(jsonable(history), indent=2), encoding="utf-8")
    return skus_path, history_path


def load_dataset(data_dir: Path | str) -> tuple[SkuCatalog, DemandHistory]:
    """Load a previously written `skus.json` + `history.json` back into
    typed dataclasses."""
    data_dir = Path(data_dir)
    skus_raw = json.loads((data_dir / "skus.json").read_text(encoding="utf-8"))
    history_raw = json.loads((data_dir / "history.json").read_text(encoding="utf-8"))

    skus = [
        Sku(
            id=s["id"],
            name=s["name"],
            category=Category(s["category"]),
            archetype=Segment(s["archetype"]),
            revenue_per_unit=s["revenue_per_unit"],
            promo_eligible=s["promo_eligible"],
        )
        for s in skus_raw["skus"]
    ]
    catalog = SkuCatalog(company=skus_raw["company"], skus=skus)

    records = [
        WeekRecord(
            sku_id=r["sku_id"],
            week=r["week"],
            actual=r["actual"],
            naive_fcst=r["naive_fcst"],
            stat_fcst=r["stat_fcst"],
            consensus_fcst=r["consensus_fcst"],
            is_promo=r["is_promo"],
        )
        for r in history_raw["records"]
    ]
    return catalog, DemandHistory(records=records)

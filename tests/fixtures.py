"""
fixtures.py — small, hand-computable `WeekRecord` fixtures shared across
the test suite.

Not a test module itself (no `Test*` classes), so `unittest discover`
skips it as a test-case source while every other test module in this
package can still `import fixtures` directly (it lives next to them in
`tests/`, which discover has already put on `sys.path`).

Every fixture below uses the *real* `datagen.BURN_IN_WEEKS` /
`datagen.EVAL_START_WEEK` boundary so `accuracy.py`'s eval-window filter
behaves exactly as it does against the real generated dataset — just
with a handful of weeks small enough that every metric computed from a
fixture is hand-verified in a comment next to the test that uses it,
rather than only cross-checked against the code under test.
"""

from __future__ import annotations

from demand_planning_diagnostics.datagen import EVAL_START_WEEK
from demand_planning_diagnostics.models import WeekRecord


def week_record(
    sku_id: str,
    week: int,
    actual: float,
    naive: float | None = None,
    stat: float | None = None,
    consensus: float | None = None,
    is_promo: bool = False,
) -> WeekRecord:
    return WeekRecord(
        sku_id=sku_id,
        week=week,
        actual=actual,
        naive_fcst=naive,
        stat_fcst=stat,
        consensus_fcst=consensus,
        is_promo=is_promo,
    )


def simple_sku_records(sku_id: str = "SKU-A") -> list[WeekRecord]:
    """
    2 burn-in weeks (actual 10, 14 -> one-step diff of 4, the MASE scale)
    + 3 eval weeks with all three forecast layers populated:

        week        actual  naive  stat  consensus
        EVAL+0        20      18    19      21
        EVAL+1        24      26    23      25
        EVAL+2        16      20    17      15

    Hand-computed metrics used across test_accuracy.py / test_fva.py:
      naive:      abs err [2, 2, 4], sum 8;  f-a [-2, 2, 4], sum 4
      stat:       abs err [1, 1, 1], sum 3;  f-a [-1,-1, 1], sum -1
      consensus:  abs err [1, 1, 1], sum 3;  f-a [ 1, 1,-1], sum 1
      sum(actual) = 60
      mase scale (burn-in) = |14 - 10| = 4
    """
    return [
        week_record(sku_id, 1, 10.0),
        week_record(sku_id, 2, 14.0),
        week_record(sku_id, EVAL_START_WEEK, 20.0, naive=18.0, stat=19.0, consensus=21.0),
        week_record(sku_id, EVAL_START_WEEK + 1, 24.0, naive=26.0, stat=23.0, consensus=25.0),
        week_record(sku_id, EVAL_START_WEEK + 2, 16.0, naive=20.0, stat=17.0, consensus=15.0),
    ]


def zero_actual_eval_records(sku_id: str = "SKU-Z") -> list[WeekRecord]:
    """One eval week with a zero actual (MAPE must skip it, WMAPE must not)."""
    return [
        week_record(sku_id, 1, 5.0),
        week_record(sku_id, 2, 5.0),
        week_record(sku_id, EVAL_START_WEEK, 0.0, naive=5.0, stat=5.0, consensus=5.0),
        week_record(sku_id, EVAL_START_WEEK + 1, 10.0, naive=10.0, stat=10.0, consensus=10.0),
    ]


def all_zero_actual_eval_records(sku_id: str = "SKU-ALLZERO") -> list[WeekRecord]:
    """Every eval week has zero actual -> MAPE is fully undefined (`None`)."""
    return [
        week_record(sku_id, 1, 0.0),
        week_record(sku_id, 2, 0.0),
        week_record(sku_id, EVAL_START_WEEK, 0.0, naive=3.0, stat=2.0, consensus=1.0),
        week_record(sku_id, EVAL_START_WEEK + 1, 0.0, naive=1.0, stat=1.0, consensus=1.0),
    ]


def perfect_forecast_records(sku_id: str = "SKU-PERFECT") -> list[WeekRecord]:
    """Forecast == actual on every eval week -> MAD is 0 -> tracking signal is `None`."""
    return [
        week_record(sku_id, 1, 10.0),
        week_record(sku_id, 2, 12.0),
        week_record(sku_id, EVAL_START_WEEK, 10.0, naive=10.0, stat=10.0, consensus=10.0),
        week_record(sku_id, EVAL_START_WEEK + 1, 12.0, naive=12.0, stat=12.0, consensus=12.0),
    ]


def insufficient_burn_in_records(sku_id: str = "SKU-NOBURNIN") -> list[WeekRecord]:
    """Only one burn-in observation -> the MASE scale is undefined (`None`)."""
    return [
        week_record(sku_id, 1, 10.0),
        week_record(sku_id, EVAL_START_WEEK, 10.0, naive=10.0, stat=10.0, consensus=10.0),
    ]


def small_catalog_and_history():
    """
    A 2-SKU catalog small enough to hand-verify `segment.py` /
    `kpi.forecastable_share` against:

      SKU-SMOOTH: actual [100, 100, 100, 100] over weeks 1-4
                  -> ADI = 1.0, CV2 = 0.0 -> SMOOTH
                  -> total volume 400
      SKU-LUMPY:  actual [0, 0, 80, 0, 0, 10] over weeks 1-6
                  -> 6 periods, 2 nonzero -> ADI = 3.0
                  -> nonzero = [80, 10], mean 45, pstdev 35 -> CV2 = (35/45)**2 ~= 0.6049
                  -> ADI >= 1.32 and CV2 >= 0.49 -> LUMPY
                  -> total volume 90

    Total portfolio volume = 490, so SKU-SMOOTH carries 400/490 of it.
    """
    from demand_planning_diagnostics.models import (
        Category,
        DemandHistory,
        Segment,
        Sku,
        SkuCatalog,
    )

    sku_smooth = Sku(
        id="SKU-SMOOTH", name="Smooth Widget", category=Category.BEVERAGES,
        archetype=Segment.SMOOTH, revenue_per_unit=2.0, promo_eligible=False,
    )
    sku_lumpy = Sku(
        id="SKU-LUMPY", name="Lumpy Widget", category=Category.SNACKS,
        archetype=Segment.LUMPY, revenue_per_unit=3.0, promo_eligible=False,
    )
    catalog = SkuCatalog(company="Toy Foods", skus=[sku_smooth, sku_lumpy])

    records: list[WeekRecord] = []
    for week, actual in enumerate([100.0, 100.0, 100.0, 100.0], start=1):
        records.append(week_record(sku_smooth.id, week, actual))
    for week, actual in enumerate([0.0, 0.0, 80.0, 0.0, 0.0, 10.0], start=1):
        records.append(week_record(sku_lumpy.id, week, actual))

    history = DemandHistory(records=records)
    return catalog, history

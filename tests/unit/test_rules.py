from datetime import datetime, timedelta

import polars as pl
import pytest

from cityflow.transform.reasons import RejectReason
from cityflow.transform.rules import (
    MAX_MONEY_AMOUNT,
    OTHER_MONEY_COLUMNS,
    distance_not_positive,
    distance_too_high,
    dropoff_before_pickup,
    duration_too_long,
    fare_not_positive,
    fare_too_high,
    invalid_dropoff_location,
    invalid_pickup_location,
    missing_distance,
    missing_dropoff_datetime,
    missing_dropoff_location,
    missing_fare,
    missing_pickup_datetime,
    missing_pickup_location,
    missing_total_amount,
    money_out_of_range,
    non_finite_distance,
    non_finite_fare,
    non_finite_money_amount,
    non_finite_total_amount,
    pickup_outside_month,
    reject_rules,
    zero_duration_with_distance,
)

NAN = float("nan")
INF = float("inf")
T0 = datetime(2025, 1, 15, 10, 0, 0)


def evaluate(rule: pl.Expr, column: str, values: list[float | None]) -> list[bool]:
    frame = pl.DataFrame({column: values}, schema={column: pl.Float64})
    result = frame.select(rule.alias("hit")).to_series()
    assert result.dtype == pl.Boolean
    assert result.null_count() == 0
    return result.to_list()


VALUES = [-1.0, 0.0, 0.01, 1000.0, 1000.01, None, NAN, INF, -INF]


@pytest.mark.parametrize(
    ("rule", "column", "expected"),
    [
        (
            fare_not_positive,
            "fare_amount",
            [True, True, False, False, False, False, False, False, False],
        ),
        (
            fare_too_high,
            "fare_amount",
            [False, False, False, False, True, False, False, False, False],
        ),
        (
            distance_not_positive,
            "trip_distance",
            [True, True, False, False, False, False, False, False, False],
        ),
    ],
)
def test_rule_flags_only_finite_values_that_break_it(rule, column, expected) -> None:
    assert evaluate(rule(), column, VALUES) == expected


def test_fare_too_high_accepts_exactly_the_limit() -> None:
    assert evaluate(fare_too_high(), "fare_amount", [1000.0, 1000.01]) == [False, True]


def test_distance_too_high_accepts_exactly_the_limit() -> None:
    assert evaluate(distance_too_high(), "trip_distance", [200.0, 200.01]) == [
        False,
        True,
    ]


def test_distance_too_high_skips_null_nan_and_infinite_values() -> None:
    assert evaluate(distance_too_high(), "trip_distance", [None, NAN, INF, -INF]) == [
        False,
        False,
        False,
        False,
    ]


def evaluate_trips(
    rule: pl.Expr,
    trips: list[tuple[datetime | None, datetime | None, float | None]],
) -> list[bool]:
    """Evaluate a rule on (pickup, dropoff, distance) rows."""
    frame = pl.DataFrame(
        {
            "tpep_pickup_datetime": [t[0] for t in trips],
            "tpep_dropoff_datetime": [t[1] for t in trips],
            "trip_distance": [t[2] for t in trips],
        },
        schema={
            "tpep_pickup_datetime": pl.Datetime("us"),
            "tpep_dropoff_datetime": pl.Datetime("us"),
            "trip_distance": pl.Float64,
        },
    )
    result = frame.select(rule.alias("hit")).to_series()
    assert result.dtype == pl.Boolean
    assert result.null_count() == 0
    return result.to_list()


def test_dropoff_before_pickup_flags_only_strictly_earlier_dropoffs() -> None:
    trips = [
        (T0, T0 - timedelta(seconds=1), 2.0),  # one second before
        (T0, T0, 2.0),  # equal
        (T0, T0 + timedelta(minutes=10), 2.0),  # normal
        (None, T0, 2.0),  # missing pickup
        (T0, None, 2.0),  # missing dropoff
    ]

    assert evaluate_trips(dropoff_before_pickup(), trips) == [
        True,
        False,
        False,
        False,
        False,
    ]


def test_zero_duration_with_distance_needs_equal_times_and_positive_distance() -> None:
    trips = [
        (T0, T0, 3.05),  # same instant, has distance
        (T0, T0, 0.0),  # same instant, no distance: distance rule's job
        (T0, T0, -1.0),  # same instant, negative distance
        (T0, T0, NAN),  # same instant, not a number
        (T0, T0, None),  # same instant, missing distance
        (T0, T0 + timedelta(seconds=1), 3.05),  # one second long
        (None, None, 3.05),  # missing timestamps
    ]

    assert evaluate_trips(zero_duration_with_distance(), trips) == [
        True,
        False,
        False,
        False,
        False,
        False,
        False,
    ]


def test_zero_duration_with_distance_flags_subsecond_trips() -> None:
    # Silver keeps whole seconds, so anything under one second would become 0.
    trips = [
        (T0, T0 + timedelta(milliseconds=500), 3.05),
        (T0, T0 + timedelta(microseconds=999_999), 3.05),
        (T0, T0 + timedelta(seconds=1), 3.05),  # the minimum is accepted
        (T0, T0 - timedelta(milliseconds=500), 3.05),  # dropoff_before_pickup's
        (T0, T0 + timedelta(milliseconds=500), 0.0),  # distance rule's job
    ]

    assert evaluate_trips(zero_duration_with_distance(), trips) == [
        True,
        True,
        False,
        False,
        False,
    ]


def test_duration_too_long_accepts_exactly_five_hours() -> None:
    five_hours = timedelta(hours=5)
    trips = [
        (T0, T0 + five_hours - timedelta(seconds=1), 2.0),
        (T0, T0 + five_hours, 2.0),
        (T0, T0 + five_hours + timedelta(seconds=1), 2.0),
        (T0, T0 - timedelta(hours=6), 2.0),  # negative duration
        (T0, None, 2.0),
        (None, T0, 2.0),
    ]

    assert evaluate_trips(duration_too_long(), trips) == [
        False,
        False,
        True,
        False,
        False,
        False,
    ]


def test_pickup_outside_month_uses_first_instants_as_boundaries() -> None:
    trips = [
        (datetime(2024, 12, 31, 23, 59, 59), T0, 2.0),
        (datetime(2025, 1, 1, 0, 0, 0), T0, 2.0),  # first instant of January
        (datetime(2025, 1, 31, 23, 59, 59), T0, 2.0),  # last second of January
        (datetime(2025, 2, 1, 0, 0, 0), T0, 2.0),  # first instant of February
        (None, T0, 2.0),
    ]

    assert evaluate_trips(pickup_outside_month("2025-01"), trips) == [
        True,
        False,
        False,
        True,
        False,
    ]


def test_pickup_outside_month_decides_by_pickup_not_dropoff() -> None:
    trips = [(datetime(2025, 1, 31, 23, 50), datetime(2025, 2, 1, 0, 10), 2.0)]

    assert evaluate_trips(pickup_outside_month("2025-01"), trips) == [False]


def test_pickup_outside_month_handles_december() -> None:
    trips = [
        (datetime(2025, 12, 31, 23, 59, 59), T0, 2.0),
        (datetime(2026, 1, 1, 0, 0, 0), T0, 2.0),
    ]

    assert evaluate_trips(pickup_outside_month("2025-12"), trips) == [False, True]


def test_pickup_outside_month_rejects_invalid_month() -> None:
    with pytest.raises(ValueError, match="expected YYYY-MM"):
        pickup_outside_month("2025-13")


@pytest.mark.parametrize(
    ("rule", "column"),
    [(missing_fare, "fare_amount"), (missing_distance, "trip_distance")],
)
def test_missing_number_rules_flag_only_null(rule, column) -> None:
    # VALUES: -1, 0, 0.01, 1000, 1000.01, null, NaN, inf, -inf
    assert evaluate(rule(), column, VALUES) == [
        False,
        False,
        False,
        False,
        False,
        True,
        False,
        False,
        False,
    ]


@pytest.mark.parametrize(
    ("rule", "column"),
    [(non_finite_fare, "fare_amount"), (non_finite_distance, "trip_distance")],
)
def test_non_finite_rules_flag_nan_and_infinite_but_not_null(rule, column) -> None:
    assert evaluate(rule(), column, VALUES) == [
        False,
        False,
        False,
        False,
        False,
        False,
        True,
        True,
        True,
    ]


def test_total_amount_rules_flag_null_and_non_finite_separately() -> None:
    # VALUES: -1, 0, 0.01, 1000, 1000.01, null, NaN, inf, -inf
    assert evaluate(missing_total_amount(), "total_amount", VALUES) == [
        False, False, False, False, False, True, False, False, False,
    ]
    assert evaluate(non_finite_total_amount(), "total_amount", VALUES) == [
        False, False, False, False, False, False, True, True, True,
    ]


def money_frame(column: str, values: list[float | None]) -> pl.DataFrame:
    """Every money column except total filled with 1.0; one column gets the values."""
    return pl.DataFrame(
        {name: [1.0] * len(values) for name in ["total_amount", *OTHER_MONEY_COLUMNS]}
    ).with_columns(pl.Series(column, values, dtype=pl.Float64))


@pytest.mark.parametrize("column", OTHER_MONEY_COLUMNS)
def test_non_finite_money_amount_flags_each_other_money_column(column: str) -> None:
    result = money_frame(column, VALUES).select(non_finite_money_amount().alias("hit"))

    assert result["hit"].null_count() == 0
    # Null is allowed in these columns; only NaN and infinities are rejected.
    assert result["hit"].to_list() == [
        False, False, False, False, False, False, True, True, True,
    ]


MONEY_VALUES = [
    -MAX_MONEY_AMOUNT - 0.01,
    -MAX_MONEY_AMOUNT,
    0.0,
    MAX_MONEY_AMOUNT,
    MAX_MONEY_AMOUNT + 0.01,
    1e17,
    None,
    NAN,
    INF,
]


@pytest.mark.parametrize("column", ["total_amount", *OTHER_MONEY_COLUMNS])
def test_money_out_of_range_flags_each_money_column(column: str) -> None:
    result = money_frame(column, MONEY_VALUES).select(money_out_of_range().alias("hit"))

    assert result["hit"].null_count() == 0
    # The limit itself is accepted in both directions. Null, NaN and infinity
    # have their own reason codes and are not "out of range".
    assert result["hit"].to_list() == [
        True, False, False, False, True, True, False, False, False,
    ]


def test_money_out_of_range_handles_integer_columns_without_overflow() -> None:
    # abs() of Int32's smallest value overflows in Int32 and stays negative.
    frame = money_frame("total_amount", [1.0, 1.0]).with_columns(
        pl.Series("extra", [-(2**31), 30_000_000], dtype=pl.Int32)
    )

    result = frame.select(money_out_of_range().alias("hit"))

    assert result["hit"].to_list() == [True, False]


def test_money_out_of_range_does_not_apply_to_fare_amount() -> None:
    frame = money_frame("total_amount", [1.0]).with_columns(
        pl.lit(1e17).alias("fare_amount")
    )

    assert frame.select(money_out_of_range()).item() is False


def test_missing_datetime_rules_flag_the_null_timestamp() -> None:
    trips = [(None, T0, 2.0), (T0, None, 2.0), (T0, T0, 2.0), (None, None, 2.0)]

    assert evaluate_trips(missing_pickup_datetime(), trips) == [True, False, False, True]
    assert evaluate_trips(missing_dropoff_datetime(), trips) == [False, True, False, True]


def evaluate_location(rule: pl.Expr, column: str, ids: list[int | None]) -> list[bool]:
    frame = pl.DataFrame({column: ids}, schema={column: pl.Int32})
    result = frame.select(rule.alias("hit")).to_series()
    assert result.dtype == pl.Boolean
    assert result.null_count() == 0
    return result.to_list()


LOCATION_IDS = [None, -1, 0, 1, 132, 264, 265, 266]


@pytest.mark.parametrize(
    ("rule", "column"),
    [
        (missing_pickup_location, "PULocationID"),
        (missing_dropoff_location, "DOLocationID"),
    ],
)
def test_missing_location_rules_flag_only_null(rule, column) -> None:
    assert evaluate_location(rule(), column, LOCATION_IDS) == [
        True,
        False,
        False,
        False,
        False,
        False,
        False,
        False,
    ]


@pytest.mark.parametrize(
    ("rule", "column"),
    [
        (invalid_pickup_location, "PULocationID"),
        (invalid_dropoff_location, "DOLocationID"),
    ],
)
def test_invalid_location_rules_flag_ids_outside_1_to_265(rule, column) -> None:
    # 1 and 265 are valid boundaries; 264 and 265 are real TLC values, not invalid.
    assert evaluate_location(rule(), column, LOCATION_IDS) == [
        False,
        True,
        True,
        False,
        False,
        False,
        False,
        True,
    ]


def test_reject_rules_has_exactly_one_rule_per_reason_code() -> None:
    rules = reject_rules("2025-01")

    assert set(rules) == set(RejectReason)
    assert len(rules) == len(RejectReason)


def test_reject_rules_rejects_invalid_month() -> None:
    with pytest.raises(ValueError, match="expected YYYY-MM"):
        reject_rules("2025-13")


def test_rules_work_on_a_lazy_frame() -> None:
    lazy = pl.LazyFrame(
        {"fare_amount": [-5.0, 20.0], "trip_distance": [0.0, 3.0]}
    ).with_columns(
        fare_not_positive().alias("bad_fare"),
        distance_not_positive().alias("bad_distance"),
    )

    result = lazy.collect()

    assert result["bad_fare"].to_list() == [True, False]
    assert result["bad_distance"].to_list() == [True, False]

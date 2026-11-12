from datetime import datetime
from typing import Any

import polars as pl
import pytest

from cityflow.transform.bronze import to_bronze
from cityflow.transform.split import add_reject_reasons, split_accepted_rejected

MONTH = "2025-01"
NAN = float("nan")

SCHEMA = {
    "tpep_pickup_datetime": pl.Datetime("us"),
    "tpep_dropoff_datetime": pl.Datetime("us"),
    "PULocationID": pl.Int32,
    "DOLocationID": pl.Int32,
    "trip_distance": pl.Float64,
    "fare_amount": pl.Float64,
    "passenger_count": pl.Int64,
}


def trip(**overrides: Any) -> dict[str, Any]:
    """A valid January trip; override fields to break a rule."""
    row = {
        "tpep_pickup_datetime": datetime(2025, 1, 15, 10, 0),
        "tpep_dropoff_datetime": datetime(2025, 1, 15, 10, 15),
        "PULocationID": 132,
        "DOLocationID": 236,
        "trip_distance": 3.2,
        "fare_amount": 17.5,
        "passenger_count": 1,
    }
    row.update(overrides)
    return row


def bronze_of(trips: list[dict[str, Any]]) -> pl.LazyFrame:
    source = pl.DataFrame(trips, schema=SCHEMA)
    return to_bronze(
        source.lazy(),
        month=MONTH,
        source_object_key="raw/key.parquet",
        source_sha256="a" * 64,
        ingested_at="2026-11-01T10:00:00+00:00",
    )


def split(trips: list[dict[str, Any]]) -> tuple[pl.DataFrame, pl.DataFrame]:
    accepted, rejected = split_accepted_rejected(bronze_of(trips), MONTH)
    return accepted.collect(), rejected.collect()


def test_valid_trip_is_accepted_without_a_reasons_column() -> None:
    accepted, rejected = split([trip()])

    assert accepted.height == 1
    assert rejected.height == 0
    assert "reject_reasons" not in accepted.columns


def test_rejected_trip_goes_to_quarantine_with_its_reason() -> None:
    accepted, rejected = split([trip(fare_amount=2000.0)])

    assert accepted.height == 0
    assert rejected["reject_reasons"].to_list() == [["fare_too_high"]]


def test_trip_breaking_several_rules_appears_once_with_all_reasons_sorted() -> None:
    _, rejected = split([trip(fare_amount=2000.0, trip_distance=300.0)])

    assert rejected.height == 1
    assert rejected["reject_reasons"].to_list() == [
        ["distance_too_high", "fare_too_high"]
    ]


def test_null_and_nan_values_get_their_own_single_reason() -> None:
    _, rejected = split(
        [trip(fare_amount=None), trip(trip_distance=NAN), trip(PULocationID=None)]
    )

    assert rejected["reject_reasons"].to_list() == [
        ["missing_fare"],
        ["non_finite_distance"],
        ["missing_pickup_location"],
    ]


def test_trip_starting_in_another_month_is_rejected() -> None:
    _, rejected = split(
        [
            trip(
                tpep_pickup_datetime=datetime(2025, 2, 1, 0, 0),
                tpep_dropoff_datetime=datetime(2025, 2, 1, 0, 15),
            )
        ]
    )

    assert rejected["reject_reasons"].to_list() == [["pickup_outside_month"]]


def test_trip_starting_in_january_and_ending_in_february_is_accepted() -> None:
    accepted, rejected = split(
        [
            trip(
                tpep_pickup_datetime=datetime(2025, 1, 31, 23, 50),
                tpep_dropoff_datetime=datetime(2025, 2, 1, 0, 10),
            )
        ]
    )

    assert accepted.height == 1
    assert rejected.height == 0


def test_flex_fare_nulls_and_unknown_zones_are_accepted() -> None:
    accepted, rejected = split(
        [trip(passenger_count=None), trip(PULocationID=264, DOLocationID=265)]
    )

    assert accepted.height == 2
    assert rejected.height == 0


def test_identical_rows_are_both_kept_with_different_ids() -> None:
    accepted, _ = split([trip(), trip()])

    assert accepted["source_row_id"].to_list() == [0, 1]


def test_every_row_lands_in_exactly_one_side() -> None:
    trips = [
        trip(),
        trip(fare_amount=-5.0),
        trip(),
        trip(fare_amount=2000.0, trip_distance=300.0),
        trip(trip_distance=0.0),
    ]

    accepted, rejected = split(trips)

    accepted_ids = set(accepted["source_row_id"])
    rejected_ids = set(rejected["source_row_id"])
    assert accepted.height + rejected.height == len(trips)
    assert accepted_ids.isdisjoint(rejected_ids)
    assert accepted_ids | rejected_ids == set(range(len(trips)))


def test_accepted_keeps_bronze_columns_and_rejected_adds_reasons() -> None:
    bronze_columns = bronze_of([trip()]).collect_schema().names()

    accepted, rejected = split([trip(), trip(fare_amount=-5.0)])

    assert accepted.columns == bronze_columns
    assert rejected.columns == [*bronze_columns, "reject_reasons"]


def test_reasons_column_is_a_string_list_and_empty_for_clean_rows() -> None:
    flagged = add_reject_reasons(bronze_of([trip(), trip(fare_amount=-5.0)]), MONTH)

    result = flagged.collect()

    assert result.schema["reject_reasons"] == pl.List(pl.String)
    assert result["reject_reasons"].to_list() == [[], ["fare_not_positive"]]


def test_add_reject_reasons_keeps_every_row() -> None:
    trips = [trip(), trip(fare_amount=-5.0), trip(trip_distance=NAN)]

    result = add_reject_reasons(bronze_of(trips), MONTH).collect()

    assert result.height == len(trips)


def test_empty_input_gives_two_empty_results_with_the_right_columns() -> None:
    accepted, rejected = split([])

    assert accepted.height == 0
    assert rejected.height == 0
    assert "reject_reasons" not in accepted.columns
    assert rejected.schema["reject_reasons"] == pl.List(pl.String)


def test_invalid_month_is_rejected() -> None:
    with pytest.raises(ValueError, match="expected YYYY-MM"):
        split_accepted_rejected(bronze_of([trip()]), "2025-13")

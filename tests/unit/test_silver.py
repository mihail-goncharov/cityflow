from datetime import date, datetime
from typing import Any

import polars as pl

from cityflow.transform.silver import MONEY_COLUMNS, dollars_to_cents, to_silver

SCHEMA: dict[str, Any] = {
    "source_row_id": pl.Int64,
    "tpep_pickup_datetime": pl.Datetime("us"),
    "tpep_dropoff_datetime": pl.Datetime("us"),
    "PULocationID": pl.Int32,
    "DOLocationID": pl.Int32,
    "trip_distance": pl.Float64,
    "passenger_count": pl.Int64,
    "RatecodeID": pl.Int64,
    "store_and_fwd_flag": pl.String,
    **dict.fromkeys(MONEY_COLUMNS, pl.Float64),
}


def trip(**overrides: Any) -> dict[str, Any]:
    """A valid accepted trip with every source column set."""
    row: dict[str, Any] = {
        "source_row_id": 0,
        "tpep_pickup_datetime": datetime(2025, 1, 15, 10, 30, 5),
        "tpep_dropoff_datetime": datetime(2025, 1, 15, 10, 45, 35),
        "PULocationID": 132,
        "DOLocationID": 236,
        "trip_distance": 3.2,
        "passenger_count": 1,
        "RatecodeID": 1,
        "store_and_fwd_flag": "N",
        **dict.fromkeys(MONEY_COLUMNS, 1.5),
    }
    row.update(overrides)
    return row


def silver_of(trips: list[dict[str, Any]]) -> pl.DataFrame:
    accepted = pl.DataFrame(trips, schema=SCHEMA).lazy()
    return to_silver(accepted).collect()


def test_dollars_to_cents_rounds_float_noise_and_half_away_from_zero() -> None:
    df = pl.DataFrame({"x": [0.0, 0.1 + 0.2, -2.5, 0.125, -0.125]})

    result = df.select(dollars_to_cents("x"))["x"].to_list()

    assert result == [0, 30, -250, 13, -13]


def test_dollars_to_cents_keeps_null_and_returns_int64() -> None:
    df = pl.DataFrame({"x": [None, 1.0]}, schema={"x": pl.Float64})

    result = df.select(dollars_to_cents("x"))

    assert result.schema["x"] == pl.Int64
    assert result["x"].to_list() == [None, 100]


def test_dollars_to_cents_does_not_overflow_an_integer_source_dtype() -> None:
    # 30,000,000 * 100 does not fit Int32; it must not wrap around.
    df = pl.DataFrame({"x": [30_000_000, -30_000_000]}, schema={"x": pl.Int32})

    result = df.select(dollars_to_cents("x"))["x"].to_list()

    assert result == [3_000_000_000, -3_000_000_000]


def test_money_columns_are_renamed_to_cents_and_dollars_are_dropped() -> None:
    silver = silver_of([trip(fare_amount=17.5, Airport_fee=1.25)])

    assert silver["fare_amount_cents"].to_list() == [1750]
    assert silver["airport_fee_cents"].to_list() == [125]
    assert all(name not in silver.columns for name in MONEY_COLUMNS)
    assert all(dst in silver.columns for dst in MONEY_COLUMNS.values())


def test_derived_columns_come_from_the_local_timestamps() -> None:
    silver = silver_of([trip()])

    assert silver["pickup_date"].to_list() == [date(2025, 1, 15)]
    assert silver["pickup_hour"].to_list() == [10]
    assert silver["trip_duration_seconds"].to_list() == [15 * 60 + 30]
    assert silver.schema["pickup_hour"] == pl.Int8
    assert silver.schema["trip_duration_seconds"] == pl.Int64


def test_trip_crossing_midnight_keeps_pickup_date() -> None:
    silver = silver_of(
        [
            trip(
                tpep_pickup_datetime=datetime(2025, 1, 31, 23, 50),
                tpep_dropoff_datetime=datetime(2025, 2, 1, 0, 10),
            )
        ]
    )

    assert silver["pickup_date"].to_list() == [date(2025, 1, 31)]
    assert silver["trip_duration_seconds"].to_list() == [20 * 60]


def test_missing_flex_field_sets_flag_and_keeps_the_nulls() -> None:
    silver = silver_of(
        [
            trip(source_row_id=0),
            trip(source_row_id=1, passenger_count=None, congestion_surcharge=None),
        ]
    )

    assert silver["has_missing_flex_fields"].to_list() == [False, True]
    assert silver["passenger_count"].to_list() == [1, None]
    assert silver["congestion_surcharge_cents"].to_list() == [150, None]


def test_unknown_zones_are_kept_and_flagged_per_side() -> None:
    silver = silver_of(
        [
            trip(source_row_id=0),
            trip(source_row_id=1, PULocationID=264, DOLocationID=265),
            trip(source_row_id=2, DOLocationID=264),
        ]
    )

    assert silver["is_unknown_pickup_zone"].to_list() == [False, True, False]
    assert silver["is_unknown_dropoff_zone"].to_list() == [False, True, True]
    assert silver["PULocationID"].to_list() == [132, 264, 132]


def test_rows_and_lineage_ids_are_preserved() -> None:
    silver = silver_of([trip(source_row_id=7), trip(source_row_id=7 + 1)])

    assert silver["source_row_id"].to_list() == [7, 8]
    assert silver.height == 2


def test_empty_input_gives_empty_silver_with_the_silver_schema() -> None:
    silver = silver_of([])

    assert silver.height == 0
    assert "fare_amount_cents" in silver.columns
    assert silver.schema["fare_amount_cents"] == pl.Int64

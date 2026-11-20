from datetime import date

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from cityflow.gold.fixture import (
    INVALID_ZONE_ID,
    build_silver_fixture,
    fixture_trips,
    main,
    silver_root,
    write_silver_fixture,
)


@pytest.fixture(scope="module")
def silver() -> pl.DataFrame:
    return build_silver_fixture(fixture_trips())


def test_every_fixture_trip_reaches_silver(silver) -> None:
    assert silver.height == fixture_trips().height == 9


def test_fixture_has_the_silver_money_and_derived_columns(silver) -> None:
    assert silver.schema["fare_amount_cents"] == pl.Int64
    assert silver.schema["total_amount_cents"] == pl.Int64
    assert silver.schema["pickup_date"] == pl.Date
    assert silver.schema["pickup_hour"] == pl.Int8
    assert "fare_amount" not in silver.columns


def test_identical_looking_trips_stay_two_rows(silver) -> None:
    pair = silver.filter(pl.col("source_row_id").is_in([0, 1]))

    assert pair.drop("source_row_id").n_unique() == 1
    assert pair["source_row_id"].to_list() == [0, 1]


def test_unknown_zones_are_present_and_flagged(silver) -> None:
    unknown = silver.filter(pl.col("is_unknown_pickup_zone"))

    assert sorted(unknown["PULocationID"].to_list()) == [264, 265]


def test_cross_midnight_trip_belongs_to_its_pickup_date(silver) -> None:
    trip = silver.filter(pl.col("PULocationID") == 265).row(0, named=True)

    assert trip["pickup_date"] == date(2025, 1, 1)
    assert trip["pickup_hour"] == 23
    assert trip["trip_duration_seconds"] == 900


def test_flex_fare_trip_keeps_its_nulls(silver) -> None:
    flex = silver.filter(pl.col("has_missing_flex_fields"))

    assert flex.height == 1
    assert flex["passenger_count"].to_list() == [None]
    assert flex["congestion_surcharge_cents"].to_list() == [None]
    assert flex["airport_fee_cents"].to_list() == [None]


def test_one_hour_has_an_average_fare_exactly_between_two_cents(silver) -> None:
    hour = silver.filter(
        (pl.col("pickup_date") == date(2025, 1, 2)) & (pl.col("pickup_hour") == 12)
    )

    # (1000 + 1001) / 2 = 1000.5: half away from zero gives 1001, banker's
    # rounding would give 1000.
    assert sorted(hour["fare_amount_cents"].to_list()) == [1000, 1001]


def test_one_trip_has_a_negative_total_and_a_positive_fare(silver) -> None:
    negative = silver.filter(pl.col("total_amount_cents") < 0)

    assert negative["total_amount_cents"].to_list() == [-800]
    assert negative["fare_amount_cents"].to_list() == [800]


def test_fixture_totals_match_the_hand_calculated_values(silver) -> None:
    # The Gold tests compare their marts with these numbers.
    daily = (
        silver.group_by("pickup_date")
        .agg(
            pl.len().alias("trips"),
            pl.col("fare_amount_cents").sum().alias("fare"),
            pl.col("total_amount_cents").sum().alias("total"),
        )
        .sort("pickup_date")
    )

    assert daily.rows() == [
        (date(2025, 1, 1), 4, 5500, 7500),
        (date(2025, 1, 2), 5, 6301, 6401),
    ]


def test_build_rejects_a_trip_that_breaks_a_quality_rule() -> None:
    trips = fixture_trips().with_columns(pl.lit(0.0).alias("fare_amount"))

    with pytest.raises(ValueError, match="fare_not_positive"):
        build_silver_fixture(trips)


def test_write_uses_the_silver_storage_layout(tmp_path) -> None:
    path = write_silver_fixture(tmp_path)

    expected = silver_root(tmp_path) / "year=2025" / "month=01" / "yellow_tripdata.parquet"
    assert path == expected
    assert_frame_equal(pl.read_parquet(path), build_silver_fixture(fixture_trips()))


def test_write_empty_keeps_the_columns_without_rows(tmp_path, silver) -> None:
    path = write_silver_fixture(tmp_path, variant="empty")

    empty = pl.read_parquet(path)
    assert empty.height == 0
    assert empty.schema == silver.schema


def test_write_invalid_zone_changes_only_one_pickup_zone(tmp_path, silver) -> None:
    path = write_silver_fixture(tmp_path, variant="invalid_zone")

    broken = pl.read_parquet(path)
    assert broken.schema == silver.schema
    assert broken.height == silver.height
    changed = broken.filter(pl.col("PULocationID") != silver["PULocationID"])
    assert changed["source_row_id"].to_list() == [0]
    assert changed["PULocationID"].to_list() == [INVALID_ZONE_ID]


def test_main_accepts_a_variant(tmp_path) -> None:
    assert main([str(tmp_path), "--variant", "empty"]) == 0

    path = silver_root(tmp_path) / "year=2025" / "month=01" / "yellow_tripdata.parquet"
    assert pl.read_parquet(path).height == 0


def test_main_rejects_an_unknown_variant(tmp_path) -> None:
    with pytest.raises(SystemExit):
        main([str(tmp_path), "--variant", "broken"])


def test_main_writes_the_fixture_and_prints_the_root(tmp_path, capsys) -> None:
    assert main([str(tmp_path)]) == 0

    out = capsys.readouterr().out
    assert f"CITYFLOW_SILVER_ROOT={silver_root(tmp_path)}" in out
    assert (silver_root(tmp_path) / "year=2025" / "month=01" / "yellow_tripdata.parquet").exists()

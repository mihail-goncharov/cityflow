from datetime import datetime
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from cityflow.ingestion.pipeline import build_object_key
from cityflow.transform.pipeline import RawInput, write_layer_files
from cityflow.transform.silver import MONEY_COLUMNS

MONTH = "2025-01"
OBJECT_KEY = build_object_key(MONTH, f"yellow_tripdata_{MONTH}.parquet")
SHA = "c" * 64
INGESTED_AT = "2026-11-16T10:00:00+00:00"

SCHEMA: dict[str, Any] = {
    "VendorID": pl.Int32,
    "tpep_pickup_datetime": pl.Datetime("us"),
    "tpep_dropoff_datetime": pl.Datetime("us"),
    "passenger_count": pl.Int64,
    "trip_distance": pl.Float64,
    "RatecodeID": pl.Int64,
    "store_and_fwd_flag": pl.String,
    "PULocationID": pl.Int32,
    "DOLocationID": pl.Int32,
    "payment_type": pl.Int64,
    **dict.fromkeys(MONEY_COLUMNS, pl.Float64),
}


def trip(**overrides: Any) -> dict[str, Any]:
    """A valid January trip with all 20 source columns."""
    row: dict[str, Any] = {
        "VendorID": 1,
        "tpep_pickup_datetime": datetime(2025, 1, 15, 10, 0),
        "tpep_dropoff_datetime": datetime(2025, 1, 15, 10, 15),
        "passenger_count": 1,
        "trip_distance": 3.2,
        "RatecodeID": 1,
        "store_and_fwd_flag": "N",
        "PULocationID": 132,
        "DOLocationID": 236,
        "payment_type": 1,
        **dict.fromkeys(MONEY_COLUMNS, 1.5),
    }
    row["fare_amount"] = 17.5
    row.update(overrides)
    return row


def make_raw(tmp_path: Path, trips: list[dict[str, Any]]) -> RawInput:
    source_dir = tmp_path / "source"
    source_dir.mkdir(exist_ok=True)
    path = source_dir / f"yellow_tripdata_{MONTH}.parquet"
    pl.DataFrame(trips, schema=SCHEMA).write_parquet(path)
    return RawInput(
        path=path,
        month=MONTH,
        object_key=OBJECT_KEY,
        sha256=SHA,
        ingested_at=INGESTED_AT,
    )


def run(tmp_path: Path, trips: list[dict[str, Any]], name: str = "work") -> Any:
    work_dir = tmp_path / name
    work_dir.mkdir(exist_ok=True)
    raw = make_raw(tmp_path, trips)
    return raw, write_layer_files(raw, work_dir)


MIXED_TRIPS = [
    trip(),
    trip(fare_amount=2000.0),
    trip(),
    trip(fare_amount=-1.0, trip_distance=300.0),
    trip(passenger_count=None, congestion_surcharge=None),
]


def test_three_files_are_written_into_the_work_dir(tmp_path: Path) -> None:
    _, files = run(tmp_path, MIXED_TRIPS)

    for path in (files.bronze, files.silver, files.quarantine):
        assert path.parent == tmp_path / "work"
        assert path.exists()
    assert len({files.bronze, files.silver, files.quarantine}) == 3


def test_bronze_rows_equal_silver_plus_quarantine(tmp_path: Path) -> None:
    _, files = run(tmp_path, MIXED_TRIPS)

    bronze = pl.read_parquet(files.bronze)
    silver = pl.read_parquet(files.silver)
    quarantine = pl.read_parquet(files.quarantine)

    assert bronze.height == 5
    assert silver.height == 3
    assert quarantine.height == 2
    assert bronze.height == silver.height + quarantine.height


def test_every_bronze_row_lands_in_exactly_one_output(tmp_path: Path) -> None:
    _, files = run(tmp_path, MIXED_TRIPS)

    bronze_ids = pl.read_parquet(files.bronze)["source_row_id"].to_list()
    silver_ids = pl.read_parquet(files.silver)["source_row_id"].to_list()
    quarantine_ids = pl.read_parquet(files.quarantine)["source_row_id"].to_list()

    assert bronze_ids == [0, 1, 2, 3, 4]
    assert set(silver_ids).isdisjoint(quarantine_ids)
    assert sorted(silver_ids + quarantine_ids) == bronze_ids


def test_row_order_of_raw_is_kept_in_every_layer(tmp_path: Path) -> None:
    _, files = run(tmp_path, MIXED_TRIPS)

    for path in (files.bronze, files.silver, files.quarantine):
        ids = pl.read_parquet(path)["source_row_id"].to_list()
        assert ids == sorted(ids)

    assert pl.read_parquet(files.silver)["source_row_id"].to_list() == [0, 2, 4]
    assert pl.read_parquet(files.quarantine)["source_row_id"].to_list() == [1, 3]


def test_bronze_keeps_the_source_columns_and_adds_lineage_from_raw(
    tmp_path: Path,
) -> None:
    raw, files = run(tmp_path, MIXED_TRIPS)

    bronze = pl.read_parquet(files.bronze)
    source = pl.read_parquet(raw.path)

    assert bronze.select(source.columns).equals(source)
    assert set(bronze["source_month"]) == {MONTH}
    assert set(bronze["source_object_key"]) == {OBJECT_KEY}
    assert set(bronze["source_sha256"]) == {SHA}
    assert set(bronze["ingested_at"]) == {INGESTED_AT}


def test_identical_trips_stay_distinguishable(tmp_path: Path) -> None:
    _, files = run(tmp_path, [trip(), trip(), trip()])

    silver = pl.read_parquet(files.silver)

    assert silver["source_row_id"].to_list() == [0, 1, 2]


def test_silver_has_cents_and_derived_columns(tmp_path: Path) -> None:
    _, files = run(tmp_path, [trip()])

    silver = pl.read_parquet(files.silver)

    assert silver["fare_amount_cents"].to_list() == [1750]
    assert silver["trip_duration_seconds"].to_list() == [15 * 60]
    assert silver["pickup_hour"].to_list() == [10]
    assert all(name not in silver.columns for name in MONEY_COLUMNS)
    assert "reject_reasons" not in silver.columns


def test_quarantine_keeps_bronze_columns_and_all_reasons(tmp_path: Path) -> None:
    _, files = run(tmp_path, [trip(fare_amount=-1.0, trip_distance=300.0)])

    quarantine = pl.read_parquet(files.quarantine)

    assert quarantine["reject_reasons"].to_list() == [
        ["distance_too_high", "fare_not_positive"]
    ]
    assert quarantine["fare_amount"].to_list() == [-1.0]
    assert "fare_amount_cents" not in quarantine.columns


def test_empty_raw_gives_three_empty_files_with_their_schemas(
    tmp_path: Path,
) -> None:
    _, files = run(tmp_path, [])

    bronze = pl.read_parquet(files.bronze)
    silver = pl.read_parquet(files.silver)
    quarantine = pl.read_parquet(files.quarantine)

    assert (bronze.height, silver.height, quarantine.height) == (0, 0, 0)
    assert "source_row_id" in bronze.columns
    assert silver.schema["fare_amount_cents"] == pl.Int64
    assert "reject_reasons" in quarantine.columns


def test_all_rows_rejected_gives_an_empty_silver(tmp_path: Path) -> None:
    _, files = run(tmp_path, [trip(fare_amount=2000.0), trip(fare_amount=3000.0)])

    assert pl.read_parquet(files.silver).height == 0
    assert pl.read_parquet(files.quarantine).height == 2


def test_raw_file_is_not_changed(tmp_path: Path) -> None:
    raw = make_raw(tmp_path, MIXED_TRIPS)
    before = raw.path.read_bytes()
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    write_layer_files(raw, work_dir)

    assert raw.path.read_bytes() == before


def test_running_twice_gives_the_same_logical_records(tmp_path: Path) -> None:
    _, first = run(tmp_path, MIXED_TRIPS, name="first")
    _, second = run(tmp_path, MIXED_TRIPS, name="second")

    for name in ("bronze", "silver", "quarantine"):
        one = pl.read_parquet(getattr(first, name))
        two = pl.read_parquet(getattr(second, name))
        assert one.equals(two), name


def test_missing_required_column_raises_instead_of_succeeding(
    tmp_path: Path,
) -> None:
    raw = make_raw(tmp_path, MIXED_TRIPS)
    pl.read_parquet(raw.path).drop("fare_amount").write_parquet(raw.path)
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    with pytest.raises(pl.exceptions.PolarsError):
        write_layer_files(raw, work_dir)

from datetime import datetime

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from cityflow.ingestion.validate import ValidationError
from cityflow.transform.bronze import LINEAGE_COLUMNS, to_bronze

MONTH = "2025-01"
OBJECT_KEY = "raw/nyc_tlc/yellow_taxi/year=2025/month=01/yellow_tripdata_2025-01.parquet"
SHA256 = "a" * 64
INGESTED_AT = "2026-11-01T10:00:00+00:00"

SOURCE_SCHEMA = {
    "tpep_pickup_datetime": pl.Datetime("us"),
    "PULocationID": pl.Int32,
    "fare_amount": pl.Float64,
    "passenger_count": pl.Int64,
}


def make_source() -> pl.DataFrame:
    trip = datetime(2025, 1, 1, 10, 0)
    return pl.DataFrame(
        {
            "tpep_pickup_datetime": [trip, trip, datetime(2025, 1, 2, 8, 30)],
            "PULocationID": [132, 132, 48],
            "fare_amount": [17.5, 17.5, -3.0],
            "passenger_count": [1, 1, None],
        },
        schema=SOURCE_SCHEMA,
    )


def bronze_of(source: pl.DataFrame) -> pl.DataFrame:
    return to_bronze(
        source.lazy(),
        month=MONTH,
        source_object_key=OBJECT_KEY,
        source_sha256=SHA256,
        ingested_at=INGESTED_AT,
    ).collect()


def test_to_bronze_adds_lineage_columns_with_expected_types() -> None:
    bronze = bronze_of(make_source())

    assert set(LINEAGE_COLUMNS) <= set(bronze.columns)
    assert bronze.schema["source_row_id"] == pl.Int64
    for column in LINEAGE_COLUMNS[1:]:
        assert bronze.schema[column] == pl.String


def test_to_bronze_sets_the_same_source_values_on_every_row() -> None:
    bronze = bronze_of(make_source())

    assert bronze["source_month"].unique().to_list() == [MONTH]
    assert bronze["source_object_key"].unique().to_list() == [OBJECT_KEY]
    assert bronze["source_sha256"].unique().to_list() == [SHA256]
    assert bronze["ingested_at"].unique().to_list() == [INGESTED_AT]


def test_to_bronze_keeps_every_row_and_source_column_unchanged() -> None:
    source = make_source()

    bronze = bronze_of(source)

    assert_frame_equal(bronze.select(source.columns), source)


def test_to_bronze_numbers_rows_by_position_so_duplicates_stay_distinct() -> None:
    bronze = bronze_of(make_source())

    assert bronze["source_row_id"].to_list() == [0, 1, 2]
    duplicates = bronze.filter(pl.col("PULocationID") == 132)
    assert duplicates.drop("source_row_id").is_duplicated().all()
    assert duplicates["source_row_id"].to_list() == [0, 1]


def test_to_bronze_empty_input_keeps_columns_and_types() -> None:
    source = pl.DataFrame(schema=SOURCE_SCHEMA)

    bronze = bronze_of(source)

    assert bronze.height == 0
    assert set(LINEAGE_COLUMNS) <= set(bronze.columns)
    assert bronze.schema["source_row_id"] == pl.Int64


def test_to_bronze_is_lazy() -> None:
    result = to_bronze(
        make_source().lazy(),
        month=MONTH,
        source_object_key=OBJECT_KEY,
        source_sha256=SHA256,
        ingested_at=INGESTED_AT,
    )

    assert isinstance(result, pl.LazyFrame)


@pytest.mark.parametrize("column", LINEAGE_COLUMNS)
def test_to_bronze_rejects_source_column_named_like_a_lineage_column(
    column: str,
) -> None:
    source = make_source().with_columns(pl.lit("original").alias(column))

    with pytest.raises(ValidationError, match=column):
        bronze_of(source)


def test_to_bronze_reports_all_colliding_columns() -> None:
    source = make_source().with_columns(
        pl.lit("x").alias("ingested_at"), pl.lit("y").alias("source_sha256")
    )

    with pytest.raises(ValidationError, match="ingested_at.*source_sha256"):
        bronze_of(source)


def test_to_bronze_rejects_invalid_month() -> None:
    with pytest.raises(ValueError, match="expected YYYY-MM"):
        to_bronze(
            make_source().lazy(),
            month="2025-13",
            source_object_key=OBJECT_KEY,
            source_sha256=SHA256,
            ingested_at=INGESTED_AT,
        )

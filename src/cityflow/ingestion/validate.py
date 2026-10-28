from pathlib import Path

import polars as pl

from cityflow.ingestion.download import build_source_url


class ValidationError(Exception):
    """Raised when a downloaded file does not meet the raw data contract."""


REQUIRED_COLUMNS: dict[str, pl.DataType] = {
    "trip_distance": pl.Float64(),
    "fare_amount": pl.Float64(),
    "total_amount": pl.Float64(),
    "tpep_pickup_datetime": pl.Datetime(time_unit="us"),
    "tpep_dropoff_datetime": pl.Datetime(time_unit="us"),
    "PULocationID": pl.Int32(),
    "DOLocationID": pl.Int32(),
}


def check_not_empty(path: Path) -> None:
    if path.stat().st_size == 0:
        raise ValidationError(f"{path} is empty")


def check_schema(path: Path) -> None:
    try:
        schema = pl.read_parquet_schema(path)
    except pl.exceptions.PolarsError as e:
        raise ValidationError(f"{path} is not a readable Parquet file") from e

    missing = []
    wrong_types = []
    for name, expected_type in REQUIRED_COLUMNS.items():
        if name not in schema:
            missing.append(name)
        elif expected_type != schema[name]:
            wrong_types.append(f"{name} (expected {expected_type}, got {schema[name]})")

    problems = []
    if missing:
        problems.append("missing: " + ", ".join(missing))
    if wrong_types:
        problems.append("wrong types: " + ", ".join(wrong_types))
    if problems:
        raise ValidationError(f"{path}: {'; '.join(problems)}")


def check_source_url(url: str, month: str) -> None:
    expected_url = build_source_url(month)
    if url != expected_url:
        raise ValidationError(f"Unexpected source URL: expected {expected_url}, got {url}")

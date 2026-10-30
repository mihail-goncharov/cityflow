import json
import logging
from pathlib import Path

import polars as pl

from cityflow.build_manifest import PROJECT_ROOT, sha256_of
from cityflow.ingestion.download import build_source_url

BASELINE_FILE = PROJECT_ROOT / "docs" / "source_manifest.json"
logger = logging.getLogger(__name__)


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


def check_checksum(path: Path, month: str, baseline_path: Path = BASELINE_FILE) -> str:
    with open(baseline_path, encoding="utf-8") as file:
        source_manifest = json.load(file)

    path_sha256 = sha256_of(path)
    if source_manifest["source_month"] == month and source_manifest["sha256"] != path_sha256:
        logger.warning("Checksum for %s differs from baseline: expected %s, got %s",
                       month, source_manifest["sha256"], path_sha256)

    return path_sha256


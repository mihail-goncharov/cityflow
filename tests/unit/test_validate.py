import json
from datetime import datetime
from pathlib import Path

import polars as pl
import pytest

from cityflow.build_manifest import sha256_of
from cityflow.ingestion.validate import (
    REQUIRED_COLUMNS,
    ValidationError,
    build_source_url,
    check_checksum,
    check_not_empty,
    check_schema,
    check_source_url,
)


@pytest.fixture()
def tmp_file(tmp_path) -> Path:
    return tmp_path / "file.parquet"


@pytest.fixture()
def data_file(tmp_path) -> Path:
    file = tmp_path / "data_file.parquet"
    file.write_bytes(b"Content")
    return file


def fake_baseline(path: Path, month: str, sha256: str) -> Path:
    with open(path, mode="w", encoding="utf-8") as file:
        json.dump({"source_month": month, "sha256": sha256}, file)

    return path


def valid_trips() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "tpep_pickup_datetime": [datetime(2025, 1, 1, 10, 0)],
            "tpep_dropoff_datetime": [datetime(2025, 1, 1, 10, 15)],
            "PULocationID": [132],
            "DOLocationID": [236],
            "trip_distance": [3.2],
            "fare_amount": [17.5],
            "total_amount": [24.8],
        },
        schema=REQUIRED_COLUMNS
    )


def test_check_not_empty_empty_file_raises_validation_error(tmp_file):
    tmp_file.write_bytes(b"")

    with pytest.raises(ValidationError):
        check_not_empty(tmp_file)


def test_check_schema_not_parquet_raises_validation_error(tmp_file):
    tmp_file.write_text("not parquet")

    with pytest.raises(ValidationError):
        check_schema(tmp_file)


def test_check_schema_valid_file_passes(tmp_file):
    valid_trips().write_parquet(tmp_file)
    check_schema(tmp_file)


def test_check_schema_missing_column_raises_validation_error(tmp_file):
    df = valid_trips().drop("fare_amount")
    df.write_parquet(tmp_file)

    with pytest.raises(ValidationError, match="fare_amount"):
        check_schema(tmp_file)


def test_check_schema_wrong_type_raises_validation_error(tmp_file):
    df = valid_trips().cast({"fare_amount": pl.Float32})
    df.write_parquet(tmp_file)

    with pytest.raises(ValidationError, match="fare_amount"):
        check_schema(tmp_file)


def test_check_source_url_matching_url_passes():
    check_source_url(build_source_url("2025-01"), "2025-01")


def test_check_source_url_wrong_month_raises_validation_error():
    with pytest.raises(ValidationError, match="Unexpected source URL"):
        check_source_url(build_source_url("2025-01"), "2025-02")


def test_check_checksum_matching_baseline_logs_no_warning(tmp_path, data_file, caplog):
    data_file_hash = sha256_of(data_file)
    baseline = fake_baseline(tmp_path / "baseline.json", "2025-01", data_file_hash)
    result = check_checksum(data_file, "2025-01", baseline_path=baseline)

    assert data_file_hash == result
    assert not caplog.records


def test_check_checksum_different_hash_logs_warning(tmp_path, data_file, caplog):
    fake_hash = sha256_of(data_file) + "0"
    baseline = fake_baseline(tmp_path / "baseline.json", "2025-01", fake_hash)
    result = check_checksum(data_file, "2025-01", baseline_path=baseline)

    assert result == sha256_of(data_file)
    assert "differs from baseline" in caplog.text


def test_check_checksum_different_month_logs_no_warning(tmp_path, data_file, caplog):
    fake_hash = sha256_of(data_file) + "0"
    baseline = fake_baseline(tmp_path / "baseline.json", "2025-01", fake_hash)
    result = check_checksum(data_file, "2025-02", baseline_path=baseline)

    assert result == sha256_of(data_file)
    assert not caplog.records
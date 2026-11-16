import dataclasses
from pathlib import Path

import polars as pl
import pytest

from cityflow.build_manifest import sha256_of
from cityflow.ingestion.manifest import (
    build_manifest,
    build_manifest_key,
    write_manifest,
)
from cityflow.ingestion.pipeline import build_object_key
from cityflow.ingestion.validate import ValidationError
from cityflow.storage.s3_adapter import S3StorageAdapter
from cityflow.transform.pipeline import (
    TransformInputError,
    read_raw_input,
)

MONTH = "2025-01"
FILENAME = f"yellow_tripdata_{MONTH}.parquet"
OBJECT_KEY = build_object_key(MONTH, FILENAME)


def publish_raw(
    adapter: S3StorageAdapter,
    local_path: Path,
    *,
    status: str = "published",
    manifest_sha256: str | None = None,
) -> None:
    """Upload a local file as the Raw object, with a Raw manifest."""
    adapter.upload_object(local_path, OBJECT_KEY)
    manifest = build_manifest(
        bucket=adapter.bucket,
        object_key=OBJECT_KEY,
        sha256=manifest_sha256 or sha256_of(local_path),
        url="https://example.test/file.parquet",
        month=MONTH,
        local_path=local_path,
    )
    manifest = dataclasses.replace(manifest, publication_status=status)  # type: ignore[type-var,arg-type]
    write_manifest(adapter, build_manifest_key(OBJECT_KEY), manifest)


@pytest.fixture()
def raw_file(tmp_path: Path, valid_trips: pl.DataFrame) -> Path:
    path = tmp_path / "source" / FILENAME
    path.parent.mkdir()
    valid_trips.write_parquet(path)
    return path


def test_read_raw_input_returns_the_verified_copy_and_lineage(
    adapter: S3StorageAdapter, tmp_path: Path, raw_file: Path
) -> None:
    publish_raw(adapter, raw_file)
    work_dir = tmp_path / "work"
    work_dir.mkdir()

    raw = read_raw_input(adapter, MONTH, work_dir)

    assert raw.path == work_dir / FILENAME
    assert raw.path.read_bytes() == raw_file.read_bytes()
    assert raw.month == MONTH
    assert raw.object_key == OBJECT_KEY
    assert raw.sha256 == sha256_of(raw_file)
    assert raw.ingested_at  # copied from the Raw manifest


def test_read_raw_input_rejects_an_invalid_month(
    adapter: S3StorageAdapter, tmp_path: Path
) -> None:
    with pytest.raises(ValueError, match="Invalid month"):
        read_raw_input(adapter, "2025-13", tmp_path)


def test_read_raw_input_without_a_manifest_asks_to_ingest_first(
    adapter: S3StorageAdapter, tmp_path: Path
) -> None:
    with pytest.raises(TransformInputError, match="ingest the month first"):
        read_raw_input(adapter, MONTH, tmp_path)


def test_read_raw_input_with_a_pending_manifest_fails(
    adapter: S3StorageAdapter, tmp_path: Path, raw_file: Path
) -> None:
    publish_raw(adapter, raw_file, status="pending")

    with pytest.raises(TransformInputError, match="not published yet"):
        read_raw_input(adapter, MONTH, tmp_path)


def test_read_raw_input_fails_when_the_object_does_not_match_the_manifest(
    adapter: S3StorageAdapter, tmp_path: Path, raw_file: Path
) -> None:
    publish_raw(adapter, raw_file, manifest_sha256="0" * 64)

    with pytest.raises(TransformInputError, match="does not match its manifest"):
        read_raw_input(adapter, MONTH, tmp_path)


def test_read_raw_input_fails_when_a_required_column_is_missing(
    adapter: S3StorageAdapter, tmp_path: Path, raw_file: Path
) -> None:
    pl.read_parquet(raw_file).drop("fare_amount").write_parquet(raw_file)
    publish_raw(adapter, raw_file)

    with pytest.raises(ValidationError, match="missing: fare_amount"):
        read_raw_input(adapter, MONTH, tmp_path)


def test_read_raw_input_fails_for_a_file_that_is_not_parquet(
    adapter: S3StorageAdapter, tmp_path: Path, raw_file: Path
) -> None:
    raw_file.write_bytes(b"this is not parquet")
    publish_raw(adapter, raw_file)

    with pytest.raises(ValidationError, match="not a readable Parquet file"):
        read_raw_input(adapter, MONTH, tmp_path)


def test_read_raw_input_does_not_change_the_raw_object(
    adapter: S3StorageAdapter, tmp_path: Path, raw_file: Path
) -> None:
    publish_raw(adapter, raw_file)
    before = adapter.read_bytes(OBJECT_KEY)

    read_raw_input(adapter, MONTH, tmp_path)

    assert adapter.read_bytes(OBJECT_KEY) == before

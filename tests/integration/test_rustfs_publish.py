"""Publish to a real RustFS bucket; never part of the default test run.

Run explicitly, with the SSH tunnel open (see README, "Object storage (RustFS)"):

    uv run --env-file .env pytest -m rustfs --no-cov

Every run works under its own ``integration-tests/<random>/`` prefix, so the
protected ``raw/`` data is never read, overwritten or deleted.
"""

import os
import uuid
from collections.abc import Iterator
from pathlib import Path

import polars as pl
import pytest

from cityflow.build_manifest import sha256_of
from cityflow.ingestion.manifest import build_manifest_key, read_manifest
from cityflow.ingestion.publish import (
    PublicationError,
    PublishOutcome,
    publish_raw_file,
)
from cityflow.storage.s3_adapter import S3StorageAdapter, create_s3_client

REQUIRED_ENV = ("S3_BUCKET", "S3_ENDPOINT_URL", "S3_ACCESS_KEY", "S3_SECRET_KEY")
MISSING_ENV = [name for name in REQUIRED_ENV if not os.environ.get(name)]
MONTH = "2025-01"
FILENAME = "yellow_tripdata_2025-01.parquet"
URL = "https://example.invalid/yellow_tripdata_2025-01.parquet"

pytestmark = [
    pytest.mark.rustfs,
    pytest.mark.skipif(bool(MISSING_ENV), reason=f"Missing environment: {MISSING_ENV}"),
]


@pytest.fixture
def rustfs() -> Iterator[tuple[S3StorageAdapter, str]]:
    """Real storage adapter plus a unique key prefix owned by this test."""
    storage = S3StorageAdapter(os.environ["S3_BUCKET"], create_s3_client())
    prefix = f"integration-tests/{uuid.uuid4().hex}"
    yield storage, prefix
    for object_key in storage.list_objects(prefix):
        storage.delete_object(object_key)


def publish(
    storage: S3StorageAdapter, key: str, local_path: Path, work_dir: Path
) -> PublishOutcome:
    return publish_raw_file(
        storage=storage,
        object_key=key,
        sha256=sha256_of(local_path),
        url=URL,
        month=MONTH,
        work_dir=work_dir,
        local_path=local_path,
    )


def test_publish_twice_leaves_one_object_and_skips(
    rustfs: tuple[S3StorageAdapter, str], valid_trips: pl.DataFrame, tmp_path: Path
) -> None:
    storage, prefix = rustfs
    key = f"{prefix}/raw/nyc_tlc/yellow_taxi/year=2025/month=01/{FILENAME}"
    manifest_key = build_manifest_key(key)
    local_path = tmp_path / FILENAME
    valid_trips.write_parquet(local_path)

    first = publish(storage, key, local_path, tmp_path)
    second = publish(storage, key, local_path, tmp_path)

    manifest = read_manifest(storage, manifest_key)
    downloaded = tmp_path / "downloaded.parquet"
    storage.download_object(key, downloaded)
    assert first == "published"
    assert second == "skipped"
    assert manifest is not None
    assert manifest.publication_status == "published"
    assert manifest.object_key == key
    assert manifest.sha256 == sha256_of(local_path)
    assert manifest.size_bytes == local_path.stat().st_size
    assert downloaded.read_bytes() == local_path.read_bytes()
    assert sorted(storage.list_objects(prefix)) == sorted([key, manifest_key])


def test_checksum_conflict_keeps_published_object_and_manifest(
    rustfs: tuple[S3StorageAdapter, str], valid_trips: pl.DataFrame, tmp_path: Path
) -> None:
    storage, prefix = rustfs
    key = f"{prefix}/raw/nyc_tlc/yellow_taxi/year=2025/month=01/{FILENAME}"
    manifest_key = build_manifest_key(key)
    original = tmp_path / FILENAME
    valid_trips.write_parquet(original)
    publish(storage, key, original, tmp_path)
    manifest_before = storage.read_bytes(manifest_key)
    other_dir = tmp_path / "other"
    other_dir.mkdir()
    different = other_dir / FILENAME
    different.write_bytes(b"different bytes, different SHA-256")

    with pytest.raises(PublicationError):
        publish(storage, key, different, other_dir)

    downloaded = tmp_path / "downloaded.parquet"
    storage.download_object(key, downloaded)
    assert downloaded.read_bytes() == original.read_bytes()
    assert storage.read_bytes(manifest_key) == manifest_before

from pathlib import Path

import pytest

from cityflow.build_manifest import sha256_of
from cityflow.ingestion.manifest import (
    build_manifest,
    build_manifest_key,
    read_manifest,
    write_manifest,
)
from cityflow.ingestion.publish import (
    PublicationError,
    PublishOutcome,
    publish_raw_file,
    verify_remote_object,
)
from cityflow.storage.s3_adapter import S3StorageAdapter

CONTENT = b"Content"
KEY = "raw/test/data.parquet"
MANIFEST_KEY = build_manifest_key(KEY)


def _publish(
    adapter: S3StorageAdapter, local_path: Path, work_dir: Path
) -> PublishOutcome:
    return publish_raw_file(
        storage=adapter,
        object_key=KEY,
        sha256=sha256_of(local_path),
        url="test-url",
        month="2025-01",
        work_dir=work_dir,
        local_path=local_path,
    )


def _write_pending_manifest(adapter: S3StorageAdapter, local_path: Path) -> None:
    manifest = build_manifest(
        bucket=adapter.bucket,
        object_key=KEY,
        sha256=sha256_of(local_path),
        url="test-url",
        month="2025-01",
        local_path=local_path,
    )
    write_manifest(adapter, MANIFEST_KEY, manifest)


def test_verify_remote_object_matches(adapter, tmp_path, tmp_file):
    tmp_file.write_bytes(CONTENT)
    expected_hash = sha256_of(tmp_file)

    adapter.upload_object(tmp_file, KEY)
    verify_remote_object(adapter, KEY, expected_hash, tmp_path)

    assert list(tmp_path.glob("*.verify")) == []


def test_verify_remote_object_mismatched_hash_raises_publication_error(
    adapter, tmp_path, tmp_file
):
    tmp_file.write_bytes(CONTENT)
    wrong_hash = "0" * 64

    adapter.upload_object(tmp_file, KEY)

    with pytest.raises(PublicationError):
        verify_remote_object(adapter, KEY, wrong_hash, tmp_path)

    assert list(tmp_path.glob("*.verify")) == []


def test_publish_raw_file_without_manifest_publishes(adapter, tmp_path, tmp_file):
    tmp_file.write_bytes(CONTENT)

    status = _publish(adapter, tmp_file, tmp_path)
    manifest = read_manifest(adapter, MANIFEST_KEY)
    sha256 = sha256_of(tmp_file)

    assert manifest is not None
    assert status == "published"
    assert manifest.publication_status == "published"
    assert manifest.sha256 == sha256
    assert manifest.object_key == KEY

    verify_remote_object(adapter, KEY, sha256, tmp_path)


def test_publish_raw_file_twice_return_skipped(adapter, tmp_path, tmp_file):
    tmp_file.write_bytes(CONTENT)

    first_publish = _publish(adapter, tmp_file, tmp_path)
    manifest1 = read_manifest(adapter, MANIFEST_KEY)

    second_publish = _publish(adapter, tmp_file, tmp_path)
    manifest2 = read_manifest(adapter, MANIFEST_KEY)

    assert first_publish == "published"
    assert second_publish == "skipped"
    assert manifest1 == manifest2


def test_publish_raw_file_different_sha256_raises_publication_error(
    adapter, tmp_path, tmp_file
):
    tmp_file.write_bytes(CONTENT)
    valid_sha256 = sha256_of(tmp_file)

    _publish(adapter, tmp_file, tmp_path)
    manifest = read_manifest(adapter, MANIFEST_KEY)

    tmp_file.write_bytes(b"new_content")
    with pytest.raises(PublicationError, match="already published"):
        _publish(adapter, tmp_file, tmp_path)

    verify_remote_object(adapter, KEY, valid_sha256, tmp_path)

    assert read_manifest(adapter, MANIFEST_KEY) == manifest


def test_publish_raw_file_pending_with_valid_object_recovers(
    adapter, tmp_path, tmp_file
):
    tmp_file.write_bytes(CONTENT)
    _write_pending_manifest(adapter, tmp_file)
    adapter.upload_object(tmp_file, KEY)

    outcome = _publish(adapter, tmp_file, tmp_path)
    manifest = read_manifest(adapter, MANIFEST_KEY)

    assert manifest is not None
    assert outcome == "recovered"
    assert manifest.sha256 == sha256_of(tmp_file)
    assert manifest.publication_status == "published"


def test_publish_raw_file_pending_without_object_publishes_again(
    adapter, tmp_path, tmp_file
):
    tmp_file.write_bytes(CONTENT)
    sha256 = sha256_of(tmp_file)
    _write_pending_manifest(adapter, tmp_file)

    outcome = _publish(adapter, tmp_file, tmp_path)
    manifest = read_manifest(adapter, MANIFEST_KEY)

    assert outcome == "published"
    assert manifest is not None
    assert manifest.publication_status == "published"
    assert manifest.sha256 == sha256

    verify_remote_object(adapter, KEY, sha256, tmp_path)

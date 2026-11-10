from pathlib import Path

import pytest

import cityflow.ingestion.publish as publish_module
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
from cityflow.storage.s3_adapter import S3StorageAdapter, StorageError

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


def test_publish_raw_file_pending_with_different_sha256_raises_publication_error(
    adapter, tmp_path, tmp_file
):
    tmp_file.write_bytes(CONTENT)
    pending_sha256 = sha256_of(tmp_file)
    _write_pending_manifest(adapter, tmp_file)
    adapter.upload_object(tmp_file, KEY)
    manifest = read_manifest(adapter, MANIFEST_KEY)

    tmp_file.write_bytes(b"new_content")
    with pytest.raises(PublicationError, match="pending"):
        _publish(adapter, tmp_file, tmp_path)

    verify_remote_object(adapter, KEY, pending_sha256, tmp_path)

    assert read_manifest(adapter, MANIFEST_KEY) == manifest


def test_publish_raw_file_run_started_while_another_is_pending_does_not_overwrite(
    adapter, tmp_path, tmp_file, monkeypatch
):
    # Run A uploads and verifies its file. Before A writes "published",
    # run B starts with different bytes for the same month.
    tmp_file.write_bytes(CONTENT)
    other_file = tmp_path / "other.parquet"
    other_file.write_bytes(b"other_content")
    original_verify = publish_module.verify_remote_object
    other_run: dict[str, PublicationError | bool | None] = {
        "started": False,
        "error": None,
    }

    def verify_then_start_other_run(storage, key, expected_sha256, work_dir):
        original_verify(storage, key, expected_sha256, work_dir)
        if not other_run["started"]:
            other_run["started"] = True
            try:
                _publish(adapter, other_file, tmp_path)
            except PublicationError as error:
                other_run["error"] = error

    monkeypatch.setattr(publish_module, "verify_remote_object", verify_then_start_other_run)
    outcome = _publish(adapter, tmp_file, tmp_path)
    monkeypatch.undo()

    manifest = read_manifest(adapter, MANIFEST_KEY)

    assert outcome == "published"
    assert isinstance(other_run["error"], PublicationError)
    assert manifest is not None
    assert manifest.sha256 == sha256_of(tmp_file)
    verify_remote_object(adapter, KEY, manifest.sha256, tmp_path)


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


def test_publish_raw_file_upload_failure_then_rerun_publishes(
    adapter, tmp_path, tmp_file, monkeypatch
):
    tmp_file.write_bytes(CONTENT)

    def fake_upload_object(local_path: Path, key: str) -> None:
        raise StorageError("Simulated upload failure")

    monkeypatch.setattr(adapter, "upload_object", fake_upload_object)
    with pytest.raises(StorageError, match="Simulated"):
        _publish(adapter, tmp_file, tmp_path)
    monkeypatch.undo()

    manifest_after_failure = read_manifest(adapter, MANIFEST_KEY)
    second_publish = _publish(adapter, tmp_file, tmp_path)

    assert second_publish == "published"
    assert manifest_after_failure is not None
    assert manifest_after_failure.publication_status == "pending"

    verify_remote_object(adapter, KEY, sha256_of(tmp_file), tmp_path)


def test_publish_raw_file_manifest_write_failure_then_rerun_recovers(
    adapter, tmp_path, tmp_file, monkeypatch
):
    tmp_file.write_bytes(CONTENT)
    original_write = adapter.write_bytes
    calls = []

    def fake_write_bytes(key: str, data: bytes) -> None:
        calls.append(key)
        if len(calls) == 1:
            original_write(key, data)
        else:
            raise StorageError("Simulated manifest write failure")

    monkeypatch.setattr(adapter, "write_bytes", fake_write_bytes)
    with pytest.raises(StorageError, match="Simulated manifest"):
        _publish(adapter, tmp_file, tmp_path)
    monkeypatch.undo()
    verify_remote_object(adapter, KEY, sha256_of(tmp_file), tmp_path)

    manifest_after_failure = read_manifest(adapter, MANIFEST_KEY)
    second_publish = _publish(adapter, tmp_file, tmp_path)
    manifest_after_rerun = read_manifest(adapter, MANIFEST_KEY)

    assert manifest_after_failure is not None
    assert manifest_after_failure.publication_status == "pending"
    assert manifest_after_rerun is not None
    assert manifest_after_rerun.publication_status == "published"
    assert second_publish == "recovered"

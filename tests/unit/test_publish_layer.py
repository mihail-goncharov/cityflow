import hashlib
from pathlib import Path
from typing import Any

import pytest

from cityflow.ingestion.publish import PublicationError
from cityflow.storage.s3_adapter import S3StorageAdapter, StorageError
from cityflow.transform.layer_manifest import read_layer_manifest
from cityflow.transform.layers import (
    Layer,
    build_layer_folder,
    build_layer_key,
    build_layer_manifest_key,
)
from cityflow.transform.publish import publish_layer

MONTH = "2025-01"
RAW_KEY = "raw/nyc_tlc/yellow_taxi/year=2025/month=01/yellow_tripdata_2025-01.parquet"
RAW_SHA = "a" * 64
RAW_BYTES = b"original raw file"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def publish(
    adapter: S3StorageAdapter,
    tmp_path: Path,
    content: bytes,
    *,
    layer: Layer = "silver",
    row_count: int = 3,
) -> None:
    local_path = tmp_path / "out.parquet"
    local_path.write_bytes(content)
    publish_layer(
        storage=adapter,
        layer=layer,
        month=MONTH,
        local_path=local_path,
        source_object_key=RAW_KEY,
        source_sha256=RAW_SHA,
        row_count=row_count,
        work_dir=tmp_path,
    )


def stored_manifest(adapter: S3StorageAdapter, layer: Layer = "silver") -> Any:
    return read_layer_manifest(adapter, build_layer_manifest_key(layer, MONTH))


def test_publish_layer_stores_the_data_object_and_a_published_manifest(
    adapter: S3StorageAdapter, tmp_path: Path
) -> None:
    publish(adapter, tmp_path, b"silver rows", row_count=5)

    assert adapter.read_bytes(build_layer_key("silver", MONTH)) == b"silver rows"
    manifest = stored_manifest(adapter)
    assert manifest.publication_status == "published"
    assert manifest.layer == "silver"
    assert manifest.source_month == MONTH
    assert manifest.source_object_key == RAW_KEY
    assert manifest.source_sha256 == RAW_SHA
    assert manifest.row_count == 5
    assert manifest.sha256 == sha256(b"silver rows")
    assert manifest.size_bytes == len(b"silver rows")


@pytest.mark.parametrize("layer", ["bronze", "silver", "quarantine"])
def test_publish_layer_writes_to_the_folder_of_its_layer(
    adapter: S3StorageAdapter, tmp_path: Path, layer: Layer
) -> None:
    publish(adapter, tmp_path, b"rows", layer=layer)

    folder = build_layer_folder(layer, MONTH)
    assert sorted(adapter.list_objects("")) == [
        f"{folder}/manifest.json",
        f"{folder}/yellow_tripdata.parquet",
    ]


def test_publish_layer_does_not_touch_the_raw_object(
    adapter: S3StorageAdapter, tmp_path: Path
) -> None:
    adapter.write_bytes(RAW_KEY, RAW_BYTES)

    publish(adapter, tmp_path, b"silver rows")

    assert adapter.read_bytes(RAW_KEY) == RAW_BYTES
    assert build_layer_key("silver", MONTH) != RAW_KEY


def test_rerun_overwrites_the_object_and_leaves_no_second_file(
    adapter: S3StorageAdapter, tmp_path: Path
) -> None:
    publish(adapter, tmp_path, b"first run", row_count=1)
    keys_after_first = sorted(adapter.list_objects(""))

    publish(adapter, tmp_path, b"second run", row_count=2)

    assert sorted(adapter.list_objects("")) == keys_after_first
    assert adapter.read_bytes(build_layer_key("silver", MONTH)) == b"second run"
    manifest = stored_manifest(adapter)
    assert manifest.publication_status == "published"
    assert manifest.row_count == 2
    assert manifest.sha256 == sha256(b"second run")


def test_rerun_with_the_same_file_gives_the_same_logical_result(
    adapter: S3StorageAdapter, tmp_path: Path
) -> None:
    publish(adapter, tmp_path, b"same rows")
    first = stored_manifest(adapter)

    publish(adapter, tmp_path, b"same rows")
    second = stored_manifest(adapter)

    assert (second.sha256, second.row_count, second.publication_status) == (
        first.sha256,
        first.row_count,
        "published",
    )


def test_manifest_is_pending_while_the_object_is_being_uploaded(
    adapter: S3StorageAdapter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []
    original_upload = adapter.upload_object

    def upload_and_look(local_path: Path, key: str) -> None:
        seen.append(stored_manifest(adapter).publication_status)
        original_upload(local_path, key)

    monkeypatch.setattr(adapter, "upload_object", upload_and_look)

    publish(adapter, tmp_path, b"rows")

    assert seen == ["pending"]


def test_corrupted_upload_raises_and_the_manifest_stays_pending(
    adapter: S3StorageAdapter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def upload_other_bytes(local_path: Path, key: str) -> None:
        adapter.write_bytes(key, b"corrupted")

    monkeypatch.setattr(adapter, "upload_object", upload_other_bytes)

    with pytest.raises(PublicationError, match="does not match"):
        publish(adapter, tmp_path, b"good rows")

    assert stored_manifest(adapter).publication_status == "pending"


def test_upload_failure_leaves_a_pending_manifest_and_a_rerun_completes(
    adapter: S3StorageAdapter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_upload(local_path: Path, key: str) -> None:
        raise StorageError("boom")

    monkeypatch.setattr(adapter, "upload_object", failing_upload)
    with pytest.raises(StorageError):
        publish(adapter, tmp_path, b"rows")
    monkeypatch.undo()

    assert stored_manifest(adapter).publication_status == "pending"
    assert adapter.read_bytes(build_layer_key("silver", MONTH)) is None

    publish(adapter, tmp_path, b"rows")

    assert stored_manifest(adapter).publication_status == "published"
    assert adapter.read_bytes(build_layer_key("silver", MONTH)) == b"rows"


def test_failure_while_writing_the_published_manifest_stays_pending(
    adapter: S3StorageAdapter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_write = adapter.write_bytes
    calls: list[str] = []

    def fail_second_write(key: str, data: bytes) -> None:
        calls.append(key)
        if len(calls) == 2:
            raise StorageError("boom")
        original_write(key, data)

    monkeypatch.setattr(adapter, "write_bytes", fail_second_write)

    with pytest.raises(StorageError):
        publish(adapter, tmp_path, b"rows")
    monkeypatch.undo()

    assert stored_manifest(adapter).publication_status == "pending"
    assert adapter.read_bytes(build_layer_key("silver", MONTH)) == b"rows"


def test_layers_do_not_overwrite_each_other(
    adapter: S3StorageAdapter, tmp_path: Path
) -> None:
    publish(adapter, tmp_path, b"bronze rows", layer="bronze")
    publish(adapter, tmp_path, b"silver rows", layer="silver")

    assert adapter.read_bytes(build_layer_key("bronze", MONTH)) == b"bronze rows"
    assert adapter.read_bytes(build_layer_key("silver", MONTH)) == b"silver rows"
    assert stored_manifest(adapter, "bronze").sha256 == sha256(b"bronze rows")
    assert stored_manifest(adapter, "silver").sha256 == sha256(b"silver rows")

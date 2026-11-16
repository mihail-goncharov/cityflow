from pathlib import Path

import pytest

from cityflow.storage.s3_adapter import S3StorageAdapter, StorageError
from cityflow.transform.layers import (
    Layer,
    build_layer_folder,
    build_layer_key,
    build_layer_manifest_key,
    build_quality_summary_key,
)
from cityflow.transform.publish import publish_layer, remove_stale_objects

MONTH = "2025-01"
RAW_KEY = "raw/nyc_tlc/yellow_taxi/year=2025/month=01/yellow_tripdata_2025-01.parquet"


def publish(adapter: S3StorageAdapter, tmp_path: Path, layer: Layer = "silver") -> None:
    local_path = tmp_path / "out.parquet"
    local_path.write_bytes(b"rows")
    publish_layer(
        storage=adapter,
        layer=layer,
        month=MONTH,
        local_path=local_path,
        source_object_key=RAW_KEY,
        source_sha256="a" * 64,
        row_count=1,
        work_dir=tmp_path,
    )


def remove(adapter: S3StorageAdapter, layer: Layer = "silver") -> list[str]:
    return remove_stale_objects(storage=adapter, layer=layer, month=MONTH)


def test_stale_file_is_removed_and_the_expected_objects_stay(
    adapter: S3StorageAdapter, tmp_path: Path
) -> None:
    publish(adapter, tmp_path)
    stale_key = f"{build_layer_folder('silver', MONTH)}/part-0.parquet"
    adapter.write_bytes(stale_key, b"old run")

    deleted = remove(adapter)

    assert deleted == [stale_key]
    assert sorted(adapter.list_objects("")) == sorted(
        [
            build_layer_key("silver", MONTH),
            build_layer_manifest_key("silver", MONTH),
        ]
    )


def test_nothing_is_deleted_when_the_folder_is_clean(
    adapter: S3StorageAdapter, tmp_path: Path
) -> None:
    publish(adapter, tmp_path)
    before = sorted(adapter.list_objects(""))

    assert remove(adapter) == []
    assert sorted(adapter.list_objects("")) == before


def test_empty_folder_is_fine(adapter: S3StorageAdapter) -> None:
    assert remove(adapter) == []


def test_silver_keeps_its_quality_summary(
    adapter: S3StorageAdapter, tmp_path: Path
) -> None:
    publish(adapter, tmp_path)
    adapter.write_bytes(build_quality_summary_key(MONTH), b"{}")

    assert remove(adapter) == []
    assert adapter.read_bytes(build_quality_summary_key(MONTH)) == b"{}"


@pytest.mark.parametrize("layer", ["bronze", "quarantine"])
def test_a_summary_file_in_another_layer_is_stale(
    adapter: S3StorageAdapter, tmp_path: Path, layer: Layer
) -> None:
    publish(adapter, tmp_path, layer=layer)
    summary_key = f"{build_layer_folder(layer, MONTH)}/quality_summary.json"
    adapter.write_bytes(summary_key, b"{}")

    assert remove(adapter, layer) == [summary_key]


def test_other_layers_months_and_raw_are_not_touched(
    adapter: S3StorageAdapter, tmp_path: Path
) -> None:
    publish(adapter, tmp_path, layer="bronze")
    publish(adapter, tmp_path, layer="silver")
    untouched = [
        RAW_KEY,
        f"{build_layer_folder('bronze', MONTH)}/extra.parquet",
        f"{build_layer_folder('silver', '2025-02')}/yellow_tripdata.parquet",
        f"{build_layer_folder('silver', '2025-10')}/yellow_tripdata.parquet",
    ]
    for key in untouched:
        adapter.write_bytes(key, b"keep me")

    assert remove(adapter, "silver") == []

    for key in untouched:
        assert adapter.read_bytes(key) == b"keep me"


def test_a_folder_with_a_longer_name_is_not_matched_by_prefix(
    adapter: S3StorageAdapter,
) -> None:
    # month=01 must not match month=010, which has the same text prefix.
    folder = build_layer_folder("silver", MONTH)
    lookalike = f"{folder}0/yellow_tripdata.parquet"
    adapter.write_bytes(lookalike, b"keep me")

    assert remove(adapter) == []
    assert adapter.read_bytes(lookalike) == b"keep me"


def test_several_stale_files_are_all_removed(
    adapter: S3StorageAdapter, tmp_path: Path
) -> None:
    publish(adapter, tmp_path)
    folder = build_layer_folder("silver", MONTH)
    stale = [f"{folder}/a.parquet", f"{folder}/sub/b.parquet", f"{folder}/c.tmp"]
    for key in stale:
        adapter.write_bytes(key, b"old")

    assert sorted(remove(adapter)) == sorted(stale)
    assert adapter.list_objects(f"{folder}/") == sorted(
        [build_layer_key("silver", MONTH), build_layer_manifest_key("silver", MONTH)]
    )


def test_delete_failure_is_raised_not_swallowed(
    adapter: S3StorageAdapter, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publish(adapter, tmp_path)
    adapter.write_bytes(f"{build_layer_folder('silver', MONTH)}/old.parquet", b"x")

    def failing_delete(key: str) -> None:
        raise StorageError("boom")

    monkeypatch.setattr(adapter, "delete_object", failing_delete)

    with pytest.raises(StorageError):
        remove(adapter)

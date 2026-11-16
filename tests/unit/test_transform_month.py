import dataclasses
import hashlib
import json
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from cityflow.build_manifest import sha256_of
from cityflow.ingestion.manifest import (
    build_manifest,
    build_manifest_key,
    write_manifest,
)
from cityflow.ingestion.pipeline import build_object_key
from cityflow.storage.s3_adapter import S3StorageAdapter
from cityflow.transform import pipeline as pipeline_module
from cityflow.transform.layer_manifest import read_layer_manifest
from cityflow.transform.layers import (
    Layer,
    build_layer_folder,
    build_layer_key,
    build_layer_manifest_key,
    build_quality_summary_key,
)
from cityflow.transform.pipeline import TransformInputError, transform_month
from cityflow.transform.silver import MONEY_COLUMNS
from cityflow.transform.summary import CountMismatchError

MONTH = "2025-01"
FILENAME = f"yellow_tripdata_{MONTH}.parquet"
RAW_KEY = build_object_key(MONTH, FILENAME)
LAYERS: list[Layer] = ["bronze", "quarantine", "silver"]

SCHEMA: dict[str, Any] = {
    "VendorID": pl.Int32,
    "tpep_pickup_datetime": pl.Datetime("us"),
    "tpep_dropoff_datetime": pl.Datetime("us"),
    "passenger_count": pl.Int64,
    "trip_distance": pl.Float64,
    "RatecodeID": pl.Int64,
    "store_and_fwd_flag": pl.String,
    "PULocationID": pl.Int32,
    "DOLocationID": pl.Int32,
    "payment_type": pl.Int64,
    **dict.fromkeys(MONEY_COLUMNS, pl.Float64),
}


def trip(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "VendorID": 1,
        "tpep_pickup_datetime": datetime(2025, 1, 15, 10, 0),
        "tpep_dropoff_datetime": datetime(2025, 1, 15, 10, 15),
        "passenger_count": 1,
        "trip_distance": 3.2,
        "RatecodeID": 1,
        "store_and_fwd_flag": "N",
        "PULocationID": 132,
        "DOLocationID": 236,
        "payment_type": 1,
        **dict.fromkeys(MONEY_COLUMNS, 1.5),
    }
    row["fare_amount"] = 17.5
    row.update(overrides)
    return row


TRIPS = [
    trip(),
    trip(fare_amount=2000.0),
    trip(),
    trip(fare_amount=-1.0, trip_distance=300.0),
    trip(passenger_count=None, congestion_surcharge=None),
]


def publish_raw(
    adapter: S3StorageAdapter, tmp_path: Path, trips: list[dict[str, Any]]
) -> bytes:
    """Store a Raw file with a published Raw manifest; return the Raw bytes."""
    source = tmp_path / "source" / FILENAME
    source.parent.mkdir(exist_ok=True)
    pl.DataFrame(trips, schema=SCHEMA).write_parquet(source)
    adapter.upload_object(source, RAW_KEY)
    manifest = build_manifest(
        bucket=adapter.bucket,
        object_key=RAW_KEY,
        sha256=sha256_of(source),
        url="https://example.test/file.parquet",
        month=MONTH,
        local_path=source,
    )
    manifest = dataclasses.replace(manifest, publication_status="published")
    write_manifest(adapter, build_manifest_key(RAW_KEY), manifest)
    return source.read_bytes()


def run(
    adapter: S3StorageAdapter, tmp_path: Path, name: str = "work"
) -> dict[str, Any]:
    work_dir = tmp_path / name
    work_dir.mkdir(exist_ok=True)
    return transform_month(adapter, MONTH, work_dir)


def stored_frame(adapter: S3StorageAdapter, layer: Layer) -> pl.DataFrame:
    data = adapter.read_bytes(build_layer_key(layer, MONTH))
    assert data is not None
    return pl.read_parquet(BytesIO(data))


@pytest.fixture()
def raw_bytes(adapter: S3StorageAdapter, tmp_path: Path) -> bytes:
    return publish_raw(adapter, tmp_path, TRIPS)


def test_returns_the_quality_summary(
    adapter: S3StorageAdapter, tmp_path: Path, raw_bytes: bytes
) -> None:
    summary = run(adapter, tmp_path)

    assert summary["source_month"] == MONTH
    assert summary["input_rows"] == 5
    assert summary["accepted_rows"] == 3
    assert summary["rejected_rows"] == 2
    assert summary["rule_counts"]["fare_too_high"] == 1
    assert summary["rule_counts"]["fare_not_positive"] == 1
    assert summary["rule_counts"]["distance_too_high"] == 1
    assert summary["flag_counts"]["has_missing_flex_fields"] == 1


def test_every_layer_is_published_with_its_own_rows(
    adapter: S3StorageAdapter, tmp_path: Path, raw_bytes: bytes
) -> None:
    run(adapter, tmp_path)

    assert stored_frame(adapter, "bronze").height == 5
    assert stored_frame(adapter, "silver")["source_row_id"].to_list() == [0, 2, 4]
    assert stored_frame(adapter, "quarantine")["source_row_id"].to_list() == [1, 3]


@pytest.mark.parametrize("layer", LAYERS)
def test_each_manifest_is_published_and_describes_its_own_object(
    adapter: S3StorageAdapter, tmp_path: Path, raw_bytes: bytes, layer: Layer
) -> None:
    run(adapter, tmp_path)

    manifest = read_layer_manifest(adapter, build_layer_manifest_key(layer, MONTH))
    stored = adapter.read_bytes(build_layer_key(layer, MONTH))

    assert manifest is not None
    assert stored is not None
    assert manifest.publication_status == "published"
    assert manifest.layer == layer
    assert manifest.row_count == stored_frame(adapter, layer).height
    assert manifest.size_bytes == len(stored)


@pytest.mark.parametrize("layer", LAYERS)
def test_each_manifest_points_to_the_raw_file_not_to_the_layer(
    adapter: S3StorageAdapter, tmp_path: Path, raw_bytes: bytes, layer: Layer
) -> None:
    run(adapter, tmp_path)
    raw_manifest_sha = sha256_of_bytes(raw_bytes)

    manifest = read_layer_manifest(adapter, build_layer_manifest_key(layer, MONTH))

    assert manifest is not None
    assert manifest.source_object_key == RAW_KEY
    assert manifest.source_sha256 == raw_manifest_sha
    assert manifest.sha256 != raw_manifest_sha


def test_layer_rows_carry_the_raw_lineage(
    adapter: S3StorageAdapter, tmp_path: Path, raw_bytes: bytes
) -> None:
    run(adapter, tmp_path)
    expected_sha = sha256_of_bytes(raw_bytes)

    for layer in LAYERS:
        frame = stored_frame(adapter, layer)
        assert set(frame["source_object_key"]) == {RAW_KEY}
        assert set(frame["source_sha256"]) == {expected_sha}
        assert set(frame["source_month"]) == {MONTH}


def test_quality_summary_is_stored_next_to_silver(
    adapter: S3StorageAdapter, tmp_path: Path, raw_bytes: bytes
) -> None:
    summary = run(adapter, tmp_path)

    stored = adapter.read_bytes(build_quality_summary_key(MONTH))

    assert stored is not None
    assert json.loads(stored) == summary
    assert build_quality_summary_key(MONTH).startswith(
        build_layer_folder("silver", MONTH)
    )


def test_each_month_folder_holds_only_the_expected_objects(
    adapter: S3StorageAdapter, tmp_path: Path, raw_bytes: bytes
) -> None:
    run(adapter, tmp_path)

    for layer in LAYERS:
        expected = {
            build_layer_key(layer, MONTH),
            build_layer_manifest_key(layer, MONTH),
        }
        if layer == "silver":
            expected.add(build_quality_summary_key(MONTH))
        assert (
            set(adapter.list_objects(f"{build_layer_folder(layer, MONTH)}/"))
            == expected
        )


def test_raw_object_and_manifest_are_not_changed(
    adapter: S3StorageAdapter, tmp_path: Path, raw_bytes: bytes
) -> None:
    raw_manifest_key = build_manifest_key(RAW_KEY)
    manifest_before = adapter.read_bytes(raw_manifest_key)

    run(adapter, tmp_path)

    assert adapter.read_bytes(RAW_KEY) == raw_bytes
    assert adapter.read_bytes(raw_manifest_key) == manifest_before


def test_stale_objects_in_the_layer_folders_are_removed(
    adapter: S3StorageAdapter, tmp_path: Path, raw_bytes: bytes
) -> None:
    stale = [f"{build_layer_folder(layer, MONTH)}/part-0.parquet" for layer in LAYERS]
    for key in stale:
        adapter.write_bytes(key, b"old run")

    run(adapter, tmp_path)

    for key in stale:
        assert adapter.read_bytes(key) is None


def test_rerun_gives_the_same_logical_records_and_counts(
    adapter: S3StorageAdapter, tmp_path: Path, raw_bytes: bytes
) -> None:
    first_summary = run(adapter, tmp_path, name="first")
    first_keys = sorted(adapter.list_objects(""))
    first_frames = {layer: stored_frame(adapter, layer) for layer in LAYERS}

    second_summary = run(adapter, tmp_path, name="second")

    assert second_summary == first_summary
    assert sorted(adapter.list_objects("")) == first_keys
    for layer in LAYERS:
        assert stored_frame(adapter, layer).equals(first_frames[layer]), layer


def test_all_rows_accepted_gives_an_empty_quarantine(
    adapter: S3StorageAdapter, tmp_path: Path
) -> None:
    publish_raw(adapter, tmp_path, [trip(), trip()])

    summary = run(adapter, tmp_path)

    assert (summary["accepted_rows"], summary["rejected_rows"]) == (2, 0)
    assert stored_frame(adapter, "quarantine").height == 0


def test_empty_raw_file_publishes_three_empty_layers(
    adapter: S3StorageAdapter, tmp_path: Path
) -> None:
    publish_raw(adapter, tmp_path, [])

    summary = run(adapter, tmp_path)

    assert (
        summary["input_rows"],
        summary["accepted_rows"],
        summary["rejected_rows"],
    ) == (0, 0, 0)
    for layer in LAYERS:
        assert stored_frame(adapter, layer).height == 0
        manifest = read_layer_manifest(adapter, build_layer_manifest_key(layer, MONTH))
        assert manifest is not None
        assert manifest.publication_status == "published"
        assert manifest.row_count == 0


def test_missing_raw_manifest_fails_and_writes_nothing(
    adapter: S3StorageAdapter, tmp_path: Path
) -> None:
    with pytest.raises(TransformInputError, match="ingest the month first"):
        run(adapter, tmp_path)

    assert adapter.list_objects("") == []


def test_unpublished_raw_manifest_fails_and_writes_nothing(
    adapter: S3StorageAdapter, tmp_path: Path
) -> None:
    publish_raw(adapter, tmp_path, TRIPS)
    manifest_key = build_manifest_key(RAW_KEY)
    raw_manifest = adapter.read_bytes(manifest_key)
    assert raw_manifest is not None
    adapter.write_bytes(
        manifest_key, raw_manifest.replace(b'"published"', b'"pending"')
    )
    keys_before = sorted(adapter.list_objects(""))

    with pytest.raises(TransformInputError, match="not published yet"):
        run(adapter, tmp_path)

    assert sorted(adapter.list_objects("")) == keys_before


def test_a_failed_count_check_publishes_nothing(
    adapter: S3StorageAdapter,
    tmp_path: Path,
    raw_bytes: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    keys_before = sorted(adapter.list_objects(""))
    # The input count no longer matches accepted + rejected, as if a row was lost.
    monkeypatch.setattr(pipeline_module, "count_rows", lambda path: 999)

    with pytest.raises(CountMismatchError):
        run(adapter, tmp_path)

    assert sorted(adapter.list_objects("")) == keys_before


def sha256_of_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

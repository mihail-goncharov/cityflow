import hashlib
import json
from datetime import datetime
from pathlib import Path

import pytest

from cityflow.storage.s3_adapter import S3StorageAdapter
from cityflow.transform.layer_manifest import (
    SCHEMA_VERSION,
    LayerManifest,
    build_layer_manifest,
    layer_manifest_from_json,
    layer_manifest_to_json,
    read_layer_manifest,
    write_layer_manifest,
)

MONTH = "2025-01"
RAW_KEY = "raw/nyc_tlc/yellow_taxi/year=2025/month=01/yellow_tripdata_2025-01.parquet"
RAW_SHA = "a" * 64
CONTENT = b"parquet bytes"


def make_manifest(**overrides: object) -> LayerManifest:
    fields: dict[str, object] = {
        "layer": "silver",
        "source_month": MONTH,
        "source_object_key": RAW_KEY,
        "source_sha256": RAW_SHA,
        "row_count": 3,
        "sha256": "b" * 64,
        "size_bytes": 13,
        "processed_at": "2026-11-16T10:00:00+00:00",
        "schema_version": SCHEMA_VERSION,
        "publication_status": "pending",
    }
    fields.update(overrides)
    return LayerManifest(**fields)  # type: ignore[arg-type]


def test_build_layer_manifest_describes_the_local_file(tmp_path: Path) -> None:
    local_path = tmp_path / "out.parquet"
    local_path.write_bytes(CONTENT)

    manifest = build_layer_manifest(
        layer="quarantine",
        month=MONTH,
        local_path=local_path,
        source_object_key=RAW_KEY,
        source_sha256=RAW_SHA,
        row_count=7,
    )

    assert manifest.layer == "quarantine"
    assert manifest.source_month == MONTH
    assert manifest.source_object_key == RAW_KEY
    assert manifest.source_sha256 == RAW_SHA
    assert manifest.row_count == 7
    assert manifest.sha256 == hashlib.sha256(CONTENT).hexdigest()
    assert manifest.size_bytes == len(CONTENT)
    assert manifest.schema_version == SCHEMA_VERSION
    assert manifest.publication_status == "pending"


def test_build_layer_manifest_processed_at_is_utc_iso(tmp_path: Path) -> None:
    local_path = tmp_path / "out.parquet"
    local_path.write_bytes(CONTENT)

    manifest = build_layer_manifest(
        layer="bronze",
        month=MONTH,
        local_path=local_path,
        source_object_key=RAW_KEY,
        source_sha256=RAW_SHA,
        row_count=0,
    )

    processed_at = datetime.fromisoformat(manifest.processed_at)
    assert processed_at.utcoffset() is not None
    assert processed_at.utcoffset().total_seconds() == 0


def test_manifest_json_roundtrip() -> None:
    manifest = make_manifest()

    assert layer_manifest_from_json(layer_manifest_to_json(manifest)) == manifest


def test_manifest_json_has_the_documented_field_names() -> None:
    data = json.loads(layer_manifest_to_json(make_manifest()))

    assert set(data) == {
        "layer",
        "source_month",
        "source_object_key",
        "source_sha256",
        "row_count",
        "sha256",
        "size_bytes",
        "processed_at",
        "schema_version",
        "publication_status",
    }


def test_read_layer_manifest_returns_none_when_missing(
    adapter: S3StorageAdapter,
) -> None:
    assert read_layer_manifest(adapter, "silver/x/manifest.json") is None


def test_write_then_read_layer_manifest(adapter: S3StorageAdapter) -> None:
    manifest = make_manifest(publication_status="published")

    write_layer_manifest(adapter, "silver/x/manifest.json", manifest)

    assert read_layer_manifest(adapter, "silver/x/manifest.json") == manifest


def test_write_layer_manifest_overwrites_the_previous_one(
    adapter: S3StorageAdapter,
) -> None:
    write_layer_manifest(adapter, "k/manifest.json", make_manifest(row_count=1))
    write_layer_manifest(adapter, "k/manifest.json", make_manifest(row_count=2))

    stored = read_layer_manifest(adapter, "k/manifest.json")
    assert stored is not None
    assert stored.row_count == 2


@pytest.mark.parametrize("layer", ["bronze", "silver", "quarantine"])
def test_build_layer_manifest_accepts_every_layer(tmp_path: Path, layer: str) -> None:
    local_path = tmp_path / "out.parquet"
    local_path.write_bytes(CONTENT)

    manifest = build_layer_manifest(
        layer=layer,  # type: ignore[arg-type]
        month=MONTH,
        local_path=local_path,
        source_object_key=RAW_KEY,
        source_sha256=RAW_SHA,
        row_count=1,
    )

    assert manifest.layer == layer

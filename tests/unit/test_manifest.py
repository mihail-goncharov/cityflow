from cityflow.ingestion.manifest import (
    Manifest,
    build_manifest_key,
    manifest_from_json,
    manifest_to_json,
    read_manifest,
    write_manifest,
)
from cityflow.storage.s3_adapter import S3StorageAdapter

MANIFEST = Manifest(
    source_month="2025-01",
    source="nyc_tlc_yellow",
    url="https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-01.parquet",
    bucket="cityflow-dev",
    object_key="raw/nyc_tlc/yellow_taxi/year=2025/month=01/yellow_tripdata_2025-01.parquet",
    sha256="9af277e4c0d3f9deb30644da822981e1e7df6af58313170fd3aa8a474485488a",
    size_bytes=59158238,
    ingested_at="2026-11-03T12:00:00+00:00",
    contract_version=1,
    publication_status="published",
)

DATA_KEY = "raw/nyc_tlc/yellow_taxi/year=2025/month=01/yellow_tripdata_2025-01.parquet"


def test_manifest_json_round_trip_preserves_fields():
    manifest_json = manifest_to_json(manifest=MANIFEST)
    manifest_restored = manifest_from_json(manifest_json)
    assert manifest_restored == MANIFEST


def test_build_manifest_key_replaces_file_name():
    manifest_key = build_manifest_key(DATA_KEY)
    assert manifest_key == "raw/nyc_tlc/yellow_taxi/year=2025/month=01/manifest.json"


def test_write_manifest_can_be_read_back(adapter: S3StorageAdapter):
    manifest_key = build_manifest_key(DATA_KEY)
    write_manifest(adapter, manifest_key, MANIFEST)
    assert read_manifest(adapter, manifest_key) == MANIFEST


def test_read_manifest_missing_key_returns_none(adapter: S3StorageAdapter):
    assert read_manifest(adapter, "missing/manifest.json") is None
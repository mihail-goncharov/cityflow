from cityflow.ingestion.manifest import Manifest, manifest_from_json, manifest_to_json

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


def test_manifest_json_round_trip_preserves_fields():
    manifest_json = manifest_to_json(manifest=MANIFEST)
    manifest_restored = manifest_from_json(manifest_json)
    assert manifest_restored == MANIFEST
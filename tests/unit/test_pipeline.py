from collections.abc import Callable

import httpx
import pytest

from cityflow.build_manifest import sha256_of
from cityflow.ingestion.manifest import read_manifest
from cityflow.ingestion.pipeline import ingest_month
from cityflow.ingestion.validate import ValidationError
from cityflow.storage.s3_adapter import S3StorageAdapter

BUCKET = "test-bucket"
MONTH = "2025-01"
CONTENT = b"CONTENT"
EXPECTED_KEY = (
    "raw/nyc_tlc/yellow_taxi/year=2025/month=01/yellow_tripdata_2025-01.parquet"
)
EXPECTED_MANIFEST_KEY = "raw/nyc_tlc/yellow_taxi/year=2025/month=01/manifest.json"


def make_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def make_handler(parquet_bytes: bytes) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request):
        return httpx.Response(
            200,
            content=iter([parquet_bytes]),
            headers={"Content-Length": str(len(parquet_bytes))},
        )

    return handler


def invalid_file_handler(request):
    return httpx.Response(
        200, content=iter([CONTENT]), headers={"Content-Length": str(len(CONTENT))}
    )


def test_ingest_month_invalid_raises_validation_error(
    adapter: S3StorageAdapter, tmp_path
) -> None:
    with (
        make_client(handler=invalid_file_handler) as client,
        pytest.raises(ValidationError),
    ):
        ingest_month(MONTH, client, adapter, tmp_path)

    assert adapter.list_objects() == []


def test_ingest_month_valid_file_publishes_object_and_manifest(
    adapter: S3StorageAdapter, tmp_path, valid_trips
) -> None:
    data_file = tmp_path / "source.parquet"
    valid_trips.write_parquet(data_file)
    parquet_bytes = data_file.read_bytes()

    with make_client(make_handler(parquet_bytes)) as client:
        outcome = ingest_month(MONTH, client, adapter, tmp_path)

    downloaded_file_path = tmp_path / "downloaded.parquet"
    adapter.download_object(EXPECTED_KEY, downloaded_file_path)
    manifest = read_manifest(adapter, EXPECTED_MANIFEST_KEY)

    assert manifest is not None
    assert outcome == "published"
    assert manifest.object_key == EXPECTED_KEY
    assert manifest.sha256 == sha256_of(data_file)
    assert manifest.size_bytes == len(parquet_bytes)
    assert manifest.source_month == MONTH
    assert manifest.publication_status == "published"
    assert sorted(adapter.list_objects()) == sorted(
        [EXPECTED_KEY, EXPECTED_MANIFEST_KEY]
    )
    assert downloaded_file_path.read_bytes() == parquet_bytes


def test_ingest_month_second_run_is_skipped(adapter, tmp_path, tmp_file, valid_trips):
    valid_trips.write_parquet(tmp_file)
    parquet_bytes = tmp_file.read_bytes()

    with make_client(make_handler(parquet_bytes=parquet_bytes)) as client:
        first_outcome = ingest_month(MONTH, client, adapter, tmp_path)
        second_outcome = ingest_month(MONTH, client, adapter, tmp_path)

    assert first_outcome == "published"
    assert second_outcome == "skipped"
    assert sorted(adapter.list_objects()) == sorted(
        [EXPECTED_KEY, EXPECTED_MANIFEST_KEY]
    )

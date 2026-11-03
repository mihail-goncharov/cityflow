
import boto3
import httpx
import pytest
from moto import mock_aws

from cityflow.ingestion.pipeline import ingest_month
from cityflow.ingestion.validate import ValidationError
from cityflow.storage.s3_adapter import S3StorageAdapter

BUCKET = "test-bucket"
MONTH = "2025-01"
CONTENT = b"CONTENT"


@pytest.fixture
def adapter():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield S3StorageAdapter(BUCKET, client)


def make_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def invalid_file_handler(request):
    return httpx.Response(200, content=iter([CONTENT]), headers={"Content-Length": str(len(CONTENT))})


def test_ingest_month_invalid_raises_validation_error(adapter: S3StorageAdapter, tmp_path) -> None:
    with make_client(handler=invalid_file_handler) as client, pytest.raises(ValidationError):
        ingest_month(MONTH, client, adapter, tmp_path)

    assert adapter.list_objects() == []


def test_ingest_month_valid_file_uploads_unchanged_bytes(adapter: S3StorageAdapter, tmp_path, valid_trips) -> None:
    expected_key = "raw/nyc_tlc/yellow_taxi/year=2025/month=01/yellow_tripdata_2025-01.parquet"
    data_file = tmp_path / "source.parquet"
    valid_trips.write_parquet(data_file)
    parquet_bytes = data_file.read_bytes()

    def handler(request):
        return httpx.Response(200, content=iter([parquet_bytes]), headers={"Content-Length": str(len(parquet_bytes))})

    with make_client(handler) as client:
        object_key = ingest_month(MONTH, client, adapter, tmp_path)

    downloaded_file_path = tmp_path / "downloaded.parquet"
    adapter.download_object(expected_key, downloaded_file_path)

    assert object_key == expected_key
    assert adapter.list_objects() == [expected_key]
    assert downloaded_file_path.read_bytes() == parquet_bytes


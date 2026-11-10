from datetime import datetime
from pathlib import Path

import boto3
import polars as pl
import pytest
from moto import mock_aws

from cityflow.ingestion.validate import REQUIRED_COLUMNS
from cityflow.storage.s3_adapter import S3StorageAdapter

BUCKET = "test-bucket"


@pytest.fixture()
def valid_trips() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "tpep_pickup_datetime": [datetime(2025, 1, 1, 10, 0)],
            "tpep_dropoff_datetime": [datetime(2025, 1, 1, 10, 15)],
            "PULocationID": [132],
            "DOLocationID": [236],
            "trip_distance": [3.2],
            "fare_amount": [17.5],
            "total_amount": [24.8],
        },
        schema=REQUIRED_COLUMNS
    )


@pytest.fixture
def adapter():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield S3StorageAdapter(BUCKET, client)


@pytest.fixture()
def tmp_file(tmp_path) -> Path:
    return tmp_path / "file.parquet"
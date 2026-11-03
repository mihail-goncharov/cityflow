from pathlib import Path

import httpx

from cityflow.ingestion.download import (
    build_source_url,
    download_with_retries,
    parse_month,
)
from cityflow.ingestion.validate import validate_raw_file
from cityflow.storage.s3_adapter import S3StorageAdapter

RAW_KEY_PREFIX = "raw/nyc_tlc/yellow_taxi"


def build_object_key(month: str, filename: str) -> str:
    year, month_number = parse_month(month).split("-")
    return f"{RAW_KEY_PREFIX}/year={year}/month={month_number}/{filename}"


def ingest_month(month: str,
                 client: httpx.Client,
                 storage: S3StorageAdapter,
                 workdir: Path,
                 ) -> str:
    """Download, validate and upload one month of raw TLC data.

    Downloads the month's file into workdir, runs all raw data contract
    checks, and uploads it to storage under the Raw object key. Validation
    runs before the upload, so a file that fails any check is never
    uploaded: the ValidationError propagates to the caller instead.
    Returns the object key of the uploaded file.
    """
    url = build_source_url(month)
    filename = f"yellow_tripdata_{month}.parquet"
    file_path = workdir / filename

    download_with_retries(url=url, destination=file_path, client=client)
    validate_raw_file(path=file_path, month=month, url=url)
    object_key = build_object_key(month, filename=filename)
    storage.upload_object(local_path=file_path, key=object_key)

    return object_key
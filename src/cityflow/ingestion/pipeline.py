from pathlib import Path

import httpx

from cityflow.ingestion.download import (
    build_source_url,
    download_with_retries,
    parse_month,
)
from cityflow.ingestion.publish import PublishOutcome, publish_raw_file
from cityflow.ingestion.validate import validate_raw_file
from cityflow.storage.s3_adapter import S3StorageAdapter

RAW_KEY_PREFIX = "raw/nyc_tlc/yellow_taxi"


def build_object_key(month: str, filename: str) -> str:
    year, month_number = parse_month(month).split("-")
    return f"{RAW_KEY_PREFIX}/year={year}/month={month_number}/{filename}"


def ingest_month(
    month: str,
    client: httpx.Client,
    storage: S3StorageAdapter,
    workdir: Path,
) -> PublishOutcome:
    """Download, validate and publish one month of raw TLC data.

    Downloads the month's file into workdir and runs all raw data contract
    checks; a file that fails any check is never published and the
    ValidationError propagates. The validated file is then published with
    its manifest by publish_raw_file, which uploads, verifies and handles
    reruns. Returns the publication outcome: "published", "skipped" or
    "recovered".
    """
    url = build_source_url(month)
    filename = f"yellow_tripdata_{month}.parquet"
    file_path = workdir / filename

    download_with_retries(url=url, destination=file_path, client=client)
    sha256 = validate_raw_file(path=file_path, month=month, url=url)
    object_key = build_object_key(month, filename=filename)
    outcome = publish_raw_file(
        storage=storage,
        object_key=object_key,
        sha256=sha256,
        url=url,
        month=month,
        work_dir=workdir,
        local_path=file_path,
    )

    return outcome

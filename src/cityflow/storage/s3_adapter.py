import os
from typing import TYPE_CHECKING
from pathlib import Path

import boto3
import botocore

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client


def create_s3_client() -> "S3Client":
    return boto3.client(
        "s3",
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        aws_access_key_id=os.environ["S3_ACCESS_KEY"],
        aws_secret_access_key=os.environ["S3_SECRET_KEY"],
        region_name="us-east-1",
    )


class StorageError(Exception):
    """Raised when a storage operation fails."""


class S3StorageAdapter:
    def __init__(self, bucket: str, client: "S3Client") -> None:
        self.bucket = bucket
        self.client = client

    def upload_object(self, local_path: Path, key: str) -> None:
        pass

    def download_object(self, key: str, local_path: Path) -> None:
        pass

    def list_objects(self, prefix: str = "") -> list[str]:
        pass

    def delete_object(self, key: str) -> None:
        pass
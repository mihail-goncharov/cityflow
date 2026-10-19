import os
from pathlib import Path
from typing import TYPE_CHECKING

import boto3
from boto3.exceptions import S3UploadFailedError
from botocore.exceptions import BotoCoreError, ClientError

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
        try:
            self.client.upload_file(Filename=str(local_path), Bucket=self.bucket, Key=key)
        except (S3UploadFailedError, BotoCoreError) as e:
            raise StorageError(f"Failed to upload '{key}' to bucket '{self.bucket}'") from e

    def download_object(self, key: str, local_path: Path) -> None:
        try:
            self.client.download_file(Bucket=self.bucket, Key=key, Filename=str(local_path))
        except (ClientError, BotoCoreError) as e:
            raise StorageError(f"Failed to download '{key}' from bucket '{self.bucket}'") from e

    def list_objects(self, prefix: str = "") -> list[str]:
        try:
            response = self.client.list_objects_v2(Bucket=self.bucket, Prefix=prefix)

        except (ClientError, BotoCoreError) as e:
            raise StorageError(f"Failed to list objects from bucket '{self.bucket}' with prefix '{prefix}'") from e

        else:
            objects = response.get("Contents", [])
            return [data_object["Key"] for data_object in objects]

    def delete_object(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except (ClientError, BotoCoreError) as e:
            raise StorageError(f"Failed to delete '{key}' from bucket '{self.bucket}'") from e



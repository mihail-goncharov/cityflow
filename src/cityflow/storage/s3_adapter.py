import os
from pathlib import Path
from typing import TYPE_CHECKING

import boto3
from boto3.exceptions import Boto3Error
from botocore.exceptions import BotoCoreError, ClientError

if TYPE_CHECKING:
    from mypy_boto3_s3 import S3Client

S3_ERRORS = (ClientError, BotoCoreError, Boto3Error)

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
        except S3_ERRORS as e:
            raise StorageError(f"Failed to upload '{key}' to bucket '{self.bucket}'") from e

    def download_object(self, key: str, local_path: Path) -> None:
        try:
            self.client.download_file(Bucket=self.bucket, Key=key, Filename=str(local_path))
        except S3_ERRORS as e:
            raise StorageError(f"Failed to download '{key}' from bucket '{self.bucket}'") from e

    def list_objects(self, prefix: str = "") -> list[str]:
        keys = []
        try:
            paginator = self.client.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=self.bucket, Prefix=prefix):
                objects = page.get("Contents", [])
                keys.extend([data_object["Key"] for data_object in objects])
        except S3_ERRORS as e:
            raise StorageError(f"Failed to list objects from bucket '{self.bucket}' with prefix '{prefix}'") from e
        return keys

    def delete_object(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=self.bucket, Key=key)
        except S3_ERRORS as e:
            raise StorageError(f"Failed to delete '{key}' from bucket '{self.bucket}'") from e

    def read_bytes(self, key: str) -> bytes | None:
        error_message = f"Failed to read '{key}' from bucket '{self.bucket}'"
        try:
            object_data = self.client.get_object(Bucket=self.bucket, Key=key)["Body"].read()
            return object_data
        except ClientError as error:
            if error.response["Error"]["Code"] == "NoSuchKey":
                return None
            raise StorageError(error_message) from error
        except S3_ERRORS as error:
            raise StorageError(error_message) from error

    def write_bytes(self, key: str, data: bytes) -> None:
        try:
            self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        except S3_ERRORS as error:
            raise StorageError(f"Failed to write '{key}' to bucket '{self.bucket}'") from error
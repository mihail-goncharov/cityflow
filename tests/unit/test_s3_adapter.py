from pathlib import Path

import boto3
import pytest
from moto import mock_aws

from cityflow.storage.s3_adapter import S3StorageAdapter, StorageError

BUCKET = "test-bucket"
KEY = "raw/example.txt"
CONTENT = b"Content"

@pytest.fixture
def adapter():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=BUCKET)
        yield S3StorageAdapter(BUCKET, client)


def upload_text_file(adapter: S3StorageAdapter, tmp_path: Path, key: str, text: str = "CityFlow") -> None:
    local_file = tmp_path / Path(key).name
    local_file.write_text(text)
    adapter.upload_object(local_path=local_file, key=key)


def test_uploaded_object_is_listed(adapter, tmp_path):
    upload_text_file(adapter=adapter, tmp_path=tmp_path, key=KEY)
    assert adapter.list_objects() == [KEY]


def test_download_uploaded_object(adapter, tmp_path):
    content = "hello CityFlow"
    upload_text_file(adapter=adapter, tmp_path=tmp_path, key=KEY, text=content)

    download_file = tmp_path / "downloaded.txt"
    adapter.download_object(key=KEY, local_path=download_file)

    assert download_file.read_text() == content


def test_list_objects_filters_by_prefix(adapter, tmp_path):
    key_1 = "raw/example.txt"
    upload_text_file(adapter=adapter, tmp_path=tmp_path, key=key_1)

    key_2 = "processed/example.txt"
    upload_text_file(adapter=adapter, tmp_path=tmp_path, key=key_2)

    assert adapter.list_objects("raw/") == [key_1]


def test_list_objects_on_empty_bucket(adapter):
    assert adapter.list_objects() == []


def test_delete_object_is_no_longer_exist(adapter, tmp_path):
    upload_text_file(adapter=adapter, tmp_path=tmp_path, key=KEY)

    adapter.delete_object(KEY)

    assert adapter.list_objects() == []


def test_download_missing_key_raises_storage_error(adapter, tmp_path):
    local_path = tmp_path / "downloaded.txt"
    with pytest.raises(StorageError):
        adapter.download_object(key=KEY, local_path=local_path)

    assert not local_path.exists()


def test_upload_to_missing_bucket_raises_storage_error(adapter, tmp_path):
    bucket = "no-such-bucket"
    new_adapter = S3StorageAdapter(bucket=bucket, client=adapter.client)

    with pytest.raises(StorageError):
        upload_text_file(adapter=new_adapter, tmp_path=tmp_path, key=KEY)


def test_list_objects_returns_all_pages(adapter):
    keys = [f"raw/{i}.txt" for i in range(1001)]
    for key in keys:
        adapter.client.put_object(Bucket=BUCKET, Key=key, Body=b"")

    assert sorted(adapter.list_objects()) == sorted(keys)


def test_written_bytes_can_be_read_back(adapter):
    adapter.write_bytes(KEY, CONTENT)
    assert adapter.read_bytes(KEY) == CONTENT


def test_read_bytes_missing_key_returns_none(adapter):
    assert adapter.read_bytes(KEY) is None


def test_read_bytes_missing_bucket_raises_storage_error(adapter):
    missing_bucket_adapter = S3StorageAdapter("no-such-bucket", adapter.client)
    with pytest.raises(StorageError):
        missing_bucket_adapter.read_bytes(KEY)
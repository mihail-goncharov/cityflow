import dataclasses
import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from cityflow.storage.s3_adapter import S3StorageAdapter

PublicationStatus = Literal["pending", "published"]


@dataclass(frozen=True)
class Manifest:
    source_month: str
    source: str
    url: str
    bucket: str
    object_key: str
    sha256: str
    size_bytes: int
    ingested_at: str
    contract_version: int
    publication_status: PublicationStatus


def manifest_to_json(manifest: Manifest) -> bytes:
    manifest_dict = dataclasses.asdict(manifest)
    return json.dumps(manifest_dict, indent=2).encode("utf-8")


def manifest_from_json(data: bytes) -> Manifest:
    manifest_dict = json.loads(data)
    return Manifest(**manifest_dict)


def build_manifest_key(object_key: str) -> str:
    manifest_key = PurePosixPath(object_key).with_name("manifest.json")
    return str(manifest_key)


def read_manifest(storage: S3StorageAdapter, key: str) -> Manifest | None:
    manifest_data = storage.read_bytes(key)
    if manifest_data is None:
        return None
    return manifest_from_json(manifest_data)


def write_manifest(storage: S3StorageAdapter, key: str, manifest: Manifest) -> None:
    storage.write_bytes(key, manifest_to_json(manifest))
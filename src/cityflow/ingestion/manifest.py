import dataclasses
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal

from cityflow.storage.s3_adapter import S3StorageAdapter

PublicationStatus = Literal["pending", "published"]
SOURCE = "nyc_tlc_yellow"
CONTRACT_VERSION = 1


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


def build_manifest(
    *, bucket: str, object_key: str, sha256: str, url: str, month: str, local_path: Path
) -> Manifest:
    """Build a pending manifest for a local raw file.

       Size and ingestion timestamp (UTC) are computed here; source and
       contract version come from module constants. The status is always
       ``pending``: it becomes ``published`` only after the object is
       uploaded and verified.
       """
    return Manifest(
        source_month=month,
        source=SOURCE,
        url=url,
        bucket=bucket,
        object_key=object_key,
        sha256=sha256,
        size_bytes=local_path.stat().st_size,
        ingested_at=datetime.now(UTC).isoformat(),
        contract_version=CONTRACT_VERSION,
        publication_status="pending",
    )

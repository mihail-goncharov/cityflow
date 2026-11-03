import dataclasses
import json
from dataclasses import dataclass
from typing import Literal

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


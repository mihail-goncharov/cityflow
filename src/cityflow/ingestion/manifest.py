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

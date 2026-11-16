import dataclasses
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from cityflow.build_manifest import sha256_of
from cityflow.storage.s3_adapter import S3StorageAdapter
from cityflow.transform.layers import Layer

LayerPublicationStatus = Literal["pending", "published"]
SCHEMA_VERSION = 1


@dataclass(frozen=True)
class LayerManifest:
    """What is stored next to a layer's data object (docs/medallion.md section 2).

    ``sha256`` and ``size_bytes`` describe the output Parquet file; the
    ``source_*`` fields say which Raw file it was built from. The status is
    ``pending`` while the layer is being written and ``published`` once the
    stored object has been verified.
    """

    layer: Layer
    source_month: str
    source_object_key: str
    source_sha256: str
    row_count: int
    sha256: str
    size_bytes: int
    processed_at: str
    schema_version: int
    publication_status: LayerPublicationStatus


def layer_manifest_to_json(manifest: LayerManifest) -> bytes:
    return json.dumps(dataclasses.asdict(manifest), indent=2).encode("utf-8")


def layer_manifest_from_json(data: bytes) -> LayerManifest:
    return LayerManifest(**json.loads(data))


def read_layer_manifest(storage: S3StorageAdapter, key: str) -> LayerManifest | None:
    data = storage.read_bytes(key)
    if data is None:
        return None
    return layer_manifest_from_json(data)


def write_layer_manifest(
    storage: S3StorageAdapter, key: str, manifest: LayerManifest
) -> None:
    storage.write_bytes(key, layer_manifest_to_json(manifest))


def build_layer_manifest(
    *,
    layer: Layer,
    month: str,
    local_path: Path,
    source_object_key: str,
    source_sha256: str,
    row_count: int,
) -> LayerManifest:
    """Build a ``pending`` manifest for a local output file.

    Checksum and size come from the file, the processing time is now (UTC).
    The status becomes ``published`` only after the upload is verified.
    """
    return LayerManifest(
        layer=layer,
        source_month=month,
        source_object_key=source_object_key,
        source_sha256=source_sha256,
        row_count=row_count,
        sha256=sha256_of(local_path),
        size_bytes=local_path.stat().st_size,
        processed_at=datetime.now(UTC).isoformat(),
        schema_version=SCHEMA_VERSION,
        publication_status="pending",
    )

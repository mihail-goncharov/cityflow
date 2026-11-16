import dataclasses
from pathlib import Path

from cityflow.ingestion.publish import verify_remote_object
from cityflow.storage.s3_adapter import S3StorageAdapter
from cityflow.transform.layer_manifest import build_layer_manifest, write_layer_manifest
from cityflow.transform.layers import (
    Layer,
    build_layer_folder,
    build_layer_key,
    build_layer_manifest_key,
    build_quality_summary_key,
)


def publish_layer(
    *,
    storage: S3StorageAdapter,
    layer: Layer,
    month: str,
    local_path: Path,
    source_object_key: str,
    source_sha256: str,
    row_count: int,
    work_dir: Path,
) -> None:
    """Publish one layer's Parquet file for one month, with its manifest.

    The output is derived data and can always be rebuilt from Raw, so a rerun
    overwrites the previous object instead of skipping or failing
    (docs/medallion.md section 8). The manifest says whether the object can
    be trusted: ``pending`` until the stored bytes are verified by SHA-256.
    Raises PublicationError if verification fails, or StorageError.
    """
    layer_key = build_layer_key(layer, month)
    layer_manifest_key = build_layer_manifest_key(layer, month)
    manifest = build_layer_manifest(
        layer=layer,
        month=month,
        local_path=local_path,
        source_object_key=source_object_key,
        source_sha256=source_sha256,
        row_count=row_count,
    )
    write_layer_manifest(storage, layer_manifest_key, manifest)
    storage.upload_object(local_path, layer_key)
    verify_remote_object(storage, layer_key, manifest.sha256, work_dir)
    write_layer_manifest(
        storage,
        layer_manifest_key,
        dataclasses.replace(manifest, publication_status="published"),
    )


def remove_stale_objects(
    *, storage: S3StorageAdapter, layer: Layer, month: str
) -> list[str]:
    """Delete objects in a layer's month folder that the pipeline did not write.

    The expected objects are the layer's data object and manifest, plus
    ``quality_summary.json`` for Silver. Everything else under the folder (for
    example a file left by an older run) is deleted, so a reader of the folder
    sees only the current output (docs/medallion.md section 8). Only the
    folder of this layer and month is touched. Returns the deleted keys.
    Call it after the layer has been published and verified, never before.
    """
    layer_folder = build_layer_folder(layer, month)
    expected = {build_layer_key(layer, month), build_layer_manifest_key(layer, month)}
    if layer == "silver":
        expected.add(build_quality_summary_key(month))

    layer_objects = storage.list_objects(f"{layer_folder}/")

    stale_keys = []
    for key in layer_objects:
        if key not in expected:
            stale_keys.append(key)
            storage.delete_object(key)

    return stale_keys

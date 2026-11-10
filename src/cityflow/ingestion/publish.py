import dataclasses
from pathlib import Path, PurePosixPath
from typing import Literal

from cityflow.build_manifest import sha256_of
from cityflow.ingestion.manifest import (
    build_manifest,
    build_manifest_key,
    read_manifest,
    write_manifest,
)
from cityflow.storage.s3_adapter import S3StorageAdapter, StorageError

PublishOutcome = Literal["published", "skipped", "recovered"]


class PublicationError(Exception):
    """Raised when a file cannot be published to storage or verified there."""


def verify_remote_object(
    storage: S3StorageAdapter, key: str, expected_sha256: str, work_dir: Path
) -> None:
    """Check that the object in storage has the expected SHA-256.

    Downloads the object into a temporary ``.verify`` file in work_dir,
    computes its SHA-256 and removes the file again. An S3 ETag is not used,
    because it is not a SHA-256 of the content. Raises PublicationError if
    the hashes differ.
    """
    file_path = work_dir / f"{PurePosixPath(key).name}.verify"
    try:
        storage.download_object(key, file_path)
        sha256_verify = sha256_of(file_path)

    finally:
        file_path.unlink(missing_ok=True)

    if sha256_verify != expected_sha256:
        raise PublicationError(
            f"Remote object '{key}' does not match the uploaded file: "
            f"expected SHA-256 {expected_sha256}, got {sha256_verify}"
        )


def _publish_new(
    *,
    storage: S3StorageAdapter,
    object_key: str,
    sha256: str,
    url: str,
    month: str,
    work_dir: Path,
    local_path: Path,
) -> None:
    """Upload and verify the file, moving the manifest from pending to published."""
    manifest = build_manifest(
        bucket=storage.bucket,
        object_key=object_key,
        sha256=sha256,
        url=url,
        month=month,
        local_path=local_path,
    )

    manifest_key = build_manifest_key(object_key)

    write_manifest(storage, manifest_key, manifest)
    storage.upload_object(local_path, object_key)
    verify_remote_object(storage, object_key, sha256, work_dir)
    manifest_published = dataclasses.replace(manifest, publication_status="published")
    write_manifest(storage, manifest_key, manifest_published)


def publish_raw_file(
    *,
    storage: S3StorageAdapter,
    object_key: str,
    sha256: str,
    url: str,
    month: str,
    work_dir: Path,
    local_path: Path,
) -> PublishOutcome:
    """Publish a validated raw file to storage together with its manifest.

    Reads the manifest stored next to the object and decides what to do:

    - no manifest: write a ``pending`` manifest, upload the file, verify the
      remote object by SHA-256, then mark the manifest ``published``;
    - ``published`` with the same SHA-256: do nothing (rerun is a no-op);
    - ``published`` with a different SHA-256: raise PublicationError and
      leave the existing object untouched;
    - ``pending`` with a different SHA-256: raise PublicationError and leave
      the object and manifest untouched, because the run that wrote it may
      still be active (or was interrupted with other bytes) and its upload
      must not be overwritten;
    - ``pending`` with the same SHA-256 (the same file): verify the object and
      complete the manifest; if the object is missing or different, publish it
      again. Two runs with the same bytes cannot corrupt each other.

    Returns "published", "skipped" or "recovered".
    """
    manifest_key = build_manifest_key(object_key)

    existing = read_manifest(storage, manifest_key)

    if existing is None:
        _publish_new(
            storage=storage,
            object_key=object_key,
            sha256=sha256,
            url=url,
            month=month,
            work_dir=work_dir,
            local_path=local_path,
        )
        return "published"

    if existing.publication_status == "published" and existing.sha256 == sha256:
        return "skipped"

    if existing.publication_status == "published" and existing.sha256 != sha256:
        raise PublicationError(
            f"Object '{object_key}' is already published with SHA-256 "
            f"{existing.sha256}, but the new file has SHA-256 {sha256}; "
            f"existing data was kept for review"
        )

    if existing.sha256 != sha256:
        raise PublicationError(
            f"Object '{object_key}' has an unfinished (pending) publication with "
            f"SHA-256 {existing.sha256}, but the new file has SHA-256 {sha256}; "
            f"another run may be active, so nothing was overwritten"
        )

    try:
        verify_remote_object(storage, object_key, sha256, work_dir)
    except (PublicationError, StorageError):
        _publish_new(
            storage=storage,
            object_key=object_key,
            sha256=sha256,
            url=url,
            month=month,
            work_dir=work_dir,
            local_path=local_path,
        )
        return "published"
    else:
        new_manifest = build_manifest(
            bucket=storage.bucket,
            object_key=object_key,
            sha256=sha256,
            url=url,
            month=month,
            local_path=local_path,
        )
        manifest = dataclasses.replace(new_manifest, publication_status="published")
        write_manifest(storage, manifest_key, manifest)
        return "recovered"

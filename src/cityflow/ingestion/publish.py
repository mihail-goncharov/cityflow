from pathlib import Path, PurePosixPath

from cityflow.build_manifest import sha256_of
from cityflow.storage.s3_adapter import S3StorageAdapter


class PublicationError(Exception):
    """Raised when a file cannot be published to storage or verified there."""


def verify_remote_object(storage: S3StorageAdapter, key: str, expected_sha256: str, work_dir: Path) -> None:
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
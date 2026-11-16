from dataclasses import dataclass
from pathlib import Path

import polars as pl

from cityflow.build_manifest import sha256_of
from cityflow.ingestion.download import parse_month
from cityflow.ingestion.manifest import build_manifest_key, read_manifest
from cityflow.ingestion.pipeline import build_object_key
from cityflow.ingestion.validate import check_contents_readable, check_schema
from cityflow.storage.s3_adapter import S3StorageAdapter
from cityflow.transform.bronze import to_bronze
from cityflow.transform.silver import to_silver
from cityflow.transform.split import split_accepted_rejected


class TransformInputError(Exception):
    """The published Raw file for a month is missing, unfinished or changed."""


@dataclass(frozen=True)
class RawInput:
    """A verified local copy of one month's Raw file and its lineage values."""

    path: Path
    month: str
    object_key: str
    sha256: str
    ingested_at: str


@dataclass(frozen=True)
class LayerFiles:
    """The local Parquet files written for one month, before publication."""

    bronze: Path
    silver: Path
    quarantine: Path


def read_raw_input(storage: S3StorageAdapter, month: str, work_dir: Path) -> RawInput:
    """Download one month's Raw file and check it is the one that was published.

    The Raw manifest must exist and be ``published``, and the downloaded bytes
    must match its SHA-256, so the lineage columns describe exactly the file
    that is processed. The file must also have the required columns and
    readable data pages. Raises TransformInputError for a missing, unfinished
    or changed Raw file, ValidationError for a file that breaks the raw data
    contract, or StorageError. Nothing is written to storage.
    """
    month = parse_month(month)
    filename = f"yellow_tripdata_{month}.parquet"
    object_key = build_object_key(month, filename)

    manifest = read_manifest(storage, build_manifest_key(object_key))
    if manifest is None:
        raise TransformInputError(
            f"No Raw manifest for {month} at '{object_key}'; ingest the month first"
        )
    if manifest.publication_status != "published":
        raise TransformInputError(
            f"Raw file for {month} is not published yet (status "
            f"'{manifest.publication_status}'); finish the ingestion first"
        )

    path = work_dir / filename
    storage.download_object(object_key, path)

    actual_sha256 = sha256_of(path)
    if actual_sha256 != manifest.sha256:
        raise TransformInputError(
            f"Raw file '{object_key}' does not match its manifest: expected "
            f"SHA-256 {manifest.sha256}, got {actual_sha256}"
        )

    check_schema(path)
    check_contents_readable(path)

    return RawInput(
        path=path,
        month=month,
        object_key=object_key,
        sha256=manifest.sha256,
        ingested_at=manifest.ingested_at,
    )


def write_layer_files(raw: RawInput, work_dir: Path) -> LayerFiles:
    """Write Bronze, Silver and Quarantine for one month as local Parquet files.

    Reads Raw lazily and writes with ``sink_parquet``, so a month never has to
    fit in memory. Bronze is written first from Raw; Silver and Quarantine are
    then built from the Bronze file, so every layer comes from the same rows.
    Row order must be kept, because ``source_row_id`` is the row position.
    Nothing is uploaded here.
    """
    bronze_path = work_dir / "bronze.parquet"
    silver_path = work_dir / "silver.parquet"
    quarantine_path = work_dir / "quarantine.parquet"

    parquet_file = pl.scan_parquet(raw.path)
    to_bronze(
        parquet_file,
        month=raw.month,
        source_object_key=raw.object_key,
        source_sha256=raw.sha256,
        ingested_at=raw.ingested_at,
    ).sink_parquet(bronze_path)
    accepted, rejected = split_accepted_rejected(
        pl.scan_parquet(bronze_path), raw.month
    )
    to_silver(accepted).sink_parquet(silver_path)
    rejected.sink_parquet(quarantine_path)
    return LayerFiles(
        bronze=bronze_path, silver=silver_path, quarantine=quarantine_path
    )

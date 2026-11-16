import argparse
import logging
import os
import sys
import tempfile
from pathlib import Path

import polars as pl

from cityflow.ingestion.download import parse_month
from cityflow.ingestion.publish import PublicationError
from cityflow.ingestion.validate import ValidationError
from cityflow.storage.s3_adapter import S3StorageAdapter, StorageError, create_s3_client
from cityflow.transform.pipeline import TransformInputError, transform_month
from cityflow.transform.summary import CountMismatchError

logger = logging.getLogger("cityflow.transform")


def _month_argument(value: str) -> str:
    """Validate --month for argparse, keeping parse_month's error message."""
    try:
        return parse_month(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments for one transform run."""
    parser = argparse.ArgumentParser(
        prog="cityflow.transform",
        description=(
            "Build and publish the Bronze, Silver and Quarantine layers "
            "of one month of NYC TLC Yellow Taxi data."
        ),
    )
    parser.add_argument(
        "--month",
        required=True,
        help="month to transform, YYYY-MM",
        type=_month_argument,
    )
    return parser.parse_args(argv)


def _log_failure(month: str, stage: str, error: Exception) -> int:
    """Log which stage failed for the month and return exit code 1."""
    logger.error("Transform of %s failed at stage %s: %s", month, stage, error)
    return 1


def main(argv: list[str] | None = None) -> int:
    """Transform one month of published Raw data and return the exit code.

    Returns 0 when all layers and the quality summary are published, and 1
    when any stage fails:
    ``config`` (missing environment variable),
    ``input`` (Raw file missing, unfinished, changed or breaking the raw data contract),
    ``transform`` (writing the layers or the row-count check) or ``publish``
    and
    ``storage`` (uploading or verifying objects).
    The failed stage and the error message are logged; credentials are never logged.
    Ingest the month first: this command reads the Raw file from storage and never downloads.
    """
    args = parse_args(argv)
    month = args.month
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    try:
        storage = S3StorageAdapter(os.environ["S3_BUCKET"], create_s3_client())
    except KeyError as error:
        logger.error(
            "Transform of %s failed at stage config: missing environment variable %s",
            month,
            error.args[0],
        )
        return 1

    with tempfile.TemporaryDirectory() as temp_dir:
        try:
            summary = transform_month(storage, month, Path(temp_dir))
        except (TransformInputError, ValidationError) as error:
            return _log_failure(month, "input", error)
        except (pl.exceptions.PolarsError, CountMismatchError) as error:
            return _log_failure(month, "transform", error)
        except PublicationError as error:
            return _log_failure(month, "publish", error)
        except StorageError as error:
            return _log_failure(month, "storage", error)

        else:
            logger.info(
                "Transform of %s finished: %d input, %d accepted, %d rejected rows",
                month,
                summary["input_rows"],
                summary["accepted_rows"],
                summary["rejected_rows"],
            )
            return 0


if __name__ == "__main__":
    sys.exit(main())

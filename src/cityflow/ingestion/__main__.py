import argparse
import logging
import os
import sys
import tempfile
from pathlib import Path

import httpx

from cityflow.ingestion.download import DownloadError, parse_month
from cityflow.ingestion.pipeline import ingest_month
from cityflow.ingestion.publish import PublicationError
from cityflow.ingestion.validate import ValidationError
from cityflow.storage.s3_adapter import S3StorageAdapter, StorageError, create_s3_client

logger = logging.getLogger("cityflow.ingestion")


def _month_argument(value: str) -> str:
    """Validate --month for argparse, keeping parse_month's error message."""
    try:
        return parse_month(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(str(error)) from error


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    """Parse command-line arguments for one ingestion run."""
    parser = argparse.ArgumentParser(
        prog="cityflow.ingestion",
        description="Download, validate and publish one month of NYC TLC Yellow Taxi data.",
    )
    parser.add_argument(
        "--month", required=True, help="month to ingest, YYYY-MM", type=_month_argument
    )
    return parser.parse_args(argv)


def _log_failure(month: str, stage: str, error: Exception) -> int:
    """Log which stage failed for the month and return exit code 1."""
    logger.error("Ingestion of %s failed at stage %s: %s", month, stage, error)
    return 1


def main(argv: list[str] | None = None) -> int:
    """Run ingestion for one month and return the process exit code.

    Returns 0 when the month is published, skipped or recovered, and 1 when
    any stage fails. The failed stage and the error message are logged;
    credentials are never logged.
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
            "Ingestion of %s failed at stage config: missing environment variable %s",
            month,
            error.args[0],
        )
        return 1

    with httpx.Client() as client, tempfile.TemporaryDirectory() as temp_dir:
        try:
            outcome = ingest_month(month, client, storage, Path(temp_dir))
        except (DownloadError, httpx.HTTPError) as error:
            return _log_failure(month, "download", error)
        except ValidationError as error:
            return _log_failure(month, "validate", error)
        except (PublicationError, StorageError) as error:
            return _log_failure(month, "publish", error)
        else:
            logger.info("Ingestion of %s finished: %s", month, outcome)
            return 0


if __name__ == "__main__":
    sys.exit(main())

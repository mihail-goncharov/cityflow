import logging
from pathlib import Path
from typing import Any

import polars as pl
import pytest

from cityflow.ingestion.publish import PublicationError
from cityflow.ingestion.validate import ValidationError
from cityflow.storage.s3_adapter import S3StorageAdapter, StorageError
from cityflow.transform import __main__ as cli
from cityflow.transform.pipeline import TransformInputError
from cityflow.transform.summary import CountMismatchError

MONTH = "2025-01"
ACCESS_KEY = "test-access-key-123"
SECRET_KEY = "test-secret-key-456"  # noqa: S105  (fake value for tests)

SUMMARY = {
    "source_month": MONTH,
    "source_sha256": "a" * 64,
    "input_rows": 10,
    "accepted_rows": 7,
    "rejected_rows": 3,
}


@pytest.fixture(autouse=True)
def s3_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Complete fake S3 configuration; creating a boto3 client does no network I/O."""
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://127.0.0.1:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", ACCESS_KEY)
    monkeypatch.setenv("S3_SECRET_KEY", SECRET_KEY)


def patch_transform_month(
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: dict[str, Any] | None = None,
    error: Exception | None = None,
) -> None:
    """Replace the pipeline so the test controls how the transform ends."""

    def fake_transform_month(*args: Any, **kwargs: Any) -> dict[str, Any] | None:
        if error is not None:
            raise error
        return result

    monkeypatch.setattr(cli, "transform_month", fake_transform_month)


def test_main_success_returns_zero_and_logs_the_row_counts(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    patch_transform_month(monkeypatch, result=SUMMARY)
    caplog.set_level(logging.INFO, logger="cityflow.transform")

    exit_code = cli.main(["--month", MONTH])

    assert exit_code == 0
    assert "Transform of 2025-01 finished" in caplog.text
    assert "10 input, 7 accepted, 3 rejected rows" in caplog.text


def test_main_success_log_does_not_dump_the_whole_summary(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    patch_transform_month(monkeypatch, result=SUMMARY)
    caplog.set_level(logging.INFO, logger="cityflow.transform")

    cli.main(["--month", MONTH])

    assert SUMMARY["source_sha256"] not in caplog.text


def test_main_passes_the_month_storage_and_a_work_dir_to_the_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Any, ...]] = []

    def fake_transform_month(
        storage: S3StorageAdapter, month: str, work_dir: Path
    ) -> dict[str, Any]:
        calls.append((storage, month, work_dir, work_dir.is_dir()))
        return SUMMARY

    monkeypatch.setattr(cli, "transform_month", fake_transform_month)

    cli.main(["--month", MONTH])

    [(storage, month, work_dir, existed)] = calls
    assert isinstance(storage, S3StorageAdapter)
    assert storage.bucket == "test-bucket"
    assert month == MONTH
    assert existed
    assert not work_dir.exists()  # the temporary directory is removed afterwards


@pytest.mark.parametrize(
    ("error", "stage"),
    [
        (TransformInputError("no Raw manifest"), "input"),
        (ValidationError("missing column"), "input"),
        (pl.exceptions.ComputeError("cannot write"), "transform"),
        (CountMismatchError("accepted + rejected != input"), "transform"),
        (PublicationError("checksum mismatch"), "publish"),
        (StorageError("upload failed"), "storage"),
    ],
)
def test_main_stage_failure_returns_one_and_logs_stage(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    stage: str,
) -> None:
    patch_transform_month(monkeypatch, error=error)

    exit_code = cli.main(["--month", MONTH])

    assert exit_code == 1
    assert f"failed at stage {stage}" in caplog.text
    assert MONTH in caplog.text
    assert str(error) in caplog.text


def test_main_unexpected_error_is_not_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_transform_month(monkeypatch, error=RuntimeError("bug"))

    with pytest.raises(RuntimeError, match="bug"):
        cli.main(["--month", MONTH])


@pytest.mark.parametrize(
    "variable", ["S3_BUCKET", "S3_ENDPOINT_URL", "S3_ACCESS_KEY", "S3_SECRET_KEY"]
)
def test_main_missing_env_variable_fails_at_config_stage(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, variable: str
) -> None:
    patch_transform_month(monkeypatch, result=SUMMARY)
    monkeypatch.delenv(variable)

    exit_code = cli.main(["--month", MONTH])

    assert exit_code == 1
    assert "Transform of 2025-01 failed at stage config" in caplog.text
    assert variable in caplog.text


def test_main_missing_env_variable_does_not_run_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(
        cli, "transform_month", lambda *args, **kwargs: calls.append("run")
    )
    monkeypatch.delenv("S3_BUCKET")

    cli.main(["--month", MONTH])

    assert calls == []


@pytest.mark.parametrize("value", ["2025-13", "202501", "jan-2025", ""])
def test_main_invalid_month_exits_with_usage_error(value: str) -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--month", value])

    assert exit_info.value.code == 2


def test_main_missing_month_exits_with_usage_error() -> None:
    with pytest.raises(SystemExit) as exit_info:
        cli.main([])

    assert exit_info.value.code == 2


def test_main_failure_log_does_not_contain_credentials(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    patch_transform_month(monkeypatch, error=StorageError("upload failed"))

    exit_code = cli.main(["--month", MONTH])

    assert exit_code == 1
    assert "failed at stage storage" in caplog.text
    assert ACCESS_KEY not in caplog.text
    assert SECRET_KEY not in caplog.text

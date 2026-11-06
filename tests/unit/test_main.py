import logging

import httpx
import pytest

from cityflow.ingestion import __main__ as cli
from cityflow.ingestion.download import DownloadError
from cityflow.ingestion.publish import PublicationError
from cityflow.ingestion.validate import ValidationError
from cityflow.storage.s3_adapter import StorageError

MONTH = "2025-01"
ACCESS_KEY = "test-access-key-123"
SECRET_KEY = "test-secret-key-456"  # noqa: S105  (fake value for tests)


@pytest.fixture(autouse=True)
def s3_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Complete fake S3 configuration; creating a boto3 client does no network I/O."""
    monkeypatch.setenv("S3_BUCKET", "test-bucket")
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://127.0.0.1:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", ACCESS_KEY)
    monkeypatch.setenv("S3_SECRET_KEY", SECRET_KEY)


def patch_ingest_month(monkeypatch: pytest.MonkeyPatch, *, result=None, error=None) -> None:
    """Replace the pipeline so the test controls how ingestion ends."""

    def fake_ingest_month(*args, **kwargs):
        if error is not None:
            raise error
        return result

    monkeypatch.setattr(cli, "ingest_month", fake_ingest_month)


@pytest.mark.parametrize("outcome", ["published", "skipped", "recovered"])
def test_main_success_returns_zero_and_logs_outcome(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, outcome: str
) -> None:
    patch_ingest_month(monkeypatch, result=outcome)
    caplog.set_level(logging.INFO, logger="cityflow.ingestion")

    exit_code = cli.main(["--month", MONTH])

    assert exit_code == 0
    assert outcome in caplog.text


@pytest.mark.parametrize(
    ("error", "stage"),
    [
        (DownloadError("incomplete download"), "download"),
        (httpx.ConnectError("connection refused"), "download"),
        (ValidationError("missing column"), "validate"),
        (PublicationError("checksum conflict"), "publish"),
        (StorageError("upload failed"), "publish"),
    ],
)
def test_main_stage_failure_returns_one_and_logs_stage(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    stage: str,
) -> None:
    patch_ingest_month(monkeypatch, error=error)

    exit_code = cli.main(["--month", MONTH])

    assert exit_code == 1
    assert f"failed at stage {stage}" in caplog.text
    assert MONTH in caplog.text
    assert str(error) in caplog.text


@pytest.mark.parametrize(
    "variable", ["S3_BUCKET", "S3_ENDPOINT_URL", "S3_ACCESS_KEY", "S3_SECRET_KEY"]
)
def test_main_missing_env_variable_fails_at_config_stage(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture, variable: str
) -> None:
    patch_ingest_month(monkeypatch, result="published")
    monkeypatch.delenv(variable)

    exit_code = cli.main(["--month", MONTH])

    assert exit_code == 1
    assert "failed at stage config" in caplog.text
    assert variable in caplog.text
                                             

def test_main_missing_env_variable_does_not_run_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []
    monkeypatch.setattr(cli, "ingest_month", lambda *args, **kwargs: calls.append("run"))
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
    patch_ingest_month(monkeypatch, error=StorageError("upload failed"))
    exit_code = cli.main(["--month", MONTH])

    assert exit_code == 1
    assert "failed at stage publish" in caplog.text
    assert ACCESS_KEY not in caplog.text
    assert SECRET_KEY not in caplog.text

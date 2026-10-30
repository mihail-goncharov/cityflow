from pathlib import Path

import httpx
import pytest

from cityflow.ingestion.download import (
    DownloadError,
    build_source_url,
    download_file,
    download_with_retries,
    parse_month,
)

CONTENT = b"CONTENT"
URL = "https://example.test/file.parquet"


@pytest.fixture()
def destination(tmp_path) -> Path:
    return tmp_path / "file.parquet"


@pytest.fixture()
def part_file(destination) -> Path:
    return Path(f"{destination}.part")


def make_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def ok_response(content_length: int | None = None) -> httpx.Response:
    if content_length is None:
        content_length = len(CONTENT)
    return httpx.Response(200, content=iter([CONTENT]), headers={"Content-Length": str(content_length)})


def ok_handler(request):
    return ok_response()


def truncated_handler(request):
    return ok_response(content_length=len(CONTENT) + 10)


@pytest.mark.parametrize("value", ["2025-1", "2025-13", "2025-00", "jan", ""])
def test_parse_month_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        parse_month(value)


@pytest.mark.parametrize("value", ["2025-01", "2025-02", "2025-03"])
def test_parse_month_accepts_valid_value(value):
    assert parse_month(value) == value


def test_build_source_url_january_2025():
    assert build_source_url("2025-01") == (
            "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-01.parquet"
    )


def test_download_file_success(destination, part_file):
    with make_client(handler=ok_handler) as client:
        download_file(URL, destination, client)

    assert destination.read_bytes() == CONTENT
    assert not part_file.exists()


def test_download_file_truncated_raises_download_error(destination, part_file):

    with make_client(handler=truncated_handler) as client, pytest.raises(DownloadError):
        download_file(URL, destination, client)

    assert not part_file.exists()
    assert not destination.exists()


def test_download_with_retries_404_raises_http_status_error(destination):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(404, content=iter([CONTENT]), headers={"Content-Length": str(len(CONTENT))})

    with make_client(handler=handler) as client, pytest.raises(httpx.HTTPStatusError):
        download_with_retries(URL, destination, client, retry_delay=0)

    assert len(requests) == 1


def test_download_with_retries_exhausted_retries_raises_download_error(destination):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx.Response(503, content=iter([CONTENT]), headers={"Content-Length": str(len(CONTENT))})

    with make_client(handler=handler) as client, pytest.raises(DownloadError):
        download_with_retries(URL, destination, client,
                              max_attempts=3, retry_delay=0)

    assert len(requests) == 3
    assert not destination.exists()


def test_download_with_retries_succeeds_after_503(destination):
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(503)

        return ok_response()

    with make_client(handler=handler) as client:
        download_with_retries(URL, destination, client, max_attempts=3, retry_delay=0)

    assert len(requests) == 2
    assert destination.read_bytes() == CONTENT


def test_download_with_retries_succeeds_after_timeout(destination):
    requests = []

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ReadTimeout("timed out", request=request)

        return ok_response()

    with make_client(handler=handler) as client:
        download_with_retries(URL, destination, client, max_attempts=3, retry_delay=0)

    assert len(requests) == 2
    assert destination.read_bytes() == CONTENT


def interrupted_body():
    yield CONTENT
    raise KeyboardInterrupt


def test_download_file_interrupted_removes_partial_file(destination, part_file):
    def handler(request):
        return httpx.Response(200, content=interrupted_body())

    with make_client(handler=handler) as client, pytest.raises(KeyboardInterrupt):
        download_file(URL, destination, client)


    assert not destination.exists()
    assert not part_file.exists()


def test_download_file_failed_rename_removes_partial_file(destination, part_file):
    destination.mkdir()
    with make_client(ok_handler) as client, pytest.raises(OSError):
        download_file(URL, destination, client)

    assert not part_file.exists()
    assert destination.is_dir()

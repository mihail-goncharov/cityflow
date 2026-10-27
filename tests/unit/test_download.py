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


def ok_handler(request):
    return httpx.Response(200, content=iter([CONTENT]), headers={"Content-Length": str(len(CONTENT))})

def truncated_handler(request):
    return httpx.Response(200, content=iter([CONTENT]), headers={"Content-Length": str(len(CONTENT) + 10)})


@pytest.mark.parametrize("value", ["2025-1", "2025-13", "2025-00", "jan", ""])
def test_parse_month_rejects_invalid_values(value):
    with pytest.raises(ValueError):
        parse_month(value)


@pytest.mark.parametrize("value", ["2025-01", "2025-02", "2025-03"])
def test_parse_month_accepts_valid_value(value):
    assert parse_month(value) == value


def test_build_source_url_january_2025():
    assert (build_source_url("2025-01") ==
            "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-01.parquet")


def test_download_file_success(tmp_path):
    destination = tmp_path / "file.parquet"
    part_file = tmp_path / "file.parquet.part"
    with httpx.Client(transport=httpx.MockTransport(ok_handler)) as client:
        download_file(build_source_url("2025-01"), destination, client)

    assert destination.read_bytes() == CONTENT
    assert not part_file.exists()


def test_download_file_truncated_raises_download_error(tmp_path):
    destination = tmp_path / "file.parquet"
    part_file = tmp_path / "file.parquet.part"
    with httpx.Client(transport=httpx.MockTransport(truncated_handler)) as client:
        with pytest.raises(DownloadError):
            download_file(build_source_url("2025-01"), destination, client)

    assert not part_file.exists()


def test_download_file_404_raises_http_status_error(tmp_path):
    requests = []

    destination = tmp_path / "file.parquet"

    def handler(request):
        requests.append(request)
        return httpx.Response(404, content=iter([CONTENT]), headers={"Content-Length": str(len(CONTENT))})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            download_with_retries(build_source_url("2025-01"), destination, client, retry_delay=0)

    assert len(requests) == 1


def test_download_file_exhausted_retries_raises_download_error(tmp_path):
    requests = []

    destination = tmp_path / "file.parquet"

    def handler(request):
        requests.append(request)
        return httpx.Response(503, content=iter([CONTENT]), headers={"Content-Length": str(len(CONTENT))})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(DownloadError):
            download_with_retries(build_source_url("2025-01"), destination, client,
                                  max_attempts=3, retry_delay=0)

    assert len(requests) == 3
    assert not destination.exists()


def test_download_with_retries_succeeds_after_503(tmp_path):
    requests = []

    destination = tmp_path / "file.parquet"

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
            return httpx.Response(503)

        return httpx.Response(200, content=iter([CONTENT]), headers={"Content-Length": str(len(CONTENT))})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        download_with_retries(build_source_url("2025-01"), destination, client, max_attempts=3, retry_delay=0)

    assert len(requests) == 2
    assert destination.read_bytes() == CONTENT


def test_download_with_retries_succeeds_after_timeout(tmp_path):
    requests = []

    destination = tmp_path / "file.parquet"

    def handler(request):
        requests.append(request)
        if len(requests) == 1:
           raise httpx.ReadTimeout("timed out", request=request)

        return httpx.Response(200, content=iter([CONTENT]), headers={"Content-Length": str(len(CONTENT))})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        download_with_retries(build_source_url("2025-01"), destination, client, max_attempts=3, retry_delay=0)

    assert len(requests) == 2
    assert destination.read_bytes() == CONTENT
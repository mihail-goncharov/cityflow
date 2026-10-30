import re
import time
from datetime import datetime
from pathlib import Path

import httpx

TLC_BASE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data"
CHUNK_SIZE = 1024 * 1024
DOWNLOAD_TIMEOUT = httpx.Timeout(timeout=30, connect=10)
MAX_ATTEMPTS = 3
RETRY_DELAY_SECONDS = 5.0


class DownloadError(Exception):
    """Raised when a file cannot be downloaded completely."""


def parse_month(value: str) -> str:
    message = f"Invalid month '{value}': expected YYYY-MM, e.g. 2025-01"
    if re.fullmatch(r"\d{4}-\d{2}", value) is None:
        raise ValueError(message)

    try:
        datetime.strptime(value, "%Y-%m")
    except ValueError as e:
        raise ValueError(message) from e
    else:
        return value


def build_source_url(month: str) -> str:
    parse_month(month)
    return f"{TLC_BASE_URL}/yellow_tripdata_{month}.parquet"


def download_file(url: str, destination: Path, client: httpx.Client) -> None:
    """Download url to destination in a single attempt.

    Streams the response into a temporary ``.part`` file and checks its size
    against Content-Length when the server provides it. On any failure the
    partial file is removed; on success it is renamed.
    """
    temp_path = Path(f"{destination}.part")

    with client.stream("GET", url, timeout=DOWNLOAD_TIMEOUT) as response:
        response.raise_for_status()

        try:
            with open(temp_path, "wb") as file:
                file.writelines(response.iter_bytes(chunk_size=CHUNK_SIZE))

            content_length = response.headers.get("Content-Length")
            received = response.num_bytes_downloaded
            if content_length is not None and int(content_length) != received:
                raise DownloadError(
                    f"Incomplete download from {url}: "
                    f"expected {content_length} bytes, received {received}"
                )

            temp_path.replace(destination)
        finally:
            temp_path.unlink(missing_ok=True)


def download_with_retries(
    url: str,
    destination: Path,
    client: httpx.Client,
    max_attempts: int = MAX_ATTEMPTS,
    retry_delay: float = RETRY_DELAY_SECONDS,
) -> None:
    """Download url to destination, retrying temporary failures.

    Makes up to max_attempts attempts (default 3), waiting retry_delay
    seconds (default 5) between them. Network errors, timeouts, 5xx
    responses and incomplete downloads are retried. 4xx responses fail
    immediately with httpx.HTTPStatusError. Raises DownloadError when all
    attempts fail.
    """
    last_error: Exception | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            download_file(url, destination, client)
            return
        except httpx.HTTPStatusError as error:
            if error.response.status_code < 500:
                raise
            last_error = error
        except (httpx.TransportError, DownloadError) as error:
            last_error = error

        if attempt < max_attempts:
            time.sleep(retry_delay)

    raise DownloadError(
        f"Failed to download {url} after {max_attempts} attempts"
    ) from last_error

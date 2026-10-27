import re
from datetime import datetime
from pathlib import Path

import httpx


TLC_BASE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data"
CHUNK_SIZE = 1024 * 1024
DOWNLOAD_TIMEOUT = httpx.Timeout(timeout=30, connect=10)


class DownloadError(Exception):
    pass


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


def download_file(url: str, destination: Path) -> None:
    temp_path = Path(f"{destination}.part")

    with httpx.stream("GET", url, timeout=DOWNLOAD_TIMEOUT) as response:
        response.raise_for_status()

        try:
            with open(temp_path, "wb") as file:
                for chunk in response.iter_bytes(chunk_size=CHUNK_SIZE):
                    file.write(chunk)

            url_content_length = response.headers.get("Content-Length")
            if url_content_length is not None and int(url_content_length) != response.num_bytes_downloaded:
                raise DownloadError(f"Incomplete download from {url}: "
                                    f"expected {url_content_length} bytes, "
                                    f"received {response.num_bytes_downloaded}")
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise
        else:
            temp_path.replace(destination)

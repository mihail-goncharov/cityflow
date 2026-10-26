import re
from datetime import datetime
from pathlib import Path

import httpx


TLC_BASE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data"
CHUNK_SIZE = 1024 * 1024
DOWNLOAD_TIMEOUT = httpx.Timeout(timeout=30, connect=10)


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
    with httpx.stream("GET", url, timeout=DOWNLOAD_TIMEOUT) as response:
        response.raise_for_status()
        with open(destination, "wb") as file:
            for chunk in response.iter_bytes(chunk_size=CHUNK_SIZE):
                file.write(chunk)
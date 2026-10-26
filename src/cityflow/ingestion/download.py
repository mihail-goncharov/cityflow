import re
from datetime import datetime


TLC_BASE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data"


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
from datetime import datetime

import polars as pl
import pytest

from cityflow.ingestion.validate import REQUIRED_COLUMNS


@pytest.fixture()
def valid_trips() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "tpep_pickup_datetime": [datetime(2025, 1, 1, 10, 0)],
            "tpep_dropoff_datetime": [datetime(2025, 1, 1, 10, 15)],
            "PULocationID": [132],
            "DOLocationID": [236],
            "trip_distance": [3.2],
            "fare_amount": [17.5],
            "total_amount": [24.8],
        },
        schema=REQUIRED_COLUMNS
    )
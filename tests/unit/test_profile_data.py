from datetime import datetime, timedelta

import polars as pl

from cityflow.profile_data import quality_checks, valid_trips

START = datetime(2025, 1, 15, 12, 0)


def make_trips(**overrides) -> pl.DataFrame:
    """One clean trip. Keyword arguments replace single values."""
    trip = {
        "VendorID": 2, "tpep_pickup_datetime": START, "tpep_dropoff_datetime": START + timedelta(minutes=15),
        "passenger_count": 1, "trip_distance": 3.0, "RatecodeID": 1, "store_and_fwd_flag": "N",
        "PULocationID": 161, "DOLocationID": 236, "payment_type": 1, "fare_amount": 15.0,
        "total_amount": 20.0, "congestion_surcharge": 2.5, "Airport_fee": 0.0,
    }
    trip.update(**overrides)
    return pl.DataFrame([trip])


def is_valid(**overrides) -> bool:
    return valid_trips(make_trips(**overrides)).height == 1


def test_clean_trip_is_kept():
    assert is_valid()


def test_fare_boundaries():
    assert not is_valid(fare_amount=0.0)
    assert is_valid(fare_amount=1000.0)
    assert not is_valid(fare_amount=1000.01)


def test_distance_boundaries():
    assert not is_valid(trip_distance=0.0)
    assert is_valid(trip_distance=200.0)
    assert not is_valid(trip_distance=200.1)


def test_duration_boundaries():
    assert is_valid(tpep_dropoff_datetime=START + timedelta(hours=5))
    assert not is_valid(tpep_dropoff_datetime=START + timedelta(hours=5, seconds=1))


def test_quality_checks_do_not_crash_on_small_data():
    quality_checks(make_trips())
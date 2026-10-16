from datetime import datetime, timedelta

import polars as pl
import pytest

from cityflow.profile_data import (
    business_questions,
    profile,
    quality_checks,
    valid_trips,
)

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


@pytest.mark.parametrize("missing_metrics", [False, True])
def test_profile_formats_numeric_metrics(capsys, missing_metrics):
    trips = make_trips()
    if missing_metrics:
        trips = trips.with_columns(
            pl.lit(None, dtype=pl.Float64).alias("fare_amount"),
            pl.lit(None, dtype=pl.Float64).alias("trip_distance"),
        )

    profile(trips)

    output = capsys.readouterr().out
    expected_distance = "N/A" if missing_metrics else "3.00"
    expected_fare = "N/A" if missing_metrics else "15.00"
    expected_extreme = "N/A" if missing_metrics else "15.0"
    assert f"Average trip_distance: {expected_distance} miles" in output
    assert f"Average fare_amount: {expected_fare}" in output
    assert f"Min fare_amount: {expected_extreme}" in output
    assert f"Max fare_amount: {expected_extreme}" in output


@pytest.mark.parametrize("missing_metrics", [False, True])
def test_business_questions_formats_metrics(tmp_path, monkeypatch, capsys, missing_metrics):
    zone_file = tmp_path / "zones.csv"
    zone_file.write_text("LocationID,Zone\n161,Midtown Center\n236,Upper East Side North\n", encoding="utf-8")
    monkeypatch.setattr("cityflow.profile_data.TAXI_ZONE", zone_file)
    trips = make_trips()
    if missing_metrics:
        trips = trips.with_columns(
            pl.lit(None, dtype=pl.Float64).alias("fare_amount"),
            pl.lit(None, dtype=pl.Float64).alias("trip_distance"),
        )

    business_questions(trips)

    output = capsys.readouterr().out
    expected_fare = "N/A" if missing_metrics else "15.00"
    expected_distance = "N/A" if missing_metrics else "3.00"
    assert f"Average fare per trip: {expected_fare}" in output
    assert f"Average distance: {expected_distance}" in output
    assert "Average duration: 0:15:00" in output
    assert "Busiest hour: 12:00 - 13:00 (1 trips)" in output

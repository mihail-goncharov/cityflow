from datetime import date, datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from cityflow.profile_data import (
    _format_numeric,
    business_questions,
    profile,
    quality_checks,
    quality_rules,
    show_examples,
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
    schema = pl.DataFrame([trip]).schema
    trip.update(**overrides)
    return pl.DataFrame([trip], schema=schema)


@pytest.fixture
def taxi_zones(tmp_path, monkeypatch):
    zone_file = tmp_path / "zones.csv"
    zone_file.write_text("LocationID,Zone\n161,Midtown Center\n236,Upper East Side North\n", encoding="utf-8")
    monkeypatch.setattr("cityflow.profile_data.TAXI_ZONE", zone_file)
    return zone_file


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
def test_business_questions_formats_metrics(taxi_zones, capsys, missing_metrics):
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


@pytest.mark.parametrize(("rule", "overrides", "expected"), [
    ("zero_or_negative_fare", {"fare_amount": -1.0}, True),
    ("zero_or_negative_fare", {"fare_amount": 0.0}, True),
    ("zero_or_negative_fare", {"fare_amount": 0.01}, False),
    ("zero_distance", {"trip_distance": -1.0}, True),
    ("zero_distance", {"trip_distance": 0.0}, True),
    ("zero_distance", {"trip_distance": 0.01}, False),
    ("unknown_location", {"PULocationID": 264}, True),
    ("unknown_location", {"PULocationID": 265}, True),
    ("unknown_location", {"DOLocationID": 264}, True),
    ("unknown_location", {"DOLocationID": 265}, True),
    ("unknown_location", {}, False),
    ("dropoff_before_pickup", {"tpep_dropoff_datetime": START - timedelta(seconds=1)}, True),
    ("dropoff_before_pickup", {"tpep_dropoff_datetime": START}, False),
    ("outside_january", {"tpep_pickup_datetime": datetime(2024, 12, 31, 23, 59, 59)}, True),
    ("outside_january", {"tpep_pickup_datetime": datetime(2025, 1, 1)}, False),
    ("outside_january", {"tpep_pickup_datetime": datetime(2025, 1, 31, 23, 59, 59)}, False),
    ("outside_january", {"tpep_pickup_datetime": datetime(2025, 2, 1)}, True),
    ("zero_duration_with_distance", {"tpep_dropoff_datetime": START}, True),
    ("zero_duration_with_distance", {"tpep_dropoff_datetime": START, "trip_distance": 0.0}, False),
    ("zero_duration_with_distance", {}, False),
    ("extreme_distance", {"trip_distance": 200.0}, False),
    ("extreme_distance", {"trip_distance": 200.01}, True),
    ("long_duration", {"tpep_dropoff_datetime": START + timedelta(hours=5)}, False),
    ("long_duration", {"tpep_dropoff_datetime": START + timedelta(hours=5, seconds=1)}, True),
    ("missing_passenger", {"passenger_count": None}, True),
    ("missing_passenger", {"passenger_count": 0}, False),
    ("missing_passenger", {}, False),
    ("extreme_fare", {"fare_amount": 1000.0}, False),
    ("extreme_fare", {"fare_amount": 1000.01}, True),
])
def test_quality_rule_boundaries(rule, overrides, expected):
    assert make_trips(**overrides).select(quality_rules()[rule]).item() is expected


@pytest.mark.parametrize("overrides", [
    {"fare_amount": -1.0},
    {"trip_distance": -1.0},
    {"tpep_dropoff_datetime": START - timedelta(seconds=1)},
    {"tpep_pickup_datetime": datetime(2024, 12, 31, 23, 59),
     "tpep_dropoff_datetime": datetime(2025, 1, 1)},
    {"tpep_pickup_datetime": datetime(2025, 2, 1),
     "tpep_dropoff_datetime": datetime(2025, 2, 1, 0, 15)},
    {"tpep_dropoff_datetime": START},
    {"trip_distance": 200.01},
    {"tpep_dropoff_datetime": START + timedelta(hours=5, seconds=1)},
    {"fare_amount": 1000.01},
    {"fare_amount": None},
    {"trip_distance": None},
    {"tpep_pickup_datetime": None},
    {"tpep_dropoff_datetime": None},
])
def test_invalid_or_incomplete_trips_are_rejected(overrides):
    assert not is_valid(**overrides)


@pytest.mark.parametrize("overrides", [
    {"passenger_count": None},
    {"PULocationID": 264},
    {"DOLocationID": 265},
    {"tpep_pickup_datetime": datetime(2025, 1, 1),
     "tpep_dropoff_datetime": datetime(2025, 1, 1, 0, 15)},
    {"tpep_pickup_datetime": datetime(2025, 1, 31, 23, 59, 59),
     "tpep_dropoff_datetime": datetime(2025, 2, 1, 0, 15)},
])
def test_acceptable_trips_are_retained(overrides):
    assert is_valid(**overrides)


def test_filter_preserves_values_schema_order_and_input():
    first = make_trips()
    last = make_trips(fare_amount=25.0, passenger_count=None, PULocationID=264)
    trips = pl.concat([first, make_trips(fare_amount=-5.0), last, make_trips(trip_distance=0.0)])
    original = trips.clone()

    result = valid_trips(trips)

    assert_frame_equal(result, pl.concat([first, last]))
    assert_frame_equal(trips, original)
    assert_frame_equal(valid_trips(result), result)


def test_empty_input_keeps_schema():
    trips = make_trips().clear()
    assert_frame_equal(valid_trips(trips), trips)


@pytest.mark.parametrize(("value", "spec", "expected"), [
    (None, ".2f", "N/A"),
    (1234, ",", "1,234"),
    (2.125, ".2f", "2.12"),
    (Decimal("12.34"), ".2f", "12.34"),
    (0, "", "0"),
])
def test_format_numeric(value, spec, expected):
    assert _format_numeric(value, spec) == expected


@pytest.mark.parametrize("value", ["12.34", [], object()])
def test_format_numeric_rejects_non_numeric_values(value):
    with pytest.raises(TypeError, match="Expected a numeric aggregate"):
        _format_numeric(value)


def test_show_examples_filters_selects_and_limits(monkeypatch):
    printed = Mock()
    monkeypatch.setattr("cityflow.profile_data.print", printed, raising=False)
    trips = pl.concat([make_trips(fare_amount=value) for value in [15.0, -1.0, -2.0, -3.0]])

    show_examples(trips, pl.col("fare_amount") < 0, ["fare_amount"], limit=2)

    assert_frame_equal(printed.call_args.args[0], pl.DataFrame({"fare_amount": [-1.0, -2.0]}))


def test_business_aggregates_use_all_valid_rows(taxi_zones, monkeypatch):
    printed = Mock()
    monkeypatch.setattr("cityflow.profile_data.print", printed, raising=False)
    trips = pl.concat([
        make_trips(fare_amount=10.0, trip_distance=1.0),
        make_trips(fare_amount=20.0, trip_distance=3.0,
                   tpep_pickup_datetime=START + timedelta(minutes=30),
                   tpep_dropoff_datetime=START + timedelta(minutes=55)),
        make_trips(fare_amount=30.0, trip_distance=5.0, PULocationID=236, DOLocationID=161,
                   tpep_pickup_datetime=START + timedelta(days=1, hours=1),
                   tpep_dropoff_datetime=START + timedelta(days=1, hours=1, minutes=20)),
        make_trips(fare_amount=-999.0, trip_distance=100.0),
    ])

    business_questions(valid_trips(trips))

    printed.assert_any_call("Valid trips: ", 3)
    printed.assert_any_call("Total fare amount: 60.00")
    printed.assert_any_call("Average fare per trip: 20.00")
    printed.assert_any_call("Average distance: 3.00")
    printed.assert_any_call("Average duration:", timedelta(minutes=20))
    printed.assert_any_call("Busiest hour: 12:00 - 13:00 (2 trips)")
    tables = {call.args[0]: call.args[1] for call in printed.call_args_list
              if len(call.args) == 2 and isinstance(call.args[1], pl.DataFrame)}
    assert tables["Top 10 pickup locations: "].to_dicts() == [
        {"PULocationID": 161, "count": 2, "Zone": "Midtown Center"},
        {"PULocationID": 236, "count": 1, "Zone": "Upper East Side North"},
    ]
    assert tables["Top 10 dropoff locations: "].to_dicts() == [
        {"DOLocationID": 236, "count": 2, "Zone": "Upper East Side North"},
        {"DOLocationID": 161, "count": 1, "Zone": "Midtown Center"},
    ]
    assert tables["Number of trips per day: "].to_dicts() == [
        {"date": date(2025, 1, 15), "trips": 2}, {"date": date(2025, 1, 16), "trips": 1},
    ]
    assert tables["Number of trips per hour: "].to_dicts() == [
        {"hour": 12, "trips": 2}, {"hour": 13, "trips": 1},
    ]


@pytest.mark.parametrize("all_rejected", [False, True])
def test_business_questions_handles_no_valid_trips(taxi_zones, capsys, all_rejected):
    trips = valid_trips(make_trips(fare_amount=-1.0)) if all_rejected else make_trips().clear()

    business_questions(trips)

    output = capsys.readouterr().out
    assert "Valid trips:  0" in output
    assert "Total fare amount: 0.00" in output
    assert "Average fare per trip: N/A" in output
    assert "Average distance: N/A" in output
    assert "Average duration: None" in output
    assert "Busiest hour: N/A" in output


def test_profile_main_reads_parquet_and_filters_metrics(tmp_path, taxi_zones, monkeypatch, capsys):
    from cityflow import profile_data

    raw_file = tmp_path / "trips.parquet"
    pl.concat([make_trips(), make_trips(fare_amount=-1.0)]).write_parquet(raw_file)
    monkeypatch.setattr(profile_data, "RAW_FILE", raw_file)

    with pl.Config():
        profile_data.main()

    output = capsys.readouterr().out
    assert "Rows: 2" in output
    assert "Zero or negative fare:  1" in output
    assert "Valid trips:  1" in output
    assert "Total fare amount: 15.00" in output

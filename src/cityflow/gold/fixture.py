"""Small, fixed Silver file for the Gold tests (docs/gold.md section 5).

The rows are written as Raw trips and passed through the real Bronze and
Silver transform, so the fixture has exactly the Silver schema and derived
columns, and cannot drift from what the pipeline produces.

Usage: python -m cityflow.gold.fixture <out_dir> [--variant trips|empty|invalid_zone]
"""

import argparse
from datetime import datetime
from pathlib import Path
from typing import Literal, get_args

import polars as pl

from cityflow.ingestion.pipeline import build_object_key
from cityflow.transform.bronze import to_bronze
from cityflow.transform.layers import DATASET_PATH, build_layer_key
from cityflow.transform.silver import to_silver
from cityflow.transform.split import split_accepted_rejected

FIXTURE_MONTH = "2025-01"

# A pickup zone that is not in taxi_zone_lookup.csv. Real Silver cannot contain
# it (the reject rules allow only 1 to 265); the invalid_zone variant uses it to
# check that Gold fails instead of silently losing the trip.
INVALID_ZONE_ID = 999

Variant = Literal["trips", "empty", "invalid_zone"]

# The 20 Raw columns with their Polars types (docs/dataset.md).
SOURCE_SCHEMA: dict[str, pl.DataType] = {
    "VendorID": pl.Int32(),
    "tpep_pickup_datetime": pl.Datetime("us"),
    "tpep_dropoff_datetime": pl.Datetime("us"),
    "passenger_count": pl.Int64(),
    "trip_distance": pl.Float64(),
    "RatecodeID": pl.Int64(),
    "store_and_fwd_flag": pl.String(),
    "PULocationID": pl.Int32(),
    "DOLocationID": pl.Int32(),
    "payment_type": pl.Int64(),
    "fare_amount": pl.Float64(),
    "extra": pl.Float64(),
    "mta_tax": pl.Float64(),
    "tip_amount": pl.Float64(),
    "tolls_amount": pl.Float64(),
    "improvement_surcharge": pl.Float64(),
    "total_amount": pl.Float64(),
    "congestion_surcharge": pl.Float64(),
    "Airport_fee": pl.Float64(),
    "cbd_congestion_fee": pl.Float64(),
}


def _trip(
    pickup: datetime,
    dropoff: datetime,
    pickup_zone: int,
    dropoff_zone: int,
    distance: float,
    fare: float,
    tip: float,
    *,
    extra: float = 0.0,
    flex_fare: bool = False,
) -> dict[str, object]:
    """One accepted trip. Every money column is filled, so total adds up.

    A Flex Fare trip has null passenger_count, RatecodeID, store_and_fwd_flag,
    congestion_surcharge and Airport_fee, as in the real data. A negative
    extra stands for an adjustment that can make the total negative.
    """
    congestion = None if flex_fare else 2.5
    total = fare + extra + 0.5 + tip + 1.0 + (congestion or 0.0)
    return {
        "VendorID": 2,
        "tpep_pickup_datetime": pickup,
        "tpep_dropoff_datetime": dropoff,
        "passenger_count": None if flex_fare else 1,
        "trip_distance": distance,
        "RatecodeID": None if flex_fare else 1,
        "store_and_fwd_flag": None if flex_fare else "N",
        "PULocationID": pickup_zone,
        "DOLocationID": dropoff_zone,
        "payment_type": 0 if flex_fare else 1,
        "fare_amount": fare,
        "extra": extra,
        "mta_tax": 0.5,
        "tip_amount": tip,
        "tolls_amount": 0.0,
        "improvement_surcharge": 1.0,
        "total_amount": total,
        "congestion_surcharge": congestion,
        "Airport_fee": None if flex_fare else 0.0,
        "cbd_congestion_fee": 0.0,
    }


def fixture_trips() -> pl.DataFrame:
    """The nine Raw trips of the fixture, each covering one Gold edge case."""
    jan1, jan2 = datetime(2025, 1, 1), datetime(2025, 1, 2)
    trips = [
        # 0 and 1: identical-looking trips; both must be counted.
        _trip(jan1.replace(hour=10), jan1.replace(hour=10, minute=10), 132, 236, 2.0, 10.0, 1.0),
        _trip(jan1.replace(hour=10), jan1.replace(hour=10, minute=10), 132, 236, 2.0, 10.0, 1.0),
        # 2: pickup in zone 264 (Unknown); must be kept.
        _trip(jan1.replace(hour=10, minute=30), jan1.replace(hour=10, minute=50), 264, 236, 4.0, 20.0, 1.0),
        # 3: pickup in zone 265 (Outside of NYC) at 23:55, dropoff the next day;
        # belongs to 1 January, hour 23.
        _trip(jan1.replace(hour=23, minute=55), jan2.replace(minute=10), 265, 132, 3.0, 15.0, 1.0),
        # 4: Flex Fare trip with null optional fields.
        _trip(jan2.replace(hour=8), jan2.replace(hour=8, minute=30), 132, 161, 6.0, 30.0, 3.5, flex_fare=True),
        # 5: a second trip in the same date and hour as trip 4.
        _trip(jan2.replace(hour=8, minute=20), jan2.replace(hour=8, minute=35), 48, 230, 1.0, 5.0, 0.0),
        # 6 and 7: fares of 1000 and 1001 cents in one hour, so the average is
        # exactly 1000.5 and must round half away from zero to 1001.
        _trip(jan2.replace(hour=12), jan2.replace(hour=12, minute=10), 132, 236, 1.5, 10.0, 0.0),
        _trip(jan2.replace(hour=12, minute=30), jan2.replace(hour=12, minute=40), 132, 236, 1.5, 10.01, 0.0),
        # 8: positive fare with a negative adjustment, so total_amount is
        # -8.00. Silver keeps negative totals; Gold must sum them as they are.
        _trip(jan2.replace(hour=15), jan2.replace(hour=15, minute=15), 48, 230, 2.0, 8.0, 0.0, extra=-20.0),
    ]
    return pl.DataFrame(trips, schema=SOURCE_SCHEMA)


def build_silver_fixture(trips: pl.DataFrame, month: str = FIXTURE_MONTH) -> pl.DataFrame:
    """Run trips through Bronze and the reject rules and return the Silver rows.

    Raises ValueError if any trip is rejected: a fixture row that would never
    reach Silver would test nothing real.
    """
    bronze = to_bronze(
        trips.lazy(),
        month=month,
        source_object_key=build_object_key(month, f"yellow_tripdata_{month}.parquet"),
        source_sha256="0" * 64,
        ingested_at="2025-02-01T00:00:00+00:00",
    )
    accepted, rejected = split_accepted_rejected(bronze, month)
    rejected_rows = rejected.collect()
    if rejected_rows.height:
        reasons = rejected_rows.select("source_row_id", "reject_reasons").to_dicts()
        raise ValueError(f"fixture trips would be rejected: {reasons}")
    return to_silver(accepted).collect()


def write_silver_fixture(out_dir: Path, *, variant: Variant = "trips") -> Path:
    """Write the fixture in the Silver storage layout and return its path.

    The file goes to <out_dir>/silver/nyc_tlc/yellow_taxi/year=YYYY/month=MM/,
    as in the bucket, so dbt reads it with
    CITYFLOW_SILVER_ROOT=<out_dir>/silver/nyc_tlc/yellow_taxi.

    Variants: "trips" writes all fixture trips; "empty" writes the same
    columns with no rows; "invalid_zone" writes all trips but gives trip 0
    the pickup zone INVALID_ZONE_ID. That variant is deliberately not valid
    Silver: it exists only to check that Gold fails on a zone missing from
    the lookup.
    """
    silver = build_silver_fixture(fixture_trips())
    if variant == "empty":
        silver = silver.clear()
    elif variant == "invalid_zone":
        silver = silver.with_columns(
            pl.when(pl.col("source_row_id") == 0)
            .then(pl.lit(INVALID_ZONE_ID))
            .otherwise(pl.col("PULocationID"))
            .cast(pl.Int32)
            .alias("PULocationID")
        )
    path = out_dir / build_layer_key("silver", FIXTURE_MONTH)
    path.parent.mkdir(parents=True, exist_ok=True)
    silver.write_parquet(path)
    return path


def silver_root(out_dir: Path) -> Path:
    """Return the value for CITYFLOW_SILVER_ROOT for a fixture in out_dir."""
    return out_dir / "silver" / DATASET_PATH


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Write the Gold test Silver fixture.")
    parser.add_argument("out_dir", type=Path)
    parser.add_argument(
        "--variant",
        choices=get_args(Variant),
        default="trips",
        help="trips (default), empty (columns without rows) or invalid_zone "
        "(one pickup zone missing from the lookup)",
    )
    args = parser.parse_args(argv)

    path = write_silver_fixture(args.out_dir, variant=args.variant)
    print(f"Wrote {path}")
    print(f"CITYFLOW_SILVER_ROOT={silver_root(args.out_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

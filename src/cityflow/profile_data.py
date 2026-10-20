from datetime import datetime
from decimal import Decimal
from pathlib import Path

import polars as pl

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "yellow_tripdata_2025-01.parquet"
TAXI_ZONE = PROJECT_ROOT / "data" / "raw" / "taxi_zone_lookup.csv"

MAX_DISTANCE_MILES = 200
MAX_DURATION = pl.duration(hours=5)
MAX_FARE = 1000


def _format_numeric(value: object, spec: str = "") -> str:
    """Format a numeric Polars aggregate, including an empty/all-null result."""
    if value is None:
        return "N/A"
    if not isinstance(value, (int, float, Decimal)):
        raise TypeError(f"Expected a numeric aggregate, got {type(value).__name__}")
    return format(value, spec)


def show_examples(df: pl.DataFrame, condition: pl.Expr, columns: list[str], limit: int = 5) -> None:
    print(df.filter(condition).select(columns).head(limit))


def quality_rules() -> dict[str, pl.Expr]:
    pickup = pl.col("tpep_pickup_datetime")
    dropoff = pl.col("tpep_dropoff_datetime")
    return {
        "zero_or_negative_fare": pl.col("fare_amount") <= 0,
        "zero_distance": pl.col("trip_distance") <= 0,
        "unknown_location": pl.col("PULocationID").is_in([264, 265]) | pl.col("DOLocationID").is_in([264, 265]),
        "dropoff_before_pickup": pickup > dropoff,
        "outside_january": (pickup < datetime(2025, 1, 1)) | (pickup >= datetime(2025, 2, 1)),
        "zero_duration_with_distance": (pickup == dropoff) & (pl.col("trip_distance") > 0),
        "extreme_distance": pl.col("trip_distance") > MAX_DISTANCE_MILES,
        "long_duration": (dropoff - pickup) > MAX_DURATION,
        "missing_passenger": pl.col("passenger_count").is_null(),
        "extreme_fare": pl.col("fare_amount") > MAX_FARE,
    }

REJECT_RULES = ["zero_or_negative_fare", "zero_distance", "dropoff_before_pickup", "outside_january",
    "zero_duration_with_distance", "extreme_distance", "long_duration", "extreme_fare",]


def profile(df: pl.DataFrame) -> None:
    print("Profile\n")
    print(f"Rows: {len(df):,}")
    print("Columns: ", len(df.columns))
    print("Schema: ", df.schema)
    print("Size: ", df.estimated_size("mb"))
    print("First 10 lines: ", df.head(10))
    print("Dimension: ", df.shape)
    print("Min pickup: ", df["tpep_pickup_datetime"].min())
    print("Max pickup: ", df["tpep_pickup_datetime"].max())

    nulls = df.null_count().unpivot(variable_name="column", value_name="null_count")
    nulls_and_pct = nulls.with_columns((pl.col("null_count") / df.height * 100).round(2).alias("null_pct"))
    print("Numbers of null elements: ", nulls_and_pct)
    print("Number of unique Pickup Locations:", df["PULocationID"].n_unique())
    print(f"Average trip_distance: {_format_numeric(df['trip_distance'].mean(), '.2f')} miles")
    print(f"Average fare_amount: {_format_numeric(df['fare_amount'].mean(), '.2f')}")
    print(f"Min fare_amount: {_format_numeric(df['fare_amount'].min())}")
    print(f"Max fare_amount: {_format_numeric(df['fare_amount'].max(), ',')}")
    print("Number of rows with trip_distance <= 0: ", (df["trip_distance"] <= 0).sum())
    print("Number of rows with fare_amount <= 0: ", (df["fare_amount"] <= 0).sum())
    print("Number of rows with pickup time after dropoff time: ", (df["tpep_pickup_datetime"] > df["tpep_dropoff_datetime"]).sum())


def quality_checks(df: pl.DataFrame) -> None:
    rules = quality_rules()

    print("Quality Checks\n")
    # 1. Negative fare
    print("Zero or negative fare: ", df.filter(rules["zero_or_negative_fare"]).height)
    show_examples(df=df, condition=rules["zero_or_negative_fare"],
                  columns=["total_amount", "fare_amount", "payment_type", "VendorID"])


    # 2. Zero trip distance
    print("Number of Zero trip distance: ", df.filter(rules["zero_distance"]).height)
    show_examples(df=df, condition=rules["zero_distance"], columns=["trip_distance", "fare_amount",
                                                        "tpep_pickup_datetime", "tpep_dropoff_datetime", "RatecodeID"])

    # 3. Unknown location
    print("Unknown/Outside Locations: ", df.filter(rules["unknown_location"]).height)
    show_examples(df=df, condition=rules["unknown_location"], columns=["PULocationID", "DOLocationID", "fare_amount",
                                                                      "VendorID"])

    # 4. Impossible datetime
    columns = ["tpep_pickup_datetime", "tpep_dropoff_datetime", "trip_distance", "fare_amount", "VendorID"]
    print("Dropoff before pickup: ", df.filter(rules["dropoff_before_pickup"]).height)
    show_examples(df=df, condition=rules["dropoff_before_pickup"], columns=columns)

    print("Outside January: ", df.filter(rules["outside_january"]).height)
    show_examples(df=df, condition=rules["outside_january"], columns=columns)

    print("Zero duration with distance: ", df.filter(rules["zero_duration_with_distance"]).height)
    show_examples(df=df, condition=rules["zero_duration_with_distance"], columns=columns)


    # 5. Extreme Trip Distance
    print("Extreme distance: ", df.filter(rules["extreme_distance"]).height)
    show_examples(df=df, condition=rules["extreme_distance"], columns=columns)

    print("Long duration (>5h): ", df.filter(rules["long_duration"]).height)
    show_examples(df=df, condition=rules["long_duration"], columns=columns)

    # 6. Empty columns
    empty_columns = rules["missing_passenger"]
    print("Empty passenger: ", df.filter(empty_columns).height)
    print("Payment type", df.filter(empty_columns)["payment_type"].value_counts())
    print("VendorID: ", df.filter(empty_columns)["VendorID"].value_counts())
    show_examples(df=df, condition=rules["missing_passenger"], columns=["passenger_count", "RatecodeID",
                            "store_and_fwd_flag", "congestion_surcharge", "Airport_fee", "VendorID", "payment_type"])


    # 7. Extreme fare
    print("Extreme fare (> 1000): ", df.filter(rules["extreme_fare"]).height)
    print(df.filter(rules["extreme_fare"]).select(columns + ["payment_type"]).sort("fare_amount", descending=True))

def valid_trips(df: pl.DataFrame) -> pl.DataFrame:
    rules = quality_rules()
    return df.filter(~pl.any_horizontal([rules[name] for name in REJECT_RULES]))


def business_questions(df: pl.DataFrame) -> None:
    print("Business Questions\n")
    # 1. Number of trips
    valid_trips_amount = len(df)
    print("Valid trips: ", valid_trips_amount)

    # 2. Total fare amount (fare_amount)
    total_fare = df["fare_amount"].sum()
    print(f"Total fare amount: {total_fare:,.2f}")

    # 3. Average fare per trip
    avg_fare = df["fare_amount"].mean()
    print(f"Average fare per trip: {_format_numeric(avg_fare, '.2f')}")

    # 4. Average distance
    avg_distance = df["trip_distance"].mean()
    print(f"Average distance: {_format_numeric(avg_distance, '.2f')}")

    # 5. Average duration
    avg_duration = (df["tpep_dropoff_datetime"] - df["tpep_pickup_datetime"]).mean()
    print("Average duration:", avg_duration)



    # 6. Top 10 pickup locations
    taxi_zone = pl.read_csv(TAXI_ZONE)
    top_10_pickup_locations = ((df["PULocationID"].value_counts().
                               join(taxi_zone, left_on="PULocationID", right_on="LocationID")).
                               sort(by="count", descending=True)).head(10)
    print("Top 10 pickup locations: ", top_10_pickup_locations)

    # 7. Top 10 dropoff locations
    top_10_dropoff_locations = (df["DOLocationID"].value_counts().
                                join(taxi_zone, left_on="DOLocationID", right_on="LocationID").
                                sort(by="count", descending=True)).head(10)
    print("Top 10 dropoff locations: ", top_10_dropoff_locations)

    # 8. Number of trips per day
    trips_per_day = (df.group_by(pl.col("tpep_pickup_datetime").alias("date").dt.date())
                     .len(name="trips")
                     .sort("date"))
    print("Number of trips per day: ", trips_per_day)

    # 9. Number of trips per hour
    trips_per_hour = (df.group_by(pl.col("tpep_pickup_datetime").alias("hour").dt.hour())
                      .len(name="trips")
                      .sort("hour"))
    print("Number of trips per hour: ", trips_per_hour)

    # 10. Busiest hour
    if trips_per_hour.is_empty():
        print("Busiest hour: N/A")
        return
    busiest_hour, trips_busy_hour = trips_per_hour.sort(by="trips", descending=True).head(1).row()
    print(f"Busiest hour: {busiest_hour:02d}:00 - {busiest_hour + 1:02d}:00 ({trips_busy_hour:,} trips)")


def main() -> None:
    pl.Config.set_tbl_cols(-1)
    pl.Config.set_tbl_rows(-1)
    df = pl.read_parquet(RAW_FILE)
    profile(df)
    quality_checks(df)
    business_questions(valid_trips(df))


if __name__ == "__main__":
    main()

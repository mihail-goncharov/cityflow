import polars as pl
from pathlib import Path
from datetime import datetime


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_FILE = PROJECT_ROOT / "data" / "raw" / "yellow_tripdata_2025-01.parquet"
TAXI_ZONE = PROJECT_ROOT / "data" / "raw" / "taxi_zone_lookup.csv"


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
    print(f"Average trip_distance: {df['trip_distance'].mean():.2f} miles")
    print(f"Average fare_amount: {df['fare_amount'].mean():.2f}")
    print(f"Min fare_amount: {df['fare_amount'].min()}")
    print(f"Max fare_amount: {df['fare_amount'].max():,}")
    print("Number of rows with trip_distance <= 0: ", (df["trip_distance"] <= 0).sum())
    print("Number of rows with fare_amount <= 0: ", (df["fare_amount"] <= 0).sum())
    print("Number of rows with pickup time after dropoff time: ", (df["tpep_pickup_datetime"] > df["tpep_dropoff_datetime"]).sum())


def quality_checks(df: pl.DataFrame) -> None:
    print("Quality Checks\n")
    # 1. Negative fare
    negative_fare = df.filter(df["fare_amount"] <= 0)
    print("Zero or negative fare: ", negative_fare.height)
    print(negative_fare.select("total_amount", "fare_amount", "payment_type", "VendorID").sample(5, seed=42))

    # 2. Zero trip distance
    zero_distance = df.filter(df["trip_distance"] <= 0)
    print("Number of Zero trip distance: ", zero_distance.height)
    print(zero_distance.select("trip_distance", "fare_amount", "tpep_pickup_datetime", "tpep_dropoff_datetime",
                               "RatecodeID").sample(5, seed=42))

    # 3. Unknown location
    unknown_location = pl.col("PULocationID").is_in([264, 265]) | pl.col("DOLocationID").is_in([264, 265])
    print("Unknown/Outside Locations: ", df.filter(unknown_location).height)

    # 4. Impossible datetime
    pickup = pl.col("tpep_pickup_datetime")
    dropoff = pl.col("tpep_dropoff_datetime")
    columns = ["tpep_pickup_datetime", "tpep_dropoff_datetime", "trip_distance", "fare_amount", "VendorID"]

    dropoff_before_pickup = pickup > dropoff
    outside_january = (pickup < datetime(2025, 1, 1)) | (pickup >= datetime(2025, 2, 1))
    zero_duration_with_distance = (pickup == dropoff) & (pl.col("trip_distance") > 0)

    print("Dropoff before pickup: ", df.filter(dropoff_before_pickup).height)
    print(df.filter(dropoff_before_pickup).select(columns).sample(3, seed=42))

    print("Outside January: ", df.filter(outside_january).height)
    print(df.filter(outside_january).select(columns).sample(3, seed=42))

    print("Zero duration with distance: ", df.filter(zero_duration_with_distance).height)
    print(df.filter(zero_duration_with_distance).select(columns).sample(3, seed=42))


    # 5. Extreme Trip Distance
    extreme_trip_distance_by_miles = df.filter(pl.col("trip_distance") > 200)
    long_duration = (dropoff - pickup) > pl.duration(hours=5)
    print("Extreme distance: ", extreme_trip_distance_by_miles.height)
    print(extreme_trip_distance_by_miles.select(columns).sample(5, seed=42))
    print("Long duration (>5h): ", df.filter(long_duration).height)
    print(df.filter(long_duration).select(columns).sample(5, seed=42))

    # 6. Empty columns
    empty_columns = pl.col("passenger_count").is_null()
    print("Empty passenger: ", df.filter(empty_columns).height)
    print("Payment type", df.filter(empty_columns)["payment_type"].value_counts())
    print("VendorID: ", df.filter(empty_columns)["VendorID"].value_counts())
    print(df.filter(empty_columns).select("passenger_count", "RatecodeID", "store_and_fwd_flag",
                                          "congestion_surcharge", "Airport_fee", "VendorID", "payment_type")
          .sample(3, seed=42))

    # 7. Extreme fare
    extreme_fare = pl.col("fare_amount") > 1000
    print("Extreme fare (> 1000): ", df.filter(extreme_fare).height)
    print(df.filter(extreme_fare).select(columns + ["payment_type"])
          .sort("fare_amount", descending=True))

def valid_trips(df: pl.DataFrame) -> pl.DataFrame:
    negative_fare = pl.col("fare_amount") <= 0
    zero_distance = pl.col("trip_distance") <= 0

    pickup = pl.col("tpep_pickup_datetime")
    dropoff = pl.col("tpep_dropoff_datetime")

    dropoff_before_pickup = pickup > dropoff
    outside_january = (pickup < datetime(2025, 1, 1)) | (pickup >= datetime(2025, 2, 1))
    zero_duration_with_distance = (pickup == dropoff) & (pl.col("trip_distance") > 0)
    extreme_trip_distance = pl.col("trip_distance") > 200

    long_duration = (dropoff - pickup) > pl.duration(hours=5)
    extreme_fare = pl.col("fare_amount") > 1000

    return df.filter(~(negative_fare | zero_distance | dropoff_before_pickup | outside_january |
                       zero_duration_with_distance | extreme_trip_distance | long_duration | extreme_fare))


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
    print(f"Average fare per trip: {avg_fare:.2f}")

    # 4. Average distance
    avg_distance = df["trip_distance"].mean()
    print(f"Average distance: {avg_distance:.2f}")

    # 5. Average duration
    avg_duration = (df["tpep_dropoff_datetime"] - df["tpep_pickup_datetime"]).mean()
    print(f"Average duration: {avg_duration}")



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
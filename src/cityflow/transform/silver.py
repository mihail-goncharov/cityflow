import polars as pl

# Source money column -> Silver column (docs/medallion.md section 4.1).
MONEY_COLUMNS = {
    "fare_amount": "fare_amount_cents",
    "extra": "extra_cents",
    "mta_tax": "mta_tax_cents",
    "tip_amount": "tip_amount_cents",
    "tolls_amount": "tolls_amount_cents",
    "improvement_surcharge": "improvement_surcharge_cents",
    "total_amount": "total_amount_cents",
    "congestion_surcharge": "congestion_surcharge_cents",
    "Airport_fee": "airport_fee_cents",
    "cbd_congestion_fee": "cbd_congestion_fee_cents",
}

FLEX_FIELDS = [
    "passenger_count",
    "RatecodeID",
    "store_and_fwd_flag",
    "congestion_surcharge",
    "Airport_fee",
]

UNKNOWN_ZONE_IDS = [264, 265]


def dollars_to_cents(column: str) -> pl.Expr:
    """Convert a dollar column to integer cents (``Int64``).

    Rounds half away from zero and keeps nulls as nulls
    (docs/medallion.md section 4.1).
    """
    return (pl.col(column) * 100).round(0, mode="half_away_from_zero").cast(pl.Int64)


def to_silver(accepted: pl.LazyFrame) -> pl.LazyFrame:
    """Turn accepted Bronze rows into Silver rows.

    Rows are neither added nor dropped: this only converts money to cents,
    adds the derived columns and the flags, and renames the money columns.
    The input must already have passed the reject rules. See
    docs/medallion.md section 4.
    """
    pickup = pl.col("tpep_pickup_datetime")
    dropoff = pl.col("tpep_dropoff_datetime")

    return accepted.with_columns(
        pickup.dt.date().alias("pickup_date"),
        pickup.dt.hour().cast(pl.Int8).alias("pickup_hour"),
        (dropoff - pickup).dt.total_seconds().alias("trip_duration_seconds"),
        pl.any_horizontal(pl.col(FLEX_FIELDS).is_null()).alias(
            "has_missing_flex_fields"
        ),
        pl.col("PULocationID").is_in(UNKNOWN_ZONE_IDS).alias("is_unknown_pickup_zone"),
        pl.col("DOLocationID").is_in(UNKNOWN_ZONE_IDS).alias("is_unknown_dropoff_zone"),
        *[dollars_to_cents(src).alias(dst) for src, dst in MONEY_COLUMNS.items()],
    ).drop(list(MONEY_COLUMNS))

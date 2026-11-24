from datetime import datetime, timedelta

import polars as pl

from cityflow.ingestion.download import parse_month
from cityflow.transform.reasons import RejectReason

MAX_FARE = 1000
# Technical bound, not a business limit: far below the Int64 cents overflow
# and the Float64 exact-cent limit (docs/medallion.md section 7.1).
MAX_MONEY_AMOUNT = 1_000_000_000
MAX_DISTANCE_MILES = 200
MAX_DURATION = timedelta(hours=5)

MIN_LOCATION_ID = 1
MAX_LOCATION_ID = 265

PICKUP = "tpep_pickup_datetime"
DROPOFF = "tpep_dropoff_datetime"
PICKUP_LOCATION = "PULocationID"
DROPOFF_LOCATION = "DOLocationID"

TOTAL_AMOUNT = "total_amount"
# The money columns of docs/medallion.md section 4.1 without fare_amount and
# total_amount, which have reason codes of their own.
OTHER_MONEY_COLUMNS = [
    "extra",
    "mta_tax",
    "tip_amount",
    "tolls_amount",
    "improvement_surcharge",
    "congestion_surcharge",
    "Airport_fee",
    "cbd_congestion_fee",
]


def _finite_and(column: str, condition: pl.Expr) -> pl.Expr:
    """Apply a condition only to non-null, finite values of a numeric column.

    Polars treats NaN as larger than every number, so without this guard a NaN
    would match "greater than" rules. Null and non-finite values get their own
    reason codes (docs/medallion.md section 7.1) and never match here. The
    result is never null: it is False wherever the condition cannot apply.
    """
    return (pl.col(column).is_finite() & condition).fill_null(False)


def fare_not_positive() -> pl.Expr:
    """True when fare_amount is zero or negative."""
    return _finite_and("fare_amount", pl.col("fare_amount") <= 0)


def fare_too_high() -> pl.Expr:
    """True when fare_amount is above MAX_FARE; exactly MAX_FARE is accepted."""
    return _finite_and("fare_amount", pl.col("fare_amount") > MAX_FARE)


def distance_not_positive() -> pl.Expr:
    """True when trip_distance is zero or negative."""
    return _finite_and("trip_distance", pl.col("trip_distance") <= 0)


def distance_too_high() -> pl.Expr:
    """True when trip_distance is above MAX_DISTANCE_MILES; the limit itself is accepted."""
    return _finite_and(
        "trip_distance", pl.col("trip_distance") > MAX_DISTANCE_MILES
    )


def dropoff_before_pickup() -> pl.Expr:
    """True when the dropoff is earlier than the pickup; equal times are accepted.

    A null timestamp never matches: it has its own reason code.
    """
    return (pl.col(DROPOFF) < pl.col(PICKUP)).fill_null(False)


def zero_duration_with_distance() -> pl.Expr:
    """True when pickup and dropoff are the same instant but the trip has distance.

    Zero distance with zero duration is not this rule; distance_not_positive
    covers it.
    """
    return _finite_and(
        "trip_distance",
        (pl.col(PICKUP) == pl.col(DROPOFF)) & (pl.col("trip_distance") > 0),
    )


def duration_too_long() -> pl.Expr:
    """True when the trip lasts longer than MAX_DURATION; exactly 5 hours is accepted."""
    return ((pl.col(DROPOFF) - pl.col(PICKUP)) > pl.lit(MAX_DURATION)).fill_null(False)


def _month_bounds(month: str) -> tuple[datetime, datetime]:
    """Return the first instant of the month and of the following month."""
    year, month_number = map(int, parse_month(month).split("-"))
    start = datetime(year, month_number, 1)
    end = datetime(year + month_number // 12, month_number % 12 + 1, 1)
    return start, end


def pickup_outside_month(month: str) -> pl.Expr:
    """True when the pickup is not inside the given month (YYYY-MM).

    Membership is decided by the pickup time only, so a trip that starts on
    31 January and ends on 1 February belongs to January. The first instant of
    the month is inside; the first instant of the next month is outside.
    """
    start, end = _month_bounds(month)
    pickup = pl.col(PICKUP)
    return ((pickup < start) | (pickup >= end)).fill_null(False)


def _missing(column: str) -> pl.Expr:
    return pl.col(column).is_null()


def _non_finite(column: str) -> pl.Expr:
    """True for NaN and infinite values; null is missing, not non-finite."""
    return (~pl.col(column).is_finite()).fill_null(False)


def _invalid_location(column: str) -> pl.Expr:
    """True for a location ID outside MIN_LOCATION_ID..MAX_LOCATION_ID.

    IDs 264 and 265 are inside the range: they are real TLC values. A null ID is
    missing, not invalid.
    """
    in_range = pl.col(column).is_between(MIN_LOCATION_ID, MAX_LOCATION_ID)
    return (~in_range).fill_null(False)


def missing_pickup_datetime() -> pl.Expr:
    """True when the pickup timestamp is null."""
    return _missing(PICKUP)


def missing_dropoff_datetime() -> pl.Expr:
    """True when the dropoff timestamp is null."""
    return _missing(DROPOFF)


def missing_fare() -> pl.Expr:
    """True when fare_amount is null."""
    return _missing("fare_amount")


def missing_distance() -> pl.Expr:
    """True when trip_distance is null."""
    return _missing("trip_distance")


def non_finite_fare() -> pl.Expr:
    """True when fare_amount is NaN or infinite."""
    return _non_finite("fare_amount")


def non_finite_distance() -> pl.Expr:
    """True when trip_distance is NaN or infinite."""
    return _non_finite("trip_distance")


def missing_total_amount() -> pl.Expr:
    """True when total_amount is null (Silver's total_amount_cents is not null)."""
    return _missing(TOTAL_AMOUNT)


def non_finite_total_amount() -> pl.Expr:
    """True when total_amount is NaN or infinite."""
    return _non_finite(TOTAL_AMOUNT)


def non_finite_money_amount() -> pl.Expr:
    """True when any money column other than fare and total is NaN or infinite.

    Null is allowed in these columns and never matches.
    """
    return pl.any_horizontal(*[_non_finite(column) for column in OTHER_MONEY_COLUMNS])


def money_out_of_range() -> pl.Expr:
    """True when total_amount or another money column is beyond MAX_MONEY_AMOUNT.

    Only the size matters, so a large negative amount is out of range too;
    exactly MAX_MONEY_AMOUNT is accepted. fare_amount has its own bounds. Null
    and non-finite values never match: they have their own reason codes.
    """
    return pl.any_horizontal(
        *[
            _finite_and(column, pl.col(column).abs() > MAX_MONEY_AMOUNT)
            for column in [TOTAL_AMOUNT, *OTHER_MONEY_COLUMNS]
        ]
    )


def missing_pickup_location() -> pl.Expr:
    """True when PULocationID is null."""
    return _missing(PICKUP_LOCATION)


def missing_dropoff_location() -> pl.Expr:
    """True when DOLocationID is null."""
    return _missing(DROPOFF_LOCATION)


def invalid_pickup_location() -> pl.Expr:
    """True when PULocationID is not null and outside 1 to 265."""
    return _invalid_location(PICKUP_LOCATION)


def invalid_dropoff_location() -> pl.Expr:
    """True when DOLocationID is not null and outside 1 to 265."""
    return _invalid_location(DROPOFF_LOCATION)


def reject_rules(month: str) -> dict[RejectReason, pl.Expr]:
    """Return every reject rule, keyed by its reason code.

    Each expression is True for a row that breaks that rule. The month is only
    needed by pickup_outside_month.
    """
    return {
        RejectReason.FARE_NOT_POSITIVE: fare_not_positive(),
        RejectReason.FARE_TOO_HIGH: fare_too_high(),
        RejectReason.DISTANCE_NOT_POSITIVE: distance_not_positive(),
        RejectReason.DISTANCE_TOO_HIGH: distance_too_high(),
        RejectReason.DROPOFF_BEFORE_PICKUP: dropoff_before_pickup(),
        RejectReason.ZERO_DURATION_WITH_DISTANCE: zero_duration_with_distance(),
        RejectReason.DURATION_TOO_LONG: duration_too_long(),
        RejectReason.PICKUP_OUTSIDE_MONTH: pickup_outside_month(month),
        RejectReason.MISSING_PICKUP_DATETIME: missing_pickup_datetime(),
        RejectReason.MISSING_DROPOFF_DATETIME: missing_dropoff_datetime(),
        RejectReason.MISSING_FARE: missing_fare(),
        RejectReason.MISSING_DISTANCE: missing_distance(),
        RejectReason.NON_FINITE_FARE: non_finite_fare(),
        RejectReason.NON_FINITE_DISTANCE: non_finite_distance(),
        RejectReason.MISSING_TOTAL_AMOUNT: missing_total_amount(),
        RejectReason.NON_FINITE_TOTAL_AMOUNT: non_finite_total_amount(),
        RejectReason.NON_FINITE_MONEY_AMOUNT: non_finite_money_amount(),
        RejectReason.MONEY_OUT_OF_RANGE: money_out_of_range(),
        RejectReason.MISSING_PICKUP_LOCATION: missing_pickup_location(),
        RejectReason.MISSING_DROPOFF_LOCATION: missing_dropoff_location(),
        RejectReason.INVALID_PICKUP_LOCATION: invalid_pickup_location(),
        RejectReason.INVALID_DROPOFF_LOCATION: invalid_dropoff_location(),
    }

from enum import StrEnum


class RejectReason(StrEnum):
    """Reason codes stored in Quarantine's ``reject_reasons`` column."""

    FARE_NOT_POSITIVE = "fare_not_positive"
    FARE_TOO_HIGH = "fare_too_high"
    DISTANCE_NOT_POSITIVE = "distance_not_positive"
    DISTANCE_TOO_HIGH = "distance_too_high"
    DROPOFF_BEFORE_PICKUP = "dropoff_before_pickup"
    ZERO_DURATION_WITH_DISTANCE = "zero_duration_with_distance"
    DURATION_TOO_LONG = "duration_too_long"
    PICKUP_OUTSIDE_MONTH = "pickup_outside_month"
    MISSING_PICKUP_DATETIME = "missing_pickup_datetime"
    MISSING_DROPOFF_DATETIME = "missing_dropoff_datetime"
    MISSING_FARE = "missing_fare"
    MISSING_DISTANCE = "missing_distance"
    NON_FINITE_FARE = "non_finite_fare"
    NON_FINITE_DISTANCE = "non_finite_distance"
    MISSING_TOTAL_AMOUNT = "missing_total_amount"
    NON_FINITE_TOTAL_AMOUNT = "non_finite_total_amount"
    NON_FINITE_MONEY_AMOUNT = "non_finite_money_amount"
    MONEY_OUT_OF_RANGE = "money_out_of_range"
    MISSING_PICKUP_LOCATION = "missing_pickup_location"
    MISSING_DROPOFF_LOCATION = "missing_dropoff_location"
    INVALID_PICKUP_LOCATION = "invalid_pickup_location"
    INVALID_DROPOFF_LOCATION = "invalid_dropoff_location"

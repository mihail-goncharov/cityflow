import json
from datetime import datetime
from typing import Any

import polars as pl
import pytest

from cityflow.transform.bronze import to_bronze
from cityflow.transform.reasons import RejectReason
from cityflow.transform.rules import OTHER_MONEY_COLUMNS
from cityflow.transform.split import split_accepted_rejected
from cityflow.transform.summary import (
    FLAG_COLUMNS,
    CountMismatchError,
    build_quality_summary,
    count_rule_hits,
)

MONTH = "2025-01"
SHA = "b" * 64

REJECTED_SCHEMA = {"reject_reasons": pl.List(pl.String)}


def rejected_of(reasons: list[list[str]]) -> pl.LazyFrame:
    return pl.LazyFrame({"reject_reasons": reasons}, schema=REJECTED_SCHEMA)


def silver_of(flags: list[dict[str, bool]]) -> pl.LazyFrame:
    schema = dict.fromkeys(FLAG_COLUMNS, pl.Boolean)
    return pl.LazyFrame(flags, schema=schema)


def flags(**overrides: bool) -> dict[str, bool]:
    row = dict.fromkeys(FLAG_COLUMNS, False)
    row.update(overrides)
    return row


def summarize(
    *, input_rows: int, silver: pl.LazyFrame, rejected: pl.LazyFrame
) -> dict[str, Any]:
    return build_quality_summary(
        month=MONTH,
        source_sha256=SHA,
        input_rows=input_rows,
        silver=silver,
        rejected=rejected,
    )


def test_rule_counts_can_overlap_but_each_reason_is_counted_per_row() -> None:
    rejected = rejected_of(
        [
            ["fare_too_high"],
            ["distance_too_high", "fare_too_high"],
            ["missing_fare"],
        ]
    )

    counts = count_rule_hits(rejected)

    assert counts["fare_too_high"] == 2
    assert counts["distance_too_high"] == 1
    assert counts["missing_fare"] == 1
    assert sum(counts.values()) == 4


def test_rule_counts_list_every_reason_in_enum_order_with_zeros() -> None:
    counts = count_rule_hits(rejected_of([["missing_fare"], ["fare_too_high"]]))

    assert list(counts) == [reason.value for reason in RejectReason]
    assert counts["duration_too_long"] == 0
    assert all(type(key) is str for key in counts)


def test_rule_counts_of_no_rejected_rows_are_all_zero() -> None:
    counts = count_rule_hits(rejected_of([]))

    assert set(counts.values()) == {0}
    assert len(counts) == len(RejectReason)


def test_summary_has_counts_flags_and_source_fields() -> None:
    summary = summarize(
        input_rows=5,
        silver=silver_of(
            [
                flags(),
                flags(has_missing_flex_fields=True),
                flags(has_missing_flex_fields=True, is_unknown_pickup_zone=True),
            ]
        ),
        rejected=rejected_of([["fare_too_high"], ["fare_too_high", "missing_fare"]]),
    )

    assert summary["source_month"] == MONTH
    assert summary["source_sha256"] == SHA
    assert summary["input_rows"] == 5
    assert summary["accepted_rows"] == 3
    assert summary["rejected_rows"] == 2
    assert summary["rule_counts"]["fare_too_high"] == 2
    assert summary["flag_counts"] == {
        "has_missing_flex_fields": 2,
        "is_unknown_pickup_zone": 1,
        "is_unknown_dropoff_zone": 0,
    }


def test_rejected_rows_count_each_row_once_even_with_several_reasons() -> None:
    summary = summarize(
        input_rows=1,
        silver=silver_of([]),
        rejected=rejected_of([["distance_too_high", "fare_too_high"]]),
    )

    assert summary["rejected_rows"] == 1
    assert sum(summary["rule_counts"].values()) == 2


def test_empty_input_gives_zero_counts_and_zero_flags() -> None:
    summary = summarize(input_rows=0, silver=silver_of([]), rejected=rejected_of([]))

    assert summary["accepted_rows"] == 0
    assert summary["rejected_rows"] == 0
    assert set(summary["flag_counts"].values()) == {0}
    assert set(summary["rule_counts"].values()) == {0}


@pytest.mark.parametrize("input_rows", [3, 5])
def test_lost_or_extra_rows_raise_count_mismatch(input_rows: int) -> None:
    with pytest.raises(CountMismatchError, match="!= input"):
        summarize(
            input_rows=input_rows,
            silver=silver_of([flags(), flags(), flags()]),
            rejected=rejected_of([["fare_too_high"]]),
        )


def test_invalid_month_is_rejected() -> None:
    with pytest.raises(ValueError, match="Invalid month"):
        build_quality_summary(
            month="2025-13",
            source_sha256=SHA,
            input_rows=0,
            silver=silver_of([]),
            rejected=rejected_of([]),
        )


def test_summary_is_json_serializable() -> None:
    summary = summarize(
        input_rows=2,
        silver=silver_of([flags(is_unknown_dropoff_zone=True)]),
        rejected=rejected_of([["fare_not_positive"]]),
    )

    assert json.loads(json.dumps(summary)) == summary


def test_summary_of_a_real_split_adds_up_to_bronze() -> None:
    schema = {
        "tpep_pickup_datetime": pl.Datetime("us"),
        "tpep_dropoff_datetime": pl.Datetime("us"),
        "PULocationID": pl.Int32,
        "DOLocationID": pl.Int32,
        "trip_distance": pl.Float64,
        "fare_amount": pl.Float64,
        "total_amount": pl.Float64,
        **dict.fromkeys(OTHER_MONEY_COLUMNS, pl.Float64),
    }

    def trip(**overrides: Any) -> dict[str, Any]:
        row: dict[str, Any] = {
            "tpep_pickup_datetime": datetime(2025, 1, 15, 10, 0),
            "tpep_dropoff_datetime": datetime(2025, 1, 15, 10, 15),
            "PULocationID": 132,
            "DOLocationID": 236,
            "trip_distance": 3.2,
            "fare_amount": 17.5,
            "total_amount": 25.0,
            **dict.fromkeys(OTHER_MONEY_COLUMNS, 1.0),
        }
        row.update(overrides)
        return row

    source = pl.DataFrame(
        [
            trip(),
            trip(),
            trip(fare_amount=2000.0),
            trip(fare_amount=-1.0, trip_distance=300.0),
        ],
        schema=schema,
    )
    bronze = to_bronze(
        source.lazy(),
        month=MONTH,
        source_object_key="raw/key.parquet",
        source_sha256=SHA,
        ingested_at="2026-11-01T10:00:00+00:00",
    )
    accepted, rejected = split_accepted_rejected(bronze, MONTH)
    silver = accepted.with_columns(
        *[pl.lit(False).alias(name) for name in FLAG_COLUMNS]
    )

    summary = summarize(input_rows=source.height, silver=silver, rejected=rejected)

    assert summary["input_rows"] == 4
    assert summary["accepted_rows"] == 2
    assert summary["rejected_rows"] == 2
    assert summary["rule_counts"]["fare_too_high"] == 1
    assert summary["rule_counts"]["fare_not_positive"] == 1
    assert summary["rule_counts"]["distance_too_high"] == 1

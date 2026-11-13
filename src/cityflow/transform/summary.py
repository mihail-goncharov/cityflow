from typing import Any

import polars as pl

from cityflow.ingestion.download import parse_month
from cityflow.transform.reasons import RejectReason
from cityflow.transform.split import REJECT_REASONS_COLUMN

FLAG_COLUMNS = [
    "has_missing_flex_fields",
    "is_unknown_pickup_zone",
    "is_unknown_dropoff_zone",
]


class CountMismatchError(Exception):
    """Accepted and rejected rows do not add up to the Bronze input rows."""


def count_rule_hits(rejected: pl.LazyFrame) -> dict[str, int]:
    """Count how many rejected rows broke each rule.

    A row that broke several rules is counted once per rule, so the counts
    can add up to more than the number of rejected rows. Every RejectReason
    is a key, with 0 for rules that never fired, so the keys are the same in
    every month (docs/medallion.md sections 7.4 and 7.5).
    """
    hits = (
        rejected.explode(REJECT_REASONS_COLUMN, empty_as_null=True)
        .group_by(REJECT_REASONS_COLUMN)
        .len()
        .collect()
    )
    counts = dict(hits.iter_rows())
    result: dict[str, int] = {}
    for reason in RejectReason:
        result[reason.value] = counts.get(reason.value, 0)
    return result


def build_quality_summary(
    *,
    month: str,
    source_sha256: str,
    input_rows: int,
    silver: pl.LazyFrame,
    rejected: pl.LazyFrame,
) -> dict[str, Any]:
    """Build the quality summary for one month (docs/medallion.md section 7.5).

    ``input_rows`` is the Bronze row count, taken separately from Silver and
    Quarantine so the check below can catch a lost or duplicated row.
    Raises CountMismatchError when accepted + rejected != input.
    """
    accepted_rows = silver.select(pl.len()).collect().item()
    rejected_rows = rejected.select(pl.len()).collect().item()
    if accepted_rows + rejected_rows != input_rows:
        raise CountMismatchError(
            f"accepted ({accepted_rows}) + rejected ({rejected_rows}) "
            f"!= input ({input_rows})"
        )

    flag_sums = silver.select(pl.col(FLAG_COLUMNS).sum()).collect().row(0, named=True)
    return {
        "source_month": parse_month(month),
        "source_sha256": source_sha256,
        "input_rows": input_rows,
        "accepted_rows": accepted_rows,
        "rejected_rows": rejected_rows,
        "rule_counts": count_rule_hits(rejected),
        "flag_counts": flag_sums,
    }

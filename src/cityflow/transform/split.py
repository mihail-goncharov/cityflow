import polars as pl

from cityflow.transform.rules import reject_rules

REJECT_REASONS_COLUMN = "reject_reasons"


def add_reject_reasons(bronze: pl.LazyFrame, month: str) -> pl.LazyFrame:
    """Add ``reject_reasons``: every rule the row breaks, sorted by reason code.

    The list is empty for a row that breaks no rule. Rows are never dropped
    here, so the result has exactly the rows of the input.
    """
    rules = reject_rules(month)

    hits = []
    # RejectReason is a str, so this sorts the codes alphabetically.
    for reason in sorted(rules):
        # The reason code where the rule fires, null where it does not.
        hits.append(pl.when(rules[reason]).then(pl.lit(reason.value)))

    # Join the columns into one list per row, then remove the nulls.
    reasons = pl.concat_list(hits).list.drop_nulls()
    return bronze.with_columns(reasons.alias(REJECT_REASONS_COLUMN))


def split_accepted_rejected(
    bronze: pl.LazyFrame, month: str
) -> tuple[pl.LazyFrame, pl.LazyFrame]:
    """Split Bronze rows into (accepted, rejected) by the reject rules.

    A row is rejected when it breaks at least one rule. Every row lands in
    exactly one of the two results. Accepted rows keep the Bronze columns
    unchanged, ready for the Silver conversion; rejected rows are the Quarantine
    rows: the Bronze columns plus ``reject_reasons`` with all their reasons.
    See docs/medallion.md sections 6 and 7.
    """
    flagged = add_reject_reasons(bronze, month)
    reason_count = pl.col(REJECT_REASONS_COLUMN).list.len()
    accepted = flagged.filter(reason_count == 0).drop(REJECT_REASONS_COLUMN)
    rejected = flagged.filter(reason_count > 0)
    return accepted, rejected

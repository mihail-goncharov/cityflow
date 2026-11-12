import polars as pl

from cityflow.ingestion.download import parse_month

LINEAGE_COLUMNS = [
    "source_row_id",
    "source_month",
    "source_object_key",
    "source_sha256",
    "ingested_at",
]


def to_bronze(
    source: pl.LazyFrame,
    *,
    month: str,
    source_object_key: str,
    source_sha256: str,
    ingested_at: str,
) -> pl.LazyFrame:
    """Add the lineage columns to the rows of one Raw file.

    Every source row and every source column is kept unchanged: no filtering,
    no conversion, no deduplication. ``source_row_id`` is the zero-based
    position of the row in the file, so identical rows get different ids.
    The other lineage values come from the Raw manifest and are the same for
    all rows. The result is lazy, so nothing is read until it is collected
    or written. See docs/medallion.md section 3.
    """
    return source.with_row_index("source_row_id").with_columns(
        pl.col("source_row_id").cast(pl.Int64),
        pl.lit(parse_month(month)).alias("source_month"),
        pl.lit(source_object_key).alias("source_object_key"),
        pl.lit(source_sha256).alias("source_sha256"),
        pl.lit(ingested_at).alias("ingested_at"),
    )

# Raw data contract: NYC TLC Yellow Taxi

**Contract version:** 1

This contract defines what a downloaded monthly file must satisfy before
`cityflow.ingestion` publishes it to the Raw layer. If any check fails, the
file is not published and ingestion fails with a clear error.


## 1. Source

- One Parquet file per month, requested as `YYYY-MM`.
- The source URL must be exactly:
  `https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_{YYYY-MM}.parquet`


## 2. File checks

| Check | Rule |
|---|---|
| Size | larger than 0 bytes |
| Format | readable Parquet: the file metadata (schema) can be read, and all data pages can be decoded. The data is read in bounded batches, so the whole file is never loaded into memory at once |
| Columns | all required columns are present, with the expected types (section 3) |


## 3. Required columns

Names are case-sensitive and must match the file exactly. Types are as read by
Polars, the same types as in [`dataset.md`](dataset.md).

| Column | Type (Polars) | Why it is required |
|---|---|---|
| `tpep_pickup_datetime` | `Datetime("us")`, no time zone | trip start, daily and hourly metrics |
| `tpep_dropoff_datetime` | `Datetime("us")`, no time zone | trip end, trip duration |
| `PULocationID` | `Int32` | pickup zone |
| `DOLocationID` | `Int32` | dropoff zone |
| `trip_distance` | `Float64` | distance metrics |
| `fare_amount` | `Float64` | metered fare |
| `total_amount` | `Float64` | amount charged to passengers |

A missing column or a different type fails validation.


## 4. Additional columns

Columns not listed in section 3 are allowed. They are not checked and are
kept unchanged. Column order is not checked. New columns from TLC, such as
`cbd_congestion_fee` added in 2025, do not fail validation.


## 5. File identity and checksum

- The SHA-256 and size in bytes of the downloaded file are computed with the
  existing helper `sha256_of` from `cityflow.build_manifest` and recorded in
  the ingestion manifest.
- [`source_manifest.json`](source_manifest.json) records the SHA-256 and size
  of January 2025 as observed on 2026-10-05. This is a recorded baseline, not
  an official checksum: TLC does not publish checksums.
- If the January checksum differs from the baseline, the difference is
  reported as a warning for manual review. It does not fail validation on its
  own.


## 6. Raw bytes are preserved

Validation only reads the file. The published object is byte-for-byte the
downloaded file: no conversion, filtering, renaming or schema changes.


## 7. Out of scope

These are business data quality concerns, handled in EPIC-04, and do not fail
this contract:

- null values
- unusual values, such as zero or negative fares or distances
- trips outside the requested month
- duplicate rows

Known problems of this kind are described in
[`data_quality_findings.md`](data_quality_findings.md).

# Medallion layers: Raw, Bronze, Silver, Quarantine

**Schema version:** 1 (draft, written for AB#4)

This document defines what each layer stores, its schema, where it lives in
RustFS, and the rules that move a record from Bronze to Silver or Quarantine.
It builds on [`raw_data_contract.md`](raw_data_contract.md) (what a Raw file
must satisfy), [`dataset.md`](dataset.md) (source columns) and
[`data_quality_findings.md`](data_quality_findings.md) (known problems).

Gold (marts and metrics) is out of scope; it belongs to a later issue.


## 1. Layers and their responsibilities

| Layer | Holds | Question it answers |
|---|---|---|
| **Raw** | The downloaded file, byte for byte. Never changed. | What exactly did we receive? |
| **Bronze** | Every source row, with the source columns unchanged plus lineage columns. No filtering, no conversion. | Where did each row come from, and which batch? |
| **Silver** | Rows that pass every reject rule, with derived fields and money in cents. | Which rows can analytics trust? |
| **Quarantine** | Rows that fail at least one reject rule, with all their reasons. | Which rows were rejected, and why? |

Why separate layers: a wrong rule can be fixed by re-running from Bronze
without downloading again, every excluded row stays visible with its reason,
and the counts can be checked (section 7).

```
Raw ──► Bronze ──┬──► Silver
                 └──► Quarantine
```


## 2. Storage paths

Same bucket and the same month-based layout as Raw
(`raw/nyc_tlc/yellow_taxi/year=<YYYY>/month=<MM>/`):

| Layer | Data object | Other objects in the same folder |
|---|---|---|
| Raw | `raw/.../yellow_tripdata_<YYYY-MM>.parquet` | `manifest.json` |
| Bronze | `bronze/nyc_tlc/yellow_taxi/year=<YYYY>/month=<MM>/yellow_tripdata.parquet` | `manifest.json` |
| Silver | `silver/nyc_tlc/yellow_taxi/year=<YYYY>/month=<MM>/yellow_tripdata.parquet` | `manifest.json`, `quality_summary.json` |
| Quarantine | `quarantine/nyc_tlc/yellow_taxi/year=<YYYY>/month=<MM>/yellow_tripdata.parquet` | `manifest.json` |

- One Parquet file per layer per month. Keys are deterministic, so a rerun
  writes to the same key and never adds a second file.
- The month is only in the folder (`year=`, `month=`), not in the file name of
  Bronze, Silver and Quarantine, so the two can never disagree. Raw keeps the
  name TLC gives the file. Inside the data, every row carries `source_month`.
- A layer's `manifest.json` follows the same idea as the Raw manifest:
  `pending` while writing, `published` once verified.


## 3. Bronze schema

Bronze keeps the 20 source columns **exactly as in Raw** (names, types, nulls,
float money). Column order is not significant. Columns that TLC adds later are
kept too (see the raw contract, section 4).

Lineage columns added by Bronze:

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| `source_row_id` | Int64 | no | Zero-based position of the row in the Raw file. Unique within one source file. Identical-looking rows get different ids. |
| `source_month` | String | no | Requested month, `YYYY-MM`. |
| `source_object_key` | String | no | Raw object key the row was read from. |
| `source_sha256` | String | no | SHA-256 of the Raw file, from the Raw manifest. Identifies the exact version. |
| `ingested_at` | String | no | `ingested_at` of the Raw manifest (UTC, ISO 8601). It identifies the ingestion batch. |

A row is identified across all layers by `(source_month, source_row_id)`.

The id is the row position, not a hash of the values, so duplicate trips stay
distinguishable. It is stable as long as the Raw file is the same; a changed
Raw file has a different `source_sha256` and is not published over the old one
(see `ingestion.md`).

Bronze data rows contain no processing time, so running the same source twice
gives identical rows. Processing time is recorded in the manifest only.


## 4. Silver schema

Silver has the Bronze lineage columns and the source columns, with these
changes.

### 4.1 Money columns

All money columns are stored as **integer cents** (`Int64`), named with the
suffix `_cents`:

`fare_amount_cents`, `extra_cents`, `mta_tax_cents`, `tip_amount_cents`,
`tolls_amount_cents`, `improvement_surcharge_cents`, `total_amount_cents`,
`congestion_surcharge_cents`, `airport_fee_cents`, `cbd_congestion_fee_cents`.

- **Unit:** US cents (1 dollar = 100).
- **Rounding:** `round(amount * 100)`, half away from zero. Source amounts
  have at most two decimals, so this only removes floating-point noise
  (for example `0.1 + 0.2` stored as `0.30000000000000004`).
- **Nulls:** a null stays null. It is never turned into 0. Only the Flex Fare
  columns (`congestion_surcharge`, `airport_fee`) are null in accepted rows.
- **Sign:** only `fare_amount` has a sign rule (section 6). Other negative
  amounts are kept as they are.
- The source column `Airport_fee` is renamed `airport_fee_cents`; the other
  Silver names are lowercase too.

### 4.2 Derived columns

| Column | Type | Nullable | Definition |
|---|---|---|---|
| `pickup_date` | Date | no | Calendar date of `tpep_pickup_datetime` (local time, section 5). |
| `pickup_hour` | Int8 | no | Hour of `tpep_pickup_datetime`, 0 to 23. |
| `trip_duration_seconds` | Int64 | no | `tpep_dropoff_datetime - tpep_pickup_datetime` in whole seconds. At least 1 and at most 18,000 for accepted rows. |

### 4.3 Flags

Flags describe a row but never reject it:

| Column | Type | Meaning |
|---|---|---|
| `has_missing_flex_fields` | Boolean | `passenger_count`, `RatecodeID`, `store_and_fwd_flag`, `congestion_surcharge` or `Airport_fee` is null (Flex Fare trips). The nulls are kept. |
| `is_unknown_pickup_zone` | Boolean | `PULocationID` is 264 (Unknown) or 265 (Outside of NYC). |
| `is_unknown_dropoff_zone` | Boolean | `DOLocationID` is 264 or 265. |

### 4.4 Nullability in Silver

Not null: the lineage columns, `tpep_pickup_datetime`, `tpep_dropoff_datetime`,
`trip_distance`, `fare_amount_cents`, `total_amount_cents`, the derived
columns and the flags.
Nullable: `passenger_count`, `RatecodeID`, `store_and_fwd_flag`,
`congestion_surcharge_cents`, `airport_fee_cents`. All other columns follow
the source.


## 5. Time zone

The source timestamps have no time zone, and the TLC dictionary does not
state one. This project **assumes they are New York local time
(`America/New_York`)**, not UTC.

- Timestamps are stored unchanged, without a time zone, in every layer.
  Nothing is converted to UTC.
- `pickup_date` and `pickup_hour` are read from the stored local value.
- `trip_duration_seconds` is the plain difference of the two stored values.
  On the two daylight-saving changeover nights a duration can be off by one
  hour. This is a known limitation of the source.
- This is an assumption, not a verified fact; see `dataset.md`, "Known
  limitations".


## 6. Quarantine schema

Quarantine has the Bronze columns **unchanged** (including float money, so the
evidence is preserved as received) plus:

| Column | Type | Nullable | Meaning |
|---|---|---|---|
| `reject_reasons` | List(String) | no | Every reason code that applies, sorted alphabetically, at least one. |

Each rejected row appears **once**, with all its reasons.


## 7. Quality rules

### 7.1 Reject rules

Month membership is decided by the **pickup** time: a trip that starts on
31 January and ends on 1 February is in January. The limits are project
assumptions, not TLC rules (see `data_quality_findings.md`).

| Reason code | Condition | Boundary |
|---|---|---|
| `fare_not_positive` | `fare_amount <= 0` | 0 is rejected |
| `fare_too_high` | `fare_amount > 1000` | exactly 1000 is accepted |
| `distance_not_positive` | `trip_distance <= 0` | 0 is rejected |
| `distance_too_high` | `trip_distance > 200` | exactly 200 is accepted |
| `dropoff_before_pickup` | dropoff earlier than pickup | equal times are not this rule |
| `zero_duration_with_distance` | dropoff equals pickup and `trip_distance > 0` | |
| `duration_too_long` | duration longer than 5 hours | exactly 5 hours is accepted |
| `pickup_outside_month` | pickup before the first instant of the month or at/after the first instant of the next month | |
| `missing_pickup_datetime` | pickup is null | |
| `missing_dropoff_datetime` | dropoff is null | |
| `missing_fare` | `fare_amount` is null | |
| `missing_distance` | `trip_distance` is null | |
| `non_finite_fare` | `fare_amount` is NaN or infinite | |
| `non_finite_distance` | `trip_distance` is NaN or infinite | |
| `missing_pickup_location`, `missing_dropoff_location`, `invalid_pickup_location`, `invalid_dropoff_location` | location ID null, or outside 1 to 265 | see section 7.3 |

Rules that need a null or non-finite value are skipped for that value, so a
missing fare gives `missing_fare` only, not also `fare_not_positive`.
"Invalid" timestamps cannot occur in a typed Parquet file; an unreadable file
fails the whole run (section 9) instead of producing rows.

Rows from `data_quality_findings.md` that this document rejects *in addition*:
nulls and non-finite values in the required columns, and the location policy
below. The accepted count is therefore expected to be equal to or slightly below
3,251,195; any difference must be explained after the first real run.

### 7.2 Retain rules

| Condition | Handling |
|---|---|
| Flex Fare nulls (`passenger_count`, `RatecodeID`, `store_and_fwd_flag`, `congestion_surcharge`, `Airport_fee`) | Retained, nulls preserved, `has_missing_flex_fields = true` |
| `PULocationID` or `DOLocationID` is 264 or 265 | Retained as Unknown / Outside of NYC, unknown-zone flag set |

### 7.3 Location ID policy (missing or unrecognized IDs)

Valid location IDs are 1 to 265 (`taxi_zone_lookup.csv`). The issue requires a
documented, tested policy for IDs that are null or outside that range.

**Policy: reject both.** A trip whose pickup or dropoff location is null, or is
not a whole number from 1 to 265, goes to Quarantine.

| Reason code | Condition |
|---|---|
| `missing_pickup_location` | `PULocationID` is null |
| `missing_dropoff_location` | `DOLocationID` is null |
| `invalid_pickup_location` | `PULocationID` is not null and outside 1 to 265 |
| `invalid_dropoff_location` | `DOLocationID` is not null and outside 1 to 265 |

Why reject instead of retain:

- Zone analytics join on `LocationID` (`dataset.md`). A Silver row with an ID
  that is not in the lookup would silently disappear from an inner join, and
  the totals would no longer match Silver.
- A null or impossible ID is a broken record, unlike 264 and 265, which TLC
  defines as real values ("Unknown", "Outside of NYC").
- January 2025 has no null IDs (`dataset.md`), so this rule does not change the
  baseline counts. It protects later months.

IDs 264 and 265 stay valid and are only flagged (section 7.2).

### 7.4 Overlap and counting

A row can break several rules. So:

- `reject_reasons` lists all of them.
- Per-rule counts can add up to more than the rejected total.
- `rejected` counts each row once.
- `bronze_rows = silver_rows + quarantine_rows`, with no row in both.

### 7.5 Quality summary

`quality_summary.json` is written next to the Silver data. Illustrative
example (made-up numbers for 10 rows, to show overlap):

```json
{
  "source_month": "2025-01",
  "source_sha256": "<sha256 of the Raw file>",
  "input_rows": 10,
  "accepted_rows": 7,
  "rejected_rows": 3,
  "rule_counts": {
    "distance_too_high": 1,
    "fare_too_high": 2,
    "fare_not_positive": 1
  },
  "flag_counts": {
    "has_missing_flex_fields": 2,
    "is_unknown_pickup_zone": 1,
    "is_unknown_dropoff_zone": 0
  }
}
```

Here the rules fired 4 times for 3 rejected rows because one row broke two
rules. `accepted_rows + rejected_rows == input_rows` must hold, or the run
fails.


## 8. Reruns and stale output

- Output keys are deterministic and each layer holds one data object per month.
  Reprocessing the same source overwrites it; nothing is appended.
- Before a run is reported successful, the folder is checked: any data object
  that is not the expected one (for example from an older run) is removed.
- The manifest is `pending` until all outputs are written and verified, so an
  interrupted run is visible and is redone from scratch.
- Running twice on the same source gives the same rows and the same counts.


## 9. Failure and memory

- A missing required column, an unreadable Raw file or a failed count check
  stops the run with a clear error. Partial output is never reported as
  success.
- The data is read lazily and written in a streaming way, one month at a time,
  so a month does not have to fit in memory (January is about 467 MB in memory
  when fully loaded; the VM has 8 GB). Runtime and observed memory for the
  January run will be recorded here after the first real run.

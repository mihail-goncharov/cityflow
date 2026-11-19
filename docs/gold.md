# Gold layer: DuckDB and dbt marts

**Status:** draft, written for AB#5 before the models. Sections marked
*To verify* are decided only after a test run.

Gold turns Silver trips into small, documented tables (marts) for the
dashboard (EPIC-07). It builds on [`medallion.md`](medallion.md), which defines
the Silver schema, and [`kpi_dictionary.md`](kpi_dictionary.md), which defines
every metric.

Gold reads only Silver. It does not repeat the Bronze-to-Silver quality rules:
every Silver row is an accepted trip and is counted.


## 1. Layers and models

```
Silver Parquet ──► stg_silver_trips ──┬──► mart_daily_trips
                                      ├──► mart_hourly_demand
taxi_zone_lookup.csv ──► dim_zone ────┴──► mart_pickup_zone_daily
```

| dbt folder | Model | Role |
|---|---|---|
| `models/staging` | `stg_silver_trips` | Selects and renames the Silver columns Gold uses, for the configured months. One row per Silver row. No filtering. |
| `models/staging` | `dim_zone` | One row per `LocationID` from the zone lookup seed. |
| `models/intermediate` | `int_trips_with_pickup_zone` | Trips joined with the pickup zone. Used by the zone mart. |
| `models/marts` | the three marts | Aggregates, section 3. |
| `seeds` | `taxi_zone_lookup` | The official TLC zone file, section 4. |

- **Multiplicity is kept.** Identical-looking trips are separate Silver rows
  with different `source_row_id`s, so each one is counted. No model uses
  `DISTINCT` or deduplicates trips.
- **Money stays in integer cents** (`*_cents`, `BIGINT`) as in Silver.


## 2. Configuration

Nothing environment-specific is hardcoded in the dbt project. Everything comes
from environment variables or dbt variables:

| Setting | Where | Default | Meaning |
|---|---|---|---|
| `source_months` | dbt var | `["2025-01"]` | Months of Silver to read (`YYYY-MM`). |
| `CITYFLOW_SILVER_ROOT` | env var | none, required | Folder that holds `year=<YYYY>/month=<MM>/yellow_tripdata.parquet`: a local folder (fixtures, staged files) or `s3://<bucket>/silver/nyc_tlc/yellow_taxi`. |
| `CITYFLOW_DUCKDB_PATH` | env var | `target/cityflow.duckdb` | The DuckDB file that holds the built tables. |
| `S3_ENDPOINT_URL`, `S3_ACCESS_KEY`, `S3_SECRET_KEY` | env vars | none | The same variables as ingestion, only needed to read from RustFS. |

- `dbt/profiles.yml` is committed. It contains no secrets, only
  `env_var(...)` calls.
- Credentials are never written to the dbt project, logs or `target/`.

The Silver path for a month is built from the root, in the same layout as
`medallion.md` section 2:
`<CITYFLOW_SILVER_ROOT>/year=2025/month=01/yellow_tripdata.parquet`.


## 3. Marts

| Model | Grain (unique key) | Metrics |
|---|---|---|
| `mart_daily_trips` | `pickup_date` | `trip_count`, `total_fare_cents`, `total_charged_cents`, `avg_trip_distance_miles`, `avg_trip_duration_seconds` |
| `mart_hourly_demand` | `pickup_date`, `pickup_hour` | `trip_count`, `total_fare_cents`, `avg_fare_cents` |
| `mart_pickup_zone_daily` | `pickup_date`, `pickup_location_id` | `trip_count`, `total_fare_cents`, `avg_trip_distance_miles`, `avg_trip_duration_seconds`, `pickup_borough`, `pickup_zone`, `pickup_service_zone`, `is_unknown_pickup_zone` |

- Each mart also has `source_month`, so a month can be filtered and reconciled.
  It is not part of the key: Silver rejects trips whose pickup is outside the
  month, so one `pickup_date` belongs to exactly one month.
- Dates and hours are Silver's `pickup_date` and `pickup_hour` (New York local
  time, `medallion.md` section 5). A trip that crosses midnight belongs to its
  pickup date.
- A row exists only for a date, hour or zone that has at least one trip. Empty
  hours are not filled with zeros, so no average has a zero denominator.
- **Unknown zones are kept.** IDs 264 (Unknown) and 265 (Outside of NYC) are
  ordinary rows in `mart_pickup_zone_daily` with `is_unknown_pickup_zone =
  true`, so the zone mart's totals reconcile with Silver. A dashboard that
  leaves them out of a ranking must filter on that flag explicitly.

Metric definitions, units and rounding: [`kpi_dictionary.md`](kpi_dictionary.md).


## 4. Taxi zone lookup

- **Source:** `https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv`
  (`dataset.md`).
- **Stored as a dbt seed:** `dbt/seeds/taxi_zone_lookup.csv`, committed
  unchanged, with explicit column types. The build never downloads it, so it
  is reproducible and works offline and in CI.
- **Recorded version:** downloaded on 2026-11-20, 265 rows, `LocationID` 1 to
  265 with no gaps or duplicates. SHA-256 of the committed file:
  `5e8f5ff10175d75f468c6fbdf0f68ca93e77ecd48942718d5403f8b7232e90b0`.
- **`dim_zone`:** `location_id` (unique, not null), `borough`, `zone`,
  `service_zone`, `is_unknown_zone` (true for 264 and 265). IDs 264 and 265
  keep their TLC labels.
- **Joins use the ID.** Zone names are not unique (`dataset.md`), so they are
  never used as a join key.


## 5. Tests

| What | How |
|---|---|
| Mart keys are unique and not null | dbt `unique` / `not_null` tests (combined keys as one expression) |
| `dim_zone.location_id` is unique, and 264 and 265 exist with their TLC labels (not null) | dbt tests |
| Every trip's pickup ID has a zone | `relationships` test from `stg_silver_trips` to `dim_zone`. A missing match fails the build instead of disappearing. |
| Joins keep the trip count | Singular test: row count of `int_trips_with_pickup_zone` equals `stg_silver_trips` |
| Each mart reconciles with Silver | Singular tests per mart: `sum(trip_count)` equals the Silver row count, and each exposed money total equals the Silver sum, for each month |
| Exact metric values | dbt unit tests (`unit_tests:` in YAML) with small input rows and the exact expected output: duplicate-looking trips, unknown zones, cross-midnight trips, nullable fields and empty input |

**Fixtures.** Unit tests define their input rows in YAML. A full `dbt build` in
CI reads a small Silver Parquet fixture written by a committed script with
fixed rows, so CI needs neither RustFS credentials nor the real dataset.


## 6. Reruns

- **A build rebuilds the complete configured dataset.** Every mart is a
  `table` that is replaced on each build from all months in `source_months`.
  There are no incremental models and nothing is appended.
- So rebuilding the same input gives the same keys and values, with no
  duplicates. Changing `source_months` changes which months the tables hold.
- A month of Silver is about 3.25 million rows, so a full rebuild is cheap
  enough that incremental logic is not worth its risk at this size.


## 7. Reading Silver from RustFS

*To verify.* Two options, tried in this order:

1. **DuckDB reads RustFS directly** with the `httpfs` extension and an S3
   secret built from the `S3_*` variables (path-style URLs, endpoint through
   the SSH tunnel).
2. **Stage locally:** download the month's Silver file with the existing
   `S3StorageAdapter`, then point `CITYFLOW_SILVER_ROOT` at the local folder.

Option 2 has one advantage: it can check the Silver manifest is `published` and
verify the file's SHA-256 before the build, as the transform does for Raw.
Option 1 would read whatever object is at the key. The chosen option and the
reason will be recorded here.


## 8. Output interface

*Draft.* The marts are persistent tables in the DuckDB file at
`CITYFLOW_DUCKDB_PATH`. Another developer or the dashboard can open the file
read-only and query them. Publishing Gold as Parquet to RustFS is left to the
orchestration epic (EPIC-06), which lists "Gold publication" as a step.


## 9. Commands

*Added with the dbt project.* Setup, `dbt build` for fixtures and for January
2025, and where the output appears.


## 10. Example queries

*Added with the marts.*


## 11. Observed January 2025 build

*Added after the real run:* runtime and peak memory on the development VM
(budget 8 GB), measured like `medallion.md` section 9.1.

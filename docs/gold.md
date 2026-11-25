# Gold layer: DuckDB and dbt marts

**Status:** implemented for AB#5. The models, tests and the January 2025
build described here are in `dbt/` and were run on 2026-11-25.

Gold turns Silver trips into small, documented tables (marts) for the
dashboard (EPIC-07). It builds on [`medallion.md`](medallion.md), which defines
the Silver schema, and [`kpi_dictionary.md`](kpi_dictionary.md), which defines
every metric.

Gold reads only Silver. It does not repeat the Bronze-to-Silver quality rules:
every Silver row is an accepted trip and is counted.


## 1. Layers and models

```
Silver Parquet ──► stg_silver_trips ──┬──────────────────────────────► mart_daily_trips
                                      ├──────────────────────────────► mart_hourly_demand
                                      └──► int_trips_with_pickup_zone ──► mart_pickup_zone_daily
taxi_zone_lookup.csv ──► dim_zone ──────────────┘
```

| dbt folder | Model | Type | Role |
|---|---|---|---|
| `models/staging` | `stg_silver_trips` | view | Selects and renames the Silver columns Gold uses, for the configured months. One row per Silver row. No filtering. |
| `models/staging` | `dim_zone` | view | One row per `LocationID` from the zone lookup seed. |
| `models/intermediate` | `int_trips_with_pickup_zone` | view | Trips joined with the pickup zone on the ID (left join). Used by the zone mart. |
| `models/marts` | the three marts | table | Aggregates, section 3. |
| `seeds` | `taxi_zone_lookup` | table | The official TLC zone file, section 4. |

- **Silver is read in one place.** `stg_silver_trips` reads
  `read_parquet({{ silver_paths() }})` itself instead of through a dbt
  `source`, because a source definition cannot call a project macro, and the
  `silver_paths` macro checks `source_months` (format, no repeated month). No
  other model reads Silver; the reconciliation tests (section 5) read it
  again on purpose, to stay independent of staging.

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
| `CITYFLOW_DUCKDB_PATH` | env var | `dbt/cityflow.duckdb` | The DuckDB file that holds the built tables. A relative path is relative to the directory dbt is run from (the repository root). |
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
| Mart keys are unique and not null | `not_null` on every column; `unique` on `mart_daily_trips.pickup_date`; singular tests `mart_hourly_demand_unique_key` and `mart_pickup_zone_daily_unique_key` for the two-column keys |
| Staging keeps every Silver row once | `not_null` on every column; singular test `stg_silver_trips_unique_row_id`: `(source_month, source_row_id)` is unique |
| `dim_zone.location_id` is unique, and 264 and 265 exist with their TLC labels | `unique` / `not_null`; singular test `dim_zone_unknown_zone_labels` |
| Every trip's pickup ID has a zone | `relationships` test from `stg_silver_trips` to `dim_zone`. A missing match fails the build instead of disappearing (checked with the `invalid_zone` fixture). |
| Joins keep the trip count | Singular test `int_trips_with_pickup_zone_keeps_trip_count`: row count of `int_trips_with_pickup_zone` equals `stg_silver_trips` |
| Each mart reconciles with Silver | Singular tests `mart_*_reconciles_with_silver`: per `source_month`, `sum(trip_count)` equals the Silver row count and each exposed money total equals the Silver sum. Silver is read straight from the Parquet files, not through staging. |
| Exact metric values | dbt unit tests (`models/marts/_unit_tests.yml`, `models/intermediate/_unit_tests.yml`): duplicate-looking trips, a negative total, rounding of every average including the 1,000.5 tie, unknown zones 264 and 265, a join on the ID where two zones share a name, a trip whose zone is missing, and empty input |
| Rebuilding is repeatable | `tests/integration/test_gold_rebuild.py` (pytest): builds the fixture twice and compares the marts; then builds an empty fixture into the same database and checks that no row is left over |

The marts only group by Silver's `pickup_date` and `pickup_hour`, so a unit test
cannot show which date a cross-midnight trip belongs to. That is checked on
the fixture (trip 3 lands on 1 January, hour 23) and by the reconciliation
tests. Nullable Silver columns (the Flex Fare fields) are not read by Gold;
fixture trip 4 has them null and is counted like any other trip.

**Fixtures.** Unit tests define their input rows in YAML. A full `dbt build` in
CI reads a small Silver Parquet fixture, so CI needs neither RustFS credentials
nor the real dataset:

```bash
uv run python -m cityflow.gold.fixture <out_dir>                         # nine trips
uv run python -m cityflow.gold.fixture <out_dir> --variant empty         # same columns, no rows
uv run python -m cityflow.gold.fixture <out_dir> --variant invalid_zone  # one zone not in the lookup
```

The command prints the `CITYFLOW_SILVER_ROOT` to use. `cityflow.gold.fixture`
writes nine January 2025 trips as Raw rows and passes them through the real
Bronze and Silver transform, so the fixture has exactly the Silver schema and
fails if any trip would be rejected. Each trip covers one case:

| Trip | Case |
|---|---|
| 0, 1 | identical-looking trips, both counted |
| 2 | pickup zone 264 (Unknown) |
| 3 | pickup zone 265 (Outside of NYC) at 23:55, dropoff on the next day: belongs to 1 January, hour 23 |
| 4 | Flex Fare trip with null optional fields |
| 5 | second trip in the same date and hour as trip 4 |
| 6, 7 | fares of 1,000 and 1,001 cents in one hour: the average fare is exactly 1,000.5 and must round half away from zero to 1,001 |
| 8 | positive fare with a negative adjustment: total charged is -800 cents |

Expected totals, calculated by hand: 1 January has 4 trips, fare 5,500 cents,
total charged 7,500 cents; 2 January has 5 trips, fare 6,301 cents, total
charged 6,401 cents.

The `invalid_zone` variant gives trip 0 the pickup zone 999, which is not in
the zone lookup. Real Silver cannot contain it, because the reject rules allow
only 1 to 265. It exists only to check that Gold fails on such a trip instead
of losing it in the zone join.


## 6. Reruns

- **A build rebuilds the complete configured dataset.** Every mart is a
  `table` that is replaced on each build from all months in `source_months`.
  There are no incremental models and nothing is appended.
- So rebuilding the same input gives the same keys and values, with no
  duplicates. Changing `source_months` changes which months the tables hold.
- A month of Silver is about 3.25 million rows, so a full rebuild is cheap
  enough that incremental logic is not worth its risk at this size.


## 7. Reading Silver from RustFS

**Decision: DuckDB reads RustFS directly.** Verified on 2026-11-25 through the
SSH tunnel (README, section 4).

Two options were considered:

1. **DuckDB reads RustFS directly** with the `httpfs` extension and an S3
   secret built from the `S3_*` variables (path-style URLs, endpoint through
   the SSH tunnel). **Chosen.**
2. **Stage locally:** download the month's Silver file with the existing
   `S3StorageAdapter`, then point `CITYFLOW_SILVER_ROOT` at the local folder.
   Not needed.

How it is set up: `dbt/profiles.yml` has a second target, `rustfs`, that loads
`httpfs` and creates the S3 secret from `S3_ACCESS_KEY`, `S3_SECRET_KEY` and
`S3_ENDPOINT_URL` (the endpoint's scheme decides SSL). The default target,
`dev`, has no S3 settings, so fixture builds and CI need no credentials. The
real run uses `--target rustfs` with
`CITYFLOW_SILVER_ROOT=s3://<bucket>/silver/nyc_tlc/yellow_taxi`.

What was checked:

- A direct read of January 2025 returned 3,251,195 rows, the `row_count` of
  the Silver manifest (`publication_status: published`) and the
  `accepted_rows` of the quality summary.
- A search of `dbt/target/`, `dbt/logs/` and the build output for the
  access key and secret key found neither.

Why option 1: it works, it needs no extra code, and DuckDB reads only the
columns a query uses (Parquet over HTTP range requests), so the tunnel is not
a bottleneck (section 11).

The trade-off: option 2 could check that the Silver manifest is `published` and
verify the file's SHA-256 before the build. Option 1 reads whatever object is
at the key. This is acceptable because Silver is replaced only by the
transform's publication steps (`medallion.md` section 8), and the
reconciliation tests (section 5) check that the marts agree with the file that
was actually read. Run Gold after the transform has finished, not while it is
publishing.


## 8. Output interface

The output is a **DuckDB file**: `dbt/cityflow.duckdb` by default, or the path
in `CITYFLOW_DUCKDB_PATH`. It is ignored by Git (`*.duckdb`) and is replaced
on every build (section 6).

| Object | Type | Query it? |
|---|---|---|
| `mart_daily_trips`, `mart_hourly_demand`, `mart_pickup_zone_daily` | table | **Yes.** This is the interface. The tables hold their data, so the file can be queried with nothing else: no RustFS, no credentials, no dbt. |
| `taxi_zone_lookup` | table | Yes, but join to `dim_zone` labels through the marts instead. |
| `stg_silver_trips`, `int_trips_with_pickup_zone` | view | No. They read Silver whenever they are queried, so after a `rustfs` build they need the tunnel and the `S3_*` variables. |
| `dim_zone` | view | Possible (it reads the seed table), but the zone mart already carries the zone labels. |

- Open the file **read-only** (`read_only=True` in Python, `-readonly` in the
  DuckDB CLI). DuckDB lets only one process write to a file, and a build
  fails while another program holds it open for writing.
- Column meanings and units: `dbt/models/marts/_marts.yml` and
  [`kpi_dictionary.md`](kpi_dictionary.md). Money is in integer cents.
- Publishing Gold as Parquet to RustFS is left to the orchestration epic
  (EPIC-06), which lists "Gold publication" as a step.


## 9. Commands

All commands run from the repository root. `--project-dir dbt --profiles-dir dbt`
is needed on every dbt command: without it dbt looks for `profiles.yml` in
`~/.dbt` and stops with `Invalid value for '--profiles-dir'`. Examples use
Bash; in PowerShell set a variable with `$env:NAME = "value"` on its own line
first.

**Setup** (once):

```bash
uv sync --locked
```

**Build on the fixture** (no RustFS, no credentials; the same check CI runs).
Use its own database file, so it does not replace the January marts:

```bash
uv run python -m cityflow.gold.fixture dbt/target/fixture
CITYFLOW_SILVER_ROOT=dbt/target/fixture/silver/nyc_tlc/yellow_taxi \
CITYFLOW_DUCKDB_PATH=dbt/target/fixture.duckdb \
  uv run dbt build --project-dir dbt --profiles-dir dbt
```

It ends with `Done. PASS=83 WARN=0 ERROR=0`. `dbt/target/` is ignored by Git
and is removed by `dbt clean`.

**Build January 2025 from RustFS.** Open the SSH tunnel (README, section 4)
and keep it open. `S3_*` come from `.env`; replace `<bucket>` with the value of
`S3_BUCKET`:

```bash
CITYFLOW_SILVER_ROOT=s3://<bucket>/silver/nyc_tlc/yellow_taxi \
  uv run --env-file .env dbt build --target rustfs --project-dir dbt --profiles-dir dbt
```

The marts are written to `dbt/cityflow.duckdb`. The Silver month must be
published first (`python -m cityflow.transform --month 2025-01`, README
section 6).

**Other months.** List them in `source_months`; the build replaces the marts
with all listed months (section 6). Each month must be published in Silver,
otherwise `stg_silver_trips` fails and names the missing file (checked with
local files: `IO Error: No files found that match the pattern
".../year=2025/month=02/yellow_tripdata.parquet"`):

```bash
... dbt build --target rustfs --project-dir dbt --profiles-dir dbt \
  --vars '{source_months: ["2025-01", "2025-02"]}'
```

**Unit tests only.** They use the rows typed in their YAML, not Silver, but dbt
reads column types from the built models, so run them after a build on the
same database (on an empty database they fail with a `Compilation Error`):

```bash
CITYFLOW_SILVER_ROOT=dbt/target/fixture/silver/nyc_tlc/yellow_taxi \
CITYFLOW_DUCKDB_PATH=dbt/target/fixture.duckdb \
  uv run dbt test --select "test_type:unit" --project-dir dbt --profiles-dir dbt
```

The rebuild test runs with the rest of the Python tests (`uv run pytest -q`), or
alone with `uv run pytest tests/integration/test_gold_rebuild.py`. It takes
about 40 seconds because it runs `dbt build` four times.

**Errors you may see:**

| Message | Cause |
|---|---|
| `Invalid value for '--profiles-dir': Path '...\.dbt' does not exist` | `--project-dir dbt --profiles-dir dbt` is missing |
| `Env var required but not provided: 'CITYFLOW_SILVER_ROOT'` | the variable is not set in this terminal |
| `Env var required but not provided: 'S3_ACCESS_KEY'` | `--target rustfs` without `--env-file .env` |
| an HTTP or connection error from DuckDB | the SSH tunnel is not open |
| `IO Error: No files found that match the pattern` | wrong `CITYFLOW_SILVER_ROOT`, or the month is not published (seen with local files; from RustFS the wording may differ) |


## 10. Example queries

Open the file read-only and query the marts, for example from Python:

```bash
uv run python -c "
import duckdb
con = duckdb.connect('dbt/cityflow.duckdb', read_only=True)
for row in con.execute('select * from mart_daily_trips order by pickup_date limit 3').fetchall():
    print(row)
"
```

The results below are from the January 2025 build (section 11).

**Daily trips** (money in cents):

```sql
select pickup_date, trip_count, total_fare_cents, total_charged_cents,
       avg_trip_distance_miles, avg_trip_duration_seconds
from mart_daily_trips
order by pickup_date;
```

| pickup_date | trip_count | total_fare_cents | total_charged_cents | avg_trip_distance_miles | avg_trip_duration_seconds |
|---|---|---|---|---|---|
| 2025-01-01 | 80,966 | 163,643,406 | 231,296,086 | 3.96 | 898.9 |
| 2025-01-02 | 80,604 | 163,330,129 | 237,530,643 | 3.73 | 974.7 |
| 2025-01-03 | 87,007 | 165,931,775 | 243,819,954 | 3.42 | 933.6 |

**Busiest hours of the day over the month.** The average is computed from the
totals, not by averaging `avg_fare_cents`, which would weight every hour the
same:

```sql
select pickup_hour,
       sum(trip_count) as trips,
       round(sum(total_fare_cents) / sum(trip_count) / 100, 2) as avg_fare_dollars
from mart_hourly_demand
group by pickup_hour
order by trips desc
limit 3;
```

| pickup_hour | trips | avg_fare_dollars |
|---|---|---|
| 18 | 236,387 | 16.51 |
| 17 | 229,160 | 17.44 |
| 15 | 204,338 | 18.74 |

**Top pickup zones**, leaving out 264 (Unknown) and 265 (Outside of NYC)
explicitly:

```sql
select pickup_location_id, pickup_zone, pickup_borough, sum(trip_count) as trips
from mart_pickup_zone_daily
where not is_unknown_pickup_zone
group by pickup_location_id, pickup_zone, pickup_borough
order by trips desc
limit 5;
```

| pickup_location_id | pickup_zone | pickup_borough | trips |
|---|---|---|---|
| 161 | Midtown Center | Manhattan | 161,254 |
| 237 | Upper East Side South | Manhattan | 157,918 |
| 236 | Upper East Side North | Manhattan | 149,664 |
| 132 | JFK Airport | Queens | 134,724 |
| 230 | Times Sq/Theatre District | Manhattan | 118,206 |

**Month totals**, to compare with the Silver manifest and quality summary:

```sql
select source_month, sum(trip_count) as trips,
       sum(total_fare_cents) as fare_cents, sum(total_charged_cents) as charged_cents
from mart_daily_trips
group by source_month;
```

| source_month | trips | fare_cents | charged_cents |
|---|---|---|---|
| 2025-01 | 3,251,195 | 5,836,819,199 | 8,718,399,248 |


## 11. Observed January 2025 build

Measured on 2026-11-25 on a Windows development machine, reading Silver from
RustFS through the SSH tunnel (section 7), like `medallion.md` section 9.1. It
was not measured on the VM itself.

| Measure | Value |
|---|---|
| Result | `dbt build --target rustfs`: 83 of 83 pass (1 seed, 6 models, 64 data tests, 12 unit tests) |
| Runtime | 31 to 32 s for the build, in two runs from an empty database |
| Peak memory | about 400 MB (peak working set of the Python process running dbt and DuckDB; about 120 MB of it is Python and dbt before the build starts) |
| Output | `dbt/cityflow.duckdb`, 2.4 MB: 31 daily rows, 744 hourly rows (every hour of January has trips), 7,216 zone rows |

- Peak memory is about 5% of the VM's 8 GB budget.
- The marts hold 3,251,195 trips, the Silver manifest's `row_count`, and
  8,209 of them have an unknown pickup zone, the `is_unknown_pickup_zone`
  count of the quality summary.
- How it was measured: dbt ran inside one Python process (`dbtRunner`), and
  the process's peak working set was read with the Windows API
  (`GetProcessMemoryInfo`). Starting dbt as a separate process and measuring
  that does not work on Windows with uv: the virtual environment's
  `python.exe` is a launcher that starts the real interpreter as another
  process.
- The build reads Silver many times (the staging views are read by each model
  and test that uses them), and still takes about 30 seconds, because DuckDB
  fetches only the columns each query needs.

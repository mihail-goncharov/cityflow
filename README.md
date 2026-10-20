# CityFlow Analytics

Portable Data Engineering and Analytics Platform.

A learning data engineering project: from open NYC taxi data to a reproducible
data platform that runs on a laptop, on a Proxmox homelab and on a public cloud
VM with the same code.

## Goal

Build the full data engineering cycle on a real public dataset: ingestion,
layered storage, data quality rules, an analytical model, orchestration, a
dashboard, CI/CD and deployment. Environments differ only in configuration and
secrets, not in business logic.

## Data source

- **Dataset:** NYC TLC Yellow Taxi Trip Records, published by the New York City
  Taxi and Limousine Commission (TLC):
  https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page
- **Period:** January 2025 for the current stage, one Parquet file per month.
- **Zone names:** `taxi_zone_lookup.csv`, a separate file from TLC.
- **Column meanings:** the Yellow Trips Data Dictionary:
  https://www.nyc.gov/assets/tlc/downloads/pdf/data_dictionary_trip_records_yellow.pdf

Raw data is not stored in Git. In the platform it is kept in S3-compatible
object storage; for local exploration it is downloaded into `data/raw/`.

## Technology stack

| Area | Tools |
|---|---|
| Language and environment | Python 3.13, uv |
| Data processing | Polars, Parquet |
| Object storage | RustFS (S3-compatible) |
| Analytics and modeling | DuckDB, dbt |
| Orchestration | Dagster |
| Dashboard | Streamlit, Plotly |
| Deployment | Docker Compose |
| Git and CI/CD | Forgejo, Forgejo Actions |

## Deployment

- Local development (Docker)
- Proxmox homelab
- Optional public cloud

## Getting started

### Prerequisites

- Git
- uv (https://docs.astral.sh/uv/getting-started/installation/). uv installs the
  required Python version itself, so a global Python is not needed.

### 1. Environment

Clone the repository and create the environment from the project folder:

```
uv sync
```

### 2. Data

No data is stored in repo.
Download January 2025 into `data/raw/`.

**Linux and macOS:**

```
mkdir -p data/raw && cd data/raw
curl -LO https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-01.parquet
curl -LO https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv
cd ../..
```

**Windows PowerShell** (here `curl` is a different command, so use `curl.exe`):

```
New-Item -ItemType Directory -Force data/raw; cd data/raw
curl.exe -LO https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-01.parquet
curl.exe -LO https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv
cd ../..
```

The expected SHA-256 of the trip file is recorded in `docs/source_manifest.json`.

### 3. Run

From the project root, run the profiling, data quality checks and business
questions:

```
uv run python src/cityflow/profile_data.py
```

### 4. Object storage (RustFS)

Copy `.env.example` to `.env` and fill in `S3_ACCESS_KEY` and `S3_SECRET_KEY`
with your keys from the RustFS admin. Never commit `.env`.

RustFS on the dev VM is reachable only through an SSH tunnel. Port 9000 is the
S3 API; port 9001 is the web UI at http://127.0.0.1:9001 (log in with the same
keys):

```
ssh -L 9000:127.0.0.1:9000 -L 9001:127.0.0.1:9001 <user>@cityflow-dev
```

### 5. Tests

```
uv run pytest
```

The S3 adapter tests use moto (an in-memory fake S3), so they need no RustFS or
credentials.

## Initial findings (January 2025)

**Data quality**

- 3,475,226 rows, 20 columns, about 59 MB on disk.
- 15.5% of rows (Flex Fare trips) have no passenger count, rate code or
  surcharge data.
- 224,031 rows (6.45%) have quality problems, such as zero or negative fares,
  zero distance, trips longer than 5 hours or impossible timestamps. They are
  excluded from the metrics below.

**Business metrics** (3,251,195 valid trips)

| Metric | Value |
|---|---|
| Total fare amount | $58,368,192 |
| Average fare per trip | $17.95 |
| Average trip distance | 3.17 miles |
| Average trip duration | 14 min 41 s |
| Busiest hour | 18:00–19:00 (236,387 trips) |
| Top pickup zone | Midtown Center, Manhattan (161,254 trips) |

Total fare amount is a preliminary metric. It is not revenue: tips, taxes,
tolls and surcharges are not included.

Most top pickup and dropoff zones are in Manhattan; JFK Airport is the
fourth busiest pickup zone. Demand is lowest at 04:00 and peaks in the
evening rush hour.

## Documentation

- [`docs/dataset.md`](docs/dataset.md): what the dataset is, its volume,
  entities, columns, business metrics and known limitations.
- [`docs/data_quality_findings.md`](docs/data_quality_findings.md): data
  quality problems found in January 2025, with counts, examples and handling.
- [`docs/source_manifest.json`](docs/source_manifest.json): URL, size and
  SHA-256 of the downloaded source file.

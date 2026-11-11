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
| Shell script checks | ShellCheck |
| Compose configuration checks | Docker Compose CLI |
| Secret scanning | Gitleaks |
| Dependency vulnerability scanning | pip-audit |

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
uv sync --locked
```

Check that `uv.lock` matches `pyproject.toml` with `uv lock --check`.
After intentionally changing dependencies in `pyproject.toml`, run `uv lock`
locally and commit both files together. CI checks the lockfile and installs
dependencies with `uv sync --locked`; it fails if the lockfile is missing or
outdated instead of updating it.

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
uv run --locked python src/cityflow/profile_data.py
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

`.env` is not loaded automatically. Pass it to every command that uses the S3
client, for example:

```
uv run --env-file .env python <script.py>
```

### 5. Ingestion

With the tunnel open and `S3_BUCKET`, `S3_ENDPOINT_URL`, `S3_ACCESS_KEY` and
`S3_SECRET_KEY` set in `.env`, one command downloads, validates and publishes a
month of Yellow Taxi data to the Raw layer:

```
uv run --locked --env-file .env python -m cityflow.ingestion --month 2025-01
```

January 2025 is published to
`raw/nyc_tlc/yellow_taxi/year=2025/month=01/yellow_tripdata_2025-01.parquet`
with a `manifest.json` beside it. Running the command again reports the month
as `skipped`. A failure logs the failed stage and exits with code 1. See the
[ingestion runbook](docs/ingestion.md) for configuration, object naming, reruns
and failure recovery.

## Tests and coverage

Install development dependencies with `uv sync --locked`, then run:

```bash
uv run pytest -q
```

Tests use small synthetic datasets and temporary files; downloaded taxi data
and external services are not required. They cover quality rule boundaries,
missing values, trip filtering and schema preservation, numeric formatting,
business aggregates, empty inputs, and source manifest metadata and SHA-256.
The S3 adapter tests use moto (an in-memory fake S3), so they need no RustFS
or credentials.

Pytest-cov measures statement and branch coverage for the entire `cityflow`
package. Each run prints missing lines and saves `htmlcov/index.html` (browsable
report) and `coverage.xml` (machine-readable report). A combined coverage score
below 80% fails the run. Generated reports are ignored by Git.

Forgejo CI runs the same tests and displays a per-file coverage table in the
job summary above the logs (Forgejo 17+ and Runner 13.2+). The table includes
statements, branches, missing coverage and totals. HTML/XML reports are uploaded
as the `coverage` artifact, retained for 14 days, including when tests fail.
Configuration lives in `pyproject.toml` and `.forgejo/workflows/ci-cd.yml`.

## Shell script checks

Forgejo CI runs ShellCheck on PRs and pushes to `main`, checking all
`infra/scripts/*.sh` files, including `deploy.sh`. Findings fail CI and block
deployment.

Install ShellCheck with `brew install shellcheck` on macOS or
`sudo apt-get install shellcheck` on Debian/Ubuntu, then run from the project root:

```bash
shellcheck --severity=style infra/scripts/*.sh
```

See [`docs/ci-cd-setup.md`](docs/ci-cd-setup.md#shell-script-checks-with-shellcheck)
for the CI setup and scope.

## Compose configuration checks

Forgejo CI validates `compose.yaml` on PRs and pushes to `main` using the
Docker Compose CLI's `config --quiet` command. Invalid configuration fails CI
and blocks deployment. Run the same check locally with Docker CLI and the
Compose plugin installed:

```bash
bash infra/scripts/check-compose.sh
```

The script supplies test values for all project variables, ignores the local
`.env`, inherited application variables and Compose overrides, and does not
print the resolved configuration. No real secrets or running Docker daemon
are required. This validates configuration only; it does not guarantee that
images can be pulled, containers start, or services become healthy.

See [`docs/ci-cd-setup.md`](docs/ci-cd-setup.md#compose-configuration-checks-with-docker-compose-cli)
for installation and check scope.

## Python dependency audit

Forgejo CI runs `pip-audit` as a separate step on PRs and pushes to `main`.
It checks the exact versions exported from `uv.lock`, including transitive
dependencies and the `dev`/`ci` groups, for the current Python and platform.
Known vulnerabilities or audit errors fail CI and block deployment.
Ruff's security rules check source code; they do not replace this dependency
audit.

Run the same audit locally:

```bash
uv sync --locked --group ci
bash infra/scripts/audit-dependencies.sh
```

The report lists affected packages, vulnerability IDs (including CVE/GHSA
aliases where available) and fixed versions. The audit requires HTTPS access
to PyPI. See [`docs/ci-cd-setup.md`](docs/ci-cd-setup.md#python-dependency-audit-with-pip-audit)
for details and remediation.

## Secret scanning

Forgejo CI runs Gitleaks on every commit introduced by a PR to `main` or a push
to `main`. Findings fail CI and block the deploy job. Built-in rules detect
private SSH keys and provider/API tokens; project rules also detect hardcoded
passwords and RustFS access/secret keys, including weak credentials.

The `Gitleaks history` workflow scans all fetched branches and tags every
Monday at 06:00 (`Europe/Chisinau`) and can also be run manually in Actions.
The schedule becomes active once the workflow is merged into the default
branch. Secret values are redacted in logs.

For local installation and scans before committing, see
[`docs/ci-cd-setup.md`](docs/ci-cd-setup.md#secret-scanning-with-gitleaks).

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
- [`docs/ingestion.md`](docs/ingestion.md): ingestion runbook, covering
  configuration, execution, object naming, reruns and failure recovery, with a
  [sample manifest](docs/examples/ingestion_manifest_2025-01.json).
- [`docs/raw_data_contract.md`](docs/raw_data_contract.md): checks a raw file
  must pass before publication.

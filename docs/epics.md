# CityFlow Analytics — Forgejo Epic Backlog and Codex Issue-Generation Brief

**Repository:** `mentorship/cityflow`  
**Project:** CityFlow Mentorship  
**Mentor:** Alex  
**Student:** Misha  
**Target:** working end-to-end data platform, documentation, and university presentation by **11 December 2026**.  
**Planning baseline:** 17 October 2026; approximately 40 weekdays remain from 19 October through 11 December, excluding any local holidays or absences.

> **How to use this file:** Give this entire Markdown document to Codex. Each `EPIC-XX` block below represents a **regular Forgejo Issue with the `type/epic` label**, not a claim that Forgejo has a separate native Epic issue type. Codex should first inspect the existing repository and issues, then create or propose detailed *child implementation issues* under these Epics. Do not blindly recreate already-finished work.

---

## Instructions to Codex

You are a senior Data Engineering technical lead and backlog planner supporting a beginner/intermediate university intern named Misha.

### Assignment

1. Review the live `mentorship/cityflow` repository, existing Forgejo Issues, Projects board, open PRs, and CI workflow **if access is available**. If access is unavailable, use this document as the specification, mark unverified facts as assumptions, and generate Markdown drafts rather than pretending to have created issues.
2. Treat the numbered Epics below as the authoritative **workstream scope**, but verify existing implementation and avoid duplicate tickets. Existing Python profiling, RustFS and Forgejo CI/CD setup may already be partly or fully implemented.
3. For each Epic, prepare **3–6 implementable child issues**, each achievable in about **0.5–2 student working days** (~2–8 hours). Keep total scope realistic for the remaining internship; propose a smaller MVP first if necessary.
4. For each child issue, provide:
   - **Title:** `[EXX] Verb + deliverable` (for example, `[E03] Download one Yellow Taxi Parquet file`)
   - **Purpose / user story**
   - **Context and prerequisites** (link to relevant existing code, issue, or Epic when known)
   - **Tasks** with Markdown `- [ ]` checkboxes
   - **Files / deliverables** (paths grounded in the actual repository; otherwise label as proposed)
   - **Acceptance criteria** with observable, reproducible checks
   - **Test plan** (unit, integration, data checks, manual demo as appropriate)
   - **Estimate** in hours and **priority** (`P0`, `P1`, `P2`)
   - **Dependencies** (`blocked by` / `blocks`, but never invent Forgejo issue numbers)
   - **Suggested labels** and a recommended board column.
5. Maintain dependencies; favour increments that can be demonstrated independently. Include a straightforward happy-path task before complex error handling.
6. Propose the order of work by week, with **feature freeze by 4 December** and **final university demo by 11 December 2026**. Do not book work on weekends or assume full-time availability.
7. If using a Forgejo API/MCP connector, **ask for approval before creating or modifying issues**. Otherwise output ready-to-paste Markdown for each issue. Do not close, delete, or overwrite existing issues automatically.
8. Attach each child to the right Epic using issue references in the child body (`Part of: #...` once the real Epic issue number is known), and use Forgejo dependencies if available. The Epic body should maintain a checklist of actual child issue links after issue creation.
9. Name branches `feature/<short-topic>` or `fix/<short-topic>`. Use Pull Requests with mentor review. Do not merge PRs automatically.
10. Keep explanations approachable for a student: state *what* to build and *how to prove it works*, but do not paste full solutions into the issue body.

### Existing environment — inspect and preserve

- **Hypervisor:** Proxmox on a Lenovo ThinkCentre with 16 GB physical RAM.
- **Forgejo:** self-hosted LXC; repo `mentorship/cityflow`, Issues/Projects, Git SSH, Tailscale private access. Forgejo 17 upgrade may be in progress — verify actual running version before making version-specific assumptions.
- **Application:** Ubuntu VM 110 `cityflow-dev`, 4 vCPU, 8 GB RAM, 150 GB disk.
- **CI Runner:** Ubuntu VM 111 `cityflow-ci`, dedicated Forgejo Actions runner, label `cityflow-ci`, `capacity: 1`; basic CI smoke test and Python CI have been demonstrated. The CD configuration is in progress; **do not assume successful automatic deployment** without evidence.
- **Storage:** one shared RustFS container on VM 110 using `/srv/cityflow/rustfs`, presently served on VM-local ports 9000 (S3) and 9001 (Console). The student should use a restricted development bucket/identity through the S3 API, not create a second RustFS container or require broad `sudo`/Docker permissions.
- **Developer machines:** Misha uses Windows and can develop locally or on VM 110 over SSH/Tailscale; his Linux username is `misha`. Alex uses a Mac and Linux username `alex` on VM 110. Use `vim`, not `nano`, in Linux terminal instructions.
- **Python project:** `pyproject.toml` currently specifies Python **>=3.13** (verify in Git, which is authoritative), using `uv`, Polars, PyArrow and related tooling. `ruff` and `pytest` were added to CI.
- **Deployment:** infrastructure defined in version-controlled `compose.yaml`; project config template `.env.example`; real `.env` excluded from Git. Application state lives outside the repository.
- **Dataset:** NYC TLC **Yellow Taxi Trip Records**, initially January 2025, then optionally February–March 2025; Taxi Zone Lookup and official Data Dictionary. Work with Parquet.
- **Core data stack:** Python, Polars, PyArrow, boto3, RustFS/S3, DuckDB, dbt Core/dbt-duckdb, Dagster, Streamlit, Plotly, Docker Compose, Forgejo Actions. Prometheus/Grafana and Iceberg are **optional**.
- **No public Proxmox, SSH, RustFS administrative console, or deployment secrets.** Use Tailscale for private access.

### Priority and completion conventions

- `P0` = essential MVP needed for the university demo.
- `P1` = important robustness/documentation work; schedule if P0 is stable.
- `P2` = optional stretch goal; never delay MVP.
- **Definition of Done for implementation issues:** code in Git, reproducible command/test, no credentials or large datasets committed, PR reviewed by mentor, relevant docs updated.
- **Definition of Done for Epics:** all `P0` child issues accepted, integrated and demonstrable; nonessential items may remain open as documented follow-ups.

### Suggested Forgejo labels

`type/epic`, `type/task`, `type/bug`, `priority/P0`, `priority/P1`, `priority/P2`, `area/python`, `area/storage`, `area/ingestion`, `area/quality`, `area/dbt`, `area/orchestration`, `area/dashboard`, `area/ci-cd`, `area/security`, `area/ops`, `area/docs`, `good-first-issue`.

Use labels that actually exist or ask before creating them. Suggested Project columns: `Backlog`, `Ready`, `In Progress`, `Code Review`, `Testing`, `Done`.

---

# Epic descriptions — paste each block as a Forgejo Issue

## EPIC-01 — Python Environment, Dataset Discovery & Profiling

**Suggested Issue title:** `[EPIC-01] Python Environment & NYC Taxi Profiling`  
**Labels:** `type/epic`, `area/python`, `priority/P0`  
**Target window:** 19–23 October (close remaining work first)  
**Owner:** Misha, reviewed by Alex  
**Depends on:** Git/Forgejo access (available)

### Objective

Create a reproducible Python development environment and establish a documented understanding of the January 2025 NYC Yellow Taxi dataset before transforming any records.

### Scope

- Use project-managed Python via `uv`, respecting the repository's `requires-python` requirement and committed lockfile.
- Obtain January 2025 Yellow Taxi Trip Records (Parquet), the official Data Dictionary and Taxi Zone Lookup.
- Implement repeatable profiling with Polars: schema, row count, nulls, date range, distance/fare distributions, unusual values, location coverage and basic daily/hourly metrics.
- Record at least five specific data-quality findings with counts, affected percentages and proposed handling.
- Write instructions so another developer can reproduce results without committing large source files.

### Deliverables

- Working `pyproject.toml` and `uv.lock` in Git.
- Reusable profiling script in `src/cityflow/` (use existing paths if present).
- `docs/dataset.md` and `docs/data_quality_findings.md`.
- Updated `README.md` and `.gitignore` rules for datasets and secrets.

### Acceptance criteria

- [ ] A clean checkout can install and run with documented `uv` commands.
- [ ] Profiling produces the agreed statistics for January 2025 from the official Parquet source.
- [ ] Five or more quality findings include counts and clear proposed treatment.
- [ ] The script is rerunnable; raw input is unchanged.
- [ ] No downloaded Parquet files, notebooks' large outputs or secrets are committed.
- [ ] Misha can give a five-minute walkthrough of source data and initial findings.

### Candidate child issues

Environment and lockfile; source/data dictionary documentation; reproducible Polars profiler; quality findings report; basic temporal and location analysis.

**Existing work:** An issue titled **“Python Environment & NYC Taxi Profiling”** may already exist. Reuse/update it rather than creating a duplicate Epic without approval.

---

## EPIC-02 — RustFS Access & Portable Storage Adapter

**Suggested Issue title:** `[EPIC-02] RustFS Storage Integration and S3 Adapter`  
**Labels:** `type/epic`, `area/storage`, `priority/P0`  
**Target window:** 19–30 October  
**Owner:** Misha (Python adapter), Alex (IAM/infrastructure)  
**Depends on:** EPIC-01 environment; existing shared RustFS deployment

### Objective

Make RustFS the shared S3-compatible object store for CityFlow, accessed from Python through a tested, configuration-driven adapter. Keep credentials and host-level permissions separate from student code.

### Scope

- Confirm RustFS is healthy and existing persistent volume is owned by UID/GID 10001.
- Mentor provisions a private **`cityflow-dev`** bucket and least-privilege IAM identity for Misha. Do not give the student RustFS admin secrets, host `sudo`, or Docker-group membership.
- Implement storage operations using `boto3`: upload, download, list, delete, existence/head, and meaningful error handling.
- Use environment-based configuration with a clear distinction between VM-local endpoint, Windows SSH tunnel, and Docker network endpoint.
- Consider a basic filesystem adapter for local/offline development if practical; the S3 adapter is required.

### Deliverables

- `src/cityflow/storage/` module(s), documented config variables and usage examples.
- Adapter unit tests and isolated RustFS integration test.
- `docs/storage.md` covering credentials, bucket conventions and access boundaries.

### Acceptance criteria

- [ ] `PUT`, `HEAD`, `GET`, `LIST`, and `DELETE` succeed in the development bucket.
- [ ] A retrieved object has the same checksum as the uploaded object.
- [ ] Invalid credentials, missing objects and unavailable endpoint produce understandable failures.
- [ ] Access to the protected main bucket is denied for Misha's credentials.
- [ ] No second RustFS instance is required in Misha's home directory.
- [ ] No secrets appear in source control, CI logs or example files.

### Candidate child issues

Storage configuration schema; boto3 adapter; unit tests with mocks; RustFS integration test; IAM/access verification (mentor); setup documentation.

**Existing work:** Shared RustFS already runs on VM 110. Validate its state; do not ticket another installation unless the system is actually broken.

---

## EPIC-03 — Reliable Batch Ingestion and Raw Data Contracts

**Suggested Issue title:** `[EPIC-03] NYC TLC Ingestion, Contracts and Raw Layer`  
**Labels:** `type/epic`, `area/ingestion`, `priority/P0`  
**Target window:** 26 October – 6 November  
**Owner:** Misha  
**Depends on:** EPIC-01, EPIC-02

### Objective

Automate downloading and publishing monthly NYC Yellow Taxi Parquet files to the RustFS Raw layer with traceability, repeatability and explicit input contracts.

### Scope

- Download January 2025 reliably from the official source, optionally followed by February/March.
- Validate source URL, file format, file size, and required schema fields before publication.
- Define object key naming for `raw/nyc_tlc/yellow_taxi/year=YYYY/month=MM/...` and maintain a simple ingestion manifest with file checksum, source URL, ingestion timestamp, size and status.
- Avoid duplicate publication on reruns; use deterministic keys and checksum comparison.
- Handle request timeouts, network failures and incomplete transfers. Never silently publish partial downloads as complete datasets.

### Deliverables

- Reusable CLI ingestion script/package in `src/cityflow/ingestion/`.
- Data contract file/documentation under `docs/` or `contracts/`.
- Runbook and sample manifest for January 2025.

### Acceptance criteria

- [ ] One command downloads and publishes the January 2025 source Parquet.
- [ ] Source checksum/size and lineage are recorded in a manifest.
- [ ] Running ingestion twice does not produce duplicate logical inputs.
- [ ] Failures are logged and return a nonzero exit code without corrupting the published dataset.
- [ ] All filenames and S3 object keys are deterministic and documented.
- [ ] Integration test uses a small sample or isolated prefix, not the protected working data.

### Candidate child issues

Source client with retry/timeout; object key conventions; ingestion manifest; schema/contract gate; idempotent publish; documented CLI and integration test.

---

## EPIC-04 — Bronze/Silver Transformations & Data Quality

**Suggested Issue title:** `[EPIC-04] Medallion Layers and Data Quality Rules`  
**Labels:** `type/epic`, `area/quality`, `priority/P0`  
**Target window:** 2–13 November  
**Owner:** Misha  
**Depends on:** EPIC-03

### Objective

Turn raw TLC records into validated and analysis-ready Parquet data while preserving lineage and making invalid records auditable.

### Scope

- Define the responsibilities of Raw, Bronze, Silver, Quarantine and later Gold.
- Implement typed, deterministic Polars transformations (prefer lazy/scanning where appropriate).
- Validate timestamps, negative/zero distance, fare values, location IDs, plausible duration and data types. Distinguish invalid data from legitimate edge cases using explicit business rules.
- Publish accepted records to Silver and rejected/flagged records to Quarantine with reason codes.
- Track input, accepted and quarantined counts; demonstrate row-count reconciliation.
- Keep the original Raw Parquet unchanged and document schema evolution assumptions.

### Deliverables

- Bronze/Silver transformation functions and quality rule modules.
- Quarantine record schema and a quality summary/report.
- Small deterministic sample fixtures and tests.

### Acceptance criteria

- [ ] Bronze retains traceability to source object/version and ingestion batch.
- [ ] Silver records conform to documented types and quality rules.
- [ ] `input rows = accepted rows + quarantined rows` for rules that partition records (explain separately any non-exclusive flags).
- [ ] A known synthetic dataset produces the exact expected accepted/rejected result.
- [ ] Transformations are repeatable and do not create duplicates on rerun.
- [ ] Processing a month is feasible on VM 110's 8 GB RAM, without loading excessive data into memory.

### Candidate child issues

Medallion/schema definitions; Bronze normalization; quality rules; Quarantine outputs; reconciliation metrics; integration tests and docs.

---

## EPIC-05 — DuckDB/dbt Gold Marts and Business Metrics

**Suggested Issue title:** `[EPIC-05] Analytics Gold Layer with DuckDB and dbt`  
**Labels:** `type/epic`, `area/dbt`, `priority/P0`  
**Target window:** 9–20 November  
**Owner:** Misha  
**Depends on:** EPIC-04

### Objective

Build tested SQL analytics marts from clean Silver data, with consistent KPI definitions suitable for the CityFlow dashboard.

### Scope

- Query Silver Parquet efficiently with DuckDB (including RustFS integration if verified for the chosen version).
- Configure `dbt-core` and `dbt-duckdb`; maintain clean `sources`, staging, intermediate and marts layers.
- Map pickup/dropoff locations to the official NYC Taxi Zone Lookup.
- Build at least three Gold marts, for example: daily trips/revenue measures, hourly demand, and zone performance.
- Define KPI calculations precisely: trip count, fare sum, total amount, average fare, duration, distance, and time-of-day breakdown. Clearly distinguish `fare_amount` from `total_amount` and avoid unsupported claims about gross business revenue.
- Use dbt tests for keys, non-null fields, relationships, accepted values and custom business invariants.

### Deliverables

- dbt project/model SQL, tests, documentation and reproducible build command.
- Published Gold Parquet artifacts or validated DuckDB tables/views with documented access path.
- `docs/kpi_dictionary.md`.

### Acceptance criteria

- [ ] `dbt build` succeeds from a clean documented setup.
- [ ] Gold marts use Silver rather than reading Raw directly.
- [ ] Zone lookup joins behave correctly, including missing/unknown IDs.
- [ ] KPI values match hand-calculated results from tiny fixtures.
- [ ] Data tests and SQL unit tests cover important assumptions.
- [ ] At least three queryable marts are ready for dashboards.

### Candidate child issues

DuckDB/S3 connectivity; dbt bootstrap; zone dimension; daily and hourly marts; spatial/zone mart; dbt tests and KPI dictionary.

---

## EPIC-06 — Dagster Orchestration & Pipeline Reliability

**Suggested Issue title:** `[EPIC-06] End-to-End Orchestration with Dagster`  
**Labels:** `type/epic`, `area/orchestration`, `priority/P0`  
**Target window:** 16–27 November  
**Owner:** Misha  
**Depends on:** EPIC-03, EPIC-04, EPIC-05

### Objective

Run the full ingestion-to-Gold process through Dagster and make jobs observable, repeatable and recoverable.

### Scope

- Implement Dagster assets/jobs for download → Raw publication → Bronze/Silver validation → dbt build → Gold publication.
- Define explicit dependencies, asset metadata, row counts, execution time and failure diagnostics.
- Use SQLite metadata storage for this small single-node educational setup unless implementation requires otherwise.
- Start with manual execution; add daily/weekly schedule only after the run is idempotent.
- Support one-month and selected multi-month backfill without unexpected duplicates or extra services.
- Limit overlapping runs and peak memory on VM 110.

### Deliverables

- `orchestration/` code and Dagster configuration.
- Compose integration for Dagster UI/daemon when needed.
- A runbook for manual run, failed-run diagnosis and safe rerun.

### Acceptance criteria

- [ ] An end-to-end run is triggerable through the Dagster UI or CLI.
- [ ] Successful run publishes or validates expected Gold outputs.
- [ ] Failed step reports a clear cause; retry/rerun is documented.
- [ ] No duplicate data appears on rerun.
- [ ] Run duration, record counts and input batch metadata are visible.
- [ ] Schedules do not start uncontrolled parallel processing on the 8 GB VM.

### Candidate child issues

Dagster project setup; asset definitions; dbt asset integration; run metadata; rerun/backfill; schedule, alerts and runbook.

---

## EPIC-07 — Interactive CityFlow Dashboard

**Suggested Issue title:** `[EPIC-07] Streamlit and Plotly Analytics Dashboard`  
**Labels:** `type/epic`, `area/dashboard`, `priority/P0`  
**Target window:** 23 November – 4 December  
**Owner:** Misha  
**Depends on:** EPIC-05 (Gold marts), ideally EPIC-06

### Objective

Deliver an intuitive dashboard demonstrating insights from NYC Yellow Taxi data and the value of the end-to-end engineering pipeline.

### Scope

- Build Streamlit dashboard reading **Gold marts**, not raw files.
- Show KPI cards: trips, monetary measures clearly labelled, average distance and duration.
- Add date/month and pickup/dropoff zone filters as supported by the available marts.
- Visualize demand by day/hour, zone ranking, and a useful fare/distance comparison with Plotly.
- Document data limitations and ensure empty selections, missing data and refresh errors are handled.
- Keep dashboard lightweight (cached aggregates rather than scanning an entire monthly Parquet file for every interaction).

### Deliverables

- `dashboard/` Streamlit application and reproducible launch instructions.
- Screenshot(s) or short demo clip for presentation, if useful.
- User-facing metric definitions and limitations.

### Acceptance criteria

- [ ] A mentor can open the dashboard privately through Tailscale.
- [ ] At least four purposeful visualizations and several KPIs work correctly.
- [ ] Filters affect charts consistently without obvious metric contradictions.
- [ ] Dashboard runs with 8 GB VM constraints and sensible load time on Gold aggregates.
- [ ] No S3/admin credentials are embedded in frontend source.
- [ ] Student can explain one interesting, data-supported observation.

### Candidate child issues

Dashboard skeleton and connection; KPI cards; temporal plots; zone plots; interactive filters; caching, usability and demo checks.

---

## EPIC-08 — Automated Quality Gates & Safe CI/CD

**Suggested Issue title:** `[EPIC-08] Forgejo CI, Test Quality Gates and Trusted Deployment`  
**Labels:** `type/epic`, `area/ci-cd`, `priority/P0`  
**Target window:** Cross-cutting; harden by 4 December  
**Owner:** Alex (deployment boundaries), Misha (tests and basic CI)  
**Depends on:** Existing Forgejo runner/Compose; all coding Epics contribute tests

### Objective

Make every Pull Request verifiable and ensure only reviewed, tested revisions are deployed to the shared CityFlow VM.

### Scope

- Preserve already-working Forgejo runner label `cityflow-ci` and basic smoke/Python workflows.
- Check lockfile consistency, Ruff lint/format, pytest, type checks where useful, secrets scanning (e.g., Gitleaks), and static Compose/script validation.
- Maintain isolated unit tests; no live RustFS admin secrets or host Docker privileges in untrusted PR jobs.
- Publish concise CI results and failure diagnostics to the PR.
- Protect `main` with mentor review and required checks.
- Implement CD using a **trusted workflow/runner/credentials boundary**; do not assume that a job-level `if: main` condition alone protects secrets from editable PR workflows. Deploy a reviewed commit to VM 110 with pinned images, health checks and rollback plan.
- Keep security scans and heavier integration tests on separate schedule/manual jobs if needed for VM 111 resources.

### Deliverables

- `.forgejo/workflows/` CI configuration, tests and `infra/scripts/deploy.sh` (or safer replacement).
- `docs/ci-cd-setup.md`, secret-handling guidance, verified deployment checklist.

### Acceptance criteria

- [ ] A normal PR triggers tests automatically and reports pass/fail.
- [ ] Tests include quality and dependency/secret checks appropriate to project maturity.
- [ ] The deployed commit SHA can be matched to a reviewed, successful CI result.
- [ ] PR-controlled code cannot read deployment credentials or control VM 110.
- [ ] A bad deploy fails visibly; known-good application state/data remain recoverable.
- [ ] Deployment does not wipe `/srv/cityflow/rustfs` or commit `.env`/tokens/keys.

### Candidate child issues

Existing CI audit; pytest fixtures/coverage; Ruff and type checks; secret scanning; trusted CD redesign and review gates; deploy smoke test and rollback.

**Existing work:** Smoke test, Ruff/Python CI and SSH connectivity already demonstrated; do not reissue these as new installation tasks without evidence they are broken. Automatic CD status requires verification.

---

## EPIC-09 — Security, Access Controls & Backup/Recovery

**Suggested Issue title:** `[EPIC-09] Homelab Security and Data Recovery`  
**Labels:** `type/epic`, `area/security`, `priority/P1`  
**Target window:** 23 November – 4 December  
**Owner:** Alex (host/security), Misha (documentation and permitted tests)  
**Depends on:** EPIC-02, EPIC-08

### Objective

Keep the shared homelab secure and demonstrate a recovery procedure without making the student a host administrator.

### Scope

- Verify least-privilege Tailscale access for Misha to Forgejo and CityFlow endpoints, without Proxmox host/root privileges.
- Verify separate RustFS development bucket credentials and deny access to protected main storage.
- Document handling of `.env`, SSH keys, Forgejo tokens and runner secrets; do not post secrets to issues or CI logs.
- Add backup steps for Forgejo config/database/repositories, RustFS published objects and Dagster metadata as relevant.
- Perform a **real restore test into a disposable location/bucket** with checksum/row-count verification.
- Pin or document service versions and update process; avoid exposing administrative services publicly.

### Deliverables

- `docs/security.md`, `docs/backup-restore.md`, verified recovery evidence.
- Reviewed access matrix and a basic incident/recovery checklist.

### Acceptance criteria

- [ ] Misha can access permitted tools without broad `sudo` or Docker group membership.
- [ ] Student credentials cannot list/read the protected main bucket.
- [ ] Backups exist outside the working state and restoration is tested.
- [ ] Secrets do not appear in Git, logs, shared screenshots or documentation.
- [ ] The team can recover a test published dataset after deliberate deletion from a disposable target.

### Candidate child issues

Access matrix; bucket/IAM negative tests; secrets review; backup scripts; isolated restore exercise; operating procedures.

---

## EPIC-10 — Portability, Observability & Resource Efficiency

**Suggested Issue title:** `[EPIC-10] Portable Deployment, Observability and Performance`  
**Labels:** `type/epic`, `area/ops`, `priority/P1`  
**Target window:** 30 November – 4 December  
**Owner:** Misha with Alex support  
**Depends on:** EPIC-05, EPIC-06, EPIC-07

### Objective

Prove the same CityFlow code can run in a lightweight local mode and on Proxmox, and describe what would change in a cloud deployment.

### Scope

- Keep `compose.yaml` and deployment scripts in Git, with `*.example` configuration and persistent state outside the repository.
- Support a local profile where storage is filesystem-backed or S3-configured, without altering transformation/business logic.
- Document the Proxmox profile using shared RustFS and private Tailscale access.
- Define how a cloud S3 endpoint could be substituted via configuration; **a deployed Azure/AWS environment is optional**, not required for MVP.
- Measure approximate run duration, record throughput, memory use and data volume for one month.
- Provide useful pipeline/health metrics in logs or a lightweight summary. Optional Prometheus/Grafana only if spare resources/time permit.

### Deliverables

- Deployment profiles and README commands.
- `docs/architecture.md` with a simple architecture diagram.
- One benchmark/performance note and a portability demonstration.

### Acceptance criteria

- [ ] Source code is identical across local and Proxmox runs; environment config may vary.
- [ ] The student can explain filesystem vs object-store responsibilities and Parquet vs DuckDB vs dbt.
- [ ] Measured run times and peak resource figures are documented rather than guessed.
- [ ] Restarting services does not lose persisted RustFS data.
- [ ] Optional Grafana/Iceberg/cloud experiments do not block the final presentation.

### Candidate child issues

Compose profiles and reproducibility; storage backend selection; architecture diagram; benchmark and memory budget; lightweight observability; cloud portability note.

---

## EPIC-11 — Documentation, Release & University Defense

**Suggested Issue title:** `[EPIC-11] Final Documentation and University Presentation`  
**Labels:** `type/epic`, `area/docs`, `priority/P0`  
**Target window:** 30 November – **11 December**  
**Owner:** Misha, reviewed by Alex  
**Depends on:** EPIC-01 through EPIC-08 core deliverables

### Objective

Deliver an understandable, reproducible CityFlow project that Misha can confidently demonstrate and defend at university.

### Scope

- Maintain one clear README: what the platform does, architecture, stack, setup, demo procedure and limitations.
- Produce architecture and data-flow diagrams, data dictionary, KPI glossary, quality findings and tests summary.
- Prepare a deployment/runbook for local and Proxmox execution, including safe restart and failure recovery.
- Create a 10–15 minute university presentation explaining the original problem, solution, choices, architecture, data quality, transformations, BI findings and trade-offs.
- Record a 3–5 minute fallback demo or capture screenshots in case the homelab is unreachable during defense.
- Run at least two dry-runs with mentor feedback; freeze features by 4 December and reserve final week for fixes and rehearsal.

### Deliverables

- Completed project README and `docs/` documentation.
- Slides or presentation outline, demo checklist, screenshots/fallback recording.
- Final tested release/tag and a brief retrospective of student contributions.

### Acceptance criteria

- [ ] The project can be explained from data source to dashboard in one coherent walkthrough.
- [ ] A clean setup or prepared reproducible demo works using documented commands.
- [ ] Presentation uses real outputs and correctly states any performance/quality limitations.
- [ ] At least one complete demo succeeds without ad hoc administrator intervention.
- [ ] Fallback material is available offline.
- [ ] Misha can explain technical decisions and answer questions about S3, Parquet, Polars, DuckDB, dbt, Dagster, CI/CD and data quality.

### Candidate child issues

Architecture/README completion; technical report and KPI glossary; end-to-end acceptance demonstration; slide deck; backup demo; rehearsal and final release.

---

# Suggested delivery sequence and milestones

| Milestone | Target window | Main focus | Demo evidence |
|---|---|---|---|
| M1 — Foundation | 19–23 Oct | Finish EPIC-01, make progress on EPIC-02 | Polars profiler, RustFS adapter smoke test |
| M2 — Ingestion | 26–30 Oct | EPIC-02/03 | NYC TLC Parquet uploaded to Raw with manifest |
| M3 — Clean Data | 2–6 Nov | EPIC-03/04 | Bronze/Silver, visible quarantine and counts |
| M4 — Analytics | 9–13 Nov | EPIC-04/05 | Gold models and tested KPIs |
| M5 — Orchestration | 16–20 Nov | EPIC-05/06 | Dagster full run and repeatable results |
| M6 — Dashboard | 23–27 Nov | EPIC-06/07 | Interactive Streamlit dashboard |
| M7 — Hardening | 30 Nov–4 Dec | EPIC-08/09/10 | CI/CD, access/recovery tests, architecture; **feature freeze** |
| M8 — Defense | 7–11 Dec | EPIC-11 | End-to-end demo, final slides, rehearsal |

The roadmap is a **planning target**, not a claim that every item is still incomplete. Codex must check the actual current implementation, prioritize missing P0 work, and defer P2 work rather than overloading Misha.

## MVP release gate (must pass by the defense)

- [ ] January 2025 NYC TLC Parquet is downloaded, profiled and ingested reproducibly.
- [ ] RustFS S3 development access works with non-admin credentials.
- [ ] Raw → Bronze → Silver → Gold is implemented, tested and idempotent.
- [ ] At least three Gold marts produce correct, documented KPIs.
- [ ] Dagster triggers and logs an end-to-end run.
- [ ] Streamlit dashboard reads Gold and demonstrates meaningful insights.
- [ ] Forgejo CI passes; trusted/manual deployment path can be demonstrated safely.
- [ ] Documentation, restore procedure and presentation are ready.

## Format of the requested Codex output

Provide the result in this order:

1. **Inventory of existing work** — completed / in progress / not found (with evidence from repo/issues if accessible).
2. **Epic reconciliation** — which existing Forgejo issues to reuse and which new Epic issues to create.
3. **Prioritized child-issue backlog** — one copy/paste-ready Markdown block per proposed issue, grouped under `EPIC-XX` and containing all required fields.
4. **Dependency map** — explicit prerequisite issue references when known, or symbolic IDs when unknown.
5. **Week-by-week execution plan** — realistic student workload through 11 December.
6. **Risks and deferred stretch goals** — anything nonessential that could threaten the MVP.

**Do not:** generate an entire solution instead of issue descriptions; invent Forgejo issue numbers, service credentials or working CI/CD status; duplicate already-completed infrastructure setup; put secret values or downloaded Taxi Parquet files in issues or the repository; require Misha to have Docker/sudo permissions on the shared VM.

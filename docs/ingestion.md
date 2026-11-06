# Ingestion: configuration, execution, publication and reruns

`cityflow.ingestion` downloads one month of NYC TLC Yellow Taxi data,
validates it against the [raw data contract](raw_data_contract.md) and
publishes it to the Raw layer together with a `manifest.json`. This document
is the runbook: how to configure and run ingestion, how object keys are named,
how a publication is verified, and what happens when ingestion runs again for
the same month, including after a failure.


## 1. Configuration

The ingestion CLI reads its storage configuration from environment variables.
Copy `.env.example` to `.env` and fill in the S3 client values. `.env` is
ignored by Git; never commit it.

| Variable | Meaning | Example (development) |
|---|---|---|
| `S3_BUCKET` | bucket that holds the Raw layer | `cityflow-dev` |
| `S3_ENDPOINT_URL` | S3 API endpoint of RustFS | `http://127.0.0.1:9000` |
| `S3_ACCESS_KEY` | personal access key from the RustFS admin | (secret) |
| `S3_SECRET_KEY` | personal secret key from the RustFS admin | (secret) |

On the development VM, RustFS is reachable only through an SSH tunnel, so open
it before running ingestion (see the README, "Object storage (RustFS)"):

```
ssh -L 9000:127.0.0.1:9000 -L 9001:127.0.0.1:9001 <user>@cityflow-dev
```

`.env` is not loaded automatically; pass it with `--env-file`. The storage
adapter is the only code that builds an S3 client. A missing variable fails
the run at the `config` stage (section 5) before anything is downloaded.


## 2. Running ingestion

```
uv run --locked --env-file .env python -m cityflow.ingestion --month 2025-01
```

`--month` is required and has the form `YYYY-MM`. One run handles one month:

1. **download** the month's Parquet file from the official TLC source
   (`https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_<YYYY-MM>.parquet`)
   into a temporary directory. Server errors (5xx), transport errors, timeouts
   and incomplete downloads are retried, up to 3 attempts with 5 seconds
   between them; client errors (4xx) fail at once. A request times out after
   30 seconds (10 seconds to connect);
2. **validate** the file against the [raw data contract](raw_data_contract.md)
   (sections 2, 3 and 5): source URL, not empty, Parquet schema, decodable
   data pages and checksum baseline;
3. **publish** the file and its manifest to storage (section 6).

The temporary directory is removed when the run ends, so no downloaded dataset
is left on disk or committed to Git.

### Result and exit code

| Outcome | Meaning | Exit code |
|---|---|---|
| `published` | month was new (or an interrupted upload was redone) | 0 |
| `skipped` | month already published with the same SHA-256, nothing written | 0 |
| `recovered` | interrupted run completed from the object already in storage | 0 |
| any failure | the failed stage and reason are logged (section 5) | 1 |

An invalid `--month` is rejected by the argument parser, which prints a usage
message and exits with code 2 before any other work starts.


## 3. Object naming

All keys are deterministic: the same month always maps to the same keys, which
is what makes reruns safe.

```
raw/nyc_tlc/yellow_taxi/year=<YYYY>/month=<MM>/yellow_tripdata_<YYYY-MM>.parquet
raw/nyc_tlc/yellow_taxi/year=<YYYY>/month=<MM>/manifest.json
```

For January 2025:

```
raw/nyc_tlc/yellow_taxi/year=2025/month=01/yellow_tripdata_2025-01.parquet
raw/nyc_tlc/yellow_taxi/year=2025/month=01/manifest.json
```

The data object keeps the file name used by TLC, and the manifest sits beside
it in the same month folder. The manifest key is derived from the data object
key, so the two can never drift apart.


## 4. Manifest

Each month folder contains one `manifest.json` that records where the data came
from and exactly which bytes were published. A sanitized example for January
2025 is in [`examples/ingestion_manifest_2025-01.json`](examples/ingestion_manifest_2025-01.json):

```json
{
  "source_month": "2025-01",
  "source": "nyc_tlc_yellow",
  "url": "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-01.parquet",
  "bucket": "example-bucket",
  "object_key": "raw/nyc_tlc/yellow_taxi/year=2025/month=01/yellow_tripdata_2025-01.parquet",
  "sha256": "9af277e4c0d3f9deb30644da822981e1e7df6af58313170fd3aa8a474485488a",
  "size_bytes": 59158238,
  "ingested_at": "2025-01-01T12:00:00+00:00",
  "contract_version": 1,
  "publication_status": "published"
}
```

| Field | Meaning |
|---|---|
| `source_month` | month of the trip data, `YYYY-MM` |
| `source` | source identifier, `nyc_tlc_yellow` |
| `url` | official source URL the file was downloaded from (lineage) |
| `bucket`, `object_key` | where the data object is published |
| `sha256`, `size_bytes` | checksum and size of the published bytes |
| `ingested_at` | UTC timestamp of the ingestion run |
| `contract_version` | version of the raw data contract the file was checked against |
| `publication_status` | `pending` until the upload is verified, then `published` |

The example is sanitized: the bucket is a placeholder, the timestamp is
illustrative, and the manifest holds no credentials or endpoint addresses. The
SHA-256 and size are those of the public January 2025 source file, also
recorded in [`source_manifest.json`](source_manifest.json).


## 5. Failures and diagnostics

Any failure ends the run with exit code 1 and a log line that names the month,
the failed stage and the reason:

```
ERROR cityflow.ingestion: Ingestion of 2025-01 failed at stage validate: <reason>
```

| Stage | What failed | Typical cause |
|---|---|---|
| `config` | a required environment variable is missing | `.env` not passed with `--env-file`, or a variable left out |
| `download` | the source could not be fetched completely | network error, 4xx/5xx from the source, truncated transfer after all retries |
| `validate` | the file breaks the raw data contract | invalid Parquet, missing required columns, incompatible types, checksum differs from the baseline, empty file |
| `publish` | storage or manifest handling failed | storage unreachable (tunnel closed), upload or manifest write error, checksum conflict with published data (section 7) |

If the SSH tunnel is closed, the `publish` failure does not appear at once: the
storage client waits for its own timeouts first, so the error can take tens of
seconds to show. Open the tunnel and run ingestion again.

Credentials are never logged: only the variable *name* is reported for a missing
setting. A file that fails any validation check is never uploaded, and a failed
run never overwrites a `published` object or manifest, so the published dataset
is not corrupted by a failure.


## 6. Publication steps

A file is published only after every contract check has passed. A file that
fails validation never reaches storage.

For a month with no manifest yet, `publish_raw_file` runs these steps in order:

1. Write `manifest.json` with `publication_status: "pending"`.
2. Upload the Parquet file to its Raw object key.
3. Verify the uploaded object (section 6.1).
4. Rewrite `manifest.json` with `publication_status: "published"`.

`published` is written only after the upload and the verification have both
succeeded, so a `published` manifest always describes bytes that are really in
storage.

### 6.1 How the uploaded bytes are verified

After the upload, the object is downloaded back from storage into a temporary
`<file name>.verify` file in the work directory. Its SHA-256 is computed and
compared with the SHA-256 of the local file that was validated. The temporary
file is always removed, also when the check fails.

- If the hashes match, the publication is complete.
- If they differ, ingestion fails with `PublicationError` and the manifest
  stays `pending`.

The S3 ETag is not used for this check. An ETag is not a SHA-256: for a simple
upload it is usually an MD5 of the content, for a multipart upload it is
derived from the parts and is not a hash of the whole file at all, and with
some server-side encryption modes it is not a content hash. Comparing the
SHA-256 of the downloaded bytes is slower, but it checks exactly the bytes a
reader of the Raw layer will get.


## 7. Reruns

Running ingestion again for the same month is safe. Before publishing, the
existing manifest is read and decides what happens:

| Existing manifest | Action | Result |
|---|---|---|
| none | publish (section 6) | `published` |
| `published`, same SHA-256 | nothing is written | `skipped` |
| `published`, different SHA-256 | nothing is written, ingestion fails | `PublicationError` |
| `pending` | verify the existing object, then complete or publish again (section 8) | `recovered` or `published` |

A second run with the same file therefore leaves exactly one data object and
one manifest for the month and reports `skipped`.

### Checksum conflict

A different SHA-256 for an already published month means the source file
changed or a different file was downloaded. Ingestion does not overwrite
published data automatically: the existing object and manifest are kept as they
are, and the error names the object key and both checksums. Which version is
correct is decided by manual review.


## 8. Recovery after an interrupted run

A `pending` manifest means a previous run stopped after step 1 and before
step 4. The next run verifies the object in storage against the local file
before it changes anything.

| What failed in the previous run | State in storage | What the rerun does | Result |
|---|---|---|---|
| upload (step 2), e.g. a network or storage error | manifest `pending`, object missing or incomplete | verification fails, so steps 1–4 run again and the upload overwrites the object | `published` |
| verification (step 3) | manifest `pending`, object with wrong bytes | same as above | `published` |
| final manifest write (step 4) | manifest `pending`, complete object | verification passes, so only a new `published` manifest is written; the object is not uploaded again | `recovered` |

Overwriting a `pending` object is safe because it was never marked
`published`, so no reader may rely on it. The recovered manifest is built from
the current run, so it describes exactly the bytes that were just verified.

No manual steps are needed for recovery: fix the cause of the failure, then run
ingestion for the same month again.

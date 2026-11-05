# Ingestion: publication, verification and reruns

`cityflow.ingestion` downloads one month of NYC TLC Yellow Taxi data,
validates it against the [raw data contract](raw_data_contract.md) and
publishes it to the Raw layer together with a `manifest.json`. This document
explains how a publication is verified and what happens when ingestion runs
again for the same month, including after a failure.


## 1. Publication steps

A file is published only after every contract check has passed. A file that
fails validation never reaches storage.

For a month with no manifest yet, `publish_raw_file` runs these steps in order:

1. Write `manifest.json` with `publication_status: "pending"`.
2. Upload the Parquet file to its Raw object key.
3. Verify the uploaded object (section 2).
4. Rewrite `manifest.json` with `publication_status: "published"`.

The manifest is stored beside the data object, in the same month folder:

```
raw/nyc_tlc/yellow_taxi/year=2025/month=01/yellow_tripdata_2025-01.parquet
raw/nyc_tlc/yellow_taxi/year=2025/month=01/manifest.json
```

It records the source month, source URL, bucket, object key, SHA-256, size in
bytes, UTC ingestion timestamp, contract version and publication status.
`published` is written only after the upload and the verification have both
succeeded, so a `published` manifest always describes bytes that are really in
storage.


## 2. How the uploaded bytes are verified

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


## 3. Reruns

Running ingestion again for the same month is safe. Before publishing, the
existing manifest is read and decides what happens:

| Existing manifest | Action | Result |
|---|---|---|
| none | publish (section 1) | `published` |
| `published`, same SHA-256 | nothing is written | `skipped` |
| `published`, different SHA-256 | nothing is written, ingestion fails | `PublicationError` |
| `pending` | verify the existing object, then complete or publish again (section 4) | `recovered` or `published` |

A second run with the same file therefore leaves exactly one data object and
one manifest for the month and reports `skipped`.

### Checksum conflict

A different SHA-256 for an already published month means the source file
changed or a different file was downloaded. Ingestion does not overwrite
published data automatically: the existing object and manifest are kept as they
are, and the error names the object key and both checksums. Which version is
correct is decided by manual review.


## 4. Recovery after an interrupted run

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

import hashlib
import json
from datetime import UTC, datetime

import pytest

from cityflow import build_manifest


@pytest.mark.parametrize("content", [b"", b"abc", b"abcdefghijk"])
def test_sha256_handles_empty_single_and_multiple_chunks(tmp_path, monkeypatch, content):
    source = tmp_path / "source.parquet"
    source.write_bytes(content)
    monkeypatch.setattr(build_manifest, "CHUNK_SIZE", 4)

    assert build_manifest.sha256_of(source) == hashlib.sha256(content).hexdigest()


def test_sha256_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_manifest.sha256_of(tmp_path / "missing.parquet")


def test_manifest_records_source_metadata(tmp_path):
    source = tmp_path / "source.parquet"
    source.write_bytes(b"abc")
    before = datetime.now(UTC)

    manifest = build_manifest.build_manifest(source, "2025-02")

    after = datetime.now(UTC)
    created_at = datetime.fromisoformat(manifest.pop("manifest_created_at"))
    assert created_at.utcoffset().total_seconds() == 0
    assert before <= created_at <= after
    assert manifest == {
        "source": "nyc_tlc_yellow",
        "source_month": "2025-02",
        "url": "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2025-02.parquet",
        "size_bytes": 3,
        "sha256": "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
    }


def test_manifest_missing_source_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        build_manifest.build_manifest(tmp_path / "missing.parquet", "2025-01")


def test_main_creates_directory_and_writes_json(tmp_path, monkeypatch):
    source = tmp_path / "source.parquet"
    source.write_bytes(b"abc")
    destination = tmp_path / "docs" / "manifest.json"
    monkeypatch.setattr(build_manifest, "RAW_FILE", source)
    monkeypatch.setattr(build_manifest, "MANIFEST_FILE", destination)

    build_manifest.main()
    manifest = json.loads(destination.read_text(encoding="utf-8"))

    assert manifest["source_month"] == "2025-01"
    assert manifest["size_bytes"] == 3
    assert manifest["sha256"] == hashlib.sha256(b"abc").hexdigest()
    # Running again must also work when the output directory already exists.
    build_manifest.main()
    assert json.loads(destination.read_text(encoding="utf-8"))["sha256"] == manifest["sha256"]

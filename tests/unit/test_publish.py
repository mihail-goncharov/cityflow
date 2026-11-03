
import pytest

from cityflow.build_manifest import sha256_of
from cityflow.ingestion.publish import PublicationError, verify_remote_object

CONTENT = b"Content"
KEY = "test-key"





def test_verify_remote_object_matches(adapter, tmp_path, tmp_file):
    tmp_file.write_bytes(CONTENT)
    expected_hash = sha256_of(tmp_file)

    adapter.upload_object(tmp_file, KEY)
    verify_remote_object(adapter, KEY, expected_hash, tmp_path)

    assert list(tmp_path.glob("*.verify")) == []


def test_verify_remote_object_mismatched_hash_raises_publication_error(adapter, tmp_path, tmp_file):
    tmp_file.write_bytes(CONTENT)
    wrong_hash = "0" * 64

    adapter.upload_object(tmp_file, KEY)

    with pytest.raises(PublicationError):
        verify_remote_object(adapter, KEY, wrong_hash, tmp_path)

    assert list(tmp_path.glob("*.verify")) == []


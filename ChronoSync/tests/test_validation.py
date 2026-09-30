import hashlib

import pytest

from core.validation import file_hash


def test_file_hash_matches_expected_sha256(tmp_path):
    sample = tmp_path / "sample.txt"
    payload = b"hello world\n"
    sample.write_bytes(payload)

    expected = hashlib.sha256(payload).hexdigest()

    assert file_hash(str(sample)) == expected
    assert len(file_hash(str(sample))) == 64


def test_file_hash_supports_custom_algorithm(tmp_path):
    sample = tmp_path / "sample.bin"
    sample.write_bytes(b"abc123")

    expected = hashlib.new("md5", b"abc123").hexdigest()

    assert file_hash(str(sample), algo="md5") == expected


def test_file_hash_raises_for_missing_file(tmp_path):
    missing = tmp_path / "missing.txt"

    with pytest.raises(FileNotFoundError):
        file_hash(str(missing))

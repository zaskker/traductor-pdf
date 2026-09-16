import os
import tempfile

import pytest

from src.infrastructure.pdf.fingerprint import FingerprintService


def test_fingerprint_generation():
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"Hello PDF")
        tmp_name = f.name

    try:
        hash_val, size_val = FingerprintService.get_fingerprint(tmp_name)

        # Mismo archivo, mismo hash
        hash_val2, size_val2 = FingerprintService.get_fingerprint(tmp_name)

        assert hash_val == hash_val2
        assert size_val == size_val2
        assert size_val == 9

        # Archivo modificado, hash distinto
        with open(tmp_name, "ab") as f:
            f.write(b" Extra")

        hash_val3, size_val3 = FingerprintService.get_fingerprint(tmp_name)
        assert hash_val != hash_val3
        assert size_val3 == 15
    finally:
        os.remove(tmp_name)


def test_fingerprint_file_not_found():
    with pytest.raises(FileNotFoundError):
        FingerprintService.get_fingerprint("non_existent_file.pdf")

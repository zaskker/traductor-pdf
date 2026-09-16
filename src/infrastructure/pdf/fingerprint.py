import hashlib
import os


class FingerprintService:
    @staticmethod
    def get_fingerprint(file_path: str) -> tuple[str, int]:
        """Devuelve una tupla (sha256, file_size) del archivo."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"El archivo {file_path} no existe.")

        file_size = os.path.getsize(file_path)

        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for byte_block in iter(lambda: f.read(4096), b""):
                sha256_hash.update(byte_block)

        return sha256_hash.hexdigest(), file_size

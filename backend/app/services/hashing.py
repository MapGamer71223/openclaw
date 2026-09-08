"""Cryptographic evidence hashing. Never modifies the source file."""
import hashlib
from pathlib import Path


def calculate_sha256(file_path: Path, chunk_size: int = 1024 * 1024) -> str:
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            sha256.update(chunk)
    return sha256.hexdigest()


def file_size_bytes(file_path: Path) -> int:
    return file_path.stat().st_size

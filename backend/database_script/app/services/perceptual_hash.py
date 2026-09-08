"""
Perceptual hashing (pHash / dHash / aHash) for similarity comparison.

IMPORTANT: perceptual similarity establishes that two media items are
visually related. It does NOT by itself prove which one is the origin,
and it is never presented to the user as ownership/origin proof.
"""
from pathlib import Path

import imagehash
from PIL import Image


def compute_hashes(path: Path) -> dict:
    with Image.open(path) as im:
        im = im.convert("RGB")
        hashes = {
            "phash": str(imagehash.phash(im)),
            "dhash": str(imagehash.dhash(im)),
            "ahash": str(imagehash.average_hash(im)),
        }
        try:
            # wHash (wavelet hash) needs PyWavelets; degrade gracefully if
            # it's not installed rather than failing the whole pipeline.
            hashes["whash"] = str(imagehash.whash(im))
        except Exception:
            hashes["whash"] = None
        return hashes


def hamming_distance(hash_a: str, hash_b: str) -> int:
    return imagehash.hex_to_hash(hash_a) - imagehash.hex_to_hash(hash_b)


def similarity_score(hash_a: str, hash_b: str, hash_bits: int = 64) -> float:
    """Converts Hamming distance to a 0..1 similarity score."""
    dist = hamming_distance(hash_a, hash_b)
    return round(max(0.0, 1.0 - (dist / hash_bits)), 4)


def classify_match(distance: int) -> str:
    """Categorizes similarity per the platform's evidence taxonomy."""
    if distance == 0:
        return "exact"
    if distance <= 4:
        return "near_identical"
    if distance <= 10:
        return "modified_copy"
    if distance <= 18:
        return "possibly_related"
    return "unrelated"

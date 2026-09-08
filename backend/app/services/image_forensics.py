"""
Image forensic signal extraction.

Every function here returns an *indicator*, not a verdict. Scores are on a
0..1 scale where higher generally means "more anomalous", but none of these
signals alone proves manipulation -- they are combined (see ai_detection.py)
into a demo/heuristic score that is clearly labeled as such.
"""
from pathlib import Path
from typing import Any, Dict, Tuple

import numpy as np
from PIL import Image, ImageChops


def error_level_analysis(src_path: Path, out_path: Path, quality: int = 90, scale: int = 15) -> float:
    """
    Recompresses the image at a known JPEG quality and diffs it against the
    original. Regions that were edited/composited after the original save
    tend to show a different error level than the rest of the image.
    Returns a normalized anomaly score 0..1 and writes a visualization PNG.
    """
    im = Image.open(src_path).convert("RGB")
    tmp_path = out_path.with_suffix(".tmp.jpg")
    im.save(tmp_path, "JPEG", quality=quality)
    resaved = Image.open(tmp_path).convert("RGB")

    diff = ImageChops.difference(im, resaved)
    diff_arr = np.asarray(diff).astype(np.float32)

    # amplify for visualization
    amplified = np.clip(diff_arr * scale, 0, 255).astype(np.uint8)
    Image.fromarray(amplified).save(out_path, "PNG")
    tmp_path.unlink(missing_ok=True)

    # Anomaly score: ratio of high-error pixels to total, normalized.
    magnitude = diff_arr.mean(axis=2)
    threshold = magnitude.mean() + 2 * magnitude.std() if magnitude.std() > 0 else magnitude.mean()
    high_error_ratio = float((magnitude > threshold).mean()) if threshold > 0 else 0.0
    score = min(1.0, high_error_ratio * 8)  # empirically scaled for demo purposes
    return round(score, 4)


def noise_analysis(path: Path) -> float:
    """
    Estimates local noise-pattern consistency by comparing the noise
    variance of non-overlapping tiles. Real camera sensor noise is fairly
    uniform; splicing/AI-generation often introduces regions with
    inconsistent noise floors.
    """
    im = np.asarray(Image.open(path).convert("L")).astype(np.float32)
    h, w = im.shape
    tile = 32
    variances = []
    for y in range(0, h - tile, tile):
        for x in range(0, w - tile, tile):
            block = im[y:y + tile, x:x + tile]
            # high-pass via simple Laplacian-like kernel to isolate noise
            lap = (
                -4 * block[1:-1, 1:-1]
                + block[:-2, 1:-1] + block[2:, 1:-1]
                + block[1:-1, :-2] + block[1:-1, 2:]
            )
            variances.append(float(np.var(lap)))
    if len(variances) < 4:
        return 0.0
    variances = np.array(variances)
    # Coefficient of variation of tile noise -- higher = more inconsistent
    mean_v = variances.mean()
    if mean_v == 0:
        return 0.0
    cv = variances.std() / mean_v
    score = min(1.0, cv / 3.0)  # empirical normalization for demo purposes
    return round(float(score), 4)


def resampling_analysis(path: Path) -> float:
    """
    Looks for periodic interpolation artifacts characteristic of
    resizing/resampling, via the variance of the second-derivative
    (Laplacian) energy spectrum. A crude but real signal-processing proxy.

    IMPORTANT: a high score here means "this image shows interpolation/
    resampling characteristics" -- it does NOT mean "this image is
    AI-generated or AI-altered". Legitimate smartphone computational
    photography pipelines (resizing, demosaicing, sharpening, denoising,
    HDR merging, lens correction) routinely produce exactly these
    characteristics on genuine, unedited camera photos. This signal must
    only ever be surfaced as a forensic indicator alongside other evidence,
    never combined into an "AI probability" on its own (see
    app.services.ai_detection and app.services.confidence).
    """
    im = np.asarray(Image.open(path).convert("L")).astype(np.float32)
    # second difference along both axes
    d2x = np.diff(im, n=2, axis=1)
    d2y = np.diff(im, n=2, axis=0)
    energy = np.abs(d2x).mean() + np.abs(d2y).mean()
    # FFT peak-to-mean ratio as periodicity indicator
    f = np.fft.fft2(im - im.mean())
    mag = np.abs(np.fft.fftshift(f))
    mag[mag.shape[0] // 2, mag.shape[1] // 2] = 0  # remove DC
    peak_ratio = float(mag.max() / (mag.mean() + 1e-6))
    score = min(1.0, (peak_ratio / 4000) + (energy / 200))
    return round(score, 4)


def compression_analysis(path: Path) -> Dict[str, Any]:
    """Inspects JPEG quantization / re-save characteristics where possible."""
    im = Image.open(path)
    notes: Dict[str, Any] = {
        "format": im.format,
        "mode": im.mode,
    }
    try:
        quantization = getattr(im, "quantization", None)
        if quantization:
            notes["quantization_tables"] = {str(k): list(v) for k, v in quantization.items()}
            # A very smooth/low table can indicate a single high-quality
            # save; multiple divergent tables across channels can indicate
            # recompression / editing history.
            table_means = [float(np.mean(v)) for v in quantization.values()]
            notes["quantization_table_means"] = table_means
        else:
            notes["quantization_tables"] = None
    except Exception:
        notes["quantization_tables"] = None
    notes["jpeg_layers"] = getattr(im, "layer", None) is not None
    return notes


def image_dimensions(path: Path) -> Tuple[int, int]:
    with Image.open(path) as im:
        return im.size

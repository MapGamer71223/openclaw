"""
Video forensics: extracts sampled frames (not every frame -- see
config.VIDEO_FRAME_SAMPLE_SECONDS / VIDEO_MAX_FRAMES) and reuses the image
forensic pipeline on each sampled frame.
"""
import subprocess
from pathlib import Path
from typing import Any, Dict, List

from app.config import settings
from app.services import image_forensics


def extract_frames(video_path: Path, out_dir: Path, duration: float | None) -> List[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    interval = settings.VIDEO_FRAME_SAMPLE_SECONDS
    max_frames = settings.VIDEO_MAX_FRAMES

    if duration and duration > 0:
        n_frames = min(max_frames, max(1, int(duration // interval)))
        fps_expr = f"1/{interval}"
    else:
        n_frames = max_frames
        fps_expr = "1/2"

    pattern = str(out_dir / "frame_%03d.jpg")
    cmd = [
        "ffmpeg", "-y", "-i", str(video_path),
        "-vf", f"fps={fps_expr}",
        "-frames:v", str(n_frames),
        "-q:v", "3",
        pattern,
    ]
    try:
        subprocess.run(cmd, capture_output=True, timeout=60, check=True)
    except Exception:
        return []
    return sorted(out_dir.glob("frame_*.jpg"))


def analyze_frames(frames: List[Path], ela_out_dir: Path) -> Dict[str, Any]:
    ela_out_dir.mkdir(parents=True, exist_ok=True)
    per_frame = []
    suspicious_frames = []
    for idx, frame in enumerate(frames):
        ela_path = ela_out_dir / f"ela_frame_{idx:03d}.png"
        try:
            ela_score = image_forensics.error_level_analysis(frame, ela_path)
            noise_score = image_forensics.noise_analysis(frame)
            resample_score = image_forensics.resampling_analysis(frame)
        except Exception:
            ela_score = noise_score = resample_score = 0.0
        composite = round((ela_score + noise_score + resample_score) / 3, 4)
        per_frame.append({
            "frame_index": idx,
            "file": frame.name,
            "ela_score": ela_score,
            "noise_score": noise_score,
            "resampling_score": resample_score,
            "composite_score": composite,
        })
        if composite > 0.45:
            suspicious_frames.append(idx)

    return {
        "frames_analyzed": len(frames),
        "per_frame": per_frame,
        "suspicious_frames": suspicious_frames,
    }

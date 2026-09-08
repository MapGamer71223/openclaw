"""
Metadata extraction.

Images: uses Pillow's EXIF reader (exiftool is not assumed to be installed;
if it is present on PATH we use it for a richer extraction).
Video: uses ffprobe (bundled with ffmpeg).

GPS coordinates are detected but never returned verbatim to the public
report payload -- only a boolean `gps_present` flag is exposed by default.
"""
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PIL import Image
from PIL.ExifTags import TAGS, GPSTAGS

EXIFTOOL_AVAILABLE = shutil.which("exiftool") is not None
FFPROBE_AVAILABLE = shutil.which("ffprobe") is not None


def _decode_exif(img: Image.Image) -> Dict[str, Any]:
    raw = img._getexif() if hasattr(img, "_getexif") else None
    if not raw:
        return {}
    out: Dict[str, Any] = {}
    gps: Dict[str, Any] = {}
    for tag_id, value in raw.items():
        tag = TAGS.get(tag_id, tag_id)
        if tag == "GPSInfo" and isinstance(value, dict):
            for gps_id, gps_val in value.items():
                gps_tag = GPSTAGS.get(gps_id, gps_id)
                gps[str(gps_tag)] = _safe(gps_val)
            continue
        out[str(tag)] = _safe(value)
    if gps:
        out["GPSInfo"] = gps
    return out


def _safe(value: Any) -> Any:
    """Make EXIF values JSON-serializable."""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")
        except Exception:
            return repr(value)
    if isinstance(value, (tuple, list)):
        return [_safe(v) for v in value]
    try:
        json.dumps(value)
        return value
    except TypeError:
        return str(value)


def extract_image_metadata(path: Path) -> Tuple[Dict[str, Any], bool, Optional[int], Optional[int]]:
    """Returns (metadata_dict, gps_present, width, height)."""
    if EXIFTOOL_AVAILABLE:
        try:
            proc = subprocess.run(
                ["exiftool", "-j", "-G", str(path)],
                capture_output=True, text=True, timeout=15, check=True,
            )
            data = json.loads(proc.stdout)[0]
            gps_present = any("GPS" in k for k in data.keys())
            with Image.open(path) as im:
                w, h = im.size
            return data, gps_present, w, h
        except Exception:
            pass  # fall through to Pillow

    with Image.open(path) as im:
        w, h = im.size
        exif = _decode_exif(im)
        metadata = {
            "Format": im.format,
            "Mode": im.mode,
            "ColorProfile": im.info.get("icc_profile") is not None,
            "EXIF": exif,
        }
        gps_present = "GPSInfo" in exif and bool(exif["GPSInfo"])
        return metadata, gps_present, w, h


def extract_video_metadata(path: Path) -> Dict[str, Any]:
    if not FFPROBE_AVAILABLE:
        return {"error": "ffprobe not available on this system", "duration": None}
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", str(path),
            ],
            capture_output=True, text=True, timeout=30, check=True,
        )
        data = json.loads(proc.stdout)
        video_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), {})
        audio_stream = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), {})
        fmt = data.get("format", {})

        fps = None
        if video_stream.get("avg_frame_rate") and video_stream["avg_frame_rate"] != "0/0":
            num, _, den = video_stream["avg_frame_rate"].partition("/")
            try:
                fps = round(int(num) / int(den), 2) if int(den) else None
            except (ValueError, ZeroDivisionError):
                fps = None

        return {
            "duration": float(fmt.get("duration", 0)) if fmt.get("duration") else None,
            "codec": video_stream.get("codec_name"),
            "width": video_stream.get("width"),
            "height": video_stream.get("height"),
            "fps": fps,
            "bitrate": int(fmt.get("bit_rate")) if fmt.get("bit_rate") else None,
            "audio_codec": audio_stream.get("codec_name"),
            "container": fmt.get("format_name"),
            "creation_time": fmt.get("tags", {}).get("creation_time"),
            "raw_format_tags": fmt.get("tags", {}),
        }
    except Exception as e:
        return {"error": str(e), "duration": None}

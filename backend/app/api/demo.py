"""
Demo-mode seeding.

Generates a synthetic sample image with a deliberately spliced region (so
ELA/noise/resampling signals have something real to detect), then runs it
through the ACTUAL pipeline end-to-end -- hashing, metadata, AI detection,
forensics, OSINT (demo provider), source verification, propagation, and
report generation. Nothing about the pipeline itself is faked; only the
OSINT layer uses the DemoSourceProvider, which is clearly labeled
`is_demo: true` on every returned source.
"""
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends
from PIL import Image
from sqlalchemy.orm import Session

from app.config import EVIDENCE_DIR, DEMO_DIR, settings
from app.database import get_db
from app.models.investigation import Investigation, MediaAsset
from app.services import orchestrator
from app.services.image_forensics import image_dimensions

router = APIRouter(prefix="/api/demo", tags=["demo"])


def _make_sample_image(path: Path):
    """Builds a deterministic base image with a resampled/recompressed patch spliced in."""
    rng = np.random.default_rng(42)
    base = rng.integers(80, 180, (600, 900, 3), dtype=np.uint8)
    # smooth it a bit to look more photographic
    img = Image.fromarray(base).filter(
        __import__("PIL.ImageFilter", fromlist=["GaussianBlur"]).GaussianBlur(3)
    )
    arr = np.asarray(img).copy()

    # splice a resized/re-compressed patch into a region -- introduces the
    # noise/resampling inconsistency the forensic pipeline is built to catch
    patch = Image.fromarray(rng.integers(150, 255, (140, 220, 3), dtype=np.uint8))
    patch = patch.resize((300, 180), Image.BICUBIC)  # resampling artifact
    arr[220:400, 300:600] = np.asarray(patch)

    Image.fromarray(arr).save(path, "JPEG", quality=88)


@router.post("/seed")
def seed_demo_investigation(db: Session = Depends(get_db)):
    inv = Investigation(state="UPLOADED", media_type="image", original_filename="demo_sample_media.jpg", demo_mode=True)
    db.add(inv)
    db.commit()
    db.refresh(inv)

    evidence_dir = Path(EVIDENCE_DIR) / inv.id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    dest_path = evidence_dir / "original.jpg"
    _make_sample_image(dest_path)

    width, height = image_dimensions(dest_path)
    asset = MediaAsset(
        investigation_id=inv.id, original_path=str(dest_path), sha256="",
        size_bytes=dest_path.stat().st_size, mime_type="image/jpeg", width=width, height=height,
    )
    db.add(asset)
    db.commit()

    orchestrator.log_event(db, inv, "evidence-agent", "Demo evidence generated and stored.", stage="UPLOADED")
    orchestrator.run_investigation(db, inv.id)
    db.refresh(inv)
    return inv

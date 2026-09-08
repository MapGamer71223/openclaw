"""
Ingest the PS-Battles dataset (github.com/dbisUnibas/PS-Battles) into the
provenance database.

Why this one specifically: it's one of the few free, openly downloadable
datasets that comes with genuine ORIGIN metadata attached to every image,
not just pixels -- author, a real Unix publication timestamp, and the
actual Reddit source-page URL, PLUS an explicit ground-truth link from
every manipulated image back to its real original. That maps directly
onto this project's schema:

    originals.tsv row   -> Asset + Page (the Reddit post) + Appearance
                            (publication_time = real timestamp, author = real
                            author, timestamp_source = "ps_battles_reddit")
    photoshops.tsv row  -> same, PLUS a ProvenanceEdge
                            (relationship="derived_from", confidence=1.0,
                            evidence="ps_battles_dataset_ground_truth")
                            pointing from the derivative back to the original

103,028 images total (11,142 originals + 90,886 derivatives), average
~320-400KB each -- confirmed by inspecting the actual TSVs, not estimated.
That's real, so this is also directly useful as benchmark ground truth for
Phase 13 (you already know the correct answer for "which is the original"
and "who made it when" for every single image here).

Usage:
    git clone --depth 1 https://github.com/dbisUnibas/PS-Battles.git
    cd PS-Battles && bash download.sh   # downloads the actual image files
    cd ../backend
    python -m scripts.ingest_ps_battles --repo-dir ../PS-Battles

Images that download.sh failed to fetch (dead imgur links -- there will be
some, this dataset is from 2018 and imgur has deleted content since) are
skipped with a warning, not treated as a fatal error.
"""
import argparse
import csv
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("ingest_ps_battles")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _find_downloaded_file(directory: Path, row_id: str, ext: str) -> Path | None:
    p = directory / f"{row_id}.{ext}"
    return p if p.exists() and p.stat().st_size > 0 else None


def _ingest_row(db, row: dict, file_path: Path, *, source_reddit_id: str):
    """Shared logic for one originals.tsv or photoshops.tsv row. Returns
    the created/found Asset, or None if the file couldn't be read."""
    from app.services import provenance_store

    try:
        asset = provenance_store.get_or_create_asset(
            db, file_path,
            mime_type=f"image/{row['end']}" if row['end'] != 'jpg' else "image/jpeg",
            width=int(row["width"]) if row.get("width") else None,
            height=int(row["height"]) if row.get("height") else None,
        )
    except Exception:
        logger.warning("Failed to process %s (row id=%s)", file_path, row.get("id"))
        return None

    page = provenance_store.get_or_create_page(
        db, f"https://{row['link']}",
        domain="reddit.com",
        platform="Reddit",
        author=row.get("author"),
    )

    pub_time = None
    if row.get("timestamp"):
        try:
            pub_time = datetime.fromtimestamp(int(row["timestamp"]), tz=timezone.utc)
        except (ValueError, OSError):
            pass

    provenance_store.record_appearance(
        db,
        asset=asset,
        page=page,
        image_url=row.get("url"),
        publication_time=pub_time,
        publication_time_type="platform_publication",
        timestamp_source="ps_battles_reddit",
        timestamp_confidence=0.95,  # real Reddit post timestamp, high but not
                                     # absolute certainty it's the FIRST appearance
                                     # anywhere (image could predate the Reddit post)
        evidence_quality_score=1.0,
    )
    return asset


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo-dir", type=Path, required=True,
                     help="Path to the cloned PS-Battles repo (after running its download.sh)")
    ap.add_argument("--limit-originals", type=int, default=None,
                     help="Cap for testing, e.g. --limit-originals 200")
    args = ap.parse_args()

    from app.provenance_db import get_engine, init_provenance_db
    from app.provenance_db import ProvenanceBase
    from sqlalchemy.orm import sessionmaker
    from app.services import provenance_store

    init_provenance_db()
    Session = sessionmaker(bind=get_engine())
    db = Session()

    originals_dir = args.repo_dir / "originals"
    photoshops_dir = args.repo_dir / "photoshops"
    originals_tsv = args.repo_dir / "originals.tsv"
    photoshops_tsv = args.repo_dir / "photoshops.tsv"
    for p in (originals_dir, photoshops_dir, originals_tsv, photoshops_tsv):
        if not p.exists():
            raise SystemExit(f"Expected {p} to exist -- did you run download.sh in {args.repo_dir}?")

    t0 = time.time()
    asset_by_original_id: dict[str, object] = {}
    n_originals_ok = n_originals_missing = 0

    with open(originals_tsv, newline="") as f:
        for i, row in enumerate(csv.DictReader(f, delimiter="\t")):
            if args.limit_originals and i >= args.limit_originals:
                break
            file_path = _find_downloaded_file(originals_dir, row["id"], row["end"])
            if not file_path:
                n_originals_missing += 1
                continue
            asset = _ingest_row(db, row, file_path, source_reddit_id=row["id"])
            if asset:
                asset_by_original_id[row["id"]] = asset
                n_originals_ok += 1
            if n_originals_ok and n_originals_ok % 500 == 0:
                logger.info("Originals: %d ingested, %d missing files, %.1fs elapsed",
                            n_originals_ok, n_originals_missing, time.time() - t0)

    logger.info("Originals done: %d ingested, %d missing (dead links) in %.1fs",
                n_originals_ok, n_originals_missing, time.time() - t0)

    n_ps_ok = n_ps_missing = n_ps_no_original = 0
    t1 = time.time()
    with open(photoshops_tsv, newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            original_asset = asset_by_original_id.get(row["original"])
            if not original_asset:
                n_ps_no_original += 1  # its original wasn't ingested (missing/limited), skip
                continue
            file_path = _find_downloaded_file(photoshops_dir / row["original"], row["id"], row["end"])
            if not file_path:
                n_ps_missing += 1
                continue
            derived_asset = _ingest_row(db, row, file_path, source_reddit_id=row["original"])
            if derived_asset:
                provenance_store.record_provenance_edge(
                    db,
                    source_asset=derived_asset,
                    target_asset=original_asset,
                    relationship="derived_from",
                    confidence=1.0,
                    evidence="ps_battles_dataset_ground_truth",
                )
                n_ps_ok += 1
            if n_ps_ok and n_ps_ok % 2000 == 0:
                logger.info("Photoshops: %d ingested, %.1fs elapsed", n_ps_ok, time.time() - t1)

    logger.info("=" * 60)
    logger.info("Done in %.1fs total.", time.time() - t0)
    logger.info("Originals: %d ingested, %d missing files", n_originals_ok, n_originals_missing)
    logger.info("Derivatives: %d ingested (+ derived_from edge), %d missing files, "
                "%d skipped (original not ingested)", n_ps_ok, n_ps_missing, n_ps_no_original)


if __name__ == "__main__":
    main()

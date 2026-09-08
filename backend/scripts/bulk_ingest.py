"""
Bulk-seed the provenance database with a large local/downloaded image
collection (up to ~1M+ images).

IMPORTANT -- read before pointing this at "1 million images":

The free discovery sources already wired in (DDGSourceProvider,
PicImageSearchProvider, MrisaSourceProvider) are per-investigation OSINT
tools with real per-query rate limits -- looping them a million times will
get your IP rate-limited/blocked long before you get anywhere close, and
that's not what they're for. This script is for the free path that
actually scales to bulk volume: your own already-downloaded image folder,
or a bulk manifest of image URLs from a dataset meant for bulk/research
download (e.g. Open Images' published image-URL CSVs). It does NOT call
any search engine.

Two input modes:
  --source-dir  /path/to/local/images     (recursive, no network needed)
  --url-list    /path/to/urls.txt         (one image URL per line, downloaded
                                            with bounded concurrency)

What it does per batch (default 64 images):
  1. Download (if --url-list) with a thread pool.
  2. Compute SHA-256 immediately; skip anything already in the DB (dedup
     set is loaded into memory once at startup -- 1M sha256 hex strings is
     ~64MB, trivial on 16GB RAM).
  3. Normalize: downscale so the longest side is <= --resize-max (default
     1024px) and re-save as JPEG q85. This is what keeps 1M images from
     costing 150-300GB -- see the storage estimate below. The very first
     "original upload" investigation path (get_or_create_asset in
     provenance_store.py) is untouched and still keeps true originals
     immutable; this bulk path is for reference-index seeding, not
     evidence preservation of a specific investigation.
  4. Hash (SHA-256 already done; pHash/dHash/aHash/wHash) via a process
     pool -- CPU-bound, benefits from multiple cores.
  5. Embed the whole batch on GPU in one forward pass (embeddings.py).
  6. Bulk-insert the batch (executemany, one transaction per batch, ON
     CONFLICT DO NOTHING on sha256) -- NOT the one-commit-per-image path
     used by the live request flow, which would be far too slow at this
     volume.
  7. Append processed count to a checkpoint file so a killed/interrupted
     run can resume with --resume.

Run a small calibration pass on your actual machine before committing to
the full run -- estimates in this docstring are ballpark, not measured:

    python -m scripts.bulk_ingest --source-dir ./my_images --benchmark-only 1000

That prints real images/sec and real average bytes/image for YOUR
hardware and YOUR image set, then extrapolates to your --limit (or 1M by
default) so you get a number grounded in reality instead of my guess.
"""
import argparse
import io
import json
import logging
import multiprocessing as mp
import time
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image

logger = logging.getLogger("bulk_ingest")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


# ---------------------------------------------------------------- sources --

def iter_local_paths(source_dir: Path):
    exts = {".jpg", ".jpeg", ".png", ".webp"}
    for p in sorted(source_dir.rglob("*")):
        if p.suffix.lower() in exts:
            yield p


def iter_url_manifest(manifest_path: Path):
    with open(manifest_path) as f:
        for line in f:
            url = line.strip()
            if url:
                yield url


def load_metadata_index(metadata_jsonl: Optional[Path]) -> dict:
    """Loads a {url: metadata_dict} lookup produced by e.g.
    prepare_open_images_manifest.py. Optional -- --source-dir or a plain
    --url-list with no --metadata-jsonl still works exactly as before,
    this just adds provenance (Page/Appearance) when metadata is available.
    1.2M small dicts is well under 1GB, fine on 16GB RAM."""
    if not metadata_jsonl:
        return {}
    index = {}
    with open(metadata_jsonl) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            index[rec["url"]] = rec
    logger.info("Loaded metadata for %d URLs from %s", len(index), metadata_jsonl)
    return index


# --------------------------------------------------------- per-item work --

def _normalize_and_hash(source_url: Optional[str], raw_bytes: bytes, resize_max: int) -> Optional[dict]:
    """Runs in a worker process. Returns everything needed to insert one
    row, or None if the bytes weren't a decodable image. source_url is
    carried through (not hashed/used) purely so the caller can look up
    provenance metadata for it afterwards -- pass None for --source-dir
    runs, which have no source URL."""
    import hashlib
    import imagehash

    try:
        im = Image.open(io.BytesIO(raw_bytes))
        im.load()
        im = im.convert("RGB")
    except Exception:
        return None

    w, h = im.size
    if max(w, h) > resize_max:
        scale = resize_max / max(w, h)
        im = im.resize((max(1, int(w * scale)), max(1, int(h * scale))), Image.LANCZOS)

    buf = io.BytesIO()
    im.save(buf, format="JPEG", quality=85)
    normalized_bytes = buf.getvalue()

    sha256 = hashlib.sha256(normalized_bytes).hexdigest()
    hashes = {
        "phash": str(imagehash.phash(im)),
        "dhash": str(imagehash.dhash(im)),
        "ahash": str(imagehash.average_hash(im)),
    }
    try:
        hashes["whash"] = str(imagehash.whash(im))
    except Exception:
        hashes["whash"] = None

    return {
        "sha256": sha256,
        "width": im.size[0],
        "height": im.size[1],
        "file_size": len(normalized_bytes),
        "image_bytes": normalized_bytes,
        "source_url": source_url,
        **hashes,
    }


def _write_checkpoint_atomic(path: Path, value: int) -> None:
    """Write-to-temp-then-rename instead of a direct write_text(). If the
    process is killed (power loss, laptop sleep glitch, forced close) at
    the exact moment of a direct write, the checkpoint file can be left
    truncated/corrupt, and a corrupt checkpoint is worse than no
    checkpoint -- it fails the whole resume, not just this one batch.
    os.replace() is atomic on both Windows and Linux, so the checkpoint
    file is always either the old value or the new one, never partial."""
    import os
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(str(value))
    os.replace(tmp, path)


def _download(url: str, timeout: float = 8.0, max_retries: int = 3) -> Optional[bytes]:
    """404/410 (dead link) fails immediately -- retrying a genuinely dead
    Flickr photo doesn't help. 429/503 (throttling) gets a short
    exponential backoff instead of being thrown away, since that request
    already cost latency and a retry has a real chance of succeeding."""
    import time as _time
    import httpx
    for attempt in range(max_retries):
        try:
            resp = httpx.get(url, timeout=timeout, follow_redirects=True)
            if resp.status_code in (429, 503):
                if attempt < max_retries - 1:
                    _time.sleep(0.5 * (2 ** attempt))
                    continue
                return None
            resp.raise_for_status()
            return resp.content
        except httpx.HTTPStatusError:
            return None  # 404/410/etc -- permanently dead, don't retry
        except Exception:
            if attempt < max_retries - 1:
                _time.sleep(0.5 * (2 ** attempt))
                continue
            return None
    return None


# -------------------------------------------------------------- pipeline --

def process_batch(
    raw_items: List[Tuple[Optional[str], bytes]],
    resize_max: int,
    pool: mp.Pool,
) -> List[dict]:
    """raw_items is a list of (source_url_or_None, raw_bytes) pairs, kept
    paired through the whole batch so a metadata lookup by URL still works
    after multiprocessing hashing (order isn't guaranteed to be preserved
    by starmap under load, so the url travels WITH its bytes, not
    alongside as a separate parallel list)."""
    hashed = pool.starmap(_normalize_and_hash, [(url, b, resize_max) for url, b in raw_items])
    return [h for h in hashed if h is not None]


def embed_batch(records: List[dict], storage_dir: Path) -> None:
    """Writes normalized JPEGs to disk (embeddings.py's model expects a
    path) and fills in `embedding` on each record, in place."""
    from app.services import embeddings as embeddings_service

    paths = []
    for rec in records:
        p = storage_dir / f"{rec['sha256']}.jpg"
        if not p.exists():
            p.write_bytes(rec["image_bytes"])
        paths.append(p)
        rec["storage_path"] = str(p)

    vectors = embeddings_service.embed_images_batch(paths)
    for rec, vec in zip(records, vectors):
        rec["embedding"] = vec


def bulk_insert_provenance(records: List[dict], sha_to_id: dict, metadata_index: dict, engine) -> int:
    """Batch version of provenance_store.get_or_create_page +
    record_appearance, for records that (a) were newly inserted this
    batch and (b) have a metadata_index entry for their source_url. Skips
    silently (not an error) for --source-dir runs or URLs with no
    metadata -- those assets/embeddings still get stored, they just don't
    get a Page/Appearance attached, same as any other asset with unknown
    origin. Returns count of appearances written."""
    from sqlalchemy import text

    to_insert = [
        (sha_to_id[r["sha256"]], metadata_index[r["source_url"]])
        for r in records
        if r["sha256"] in sha_to_id and r.get("source_url") and r["source_url"] in metadata_index
    ]
    if not to_insert:
        return 0

    with engine.begin() as conn:
        page_rows = [
            {
                "url": meta.get("landing_url") or meta["url"],
                "domain": meta.get("domain"),
                "platform": meta.get("platform"),
                "title": meta.get("title"),
                "author": meta.get("author"),
                "author_url": meta.get("author_url"),
                "page_metadata": json.dumps({"license": meta.get("license")}) if meta.get("license") else None,
            }
            for _asset_id, meta in to_insert
        ]
        # Postgres executemany-of-INSERT doesn't return a row per input
        # when some conflict and some don't in a way we can zip back
        # positionally, so upsert pages one statement per unique url
        # (still batched in one transaction) and read back the ids.
        seen_urls = {}
        for row in page_rows:
            if row["url"] in seen_urls:
                continue
            result = conn.execute(
                text("""
                    INSERT INTO pages (page_id, url, domain, platform, title, author, author_url,
                                        page_metadata, first_seen_at, last_seen_at)
                    VALUES (gen_random_uuid(), :url, :domain, :platform, :title, :author, :author_url,
                            CAST(:page_metadata AS JSONB), now(), now())
                    ON CONFLICT (url) DO UPDATE SET last_seen_at = now()
                    RETURNING page_id
                """),
                row,
            ).fetchone()
            seen_urls[row["url"]] = result.page_id

        appearance_rows = [
            {
                "asset_id": asset_id,
                "page_id": seen_urls[meta.get("landing_url") or meta["url"]],
                "image_url": meta["url"],
                "timestamp_source": meta.get("timestamp_source"),
                "timestamp_confidence": meta.get("timestamp_confidence"),
                "publication_time": meta.get("publication_time"),
            }
            for asset_id, meta in to_insert
        ]
        conn.execute(
            text("""
                INSERT INTO appearances (appearance_id, asset_id, page_id, image_url,
                                          publication_time, publication_time_type,
                                          timestamp_source, timestamp_confidence, crawl_time)
                VALUES (gen_random_uuid(), :asset_id, :page_id, :image_url,
                        CAST(:publication_time AS TIMESTAMPTZ),
                        CASE WHEN :publication_time IS NOT NULL THEN 'platform_publication' ELSE NULL END,
                        :timestamp_source, :timestamp_confidence, now())
            """),
            appearance_rows,
        )

    return len(appearance_rows)


def bulk_insert(records: List[dict], engine, metadata_index: Optional[dict] = None) -> Tuple[int, int]:
    """One transaction per batch, executemany-style, ON CONFLICT DO
    NOTHING on sha256 so re-running over already-seen images is a
    no-op/dedup rather than an error or a duplicate row. Returns
    (n_assets_stored, n_appearances_stored)."""
    from sqlalchemy import text
    from sqlalchemy.dialects.postgresql import insert as pg_insert
    from app.models.provenance import Asset
    from app.services import embeddings as embeddings_service

    if not records:
        return 0, 0

    with engine.begin() as conn:
        # NOTE: this must be sqlalchemy.dialects.postgresql.insert(), not
        # plain conn.execute(text(...), records) -- passing a list of dicts
        # to a textual query triggers psycopg2 executemany(), and DBAPI
        # executemany() cannot return RETURNING rows (raises
        # ResourceClosedError: "This result object does not return rows").
        # pg_insert(...).values(records) uses SQLAlchemy 2.0's
        # "insertmanyvalues" path instead, which supports RETURNING across
        # a whole batch in one round trip. asset_id isn't in `records` --
        # Asset.asset_id's Python-side default (_uuid) fires per row same
        # as it would for a normal ORM insert.
        # Only pass real Asset columns to .values() -- unlike the old
        # text() query (which just ignored extra dict keys), Core's
        # insert().values(list_of_dicts) errors on "unconsumed column
        # names" if a dict has keys that aren't columns on the table, and
        # `records` also carries image_bytes/embedding/phash/etc for the
        # other two inserts below.
        asset_values = [
            {
                "sha256": r["sha256"],
                "mime_type": "image/jpeg",
                "width": r["width"],
                "height": r["height"],
                "file_size": r["file_size"],
                "storage_path": r["storage_path"],
                "is_original_upload": False,
            }
            for r in records
        ]
        stmt = (
            pg_insert(Asset)
            .values(asset_values)
            .on_conflict_do_nothing(index_elements=["sha256"])
            .returning(Asset.asset_id, Asset.sha256)
        )
        asset_rows = conn.execute(stmt).fetchall()

        # ON CONFLICT rows return nothing, so map sha256 -> asset_id for
        # exactly the rows that were newly inserted this batch.
        sha_to_id = {row.sha256: row.asset_id for row in asset_rows}
        inserted = list(sha_to_id.keys())
        if not inserted:
            return 0, 0

        fp_rows = [
            {"asset_id": sha_to_id[r["sha256"]], "phash": r["phash"], "dhash": r["dhash"],
             "ahash": r["ahash"], "whash": r["whash"]}
            for r in records if r["sha256"] in sha_to_id
        ]
        conn.execute(
            text("""
                INSERT INTO image_fingerprints (asset_id, phash, dhash, ahash, whash)
                VALUES (:asset_id, :phash, :dhash, :ahash, :whash)
                ON CONFLICT (asset_id) DO NOTHING
            """),
            fp_rows,
        )

        emb_rows = [
            {"embedding_id": None, "asset_id": sha_to_id[r["sha256"]],
             "model": embeddings_service.MODEL_NAME, "model_version": embeddings_service.MODEL_ID,
             "dimension": embeddings_service.EMBEDDING_DIM, "vector": str(r["embedding"])}
            for r in records if r["sha256"] in sha_to_id
        ]
        conn.execute(
            text("""
                INSERT INTO embeddings (embedding_id, asset_id, model, model_version, dimension, vector, created_at)
                VALUES (gen_random_uuid(), :asset_id, :model, :model_version, :dimension, :vector, now())
                ON CONFLICT (asset_id, model, model_version) DO NOTHING
            """),
            emb_rows,
        )

    n_appearances = 0
    if metadata_index:
        n_appearances = bulk_insert_provenance(records, sha_to_id, metadata_index, engine)

    return len(inserted), n_appearances


# ------------------------------------------------------------------ main --

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--source-dir", type=Path, help="Local directory of images (recursive)")
    src.add_argument("--url-list", type=Path, help="Text file, one image URL per line")
    ap.add_argument("--limit", type=int, default=1_000_000)
    ap.add_argument("--batch-size", type=int, default=64)
    ap.add_argument("--resize-max", type=int, default=1024, help="Longest side in pixels after normalization")
    ap.add_argument("--storage-dir", type=Path, default=Path("./data/bulk_assets"))
    ap.add_argument("--checkpoint-file", type=Path, default=Path("./data/bulk_ingest.checkpoint"))
    ap.add_argument("--download-workers", type=int, default=16)
    ap.add_argument("--hash-workers", type=int, default=max(1, mp.cpu_count() - 1))
    ap.add_argument("--metadata-jsonl", type=Path, default=None,
                     help="Optional. Output of prepare_open_images_manifest.py (or any "
                          "{url: {...}} JSONL with the same fields) -- when given, each "
                          "downloaded image that has a matching URL also gets a real Page "
                          "(source URL, author, license) + Appearance recorded, not just "
                          "pixels. Only valid with --url-list; ignored for --source-dir "
                          "since local files have no source URL to look up.")
    ap.add_argument("--benchmark-only", type=int, default=0,
                     help="Process only N images, print measured throughput/storage, then exit "
                          "without processing the full --limit")
    args = ap.parse_args()

    from app.provenance_db import get_engine, init_provenance_db
    init_provenance_db()
    engine = get_engine()
    args.storage_dir.mkdir(parents=True, exist_ok=True)

    target = args.benchmark_only or args.limit
    metadata_index = load_metadata_index(args.metadata_jsonl if args.url_list else None)

    if args.source_dir:
        item_iter = iter_local_paths(args.source_dir)
        is_url = False
    else:
        item_iter = iter_url_manifest(args.url_list)
        is_url = True

    start_index = 0
    if not args.benchmark_only and args.checkpoint_file.exists():
        start_index = int(args.checkpoint_file.read_text().strip() or 0)
        logger.info("Resuming from checkpoint: skipping first %d items", start_index)
        for _ in range(start_index):
            next(item_iter, None)

    pool = mp.Pool(args.hash_workers)
    t0 = time.time()
    total_in = 0
    total_stored = 0
    total_appearances = 0
    total_bytes = 0
    stage_time = {"download": 0.0, "hash": 0.0, "embed": 0.0, "insert": 0.0}

    try:
        while total_in < target:
            chunk = []
            for _ in range(args.batch_size):
                item = next(item_iter, None)
                if item is None:
                    break
                chunk.append(item)
            if not chunk:
                break

            if is_url:
                import concurrent.futures
                t_stage = time.time()
                with concurrent.futures.ThreadPoolExecutor(args.download_workers) as ex:
                    downloaded = list(ex.map(_download, chunk))
                stage_time["download"] += time.time() - t_stage
                # Keep (url, bytes) paired so a failed download for one URL
                # doesn't shift every later url out of alignment with its bytes.
                batch_raw = [(url, b) for url, b in zip(chunk, downloaded) if b]
            else:
                t_stage = time.time()
                batch_raw = [(None, Path(p).read_bytes()) for p in chunk]
                stage_time["download"] += time.time() - t_stage

            total_in += len(chunk)
            t_stage = time.time()
            records = process_batch(batch_raw, args.resize_max, pool)
            stage_time["hash"] += time.time() - t_stage
            if records:
                t_stage = time.time()
                embed_batch(records, args.storage_dir)
                stage_time["embed"] += time.time() - t_stage
                t_stage = time.time()
                stored, appearances = bulk_insert(records, engine, metadata_index)
                stage_time["insert"] += time.time() - t_stage
                total_stored += stored
                total_appearances += appearances
                total_bytes += sum(r["file_size"] for r in records)

            # Checkpoint after every batch (not benchmark runs, which are
            # disposable). This is the ONLY progress that's saved -- a
            # batch is all-or-nothing: it's either fully committed to the
            # DB (bulk_insert's `with engine.begin()`) and checkpointed
            # here, or the whole batch is redone next run. Re-downloading
            # a handful of already-stored images on resume is harmless
            # (sha256 ON CONFLICT DO NOTHING dedupes them for free) --
            # losing the checkpoint file itself would not be.
            if not args.benchmark_only:
                _write_checkpoint_atomic(args.checkpoint_file, total_in + start_index)

            elapsed = time.time() - t0
            rate = total_in / elapsed if elapsed else 0
            logger.info(
                "Processed %d/%d (stored %d new, %d with provenance, %d dup/skip) -- "
                "%.1f img/s, %.1f MB so far",
                total_in, target, total_stored, total_appearances, total_in - total_stored,
                rate, total_bytes / 1e6,
            )
    except KeyboardInterrupt:
        logger.info("=" * 60)
        logger.info(
            "Stopped by Ctrl+C after %d images (%d newly stored). Checkpoint saved at %s.",
            total_in, total_stored, args.checkpoint_file,
        )
        logger.info("Safe to resume -- just re-run the exact same command.")
        return
    finally:
        pool.close()
        pool.join()

    elapsed = time.time() - t0
    rate = total_in / elapsed if elapsed else 0
    avg_bytes = (total_bytes / total_stored) if total_stored else 0
    logger.info("=" * 60)
    logger.info("Done. %d processed, %d newly stored (%d with a real source Page/Appearance), "
                "%.1fs elapsed, %.2f img/s",
                total_in, total_stored, total_appearances, elapsed, rate)
    logger.info("Average stored image size: %.1f KB", avg_bytes / 1024)

    stage_total = sum(stage_time.values()) or 1.0
    logger.info("Stage breakdown (share of total pipeline time, not wall-clock overlap):")
    for name in ("download", "hash", "embed", "insert"):
        logger.info("  %-10s %6.1fs  (%.0f%%)", name, stage_time[name], 100 * stage_time[name] / stage_total)

    if args.benchmark_only and rate > 0:
        full_target = args.limit
        est_seconds = full_target / rate
        est_bytes = avg_bytes * full_target
        logger.info("--- Extrapolated to %d images (measured on THIS run/machine) ---", full_target)
        logger.info("Estimated time: %.1f hours", est_seconds / 3600)
        logger.info("Estimated original/normalized image storage: %.1f GB", est_bytes / 1e9)
        logger.info("(add ~5-10GB for the embeddings/fingerprint tables and vector index at 1M rows)")


if __name__ == "__main__":
    main()

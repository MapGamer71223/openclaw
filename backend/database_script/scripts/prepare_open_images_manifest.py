"""
Turn Google's free Open Images metadata CSV into a bulk_ingest.py-ready
URL manifest, WITH real origin metadata attached (not just pixels).

Why Open Images specifically, for the "1M images" goal:

  - It's a single static file, no API key, no login, no rate limit --
    served straight off storage.googleapis.com like any other static
    asset, so it doesn't have the "weeks of crawling at 60-100 req/min"
    problem Reddit's API has.
  - The full-set metadata CSV (9,178,275 rows) is NOT just an image-ID
    list -- every row carries the real Flickr source, in the same spirit
    as PS-Battles' real author/timestamp/link:
        ImageID,Subset,OriginalURL,OriginalLandingURL,License,
        AuthorProfileURL,Author,Title,OriginalSize,OriginalMD5,
        Thumbnail300KURL,Rotation
    OriginalLandingURL is the real Flickr photo page, Author is the real
    Flickr username, License is the real Creative Commons license URL
    (Open Images only indexed CC-licensed Flickr photos to begin with).
    Title sometimes carries a human-entered date ("28 Nov 2010 Our new
    house.") which we opportunistically parse but never trust blindly --
    see PUB_DATE_RE below.
  - 9.2M rows means a random ~1.2M-row sample (to absorb dead-link/
    download failures) is a small fraction of the file, not a scrape of
    the whole thing.

Step 0 -- download the metadata CSV yourself (one-time, ~2.8GB, no script
needed, it's a plain static file):

    wget https://storage.googleapis.com/openimages/2018_04/image_ids_and_rotation.csv

Step 1 -- this script (streams the CSV, never loads all 9.2M rows as
parsed objects -- reservoir sampling keeps only --limit rows in memory):

    python -m scripts.prepare_open_images_manifest \\
        --metadata-csv image_ids_and_rotation.csv \\
        --output-dir ./data/open_images_manifest \\
        --limit 1200000

    Produces, in --output-dir:
      urls.txt              one OriginalURL per line -- feed straight into
                             bulk_ingest.py's --url-list
      manifest_meta.jsonl   one JSON object per line, keyed by url, with
                             the origin fields bulk_ingest.py will attach
                             as a Page + Appearance per downloaded image

Step 2 -- run the actual bulk ingest (see bulk_ingest.py's own docstring
for the --benchmark-only calibration step you should do first):

    python -m scripts.bulk_ingest \\
        --url-list ./data/open_images_manifest/urls.txt \\
        --metadata-jsonl ./data/open_images_manifest/manifest_meta.jsonl \\
        --limit 1000000
"""
import argparse
import csv
import json
import logging
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("prepare_open_images_manifest")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

EXPECTED_HEADER = [
    "ImageID", "Subset", "OriginalURL", "OriginalLandingURL", "License",
    "AuthorProfileURL", "Author", "Title", "OriginalSize", "OriginalMD5",
    "Thumbnail300KURL", "Rotation",
]

# Titles are free-text and mostly NOT dates ("My dog", "IMG_3021"...); only
# trust a leading "D Mon YYYY" / "DD Mon YYYY" pattern, and still record it
# at reduced confidence -- this is "the uploader wrote a date in the title
# field", not a platform-verified publication timestamp.
PUB_DATE_RE = re.compile(r"^\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})\b")
DATE_FORMATS = ("%d %b %Y", "%d %B %Y")


def _try_parse_title_date(title: str):
    if not title:
        return None
    m = PUB_DATE_RE.match(title)
    if not m:
        return None
    raw = m.group(1)
    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            # Sanity bound -- Flickr predates Open Images' 2016-2020 crawl
            # window, so anything wildly outside that is a misparse.
            if 2000 <= dt.year <= 2021:
                return dt
        except ValueError:
            continue
    return None


def _domain_from_url(url: str) -> str:
    m = re.match(r"^https?://([^/]+)", url or "")
    return m.group(1) if m else ""


def stream_filtered_rows(metadata_csv: Path, subset_filter: str, cc_only: bool):
    with open(metadata_csv, newline="", encoding="utf-8", errors="replace") as f:
        reader = csv.reader(f)
        header = next(reader)
        if header[:3] != EXPECTED_HEADER[:3]:
            logger.warning(
                "CSV header doesn't look like the expected Open Images format "
                "(got %s) -- continuing, but check you downloaded the right file.",
                header[:4],
            )
        idx = {name: i for i, name in enumerate(header)}

        def get(row, name):
            i = idx.get(name)
            return row[i] if i is not None and i < len(row) else ""

        n_seen = 0
        n_kept = 0
        for row in reader:
            n_seen += 1
            if n_seen % 1_000_000 == 0:
                logger.info("Scanned %d rows, kept %d so far", n_seen, n_kept)

            subset = get(row, "Subset")
            if subset_filter != "all" and subset != subset_filter:
                continue

            url = get(row, "OriginalURL")
            if not url:
                continue

            license_url = get(row, "License")
            if cc_only and "creativecommons.org" not in license_url:
                continue

            n_kept += 1
            yield {
                "image_id": get(row, "ImageID"),
                "url": url,
                "landing_url": get(row, "OriginalLandingURL"),
                "license": license_url,
                "author": get(row, "Author"),
                "author_url": get(row, "AuthorProfileURL"),
                "title": get(row, "Title"),
                "domain": _domain_from_url(get(row, "OriginalLandingURL")) or "flickr.com",
            }


def reservoir_sample(row_iter, limit: int, seed: int):
    """Classic reservoir sampling -- gives an unbiased random --limit-sized
    sample from a stream of unknown total length, holding only --limit
    rows in memory at once (not the full 9.2M)."""
    rng = random.Random(seed)
    reservoir = []
    for i, row in enumerate(row_iter):
        if i < limit:
            reservoir.append(row)
        else:
            j = rng.randint(0, i)
            if j < limit:
                reservoir[j] = row
    rng.shuffle(reservoir)
    return reservoir


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metadata-csv", type=Path, required=True,
                     help="Path to the downloaded image_ids_and_rotation.csv (9.2M rows)")
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=1_200_000,
                     help="Sample size. Set above your real target (default 1.2M for a "
                          "1M target) to absorb dead links / download failures.")
    ap.add_argument("--subset", choices=["train", "validation", "test", "all"], default="all")
    ap.add_argument("--cc-only", action="store_true", default=True,
                     help="Keep only rows whose License is a creativecommons.org URL "
                          "(on by default -- Open Images is Flickr-sourced and nearly "
                          "every row already qualifies, this just drops the rare exception)")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    if not args.metadata_csv.exists():
        raise SystemExit(
            f"{args.metadata_csv} not found. Download it first:\n"
            "  wget https://storage.googleapis.com/openimages/2018_04/image_ids_and_rotation.csv"
        )

    args.output_dir.mkdir(parents=True, exist_ok=True)

    logger.info("Streaming %s (subset=%s, cc_only=%s)...", args.metadata_csv, args.subset, args.cc_only)
    rows = stream_filtered_rows(args.metadata_csv, args.subset, args.cc_only)
    sample = reservoir_sample(rows, args.limit, args.seed)
    logger.info("Sampled %d rows", len(sample))

    urls_path = args.output_dir / "urls.txt"
    meta_path = args.output_dir / "manifest_meta.jsonl"

    n_with_date = 0
    with open(urls_path, "w") as uf, open(meta_path, "w") as mf:
        for row in sample:
            uf.write(row["url"] + "\n")
            pub_dt = _try_parse_title_date(row["title"])
            if pub_dt:
                n_with_date += 1
            meta = {
                "url": row["url"],
                "image_id": row["image_id"],
                "landing_url": row["landing_url"],
                "domain": row["domain"],
                "platform": "Flickr",
                "author": row["author"] or None,
                "author_url": row["author_url"] or None,
                "license": row["license"] or None,
                "title": row["title"] or None,
                "publication_time": pub_dt.isoformat() if pub_dt else None,
                "timestamp_source": "open_images_title_parse" if pub_dt else None,
                "timestamp_confidence": 0.55 if pub_dt else None,
            }
            mf.write(json.dumps(meta) + "\n")

    logger.info("Wrote %s (%d urls)", urls_path, len(sample))
    logger.info("Wrote %s (%d records, %d with a parsed title date)", meta_path, len(sample), n_with_date)
    logger.info(
        "Next: python -m scripts.bulk_ingest --url-list %s --metadata-jsonl %s --limit %d",
        urls_path, meta_path, len(sample),
    )


if __name__ == "__main__":
    main()

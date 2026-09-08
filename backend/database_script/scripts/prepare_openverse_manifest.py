"""
Pull images from the free, keyless Openverse API into a bulk_ingest.py-ready
URL manifest, WITH real origin metadata attached (not just pixels).

Why Openverse for the "grow the database" goal:

  - No API key or account needed for basic use (anonymous requests are
    allowed) -- unlike Google Vision/Brave/TinEye, there's nothing to sign
    up for before this script runs. Openverse does apply IP-based
    throttling, but there's no hard published per-day cap the way
    Google Vision's free tier has (1000/mo); pass --sleep-seconds to stay
    well under any reasonable ceiling for a multi-thousand-row pull.
  - Every result carries REAL structured provenance: `license`,
    `creator`/`creator_url`, and `foreign_landing_url` (the original
    source page -- Wikimedia Commons, Flickr's CC subset, museum
    collections, etc.), straight from the API response, not inferred from
    a domain name the way DDG/Brave hits are.
  - It's a live search API, not a single static dump -- so unlike Open
    Images (one fixed 9.2M-row CSV), you can target specific --queries to
    grow the index toward whatever subject matter your investigations
    actually see, and re-run it over time to keep adding new material.

Step 1 -- run this script directly (no separate download step, unlike
Open Images' CSV):

    python -m scripts.prepare_openverse_manifest \\
        --queries "protest,flood,wildfire,election rally" \\
        --output-dir ./data/openverse_manifest \\
        --limit 5000

    Produces, in --output-dir:
      urls.txt              one image URL per line -- feed straight into
                             bulk_ingest.py's --url-list
      manifest_meta.jsonl   one JSON object per line, keyed by url, with
                             the origin fields bulk_ingest.py will attach
                             as a Page + Appearance per downloaded image

Step 2 -- run the actual bulk ingest (see bulk_ingest.py's own docstring
for the --benchmark-only calibration step you should do first):

    python -m scripts.bulk_ingest \\
        --url-list ./data/openverse_manifest/urls.txt \\
        --metadata-jsonl ./data/openverse_manifest/manifest_meta.jsonl \\
        --limit 5000

Optional: set OPENVERSE_CLIENT_ID/OPENVERSE_CLIENT_SECRET in .env (free,
register at api.openverse.org) for a higher rate ceiling on a big pull --
this script runs anonymously if they're unset, same as
OpenverseSourceProvider in app/services/source_search.py.
"""
import argparse
import json
import logging
import time
from pathlib import Path
from typing import Iterator, Optional

import httpx

logger = logging.getLogger("prepare_openverse_manifest")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

BASE_URL = "https://api.openverse.org/v1/images/"
TOKEN_URL = "https://api.openverse.org/v1/auth_tokens/token/"
PAGE_SIZE = 20  # Openverse's per-page max for the public search endpoint


def _get_token(client_id: Optional[str], client_secret: Optional[str]) -> Optional[str]:
    if not (client_id and client_secret):
        return None
    try:
        resp = httpx.post(
            TOKEN_URL,
            data={"client_id": client_id, "client_secret": client_secret, "grant_type": "client_credentials"},
            timeout=8,
        )
        resp.raise_for_status()
        return resp.json().get("access_token")
    except Exception:
        logger.warning("Openverse auth failed; continuing anonymously")
        return None


def iter_openverse_results(
    query: str, per_query_limit: int, headers: dict, sleep_seconds: float
) -> Iterator[dict]:
    page = 1
    n_yielded = 0
    while n_yielded < per_query_limit:
        try:
            resp = httpx.get(
                BASE_URL,
                params={"q": query, "page_size": PAGE_SIZE, "page": page},
                headers=headers,
                timeout=10,
            )
            if resp.status_code == 429:
                logger.warning("Rate limited on %r page %d -- backing off 30s", query, page)
                time.sleep(30)
                continue
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            logger.warning("Openverse request failed for %r page %d: %s -- stopping this query", query, page, e)
            return

        results = data.get("results", [])
        if not results:
            return
        for item in results:
            if n_yielded >= per_query_limit:
                return
            yield item
            n_yielded += 1

        if not data.get("result_count") or page * PAGE_SIZE >= data.get("result_count", 0):
            return
        page += 1
        time.sleep(sleep_seconds)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--queries", required=True,
                     help="Comma-separated search terms, e.g. 'protest,flood,wildfire'")
    ap.add_argument("--output-dir", type=Path, required=True)
    ap.add_argument("--limit", type=int, default=5000, help="Total rows across all queries")
    ap.add_argument("--sleep-seconds", type=float, default=1.0,
                     help="Delay between paged requests -- stay polite to the free anonymous tier")
    ap.add_argument("--client-id", default=None, help="Optional Openverse OAuth client id (free, higher rate ceiling)")
    ap.add_argument("--client-secret", default=None)
    args = ap.parse_args()

    queries = [q.strip() for q in args.queries.split(",") if q.strip()]
    if not queries:
        raise SystemExit("--queries produced no usable search terms")

    per_query_limit = max(1, args.limit // len(queries))
    token = _get_token(args.client_id, args.client_secret)
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    if not token:
        logger.info("Running anonymously (no --client-id/--client-secret) -- fine for a few thousand rows")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    urls_path = args.output_dir / "urls.txt"
    meta_path = args.output_dir / "manifest_meta.jsonl"

    seen_urls = set()
    n_written = 0
    with open(urls_path, "w") as uf, open(meta_path, "w") as mf:
        for query in queries:
            logger.info("Querying Openverse for %r (target %d rows)", query, per_query_limit)
            for item in iter_openverse_results(query, per_query_limit, headers, args.sleep_seconds):
                img_url = item.get("url")
                if not img_url or img_url in seen_urls:
                    continue
                seen_urls.add(img_url)

                meta = {
                    "url": img_url,
                    "landing_url": item.get("foreign_landing_url"),
                    "domain": item.get("source") or "openverse",
                    "platform": item.get("source") or "Openverse",
                    "author": item.get("creator") or None,
                    "author_url": item.get("creator_url") or None,
                    "license": item.get("license_url") or item.get("license") or None,
                    "title": item.get("title") or None,
                    # Openverse's search index doesn't expose a real
                    # upload/publication timestamp -- leave unset rather
                    # than fabricate one; bulk_ingest.py/Wayback enrichment
                    # can backfill an approximate "earliest seen" date.
                    "publication_time": None,
                    "timestamp_source": None,
                    "timestamp_confidence": None,
                }
                uf.write(img_url + "\n")
                mf.write(json.dumps(meta) + "\n")
                n_written += 1

    logger.info("Wrote %s (%d urls)", urls_path, n_written)
    logger.info("Wrote %s (%d records)", meta_path, n_written)
    logger.info(
        "Next: python -m scripts.bulk_ingest --url-list %s --metadata-jsonl %s --limit %d",
        urls_path, meta_path, n_written,
    )


if __name__ == "__main__":
    main()

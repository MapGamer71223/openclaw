# What changed (drop-in replacements for your existing files)

1. `app/services/source_search.py`
   - Added `OpenverseSourceProvider` — free, keyless, no meaningful rate
     limit for your traffic (Wikimedia Commons + CC Flickr + museums).
     Returns real license/creator/landing-page metadata per hit.
   - Added `_CompositeProvider` — runs multiple providers concurrently and
     merges/dedupes results by URL.
   - `get_source_provider()` now ALWAYS merges Openverse on top of
     whichever primary provider your `.env` selects (Google Vision /
     PicImageSearch / MRISA / Brave / DDG) — so you get extra coverage
     for free on every investigation, live-mode data goes straight into
     the orchestrator -> API response -> report exactly like the other
     providers already did (no other wiring needed, since
     `get_source_provider()` is the single seam everything else calls).

2. `app/config.py`
   - Added `OPENVERSE_CLIENT_ID` / `OPENVERSE_CLIENT_SECRET` (both
     optional — leave blank in `.env` to run fully anonymous/keyless;
     register free at api.openverse.org only if you want a higher
     ceiling later).

3. `scripts/prepare_openverse_manifest.py` (new)
   - Same job as `prepare_open_images_manifest.py`, but pulls live from
     Openverse's keyless API instead of a static CSV — this is your
     "download source for the database" (provenance DB / bulk_ingest.py).
   - Usage:
     ```
     python -m scripts.prepare_openverse_manifest \
         --queries "protest,flood,wildfire,election rally" \
         --output-dir ./data/openverse_manifest --limit 5000

     python -m scripts.bulk_ingest \
         --url-list ./data/openverse_manifest/urls.txt \
         --metadata-jsonl ./data/openverse_manifest/manifest_meta.jsonl \
         --limit 5000
     ```
   - Note: `bulk_ingest.py` needs `PROVENANCE_DATABASE_URL` pointing at a
     running Postgres+pgvector (`docker compose up provdb`). If that's not
     up and you're short on time, skip step 3 for the demo — the
     Openverse *live search* (item 1 above) already works standalone and
     needs no database.

DEMO_MODE was already `false` and GOOGLE_VISION_API_KEY was already set in
your `.env`, so you're already in real mode — no change needed there.

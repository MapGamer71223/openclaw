"""
DiscoveryManager -- ties the existing SourceSearchProvider chain
(source_search.py) into the permanent provenance database.

This does NOT replace source_search.py's providers. It wraps them: every
CandidateSource any free provider returns gets persisted as a Page +
DiscoveryEvent (+ an Appearance once/if the candidate image is confirmed
similar), so a search performed today keeps paying off on every future
investigation -- that's the "our own database, like Google, for images"
goal. Paid/official providers (Google Vision) can still be layered in
later; nothing here requires them.

Flow for one investigation:
  1. check_own_database()   -- cheap, local, instant: has anything close
                                to this image already been discovered?
  2. run_free_discovery()   -- only for images we don't already have deep
                                coverage on: fan out to DDG + PicImageSearch
                                (free engines) + MRISA (if a local instance
                                is running) + Wayback CDX date enrichment
                                (all already free/keyless in this repo),
                                persisting every result as it comes in.

Cost ordering follows Phase 16 of the spec: cheap hash/db lookup first,
external network calls only when the local database doesn't already
answer the question.
"""
import logging
from pathlib import Path
from typing import List

from sqlalchemy.orm import Session

from app.config import settings
from app.services import provenance_store, embeddings as embeddings_service
from app.services.perceptual_hash import hamming_distance
from app.services.source_search import (
    DDGSourceProvider, PicImageSearchProvider, MrisaSourceProvider,
    CandidateSource,
)

logger = logging.getLogger("discovery_manager")

# Only free/keyless sources are wired here by default, per "it should be
# free". Google Vision / Brave stay available in source_search.py for
# anyone who does add a key later, but this manager doesn't require either.
FREE_SOURCES = {"picimagesearch", "mrisa", "ddg"}


def _free_providers() -> List[tuple]:
    """Returns (source_name, provider) pairs for whichever free providers
    are actually usable given current settings -- mirrors the priority
    logic in source_search.get_source_provider() but runs ALL available
    free sources (not just the first match), since the goal here is
    maximum free coverage into our own database, not picking one."""
    providers = []
    if settings.PICIMAGESEARCH_ENABLED:
        engines = [e.strip() for e in settings.PICIMAGESEARCH_ENGINES.split(",") if e.strip()]
        providers.append(("picimagesearch", PicImageSearchProvider(engines=engines)))
    if settings.MRISA_URL:
        providers.append(("mrisa", MrisaSourceProvider(settings.MRISA_URL, "")))
    providers.append(("ddg", DDGSourceProvider()))  # always available, no config needed
    return providers


def check_own_database(db: Session, file_path: Path, *, similarity_threshold: float = 0.90) -> dict:
    """Step 1: before calling any external provider, see if this image (or
    something visually very close to it) is already in our own database."""
    vector = embeddings_service.embed_image(file_path)
    matches = provenance_store.find_similar_assets(db, vector, limit=25)
    strong_matches = [m for m in matches if m["similarity"] >= similarity_threshold]
    return {
        "already_known": len(strong_matches) > 0,
        "matches": matches,
        "strong_matches": strong_matches,
    }


def run_free_discovery(
    db: Session,
    query_asset,
    file_path: Path,
    queries: List[str],
    media_phash: str,
    *,
    image_url: str = "",
) -> List[CandidateSource]:
    """Step 2: fan out to every configured free provider, persisting each
    result into the permanent database as it arrives (not just returning
    it for one-time use)."""
    all_results: List[CandidateSource] = []

    for source_name, provider in _free_providers():
        # MRISA needs the actual image_url set per-call, not at construction.
        if source_name == "mrisa":
            if not image_url:
                continue
            provider.image_url = image_url

        try:
            results = provider.search(queries, media_phash)
        except Exception:
            logger.exception("Free discovery source %r failed", source_name)
            continue

        for rank, candidate in enumerate(results, start=1):
            all_results.append(candidate)
            accepted = None
            reject_reason = None

            if candidate.candidate_phash:
                distance = hamming_distance(media_phash, candidate.candidate_phash)
                accepted = distance <= 18  # "possibly_related" or better, see perceptual_hash.classify_match
                if not accepted:
                    reject_reason = "low_perceptual_similarity"
            else:
                reject_reason = "no_comparable_hash"

            provenance_store.record_discovery_event(
                db,
                query_asset=query_asset,
                source=source_name,
                result_url=candidate.url,
                rank=rank,
                accepted=accepted,
                reject_reason=reject_reason,
            )

            if accepted:
                page = provenance_store.get_or_create_page(
                    db,
                    candidate.url,
                    domain=candidate.domain,
                    platform=candidate.platform,
                    title=candidate.title,
                )
                pub_time = None
                pub_type = None
                if candidate.publication_date and candidate.publication_date != "unknown":
                    pub_type = "page_publication"
                provenance_store.record_appearance(
                    db,
                    asset=query_asset,
                    page=page,
                    image_url=candidate.thumbnail_url,
                    publication_time=pub_time,  # left for the metadata-extraction stage to
                    publication_time_type=pub_type,  # parse candidate.publication_date properly
                    timestamp_source=source_name,
                    evidence_quality_score=1.0 - (distance / 64.0) if candidate.candidate_phash else None,
                )

    logger.info(
        "Free discovery for asset %s: %d raw candidates from %d sources",
        query_asset.asset_id, len(all_results), len(_free_providers()),
    )
    return all_results

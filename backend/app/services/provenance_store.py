"""
Read/write layer for the provenance database (app/models/provenance.py).

Every function here is additive and idempotent where the schema allows it
(unique constraints on sha256 / url / (asset_id,model,model_version)) --
re-ingesting the same image or page never creates a duplicate row, it
updates last_seen_at / adds a new Appearance observation instead, per the
"preserve all observations, never overwrite" principle from the spec.
"""
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.provenance import (
    Asset, ImageFingerprint, Embedding, Page, Appearance, DiscoveryEvent, Match,
)
from app.services.hashing import calculate_sha256, file_size_bytes
from app.services.perceptual_hash import compute_hashes
from app.services import embeddings as embeddings_service

logger = logging.getLogger("provenance_store")


def get_or_create_asset(
    db: Session,
    file_path: Path,
    *,
    mime_type: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    is_original_upload: bool = False,
    storage_path: Optional[str] = None,
) -> Asset:
    sha256 = calculate_sha256(file_path)
    existing = db.execute(select(Asset).where(Asset.sha256 == sha256)).scalar_one_or_none()
    if existing:
        return existing

    asset = Asset(
        sha256=sha256,
        mime_type=mime_type,
        width=width,
        height=height,
        file_size=file_size_bytes(file_path),
        storage_path=storage_path or str(file_path),
        is_original_upload=is_original_upload,
    )
    db.add(asset)
    db.flush()  # get asset.asset_id without committing yet

    hashes = compute_hashes(file_path)
    db.add(ImageFingerprint(
        asset_id=asset.asset_id,
        phash=hashes["phash"],
        dhash=hashes["dhash"],
        ahash=hashes["ahash"],
        whash=hashes.get("whash"),
    ))

    vector = embeddings_service.embed_image(file_path)
    db.add(Embedding(
        asset_id=asset.asset_id,
        model=embeddings_service.MODEL_NAME,
        model_version=embeddings_service.MODEL_ID,
        dimension=embeddings_service.EMBEDDING_DIM,
        vector=vector,
    ))

    db.commit()
    db.refresh(asset)
    logger.info("Stored new asset %s (sha256=%s...)", asset.asset_id, sha256[:12])
    return asset


def get_or_create_page(
    db: Session,
    url: str,
    *,
    canonical_url: Optional[str] = None,
    domain: Optional[str] = None,
    platform: Optional[str] = None,
    title: Optional[str] = None,
    description: Optional[str] = None,
    author: Optional[str] = None,
    author_url: Optional[str] = None,
    page_metadata: Optional[dict] = None,
) -> Page:
    existing = db.execute(select(Page).where(Page.url == url)).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if existing:
        existing.last_seen_at = now
        # Fill in anything we now know that we didn't before; never
        # overwrite a previously-recorded value with a blank one.
        for field, value in (
            ("canonical_url", canonical_url), ("domain", domain), ("platform", platform),
            ("title", title), ("description", description),
            ("author", author), ("author_url", author_url),
        ):
            if value and not getattr(existing, field):
                setattr(existing, field, value)
        if page_metadata:
            existing.page_metadata = {**(existing.page_metadata or {}), **page_metadata}
        db.commit()
        return existing

    page = Page(
        url=url, canonical_url=canonical_url, domain=domain, platform=platform,
        title=title, description=description, author=author, author_url=author_url,
        page_metadata=page_metadata,
    )
    db.add(page)
    db.commit()
    db.refresh(page)
    return page


def record_appearance(
    db: Session,
    *,
    asset: Asset,
    page: Page,
    image_url: Optional[str] = None,
    publication_time: Optional[datetime] = None,
    publication_time_type: Optional[str] = None,
    timestamp_source: Optional[str] = None,
    timestamp_confidence: Optional[float] = None,
    archive_time: Optional[datetime] = None,
    http_status: Optional[int] = None,
    evidence_quality_score: Optional[float] = None,
    raw_evidence_path: Optional[str] = None,
) -> Appearance:
    """Always inserts a new row -- re-crawling the same (asset, page) pair
    over time is a new observation, not an update, so timeline/propagation
    analysis later can see how a page's claimed date/state changed."""
    appearance = Appearance(
        asset_id=asset.asset_id,
        page_id=page.page_id,
        image_url=image_url,
        publication_time=publication_time,
        publication_time_type=publication_time_type,
        timestamp_source=timestamp_source,
        timestamp_confidence=timestamp_confidence,
        archive_time=archive_time,
        http_status=http_status,
        evidence_quality_score=evidence_quality_score,
        raw_evidence_path=raw_evidence_path,
    )
    db.add(appearance)
    db.commit()
    db.refresh(appearance)
    return appearance


def record_discovery_event(
    db: Session,
    *,
    query_asset: Asset,
    source: str,
    result_url: str,
    rank: Optional[int] = None,
    accepted: Optional[bool] = None,
    reject_reason: Optional[str] = None,
) -> DiscoveryEvent:
    event = DiscoveryEvent(
        query_asset_id=query_asset.asset_id,
        source=source,
        result_url=result_url,
        rank=rank,
        accepted=accepted,
        reject_reason=reject_reason,
    )
    db.add(event)
    db.commit()
    return event


def record_provenance_edge(
    db: Session,
    *,
    source_asset: Asset,
    target_asset: Asset,
    relationship: str,
    confidence: Optional[float] = None,
    evidence: Optional[str] = None,
) -> "object":
    from app.models.provenance import ProvenanceEdge
    edge = ProvenanceEdge(
        source_asset_id=source_asset.asset_id,
        target_asset_id=target_asset.asset_id,
        relationship=relationship,
        confidence=confidence,
        evidence=evidence,
    )
    db.add(edge)
    db.commit()
    return edge


def record_match(
    db: Session,
    *,
    source_asset: Asset,
    candidate_asset: Asset,
    phash_distance: Optional[int] = None,
    embedding_similarity: Optional[float] = None,
    feature_similarity: Optional[float] = None,
    overall_score: float,
    match_confidence: Optional[float] = None,
) -> Match:
    match = Match(
        source_asset_id=source_asset.asset_id,
        candidate_asset_id=candidate_asset.asset_id,
        phash_distance=phash_distance,
        embedding_similarity=embedding_similarity,
        feature_similarity=feature_similarity,
        overall_score=overall_score,
        match_confidence=match_confidence,
    )
    db.add(match)
    db.commit()
    return match


def find_similar_assets(db: Session, vector: list, *, limit: int = 25) -> list:
    """Nearest-neighbor search over every embedding this system has ever
    stored -- the 'check our own database first' step that lets repeat
    images skip external discovery providers entirely. Uses pgvector's
    inner-product operator (<#>); vectors are stored L2-normalized (see
    embeddings.py) so inner product == cosine similarity."""
    from app.models.provenance import Embedding as EmbeddingModel
    rows = db.execute(
        select(EmbeddingModel, EmbeddingModel.vector.max_inner_product(vector).label("distance"))
        .order_by(EmbeddingModel.vector.max_inner_product(vector))
        .limit(limit)
    ).all()
    return [{"asset_id": row[0].asset_id, "similarity": -row[1]} for row in rows]

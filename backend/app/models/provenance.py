"""
SQLAlchemy models for the provenance ("our own image database") layer.

This is the permanent, ever-growing store: every image, fingerprint,
embedding, page, and appearance the system has ever observed lives here,
independent of any single investigation in the existing SQLite DB. The
existing `SourceSearchProvider`s (Google Vision / PicImageSearch / MRISA /
Brave / DDG) become *feeds* into this store via
app/services/discovery_manager.py, instead of being queried fresh and
thrown away on every investigation.

Design mirrors the schema originally scoped for this layer:
assets -> image_fingerprints / embeddings
pages -> appearances (many appearances per page, per asset)
discovery_events records which source found what, when
matches records asset-to-asset similarity (for variant/duplicate linking)
"""
import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Column, String, Integer, Float, BigInteger, DateTime, Boolean,
    ForeignKey, Text, UniqueConstraint, Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship

from app.provenance_db import ProvenanceBase


def _uuid():
    return str(uuid.uuid4())


def _now():
    return datetime.now(timezone.utc)


class Asset(ProvenanceBase):
    """One physically distinct image we've stored a copy of -- the
    original upload, or a downloaded candidate/variant image."""
    __tablename__ = "assets"

    asset_id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    sha256 = Column(String(64), unique=True, nullable=False, index=True)
    mime_type = Column(String(64), nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    file_size = Column(BigInteger, nullable=True)
    storage_path = Column(Text, nullable=True)  # local path or object-store key
    is_original_upload = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    fingerprints = relationship("ImageFingerprint", back_populates="asset", uselist=False,
                                 cascade="all, delete-orphan")
    embeddings = relationship("Embedding", back_populates="asset", cascade="all, delete-orphan")
    appearances = relationship("Appearance", back_populates="asset", cascade="all, delete-orphan")


class ImageFingerprint(ProvenanceBase):
    __tablename__ = "image_fingerprints"

    asset_id = Column(UUID(as_uuid=False), ForeignKey("assets.asset_id", ondelete="CASCADE"),
                       primary_key=True)
    phash = Column(String(64), nullable=True, index=True)
    dhash = Column(String(64), nullable=True, index=True)
    ahash = Column(String(64), nullable=True, index=True)
    whash = Column(String(64), nullable=True, index=True)

    asset = relationship("Asset", back_populates="fingerprints")


class Embedding(ProvenanceBase):
    __tablename__ = "embeddings"
    __table_args__ = (
        UniqueConstraint("asset_id", "model", "model_version", name="uq_embedding_asset_model"),
    )

    embedding_id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    asset_id = Column(UUID(as_uuid=False), ForeignKey("assets.asset_id", ondelete="CASCADE"),
                       nullable=False, index=True)
    model = Column(String(128), nullable=False)          # e.g. "clip"
    model_version = Column(String(128), nullable=False)  # e.g. "openai/clip-vit-base-patch32"
    dimension = Column(Integer, nullable=False)
    vector = Column(Vector(512), nullable=False)  # 512 = CLIP ViT-B/32 dim; see embeddings.py
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    asset = relationship("Asset", back_populates="embeddings")


class Page(ProvenanceBase):
    """A distinct web page/post where one or more appearances were found."""
    __tablename__ = "pages"
    __table_args__ = (UniqueConstraint("url", name="uq_pages_url"),)

    page_id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    url = Column(Text, nullable=False)
    canonical_url = Column(Text, nullable=True)
    domain = Column(String(255), nullable=True, index=True)
    platform = Column(String(64), nullable=True, index=True)
    title = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    author = Column(String(255), nullable=True)
    author_url = Column(Text, nullable=True)
    page_metadata = Column(JSONB, nullable=True)  # OpenGraph/JSON-LD/twitter-card dump
    first_seen_at = Column(DateTime(timezone=True), default=_now, nullable=False)
    last_seen_at = Column(DateTime(timezone=True), default=_now, nullable=False)

    appearances = relationship("Appearance", back_populates="page", cascade="all, delete-orphan")


class Appearance(ProvenanceBase):
    """One observation of one asset on one page. Multiple appearances can
    point at the same (asset_id, page_id) over time (re-crawls) -- each
    crawl is preserved rather than overwritten, per the
    'preserve all observations' principle."""
    __tablename__ = "appearances"

    appearance_id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    asset_id = Column(UUID(as_uuid=False), ForeignKey("assets.asset_id", ondelete="CASCADE"),
                       nullable=False, index=True)
    page_id = Column(UUID(as_uuid=False), ForeignKey("pages.page_id", ondelete="CASCADE"),
                      nullable=False, index=True)
    image_url = Column(Text, nullable=True)

    publication_time = Column(DateTime(timezone=True), nullable=True)
    publication_time_type = Column(String(64), nullable=True)  # platform_publication / page_modified / archive_capture / ...
    timestamp_source = Column(String(64), nullable=True)       # e.g. "reddit_api", "wayback_cdx", "opengraph"
    timestamp_confidence = Column(Float, nullable=True)

    archive_time = Column(DateTime(timezone=True), nullable=True)
    crawl_time = Column(DateTime(timezone=True), default=_now, nullable=False)

    http_status = Column(Integer, nullable=True)
    evidence_quality_score = Column(Float, nullable=True)
    raw_evidence_path = Column(Text, nullable=True)  # saved HTML/screenshot/JSON, if preserved

    asset = relationship("Asset", back_populates="appearances")
    page = relationship("Page", back_populates="appearances")


class DiscoveryEvent(ProvenanceBase):
    """Audit trail: which discovery adapter produced which candidate URL,
    for which query asset, ranked how. Kept even for candidates that never
    turned into a confirmed Appearance, so a failed/rejected lead is still
    traceable."""
    __tablename__ = "discovery_events"

    event_id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    query_asset_id = Column(UUID(as_uuid=False), ForeignKey("assets.asset_id", ondelete="CASCADE"),
                             nullable=False, index=True)
    source = Column(String(64), nullable=False, index=True)  # "google_vision" / "picimagesearch" / "mrisa" / ...
    result_url = Column(Text, nullable=False)
    rank = Column(Integer, nullable=True)
    accepted = Column(Boolean, nullable=True)  # did it turn into a stored Appearance?
    reject_reason = Column(String(255), nullable=True)  # e.g. "robots_disallow", "low_similarity"
    discovered_at = Column(DateTime(timezone=True), default=_now, nullable=False)


class ProvenanceEdge(ProvenanceBase):
    """A claimed/known relationship between two assets, distinct from a
    Match (which is a similarity SCORE). This is for cases where the
    relationship itself is known -- e.g. ground-truth dataset labels
    ('this is a derivative of that'), or a later inference step's
    conclusion -- not just 'these look alike'."""
    __tablename__ = "provenance_edges"

    edge_id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    source_asset_id = Column(UUID(as_uuid=False), ForeignKey("assets.asset_id", ondelete="CASCADE"),
                              nullable=False, index=True)
    target_asset_id = Column(UUID(as_uuid=False), ForeignKey("assets.asset_id", ondelete="CASCADE"),
                              nullable=False, index=True)
    relationship = Column(String(32), nullable=False)  # derived_from/reposted_from/copied_from/
                                                         # embedded_from/screenshot_of/variant_of/unknown
    confidence = Column(Float, nullable=True)
    evidence = Column(Text, nullable=True)  # free text: what established this edge
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)


class Match(ProvenanceBase):
    """Similarity between two stored assets (e.g. a candidate vs. the
    original upload, or two candidates found to be the same image)."""
    __tablename__ = "matches"
    __table_args__ = (
        Index("ix_matches_source_candidate", "source_asset_id", "candidate_asset_id"),
    )

    match_id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    source_asset_id = Column(UUID(as_uuid=False), ForeignKey("assets.asset_id", ondelete="CASCADE"),
                              nullable=False)
    candidate_asset_id = Column(UUID(as_uuid=False), ForeignKey("assets.asset_id", ondelete="CASCADE"),
                                 nullable=False)
    phash_distance = Column(Integer, nullable=True)
    embedding_similarity = Column(Float, nullable=True)
    feature_similarity = Column(Float, nullable=True)
    overall_score = Column(Float, nullable=False)
    match_confidence = Column(Float, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now, nullable=False)

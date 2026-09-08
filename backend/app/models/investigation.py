import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, String, Float, Integer, Boolean, DateTime, ForeignKey, Text, JSON
)
from sqlalchemy.orm import relationship

from app.database import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Investigation(Base):
    __tablename__ = "investigations"

    id = Column(String, primary_key=True, default=new_id)
    state = Column(String, default="UPLOADED", nullable=False)
    media_type = Column(String, nullable=False)  # "image" | "video"
    original_filename = Column(String, nullable=False)
    demo_mode = Column(Boolean, default=True)
    verdict = Column(String, nullable=True)  # AI_GENERATED | AI_ALTERED | LIKELY_AUTHENTIC | INCONCLUSIVE
    confidence_label = Column(String, nullable=True)  # HIGH | MEDIUM | LOW | INCONCLUSIVE
    overall_score = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    media_asset = relationship("MediaAsset", back_populates="investigation", uselist=False, cascade="all, delete-orphan")
    forensic_results = relationship("ForensicResult", back_populates="investigation", uselist=False, cascade="all, delete-orphan")
    ai_detection = relationship("AIDetection", back_populates="investigation", uselist=False, cascade="all, delete-orphan")
    sources = relationship("Source", back_populates="investigation", cascade="all, delete-orphan")
    propagation_edges = relationship("PropagationEdge", back_populates="investigation", cascade="all, delete-orphan")
    events = relationship("InvestigationEvent", back_populates="investigation", cascade="all, delete-orphan", order_by="InvestigationEvent.timestamp")
    report = relationship("Report", back_populates="investigation", uselist=False, cascade="all, delete-orphan")

    @property
    def source_count(self) -> int:
        """Used by InvestigationOut (the list-view schema) so the dashboard
        table can show a real source count instead of a hardcoded placeholder."""
        return len(self.sources)


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id = Column(String, primary_key=True, default=new_id)
    investigation_id = Column(String, ForeignKey("investigations.id"), nullable=False)
    original_path = Column(String, nullable=False)
    sha256 = Column(String, nullable=False, index=True)
    size_bytes = Column(Integer, nullable=False)
    mime_type = Column(String, nullable=False)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    duration_seconds = Column(Float, nullable=True)
    metadata_json = Column(JSON, nullable=True)
    gps_present = Column(Boolean, default=False)
    phash = Column(String, nullable=True)
    dhash = Column(String, nullable=True)
    ahash = Column(String, nullable=True)

    investigation = relationship("Investigation", back_populates="media_asset")


class ForensicResult(Base):
    __tablename__ = "forensic_results"

    id = Column(String, primary_key=True, default=new_id)
    investigation_id = Column(String, ForeignKey("investigations.id"), nullable=False)
    ela_artifact_path = Column(String, nullable=True)
    ela_score = Column(Float, nullable=True)
    noise_score = Column(Float, nullable=True)
    resampling_score = Column(Float, nullable=True)
    compression_notes = Column(JSON, nullable=True)
    suspicious_indicators = Column(JSON, nullable=True)  # list[str]
    frame_analysis = Column(JSON, nullable=True)  # video only
    forensic_score = Column(Float, nullable=True)  # 0..1 aggregated evidence-strength

    investigation = relationship("Investigation", back_populates="forensic_results")


class AIDetection(Base):
    __tablename__ = "ai_detections"

    id = Column(String, primary_key=True, default=new_id)
    investigation_id = Column(String, ForeignKey("investigations.id"), nullable=False)
    classification = Column(String, nullable=False)  # AI_GENERATED | AI_ALTERED | LIKELY_AUTHENTIC | INCONCLUSIVE | NOT_AVAILABLE
    probability = Column(Float, nullable=False)
    confidence = Column(String, nullable=False)  # high | medium | low | unavailable
    model_name = Column(String, nullable=False)
    signals = Column(JSON, nullable=True)  # list[str]
    is_demo = Column(Boolean, default=True)
    detector_status = Column(String, default="demo")  # demo | real | unavailable
    heatmap_path = Column(String, nullable=True)

    investigation = relationship("Investigation", back_populates="ai_detection")


class Source(Base):
    __tablename__ = "sources"

    id = Column(String, primary_key=True, default=new_id)
    investigation_id = Column(String, ForeignKey("investigations.id"), nullable=False)
    url = Column(String, nullable=False)
    title = Column(String, nullable=True)
    platform = Column(String, nullable=True)
    domain = Column(String, nullable=True)
    publication_date = Column(String, nullable=True)  # SOURCE date (as claimed by the source) - string, may be "unknown"
    date_found = Column(DateTime, default=utcnow)  # when WE discovered it (retrieval timestamp)
    similarity_score = Column(Float, nullable=True)
    phash_distance = Column(Integer, nullable=True)
    match_category = Column(String, nullable=True)  # exact | near_identical | modified_copy | possibly_related | unrelated
    source_confidence = Column(Float, nullable=True)
    classification = Column(String, nullable=True)  # LIKELY_EARLIEST_FOUND_SOURCE | REPOST | UNVERIFIED
    reasoning = Column(JSON, nullable=True)  # list[str]
    evidence_notes = Column(Text, nullable=True)
    accessible = Column(Boolean, default=True)
    inaccessible_reason = Column(String, nullable=True)
    is_demo = Column(Boolean, default=True)
    thumbnail_url = Column(String, nullable=True)
    # True when thumbnail_url is a generic stand-in image (no real preview
    # could be fetched/downloaded) rather than an actual pixel-verified
    # preview of this candidate. Kept separate from is_demo: a REAL source
    # can still end up with a placeholder thumbnail if its image failed to
    # download. UI should badge these ("no preview") and the report/
    # confidence pipeline must never treat this as visual evidence.
    thumbnail_is_placeholder = Column(Boolean, default=False)

    investigation = relationship("Investigation", back_populates="sources")


class PropagationEdge(Base):
    __tablename__ = "propagation_edges"

    id = Column(String, primary_key=True, default=new_id)
    investigation_id = Column(String, ForeignKey("investigations.id"), nullable=False)
    from_node = Column(String, nullable=False)  # node id
    to_node = Column(String, nullable=False)
    edge_type = Column(String, nullable=False)  # reposted_from | similar_to | published_before | linked_to | embedded_from

    investigation = relationship("Investigation", back_populates="propagation_edges")


class InvestigationEvent(Base):
    __tablename__ = "investigation_events"

    id = Column(String, primary_key=True, default=new_id)
    investigation_id = Column(String, ForeignKey("investigations.id"), nullable=False)
    timestamp = Column(DateTime, default=utcnow)
    agent = Column(String, nullable=False)  # e.g. "evidence-agent", "ai-detector", "osint-agent"
    action = Column(String, nullable=False)
    detail = Column(Text, nullable=True)
    stage = Column(String, nullable=True)
    progress = Column(Integer, nullable=True)

    investigation = relationship("Investigation", back_populates="events")


class Report(Base):
    __tablename__ = "reports"

    id = Column(String, primary_key=True, default=new_id)
    investigation_id = Column(String, ForeignKey("investigations.id"), nullable=False)
    content_json = Column(JSON, nullable=False)
    generated_at = Column(DateTime, default=utcnow)

    investigation = relationship("Investigation", back_populates="report")

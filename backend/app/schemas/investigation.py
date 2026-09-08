from datetime import datetime
from typing import Optional, List, Any
from pydantic import BaseModel, ConfigDict


class MediaAssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    sha256: str
    size_bytes: int
    mime_type: str
    width: Optional[int] = None
    height: Optional[int] = None
    duration_seconds: Optional[float] = None
    gps_present: bool = False
    phash: Optional[str] = None
    dhash: Optional[str] = None
    ahash: Optional[str] = None
    metadata_json: Optional[Any] = None


class ForensicResultOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    ela_score: Optional[float] = None
    noise_score: Optional[float] = None
    resampling_score: Optional[float] = None
    compression_notes: Optional[Any] = None
    suspicious_indicators: Optional[Any] = None
    frame_analysis: Optional[Any] = None
    forensic_score: Optional[float] = None


class AIDetectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    classification: str
    probability: float
    confidence: str
    model_name: str
    signals: Optional[Any] = None
    is_demo: bool = True
    detector_status: str = "demo"  # demo | real | unavailable


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    url: str
    title: Optional[str] = None
    platform: Optional[str] = None
    domain: Optional[str] = None
    publication_date: Optional[str] = None
    date_found: datetime
    similarity_score: Optional[float] = None
    phash_distance: Optional[int] = None
    match_category: Optional[str] = None
    source_confidence: Optional[float] = None
    classification: Optional[str] = None
    reasoning: Optional[Any] = None
    accessible: bool = True
    inaccessible_reason: Optional[str] = None
    is_demo: bool = True
    thumbnail_url: Optional[str] = None
    thumbnail_is_placeholder: bool = False


class PropagationEdgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    from_node: str
    to_node: str
    edge_type: str


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    timestamp: datetime
    agent: str
    action: str
    detail: Optional[str] = None
    stage: Optional[str] = None
    progress: Optional[int] = None


class InvestigationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    state: str
    media_type: str
    original_filename: str
    demo_mode: bool
    verdict: Optional[str] = None
    confidence_label: Optional[str] = None
    overall_score: Optional[float] = None
    error_message: Optional[str] = None
    source_count: int = 0
    created_at: datetime
    updated_at: datetime


class InvestigationDetailOut(InvestigationOut):
    media_asset: Optional[MediaAssetOut] = None
    forensic_results: Optional[ForensicResultOut] = None
    ai_detection: Optional[AIDetectionOut] = None
    sources: List[SourceOut] = []
    propagation_edges: List[PropagationEdgeOut] = []
    events: List[EventOut] = []

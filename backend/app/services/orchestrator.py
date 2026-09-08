"""
Investigation orchestrator.

This module implements the exact decision workflow described in
openclaw/skills/*/SKILL.md (evidence preservation -> hashing -> metadata ->
AI detection -> forensics -> OSINT -> source verification -> propagation ->
correlation -> report), with the same branching rules an OpenClaw agent
following those skills would apply (broaden search if no candidates found,
verify strong candidates, stop expanding once confidence is sufficient,
degrade gracefully when a source is inaccessible, etc).

Two ways this logic gets driven, both real and both wired to the same
FastAPI tool endpoints:

1. **Native mode (this module)** -- used automatically so the MVP is fully
   runnable end-to-end without any external agent process attached. Useful
   for CI, tests, and the default demo.
2. **OpenClaw-driven mode** -- a real `openclaw` agent process, configured
   with workspace=openclaw/ (see openclaw/README.md), reads the SKILL.md
   files and calls the *same* /api/investigations/{id}/* endpoints as
   tools, using its own LLM reasoning for query formulation, source
   triage, and branching instead of the deterministic rules below. Set
   OPENCLAW_ENABLED=true to have new investigations wait for an external
   OpenClaw agent to drive them via the API instead of running natively.

Either way, OpenClaw is the orchestration/investigation layer described in
the skills, and the deterministic engine here is intentionally written to
mirror its documented branching logic 1:1, not to replace it.
"""
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from sqlalchemy.orm import Session

from app.config import settings, EVIDENCE_DIR, FRAMES_DIR
from app.models.investigation import (
    Investigation, MediaAsset, ForensicResult, AIDetection, Source,
    PropagationEdge, InvestigationEvent, Report,
)
from app.services import (
    hashing, metadata_service, image_forensics, video_forensics,
    perceptual_hash, ai_detection, source_search, source_verification,
    propagation, confidence, report as report_service,
)

STATES = [
    "UPLOADED", "HASHING", "METADATA_ANALYSIS", "AI_ANALYSIS", "FORENSIC_ANALYSIS",
    "ORIGIN_SEARCH", "SOURCE_VERIFICATION", "PROPAGATION_ANALYSIS", "CORRELATION",
    "REPORT_GENERATION", "COMPLETED", "FAILED", "PARTIAL",
]

TERMINAL_STATES = ("COMPLETED", "FAILED", "PARTIAL")

STAGE_PROGRESS = {
    "HASHING": 10, "METADATA_ANALYSIS": 20, "AI_ANALYSIS": 35, "FORENSIC_ANALYSIS": 50,
    "ORIGIN_SEARCH": 65, "SOURCE_VERIFICATION": 75, "PROPAGATION_ANALYSIS": 85,
    "CORRELATION": 92, "REPORT_GENERATION": 97, "COMPLETED": 100,
}

# The linear "driven" state progression used to validate that agent-tool
# calls arrive in the right order (see app/api/agent.py). Terminal states
# are reachable from any non-terminal state via the explicit /complete tool.
AGENT_STAGE_PRECONDITION = {
    "hash_metadata": "UPLOADED",
    "forensics_detection": "METADATA_ANALYSIS",
    "origin_search": "FORENSIC_ANALYSIS",
    "propagation": "SOURCE_VERIFICATION",
    "correlate": "PROPAGATION_ANALYSIS",
    "report": "CORRELATION",
}


def log_event(db: Session, inv: Investigation, agent: str, action: str, detail: str = None, stage: str = None):
    ev = InvestigationEvent(
        investigation_id=inv.id, agent=agent, action=action, detail=detail,
        stage=stage, progress=STAGE_PROGRESS.get(stage),
    )
    db.add(ev)
    inv.state = stage or inv.state
    db.commit()


def is_stalled(inv: Investigation) -> bool:
    """True if an OpenClaw-driven investigation has sat in a non-terminal
    state longer than OPENCLAW_STALL_TIMEOUT_SECONDS without progressing --
    i.e. the agent likely crashed, disconnected, or never started."""
    if settings.OPENCLAW_STALL_TIMEOUT_SECONDS <= 0:
        return False
    if inv.state in TERMINAL_STATES:
        return False
    updated_at = inv.updated_at
    if updated_at is None:
        return False
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    elapsed = (datetime.now(timezone.utc) - updated_at).total_seconds()
    return elapsed > settings.OPENCLAW_STALL_TIMEOUT_SECONDS


def mark_stalled_as_failed(db: Session, inv: Investigation) -> None:
    stalled_in_state = inv.state
    inv.state = "FAILED"
    inv.error_message = (
        f"No progress for over {settings.OPENCLAW_STALL_TIMEOUT_SECONDS}s while in state "
        f"'{stalled_in_state}'. The OpenClaw agent likely disconnected or crashed before "
        f"finishing this investigation."
    )
    db.commit()
    log_event(
        db, inv, "orchestrator",
        "Investigation marked FAILED: no agent progress within the stall timeout.",
        detail=inv.error_message,
    )


def run_investigation(db: Session, investigation_id: str) -> Investigation:
    inv = db.get(Investigation, investigation_id)
    if inv is None:
        raise ValueError("investigation not found")

    try:
        log_event(db, inv, "evidence-agent", "Evidence upload confirmed; original preserved unmodified.", stage="HASHING")
        asset = _stage_hash_and_metadata(db, inv)
        log_event(db, inv, "ai-detector-agent", "Running AI/manipulation detection.", stage="AI_ANALYSIS")
        forensics, detection = _stage_forensics_and_detection(db, inv, asset)
        log_event(db, inv, "osint-agent", "Generating search fingerprints and beginning origin search.", stage="ORIGIN_SEARCH")
        ranked_sources = _stage_origin_search(db, inv, asset)
        log_event(db, inv, "osint-agent", "Verifying candidate sources and scoring credibility.", stage="SOURCE_VERIFICATION")
        _stage_source_persist(db, inv, ranked_sources)
        log_event(db, inv, "correlation-agent", "Building propagation graph.", stage="PROPAGATION_ANALYSIS")
        _stage_propagation(db, inv, ranked_sources)
        log_event(db, inv, "correlation-agent", "Correlating all evidence into a final assessment.", stage="CORRELATION")
        _stage_correlate(db, inv, detection, forensics, ranked_sources)
        log_event(db, inv, "report-agent", "Generating forensic report.", stage="REPORT_GENERATION")
        _stage_report(db, inv)
        log_event(db, inv, "orchestrator", "Investigation completed.", stage="COMPLETED")
    except Exception as e:
        inv.state = "FAILED"
        inv.error_message = str(e)
        db.commit()
        log_event(db, inv, "orchestrator", "Investigation failed.", detail=str(e))
        raise
    return inv


# =====================================================================
# Fast-mode: AI detection, then (only if AI-generated) origin search.
# Skips metadata/forensics/propagation/report entirely -- built for a
# simple "is this AI, and if so who posted it first" flow, not the full
# forensic-report pipeline above.
# =====================================================================
FAST_STAGE_PROGRESS = {
    "HASHING": 20, "AI_ANALYSIS": 55, "ORIGIN_SEARCH": 80, "COMPLETED": 100,
}


def run_fast_investigation(db: Session, investigation_id: str) -> Investigation:
    inv = db.get(Investigation, investigation_id)
    if inv is None:
        raise ValueError("investigation not found")

    try:
        log_event(db, inv, "evidence-agent", "Evidence upload confirmed.", stage="HASHING")
        asset = _stage_hash_only(db, inv)

        log_event(db, inv, "ai-detector-agent", "Checking if image is AI-generated.", stage="AI_ANALYSIS")
        detection = _stage_ai_detection_only(db, inv, asset)

        is_ai = detection.classification in ("AI_GENERATED", "AI_ALTERED")

        ranked_sources: List[dict] = []
        if is_ai:
            log_event(db, inv, "osint-agent", "AI-generated image detected; searching for the first/original post.", stage="ORIGIN_SEARCH")
            ranked_sources = _stage_origin_search(db, inv, asset)
            _stage_source_persist(db, inv, ranked_sources)
        else:
            log_event(db, inv, "osint-agent", "Image not flagged as AI-generated; skipping origin search.")

        inv.verdict = detection.classification
        inv.confidence_label = confidence.confidence_label(detection.probability if detection.probability is not None else 0.0)
        inv.overall_score = detection.probability
        db.commit()

        log_event(db, inv, "orchestrator", "Investigation completed.", stage="COMPLETED")
    except Exception as e:
        inv.state = "FAILED"
        inv.error_message = str(e)
        db.commit()
        log_event(db, inv, "orchestrator", "Investigation failed.", detail=str(e))
        raise
    return inv


def _stage_hash_only(db: Session, inv: Investigation) -> MediaAsset:
    asset = inv.media_asset
    src = Path(asset.original_path)
    asset.sha256 = hashing.calculate_sha256(src)
    asset.size_bytes = hashing.file_size_bytes(src)
    db.commit()

    if inv.media_type == "image":
        hashes = perceptual_hash.compute_hashes(src)
        asset.phash, asset.dhash, asset.ahash = hashes["phash"], hashes["dhash"], hashes["ahash"]
    else:
        # still need a representative frame phash for video origin search
        frames_dir = Path(FRAMES_DIR) / inv.id
        frames = video_forensics.extract_frames(src, frames_dir, None)
        if frames:
            hashes = perceptual_hash.compute_hashes(frames[0])
            asset.phash = hashes["phash"]
    db.commit()
    return asset


def _stage_ai_detection_only(db: Session, inv: Investigation, asset: MediaAsset) -> AIDetection:
    src = Path(asset.original_path)
    detector = ai_detection.get_detector()

    if inv.media_type == "image":
        result = detector.analyze_image(src, {})
    else:
        frames_dir = Path(FRAMES_DIR) / inv.id
        frames = list(frames_dir.glob("*")) if frames_dir.exists() else []
        result = detector.analyze_video(src, {"frame_paths": [str(f) for f in frames]})

    detection = AIDetection(
        investigation_id=inv.id, classification=result.classification, probability=result.probability,
        confidence=result.confidence, model_name=result.model_name, signals=result.signals,
        is_demo=result.is_demo, detector_status=result.detector_status, heatmap_path=result.heatmap_path,
    )
    db.add(detection)
    db.commit()
    log_event(db, inv, "ai-detector-agent", f"Classification: {result.classification} ({round(result.probability * 100)}%, {result.confidence} confidence).")
    return detection


def _stage_hash_and_metadata(db: Session, inv: Investigation) -> MediaAsset:
    asset = inv.media_asset
    src = Path(asset.original_path)

    sha256 = hashing.calculate_sha256(src)
    size_bytes = hashing.file_size_bytes(src)
    asset.sha256 = sha256
    asset.size_bytes = size_bytes
    db.commit()
    log_event(db, inv, "evidence-agent", f"SHA-256 calculated: {sha256[:16]}...", stage="METADATA_ANALYSIS")

    if inv.media_type == "image":
        meta, gps_present, w, h = metadata_service.extract_image_metadata(src)
        asset.metadata_json = meta
        asset.gps_present = gps_present
        asset.width, asset.height = w, h
        hashes = perceptual_hash.compute_hashes(src)
        asset.phash, asset.dhash, asset.ahash = hashes["phash"], hashes["dhash"], hashes["ahash"]
    else:
        meta = metadata_service.extract_video_metadata(src)
        asset.metadata_json = meta
        asset.duration_seconds = meta.get("duration")
        asset.width, asset.height = meta.get("width"), meta.get("height")
        asset.gps_present = False

    db.commit()
    log_event(db, inv, "evidence-agent", "Metadata extraction complete.")
    return asset


def _stage_forensics_and_detection(db: Session, inv: Investigation, asset: MediaAsset):
    src = Path(asset.original_path)
    evidence_dir = Path(EVIDENCE_DIR) / inv.id
    evidence_dir.mkdir(parents=True, exist_ok=True)

    detector = ai_detection.get_detector()

    if inv.media_type == "image":
        ela_path = evidence_dir / "ela.png"
        ela_score = image_forensics.error_level_analysis(src, ela_path)
        noise_score = image_forensics.noise_analysis(src)
        resample_score = image_forensics.resampling_analysis(src)
        compression = image_forensics.compression_analysis(src)

        indicators = []
        if ela_score > 0.45:
            indicators.append("Elevated Error Level Analysis anomaly")
        if noise_score > 0.45:
            indicators.append("Inconsistent local noise pattern")
        if resample_score > 0.45:
            indicators.append("Possible resampling/interpolation artifacts")

        forensic_score = round((ela_score + noise_score + resample_score) / 3, 4)
        forensics = ForensicResult(
            investigation_id=inv.id, ela_artifact_path=str(ela_path), ela_score=ela_score,
            noise_score=noise_score, resampling_score=resample_score,
            compression_notes=compression, suspicious_indicators=indicators, forensic_score=forensic_score,
        )
        db.add(forensics)
        db.commit()

        signals = {"ela_score": ela_score, "noise_score": noise_score, "resampling_score": resample_score}
        result = detector.analyze_image(src, signals)
    else:
        frames_dir = Path(FRAMES_DIR) / inv.id
        frames = video_forensics.extract_frames(src, frames_dir, asset.duration_seconds)
        frame_analysis = video_forensics.analyze_frames(frames, evidence_dir / "frames_ela")
        avg_ela = (sum(f["ela_score"] for f in frame_analysis["per_frame"]) / len(frame_analysis["per_frame"])) if frame_analysis["per_frame"] else 0.0
        avg_noise = (sum(f["noise_score"] for f in frame_analysis["per_frame"]) / len(frame_analysis["per_frame"])) if frame_analysis["per_frame"] else 0.0
        avg_resample = (sum(f["resampling_score"] for f in frame_analysis["per_frame"]) / len(frame_analysis["per_frame"])) if frame_analysis["per_frame"] else 0.0
        forensic_score = round((avg_ela + avg_noise + avg_resample) / 3, 4)

        indicators = []
        if frame_analysis["suspicious_frames"]:
            indicators.append(f"{len(frame_analysis['suspicious_frames'])} suspicious frame(s) detected")

        forensics = ForensicResult(
            investigation_id=inv.id, ela_score=avg_ela, noise_score=avg_noise,
            resampling_score=avg_resample, frame_analysis=frame_analysis,
            suspicious_indicators=indicators, forensic_score=forensic_score,
        )
        db.add(forensics)
        db.commit()

        # use first frame's phash as the representative perceptual hash for OSINT
        if frames:
            hashes = perceptual_hash.compute_hashes(frames[0])
            asset.phash = hashes["phash"]
        # frame_analysis only carries per-frame filenames (not full paths);
        # thread the real extracted-frame paths through separately so a
        # real detector (HFImageDetector) can actually load frame pixels.
        signals = {"frame_analysis": frame_analysis, "frame_paths": [str(f) for f in frames]}
        result = detector.analyze_video(src, signals)

    detection = AIDetection(
        investigation_id=inv.id, classification=result.classification, probability=result.probability,
        confidence=result.confidence, model_name=result.model_name, signals=result.signals,
        is_demo=result.is_demo, detector_status=result.detector_status, heatmap_path=result.heatmap_path,
    )
    db.add(detection)
    db.commit()
    log_event(db, inv, "forensics-agent", f"Forensic score: {forensic_score}. {len(indicators)} indicator(s).", stage="FORENSIC_ANALYSIS")
    log_event(db, inv, "ai-detector-agent", f"Classification: {result.classification} ({result.probability}, {result.confidence} confidence).")
    return forensics, detection


def _score_candidates(asset: MediaAsset, candidates: List["source_search.CandidateSource"]) -> List[dict]:
    """
    Deterministic scoring shared by both the native provider-driven search
    and the agent-submitted-candidates path. Never invents a candidate --
    only scores/ranks candidates it is given.
    """
    scored = []
    for c in candidates:
        similarity, distance = 0.0, 64
        if asset.phash and c.candidate_phash:
            distance = perceptual_hash.hamming_distance(asset.phash, c.candidate_phash)
            similarity = perceptual_hash.similarity_score(asset.phash, c.candidate_phash)
        match_category = perceptual_hash.classify_match(distance)

        looks_like_repost = c.platform in ("Facebook", "Instagram") and similarity < 0.9
        conf, reasoning = source_verification.score_candidate(
            publication_date=c.publication_date,
            similarity=similarity,
            is_demo=c.is_demo,
            has_metadata=True,
            appears_independent=not looks_like_repost,
            looks_like_repost=looks_like_repost,
        )
        classification = source_verification.classify_confidence(conf)
        scored.append({
            "url": c.url, "title": c.title, "platform": c.platform, "domain": c.domain,
            "publication_date": c.publication_date, "similarity_score": similarity,
            "phash_distance": distance, "match_category": match_category,
            "source_confidence": conf, "classification": classification, "reasoning": reasoning,
            "accessible": c.accessible, "inaccessible_reason": c.inaccessible_reason,
            "is_demo": c.is_demo,
            "thumbnail_url": c.thumbnail_url, "thumbnail_is_placeholder": c.thumbnail_is_placeholder,
        })
    return source_verification.rank_sources(scored)


def _stage_origin_search(db: Session, inv: Investigation, asset: MediaAsset) -> List[dict]:
    """
    Native-mode origin search. Mirrors origin-investigator SKILL.md branching:
    - build search fingerprints (filename, phash)
    - search; if nothing found, broaden query
    - stop expanding once confidence threshold is met
    """
    image_url = f"{settings.OPENCLAW_BACKEND_BASE_URL}/api/investigations/{inv.id}/original" if inv.media_type == "image" else None
    # Prefer the on-disk path (asset.original_path) so real providers like
    # PicImageSearchProvider can read the file directly instead of needing
    # to fetch it back over HTTP -- image_url is kept as a fallback for
    # providers (e.g. MrisaSourceProvider) that require a fetchable URL.
    image_path = asset.original_path if inv.media_type == "image" else None
    provider = source_search.get_source_provider(image_url=image_url, image_path=image_path)
    queries = _build_queries(inv)

    candidates = provider.search(queries, asset.phash or "")
    if not candidates:
        log_event(db, inv, "osint-agent", "No candidates on first pass; broadening search query.")
        candidates = provider.search(["media forensic investigation"], asset.phash or "")

    if not provider.reverse_image_search_available:
        log_event(db, inv, "osint-agent", "True reverse-image search unavailable; performed web/text similarity search instead.")

    ranked = _score_candidates(asset, candidates)
    if ranked and ranked[0]["source_confidence"] >= settings.SOURCE_CONFIDENCE_STOP_THRESHOLD:
        log_event(db, inv, "osint-agent", "Strong candidate source found; verification threshold met, stopping search expansion.")
    log_event(db, inv, "osint-agent", f"{len(ranked)} candidate source(s) ranked.")
    return ranked


def _build_queries(inv: Investigation) -> List[str]:
    base = Path(inv.original_filename).stem.replace("_", " ").replace("-", " ")
    queries = [base] if base and not base.lower().startswith(("img", "screenshot", "video", "vid")) else []
    queries.append(f"{inv.media_type} investigation {inv.original_filename}")
    return queries or ["uploaded media"]


def _stage_source_persist(db: Session, inv: Investigation, ranked_sources: List[dict]):
    for s in ranked_sources:
        # Agent-submitted candidates (see api/agent.py) don't carry a
        # thumbnail at all -- fall back to the same generic placeholder used
        # elsewhere so the UI never shows a broken-image box, but still
        # flagged as non-evidentiary. See PLACEHOLDER_THUMBNAIL_URL in
        # source_search.py. Native-provider candidates already have both
        # fields set (real thumbnail or placeholder) by the time they reach
        # this dict, via _score_candidates.
        thumbnail_url = s.get("thumbnail_url")
        thumbnail_is_placeholder = s.get("thumbnail_is_placeholder", False)
        if not thumbnail_url:
            thumbnail_url = source_search.PLACEHOLDER_THUMBNAIL_URL
            thumbnail_is_placeholder = True

        row = Source(
            investigation_id=inv.id, url=s["url"], title=s["title"], platform=s["platform"],
            domain=s["domain"], publication_date=s["publication_date"],
            similarity_score=s["similarity_score"], phash_distance=s["phash_distance"],
            match_category=s["match_category"], source_confidence=s["source_confidence"],
            classification=s["classification"], reasoning=s["reasoning"],
            accessible=s["accessible"], inaccessible_reason=s["inaccessible_reason"], is_demo=s["is_demo"],
            thumbnail_url=thumbnail_url, thumbnail_is_placeholder=thumbnail_is_placeholder,
        )
        db.add(row)
    db.commit()
    # attach DB ids back onto the ranked_sources list for the propagation stage
    persisted = db.query(Source).filter(Source.investigation_id == inv.id).all()
    by_url = {p.url: p.id for p in persisted}
    for s in ranked_sources:
        s["id"] = by_url.get(s["url"])


def _stage_propagation(db: Session, inv: Investigation, ranked_sources: List[dict]):
    edges = propagation.build_graph(inv.id, ranked_sources)
    for e in edges:
        db.add(PropagationEdge(investigation_id=inv.id, from_node=e["from_node"], to_node=e["to_node"], edge_type=e["edge_type"]))
    db.commit()
    log_event(db, inv, "correlation-agent", f"{len(edges)} propagation edge(s) generated.")


def _stage_correlate(db: Session, inv: Investigation, detection: AIDetection, forensics: ForensicResult, ranked_sources: List[dict]):
    best_source_conf = ranked_sources[0]["source_confidence"] if ranked_sources else None
    best_similarity = ranked_sources[0]["similarity_score"] if ranked_sources else None
    forensic_score = forensics.forensic_score or 0.0

    # AI-detection evidence is only used when a detector actually produced
    # a usable result (real or demo). When the real detector reported
    # NOT_AVAILABLE, it is excluded from scoring entirely instead of being
    # backfilled with forensic signals pretending to be an AI probability.
    ai_available = getattr(detection, "detector_status", "demo") != "unavailable"

    overall = confidence.compute_overall_score(
        forensic_score=forensic_score,
        ai_probability=detection.probability if ai_available else None,
        ai_detection_available=ai_available,
        best_source_confidence=best_source_conf,
        best_similarity=best_similarity,
    )
    inv.overall_score = overall
    inv.confidence_label = confidence.confidence_label(overall)
    inv.verdict = confidence.derive_verdict(
        detection.classification, overall,
        ai_detection_available=ai_available,
        forensic_score=forensic_score,
    )
    db.commit()
    log_event(db, inv, "correlation-agent", f"Verdict: {inv.verdict}, overall confidence: {inv.confidence_label} ({overall}).")


def _stage_report(db: Session, inv: Investigation):
    content = report_service.build_report(inv)
    row = Report(investigation_id=inv.id, content_json=content)
    db.add(row)
    db.commit()


# =====================================================================
# Agent-driven stage entrypoints
# =====================================================================
# These are the functions app/api/agent.py calls for each narrow tool
# endpoint. Each one performs exactly one deterministic backend
# computation and advances investigation state -- they are the same
# underlying service calls run_investigation() above uses natively, just
# invoked one at a time by an external caller (the OpenClaw/Crestodian
# agent) instead of run end-to-end in a single background task. No
# forensic/OSINT-scoring logic is duplicated: everything here delegates
# to the exact same _stage_* / service functions.

def ranked_sources_from_db(inv: Investigation) -> List[dict]:
    """Rebuilds the ranked_sources dict shape (id/platform/similarity_score/
    source_confidence/publication_date) that propagation.build_graph() and
    the correlation step expect, from whatever Source rows are currently
    persisted for this investigation. Used by the agent-driven propagation
    and correlate stages, which run as separate HTTP calls and therefore
    can't rely on an in-memory list from the origin-search step."""
    sources = [
        {
            "id": s.id, "platform": s.platform, "similarity_score": s.similarity_score,
            "source_confidence": s.source_confidence, "publication_date": s.publication_date,
        }
        for s in inv.sources
    ]
    return source_verification.rank_sources(sources)


def agent_stage_hash_metadata(db: Session, inv: Investigation) -> MediaAsset:
    log_event(db, inv, "evidence-agent", "Evidence upload confirmed; original preserved unmodified.", stage="HASHING")
    return _stage_hash_and_metadata(db, inv)


def agent_stage_forensics_detection(db: Session, inv: Investigation, asset: MediaAsset):
    log_event(db, inv, "ai-detector-agent", "Running AI/manipulation detection.", stage="AI_ANALYSIS")
    return _stage_forensics_and_detection(db, inv, asset)


def agent_stage_origin_search(
    db: Session, inv: Investigation, asset: MediaAsset,
    candidates: List["source_search.CandidateSource"],
) -> List[dict]:
    """
    Agent-submitted-candidates version of origin search. The OpenClaw
    origin-investigator skill performs the actual OSINT reasoning (web
    search/browsing) and submits the candidate sources it found; this
    function only ever scores/ranks/persists candidates it is given -- it
    never invents URLs, dates, or authors itself.
    """
    log_event(db, inv, "osint-agent", "Generating search fingerprints and beginning origin search.", stage="ORIGIN_SEARCH")
    ranked = _score_candidates(asset, candidates)
    if ranked and ranked[0]["source_confidence"] >= settings.SOURCE_CONFIDENCE_STOP_THRESHOLD:
        log_event(db, inv, "osint-agent", "Strong candidate source found; verification threshold met.")
    log_event(db, inv, "osint-agent", f"{len(ranked)} candidate source(s) ranked.", stage="SOURCE_VERIFICATION")
    _stage_source_persist(db, inv, ranked)
    return ranked


def agent_stage_propagation(db: Session, inv: Investigation) -> List[dict]:
    log_event(db, inv, "correlation-agent", "Building propagation graph.", stage="PROPAGATION_ANALYSIS")
    ranked_sources = ranked_sources_from_db(inv)
    _stage_propagation(db, inv, ranked_sources)
    return ranked_sources


def agent_stage_correlate(db: Session, inv: Investigation):
    log_event(db, inv, "correlation-agent", "Correlating all evidence into a final assessment.", stage="CORRELATION")
    detection = inv.ai_detection
    forensics = inv.forensic_results
    if detection is None or forensics is None:
        raise ValueError("AI detection and forensic results must exist before correlation.")
    ranked_sources = ranked_sources_from_db(inv)
    _stage_correlate(db, inv, detection, forensics, ranked_sources)
    return inv


def agent_stage_report(db: Session, inv: Investigation):
    log_event(db, inv, "report-agent", "Generating forensic report.", stage="REPORT_GENERATION")
    _stage_report(db, inv)
    return inv.report


def agent_complete_investigation(
    db: Session, inv: Investigation, status: str, agent: str, reason: Optional[str] = None,
) -> Investigation:
    """Explicit terminal-state transition, driven by the agent (e.g. the
    evidence-correlator / forensic-report-generator skill deciding the
    investigation is done, or any skill deciding it can't continue)."""
    if status not in TERMINAL_STATES:
        raise ValueError(f"status must be one of {TERMINAL_STATES}")
    if status in ("FAILED", "PARTIAL"):
        inv.error_message = reason or inv.error_message
        db.commit()
    log_event(
        db, inv, agent,
        f"Investigation marked {status} by agent." + (f" Reason: {reason}" if reason else ""),
        detail=reason, stage=status,
    )
    return inv

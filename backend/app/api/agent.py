"""
Agent tool endpoints -- the narrow HTTP surface an external OpenClaw agent
(crestodian) uses to drive an investigation forward one deterministic stage
at a time.

Design:
- Every endpoint here wraps exactly one existing deterministic service call
  (see app/services/orchestrator.py's agent_stage_* functions). No forensic
  computation, scoring, or ranking logic is duplicated or reimplemented --
  this file is pure HTTP plumbing plus state-machine validation.
- Endpoints only ever accept structured data the agent claims to have found
  (candidate source URLs, its own narrative log lines). They never accept
  arbitrary code, shell commands, or filesystem paths.
- Every mutating call validates investigation_id exists and that the
  investigation is in the expected precondition state for that stage,
  returning 409 Conflict (not a silent no-op or a duplicate side effect)
  if it's not -- this keeps retries/duplicate calls from double-persisting
  sources, edges, or events.
- Gated by require_agent_token (no-op if OPENCLAW_API_TOKEN isn't set).
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.investigation import Investigation
from app.schemas.agent import (
    AgentOriginSearchIn, AgentEventIn, AgentCompleteIn, AgentStageAck,
)
from app.schemas.investigation import (
    MediaAssetOut, ForensicResultOut, AIDetectionOut, SourceOut, PropagationEdgeOut, InvestigationOut,
)
from app.services import orchestrator
from app.services.agent_auth import require_agent_token
from app.services.source_search import CandidateSource

router = APIRouter(
    prefix="/api/investigations/{investigation_id}/agent",
    tags=["agent"],
    dependencies=[Depends(require_agent_token)],
)


def _get_investigation_or_404(investigation_id: str, db: Session) -> Investigation:
    inv = db.get(Investigation, investigation_id)
    if inv is None:
        raise HTTPException(404, "Investigation not found")
    return inv


def _require_state(inv: Investigation, expected: str, stage_name: str) -> None:
    if inv.state != expected:
        raise HTTPException(
            409,
            f"Cannot run '{stage_name}': investigation {inv.id} is in state '{inv.state}', "
            f"expected '{expected}'. Either this stage already ran, or an earlier stage hasn't.",
        )


def _fail_investigation(db: Session, inv: Investigation, agent: str, exc: Exception) -> None:
    orchestrator.log_event(db, inv, agent, "Stage failed with an error.", detail=str(exc))
    inv.state = "FAILED"
    inv.error_message = str(exc)
    db.commit()


@router.post("/hash-metadata", response_model=MediaAssetOut)
def hash_metadata(investigation_id: str, db: Session = Depends(get_db)):
    inv = _get_investigation_or_404(investigation_id, db)
    _require_state(inv, "UPLOADED", "hash-metadata")
    try:
        asset = orchestrator.agent_stage_hash_metadata(db, inv)
    except Exception as e:
        _fail_investigation(db, inv, "evidence-agent", e)
        raise HTTPException(500, f"hash-metadata stage failed: {e}")
    return asset


@router.post("/forensics-detection")
def forensics_detection(investigation_id: str, db: Session = Depends(get_db)):
    inv = _get_investigation_or_404(investigation_id, db)
    _require_state(inv, "METADATA_ANALYSIS", "forensics-detection")
    asset = inv.media_asset
    try:
        forensics, detection = orchestrator.agent_stage_forensics_detection(db, inv, asset)
    except Exception as e:
        _fail_investigation(db, inv, "forensics-agent", e)
        raise HTTPException(500, f"forensics-detection stage failed: {e}")
    return {
        "forensics": ForensicResultOut.model_validate(forensics),
        "detection": AIDetectionOut.model_validate(detection),
    }


@router.post("/origin-search", response_model=list[SourceOut])
def origin_search(investigation_id: str, payload: AgentOriginSearchIn, db: Session = Depends(get_db)):
    inv = _get_investigation_or_404(investigation_id, db)
    _require_state(inv, "FORENSIC_ANALYSIS", "origin-search")
    asset = inv.media_asset

    if payload.queries_used:
        orchestrator.log_event(
            db, inv, "osint-agent",
            f"Origin-investigator queries: {', '.join(payload.queries_used)}",
        )

    candidates = [
        CandidateSource(
            url=c.url, title=c.title, platform=c.platform, domain=c.domain,
            publication_date=c.publication_date or "unknown",
            accessible=c.accessible, inaccessible_reason=c.inaccessible_reason,
            is_demo=payload.is_demo, candidate_phash=c.candidate_phash,
        )
        for c in payload.candidates
    ]

    try:
        orchestrator.agent_stage_origin_search(db, inv, asset, candidates)
    except Exception as e:
        _fail_investigation(db, inv, "osint-agent", e)
        raise HTTPException(500, f"origin-search stage failed: {e}")

    db.refresh(inv)
    return sorted(inv.sources, key=lambda s: -(s.source_confidence or 0))


@router.post("/propagation", response_model=list[PropagationEdgeOut])
def propagation_stage(investigation_id: str, db: Session = Depends(get_db)):
    inv = _get_investigation_or_404(investigation_id, db)
    _require_state(inv, "SOURCE_VERIFICATION", "propagation")
    try:
        orchestrator.agent_stage_propagation(db, inv)
    except Exception as e:
        _fail_investigation(db, inv, "correlation-agent", e)
        raise HTTPException(500, f"propagation stage failed: {e}")
    db.refresh(inv)
    return inv.propagation_edges


@router.post("/correlate", response_model=InvestigationOut)
def correlate_stage(investigation_id: str, db: Session = Depends(get_db)):
    inv = _get_investigation_or_404(investigation_id, db)
    _require_state(inv, "PROPAGATION_ANALYSIS", "correlate")
    try:
        orchestrator.agent_stage_correlate(db, inv)
    except Exception as e:
        _fail_investigation(db, inv, "correlation-agent", e)
        raise HTTPException(500, f"correlate stage failed: {e}")
    db.refresh(inv)
    return inv


@router.post("/report", response_model=InvestigationOut)
def report_stage(investigation_id: str, db: Session = Depends(get_db)):
    inv = _get_investigation_or_404(investigation_id, db)
    _require_state(inv, "CORRELATION", "report")
    try:
        orchestrator.agent_stage_report(db, inv)
    except Exception as e:
        _fail_investigation(db, inv, "report-agent", e)
        raise HTTPException(500, f"report stage failed: {e}")
    db.refresh(inv)
    return inv


@router.post("/events", response_model=AgentStageAck)
def log_agent_event(investigation_id: str, payload: AgentEventIn, db: Session = Depends(get_db)):
    """Free-form progress/reasoning narration from any skill -- does not by
    itself advance the state machine unless `stage` names a valid state."""
    inv = _get_investigation_or_404(investigation_id, db)
    if payload.stage is not None and payload.stage not in orchestrator.STATES:
        raise HTTPException(400, f"Unknown stage '{payload.stage}'. Must be one of {orchestrator.STATES}")
    orchestrator.log_event(db, inv, payload.agent, payload.action, detail=payload.detail, stage=payload.stage)
    db.refresh(inv)
    return AgentStageAck(investigation_id=inv.id, state=inv.state, message="Event recorded.")


@router.post("/complete", response_model=InvestigationOut)
def complete_stage(investigation_id: str, payload: AgentCompleteIn, db: Session = Depends(get_db)):
    inv = _get_investigation_or_404(investigation_id, db)
    if inv.state in orchestrator.TERMINAL_STATES:
        raise HTTPException(409, f"Investigation {inv.id} is already in terminal state '{inv.state}'.")
    if payload.status not in orchestrator.TERMINAL_STATES:
        raise HTTPException(400, f"status must be one of {orchestrator.TERMINAL_STATES}")
    if payload.status == "COMPLETED" and inv.state != "REPORT_GENERATION":
        raise HTTPException(
            409,
            f"Cannot mark COMPLETED: report has not been generated yet (state is '{inv.state}'). "
            f"Use PARTIAL or FAILED with a reason if the investigation cannot continue.",
        )
    try:
        orchestrator.agent_complete_investigation(
            db, inv, payload.status, payload.agent, payload.reason,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.refresh(inv)
    return inv

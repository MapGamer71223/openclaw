import asyncio
import logging
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.config import settings, EVIDENCE_DIR
from app.database import get_db
from app.models.investigation import Investigation, MediaAsset, InvestigationEvent
from app.schemas.investigation import InvestigationOut, InvestigationDetailOut
from app.services import orchestrator, openclaw_bridge
from app.services.hashing import calculate_sha256, file_size_bytes
from app.services.image_forensics import image_dimensions

logger = logging.getLogger("investigations")

router = APIRouter(prefix="/api/investigations", tags=["investigations"])


def _classify_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in settings.ALLOWED_IMAGE_EXTENSIONS:
        return "image"
    if ext in settings.ALLOWED_VIDEO_EXTENSIONS:
        return "video"
    raise HTTPException(400, f"Unsupported file extension '{ext}'. Allowed: "
                              f"{sorted(settings.ALLOWED_IMAGE_EXTENSIONS | settings.ALLOWED_VIDEO_EXTENSIONS)}")


@router.post("", response_model=InvestigationOut)
async def create_investigation(background_tasks: BackgroundTasks, file: UploadFile = File(...), db: Session = Depends(get_db)):
    media_type = _classify_extension(file.filename)

    allowed_mime = settings.ALLOWED_IMAGE_MIME if media_type == "image" else settings.ALLOWED_VIDEO_MIME
    if file.content_type and file.content_type not in allowed_mime:
        # Some browsers/tools send generic mimetypes; don't hard-fail on this alone,
        # but do record a note. Extension check above is the authoritative gate.
        pass

    inv = Investigation(state="UPLOADED", media_type=media_type, original_filename=file.filename, demo_mode=settings.DEMO_MODE)
    db.add(inv)
    db.commit()
    db.refresh(inv)

    evidence_dir = Path(EVIDENCE_DIR) / inv.id
    evidence_dir.mkdir(parents=True, exist_ok=True)
    dest_path = evidence_dir / f"original{Path(file.filename).suffix.lower()}"

    size = 0
    max_bytes = settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024
    with open(dest_path, "wb") as out:
        while chunk := await file.read(1024 * 1024):
            size += len(chunk)
            if size > max_bytes:
                out.close()
                dest_path.unlink(missing_ok=True)
                db.delete(inv)
                db.commit()
                raise HTTPException(413, f"File exceeds maximum size of {settings.MAX_UPLOAD_SIZE_MB}MB")
            out.write(chunk)

    if size == 0:
        db.delete(inv)
        db.commit()
        raise HTTPException(400, "Uploaded file is empty")

    width = height = None
    if media_type == "image":
        try:
            width, height = image_dimensions(dest_path)
        except Exception:
            raise HTTPException(400, "File could not be read as a valid image")

    asset = MediaAsset(
        investigation_id=inv.id, original_path=str(dest_path),
        sha256="", size_bytes=size, mime_type=file.content_type or "application/octet-stream",
        width=width, height=height,
    )
    db.add(asset)
    db.commit()

    orchestrator.log_event(db, inv, "evidence-agent", "Evidence received and stored.", stage="UPLOADED")

    db.refresh(inv)
    return inv


@router.post("/{investigation_id}/start", response_model=InvestigationOut)
def start_investigation(investigation_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    inv = db.get(Investigation, investigation_id)
    if inv is None:
        raise HTTPException(404, "Investigation not found")
    if inv.state not in ("UPLOADED", "FAILED"):
        raise HTTPException(400, f"Investigation already in state {inv.state}")

    # Reset a previously-failed investigation back to UPLOADED before
    # re-dispatching/re-running, so both paths below start from a clean,
    # well-defined precondition state.
    if inv.state == "FAILED":
        inv.state = "UPLOADED"
        inv.error_message = None
        db.commit()

    if settings.OPENCLAW_ENABLED:
        # OPENCLAW_ENABLED=true: do NOT run the native orchestrator. Leave
        # the investigation in UPLOADED and hand off to the external
        # crestodian agent, which drives it forward via /agent/* below.
        # There is no silent fallback to native mode here -- a failed
        # dispatch either marks the investigation FAILED or, only if
        # OPENCLAW_ALLOW_NATIVE_FALLBACK=true, explicitly logs the fallback
        # and runs natively so it's visible in the investigation timeline.
        background_tasks.add_task(_dispatch_openclaw_in_background, investigation_id)
    else:
        background_tasks.add_task(_run_native_in_background, investigation_id)

    return inv


def _run_native_in_background(investigation_id: str):
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        orchestrator.run_investigation(db, investigation_id)
    except Exception:
        pass  # error already recorded on the investigation by run_investigation
    finally:
        db.close()


@router.post("/{investigation_id}/start-fast", response_model=InvestigationOut)
def start_fast_investigation(investigation_id: str, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Simplified flow: AI-detection only, then (only if AI-generated) origin
    search for the earliest post. Skips metadata/forensics/propagation/
    report. Always runs natively -- OpenClaw dispatch is not used for this
    fast path.
    """
    inv = db.get(Investigation, investigation_id)
    if inv is None:
        raise HTTPException(404, "Investigation not found")
    if inv.state not in ("UPLOADED", "FAILED"):
        raise HTTPException(400, f"Investigation already in state {inv.state}")

    if inv.state == "FAILED":
        inv.state = "UPLOADED"
        inv.error_message = None
        db.commit()

    background_tasks.add_task(_run_fast_in_background, investigation_id)
    return inv


def _run_fast_in_background(investigation_id: str):
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        orchestrator.run_fast_investigation(db, investigation_id)
    except Exception:
        pass  # error already recorded on the investigation by run_fast_investigation
    finally:
        db.close()


async def _dispatch_openclaw_in_background(investigation_id: str):
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        inv = db.get(Investigation, investigation_id)
        if inv is None:
            return
        try:
            result = await openclaw_bridge.dispatch_to_openclaw(investigation_id)
            orchestrator.log_event(
                db, inv, "openclaw-agent",
                f"Dispatched investigation to '{result['agent']}'. Output log: {result['log_path']}",
                detail=f"pid={result['pid']} workspace={result['workspace']} log={result['log_path']}",
                stage="UPLOADED",
            )
        except openclaw_bridge.DispatchError as e:
            logger.error("Failed to dispatch investigation %s to OpenClaw: %s", investigation_id, e)
            if settings.OPENCLAW_ALLOW_NATIVE_FALLBACK:
                orchestrator.log_event(
                    db, inv, "orchestrator",
                    "OpenClaw dispatch failed; OPENCLAW_ALLOW_NATIVE_FALLBACK=true, "
                    "falling back to the native orchestrator.",
                    detail=str(e),
                )
                try:
                    orchestrator.run_investigation(db, investigation_id)
                except Exception:
                    pass  # error already recorded on the investigation by run_investigation
            else:
                inv.state = "FAILED"
                inv.error_message = f"OpenClaw dispatch failed: {e}"
                db.commit()
                orchestrator.log_event(
                    db, inv, "orchestrator", "Investigation failed: could not dispatch to OpenClaw.",
                    detail=str(e),
                )
        except Exception as e:
            # Defense in depth: openclaw_bridge.dispatch_to_openclaw should
            # only ever raise DispatchError, but background_tasks callbacks
            # run outside the request/response cycle -- any exception that
            # escapes here becomes an uncaught ASGI background-task
            # traceback instead of a recorded investigation failure. Never
            # let that happen; always land on FAILED with a message instead.
            logger.exception(
                "Unexpected error dispatching investigation %s to OpenClaw", investigation_id
            )
            inv.state = "FAILED"
            inv.error_message = f"OpenClaw dispatch failed unexpectedly: {e}"
            db.commit()
            orchestrator.log_event(
                db, inv, "orchestrator",
                "Investigation failed: unexpected error dispatching to OpenClaw.",
                detail=str(e),
            )
    finally:
        db.close()


@router.get("", response_model=list[InvestigationOut])
def list_investigations(db: Session = Depends(get_db)):
    return db.query(Investigation).order_by(Investigation.created_at.desc()).all()


@router.get("/{investigation_id}", response_model=InvestigationDetailOut)
def get_investigation(investigation_id: str, db: Session = Depends(get_db)):
    inv = db.get(Investigation, investigation_id)
    if inv is None:
        raise HTTPException(404, "Investigation not found")
    if orchestrator.is_stalled(inv):
        orchestrator.mark_stalled_as_failed(db, inv)
        db.refresh(inv)
    return inv


@router.get("/{investigation_id}/status")
def get_status(investigation_id: str, db: Session = Depends(get_db)):
    inv = db.get(Investigation, investigation_id)
    if inv is None:
        raise HTTPException(404, "Investigation not found")
    if orchestrator.is_stalled(inv):
        orchestrator.mark_stalled_as_failed(db, inv)
        db.refresh(inv)
    events = (
        db.query(InvestigationEvent)
        .filter(InvestigationEvent.investigation_id == investigation_id)
        .order_by(InvestigationEvent.timestamp)
        .all()
    )
    return {
        "state": inv.state,
        "error_message": inv.error_message,
        "events": [
            {"timestamp": e.timestamp.isoformat(), "agent": e.agent, "action": e.action,
             "detail": e.detail, "stage": e.stage, "progress": e.progress}
            for e in events
        ],
    }


@router.get("/{investigation_id}/forensics")
def get_forensics(investigation_id: str, db: Session = Depends(get_db)):
    inv = db.get(Investigation, investigation_id)
    if inv is None or inv.forensic_results is None:
        raise HTTPException(404, "Forensic results not available yet")
    return inv.forensic_results


@router.get("/{investigation_id}/detections")
def get_detections(investigation_id: str, db: Session = Depends(get_db)):
    inv = db.get(Investigation, investigation_id)
    if inv is None or inv.ai_detection is None:
        raise HTTPException(404, "Detection results not available yet")
    return inv.ai_detection


@router.get("/{investigation_id}/sources")
def get_sources(investigation_id: str, db: Session = Depends(get_db)):
    inv = db.get(Investigation, investigation_id)
    if inv is None:
        raise HTTPException(404, "Investigation not found")
    return sorted(inv.sources, key=lambda s: -(s.source_confidence or 0))


@router.get("/{investigation_id}/timeline")
def get_timeline(investigation_id: str, db: Session = Depends(get_db)):
    inv = db.get(Investigation, investigation_id)
    if inv is None:
        raise HTTPException(404, "Investigation not found")
    return sorted(
        [{"url": s.url, "platform": s.platform, "date": s.publication_date, "confidence": s.source_confidence}
         for s in inv.sources],
        key=lambda s: s["date"] or "9999",
    )


@router.get("/{investigation_id}/graph")
def get_graph(investigation_id: str, db: Session = Depends(get_db)):
    inv = db.get(Investigation, investigation_id)
    if inv is None:
        raise HTTPException(404, "Investigation not found")
    nodes = []
    node_ids = set()
    best = max(inv.sources, key=lambda s: s.source_confidence or 0) if inv.sources else None

    if best is not None:
        root_id = f"source:{best.id}"
        nodes.append({
            "id": root_id, "type": "source", "platform": best.platform, "url": best.url,
            "timestamp": best.publication_date, "similarity_score": 1.0,
            "evidence_confidence": best.source_confidence,
        })
        node_ids.add(root_id)

    for s in inv.sources:
        if best is not None and s.id == best.id:
            continue  # already represented as the root "source" node
        node_type = "post" if s.platform in ("X", "Facebook", "Instagram", "Reddit") else "article"
        node_id = f"{node_type}:{s.id}"
        if node_id not in node_ids:
            nodes.append({
                "id": node_id, "type": node_type, "platform": s.platform, "url": s.url,
                "timestamp": s.publication_date, "similarity_score": s.similarity_score,
                "evidence_confidence": s.source_confidence,
            })
            node_ids.add(node_id)
    edges = [{"from": e.from_node, "to": e.to_node, "type": e.edge_type} for e in inv.propagation_edges]
    return {"nodes": nodes, "edges": edges}


@router.get("/{investigation_id}/report")
def get_report(investigation_id: str, db: Session = Depends(get_db)):
    inv = db.get(Investigation, investigation_id)
    if inv is None or inv.report is None:
        raise HTTPException(404, "Report not available yet")
    return inv.report.content_json


@router.get("/{investigation_id}/artifacts/ela")
def get_ela_artifact(investigation_id: str, db: Session = Depends(get_db)):
    inv = db.get(Investigation, investigation_id)
    if inv is None or inv.forensic_results is None or not inv.forensic_results.ela_artifact_path:
        raise HTTPException(404, "ELA artifact not available")
    path = Path(inv.forensic_results.ela_artifact_path)
    if not path.exists():
        raise HTTPException(404, "ELA artifact file missing on disk")
    return FileResponse(path, media_type="image/png")


@router.get("/{investigation_id}/original")
def get_original(investigation_id: str, db: Session = Depends(get_db)):
    inv = db.get(Investigation, investigation_id)
    if inv is None or inv.media_asset is None:
        raise HTTPException(404, "Investigation not found")
    path = Path(inv.media_asset.original_path)
    if not path.exists():
        raise HTTPException(404, "Original evidence file missing on disk")
    return FileResponse(path, media_type=inv.media_asset.mime_type)


@router.websocket("/ws/{investigation_id}")
async def investigation_ws(websocket: WebSocket, investigation_id: str):
    await websocket.accept()
    from app.database import SessionLocal
    sent_count = 0
    try:
        while True:
            db = SessionLocal()
            inv = db.get(Investigation, investigation_id)
            if inv is None:
                await websocket.send_json({"error": "not found"})
                db.close()
                break
            if orchestrator.is_stalled(inv):
                orchestrator.mark_stalled_as_failed(db, inv)
                db.refresh(inv)
            events = (
                db.query(InvestigationEvent)
                .filter(InvestigationEvent.investigation_id == investigation_id)
                .order_by(InvestigationEvent.timestamp)
                .all()
            )
            for e in events[sent_count:]:
                await websocket.send_json({
                    "stage": e.stage, "progress": e.progress, "agent": e.agent,
                    "action": e.action, "detail": e.detail, "message": e.action,
                })
            sent_count = len(events)
            terminal = inv.state in ("COMPLETED", "FAILED", "PARTIAL")
            db.close()
            if terminal:
                break
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass

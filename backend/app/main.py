import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db
from app.api import investigations, demo, agent

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    if settings.PROVENANCE_DATABASE_URL:
        from app.provenance_db import init_provenance_db
        try:
            init_provenance_db()
        except Exception:
            # Never take down the existing, working investigation pipeline
            # because the new provenance layer's DB isn't reachable yet
            # (e.g. `docker compose up` without provdb, or a bad URL during
            # setup). Log loudly instead of crashing startup.
            logging.getLogger("main").exception(
                "Provenance database init failed -- discovery_manager/"
                "provenance_store will be unusable until this is fixed, "
                "but the rest of the app continues normally."
            )
    yield


app = FastAPI(
    title="AI Media Forensics & Origin Tracing Platform",
    description="Autonomous digital-media investigation platform. OpenClaw orchestrates specialized "
                "forensic, AI-detection, and OSINT agents to detect AI-generated/manipulated media and "
                "trace its origin and propagation across the web and social media.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        settings.FRONTEND_ORIGIN,
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8081",
        "http://127.0.0.1:8081",
        "http://localhost:19006",
        "http://127.0.0.1:19006",
        "http://localhost:8082",
        "http://127.0.0.1:8082",
    ],
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _ai_detector_status() -> str:
    if settings.DEMO_MODE:
        return "demo"
    if settings.AI_DETECTOR_CONFIGURED:
        return "real"
    return "unavailable"


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "demo_mode": settings.DEMO_MODE,
        "openclaw_enabled": settings.OPENCLAW_ENABLED,
        "openclaw_agent": settings.OPENCLAW_AGENT if settings.OPENCLAW_ENABLED else None,
        "openclaw_workspace": settings.OPENCLAW_WORKSPACE if settings.OPENCLAW_ENABLED else None,
        "openclaw_agent_auth_enabled": bool(settings.OPENCLAW_API_TOKEN),
        # Additive field -- does not change any existing key above.
        "ai_detector_status": _ai_detector_status(),
    }


@app.get("/api/stats")
def stats():
    from app.database import SessionLocal
    from app.models.investigation import Investigation
    db = SessionLocal()
    try:
        invs = db.query(Investigation).all()
        return {
            "total_investigations": len(invs),
            "ai_generated": sum(1 for i in invs if i.verdict == "AI_GENERATED"),
            "ai_altered": sum(1 for i in invs if i.verdict == "AI_ALTERED"),
            "authentic": sum(1 for i in invs if i.verdict == "LIKELY_AUTHENTIC"),
            "inconclusive": sum(1 for i in invs if i.verdict in (None, "INCONCLUSIVE")),
            "sources_traced": sum(len(i.sources) for i in invs),
        }
    finally:
        db.close()


app.include_router(investigations.router)
app.include_router(agent.router)
app.include_router(demo.router)

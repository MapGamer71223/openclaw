"""
Central configuration for the Media Forensics platform.

All settings are environment-driven (see .env.example at the repo root).
DEMO_MODE=true (the default) makes the entire investigation pipeline run
with zero external API keys, using local heuristic/demo providers.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent  # repo root: media-forensics/
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data"))

UPLOADS_DIR = DATA_DIR / "uploads"
EVIDENCE_DIR = DATA_DIR / "evidence"
FRAMES_DIR = DATA_DIR / "extracted_frames"
REPORTS_DIR = DATA_DIR / "reports"
DEMO_DIR = DATA_DIR / "demo"

for d in (UPLOADS_DIR, EVIDENCE_DIR, FRAMES_DIR, REPORTS_DIR, DEMO_DIR):
    d.mkdir(parents=True, exist_ok=True)


def _bool(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


def _env_str(name: str, default: str) -> str:
    """
    Like os.getenv(name, default), but also falls back to `default` when the
    variable IS set but is empty or whitespace-only (e.g. `DATABASE_URL=`
    in a .env file). Plain os.getenv() returns "" in that case, not
    `default` -- for variables whose default is a meaningful non-empty
    value (a DB URL, a hostname, an agent name, ...), that "" then gets
    used as-is downstream and breaks things (e.g. SQLAlchemy failing to
    parse an empty DATABASE_URL). Values are also stripped of surrounding
    whitespace.
    """
    val = os.getenv(name)
    if val is None:
        return default
    val = val.strip()
    return val if val else default


def _env_int(name: str, default: int) -> int:
    """int() equivalent of _env_str -- an empty/whitespace-only value falls
    back to `default` instead of raising ValueError from int('')."""
    val = os.getenv(name)
    if val is None or not val.strip():
        return default
    return int(val.strip())


def _env_float(name: str, default: float) -> float:
    """float() equivalent of _env_str -- an empty/whitespace-only value
    falls back to `default` instead of raising ValueError from float('')."""
    val = os.getenv(name)
    if val is None or not val.strip():
        return default
    return float(val.strip())


class Settings:
    # --- Core mode ---
    DEMO_MODE: bool = _bool("DEMO_MODE", True)

    # --- Provenance database (own image index -- see app/provenance_db.py) ---
    # Postgres + pgvector, separate from DATABASE_URL below (which stays
    # SQLite for the existing per-investigation records). Empty means the
    # provenance layer (discovery_manager.py / provenance_store.py) is not
    # usable yet -- the rest of the app runs fine without it. Bring up the
    # `provdb` service in docker-compose.yml and point this at it, e.g.
    # postgresql+psycopg2://provenance:provenance@localhost:5433/provenance
    PROVENANCE_DATABASE_URL: str = _env_str("PROVENANCE_DATABASE_URL", "")

    # --- Database ---
    # Empty or unset DATABASE_URL both mean "use the default local SQLite
    # database" -- os.getenv("DATABASE_URL", default) alone does NOT cover
    # the empty-but-set case (e.g. `DATABASE_URL=` in .env), which used to
    # produce DATABASE_URL="" and crash SQLAlchemy with
    # `Could not parse SQLAlchemy URL from string ''`.
    DATABASE_URL: str = _env_str(
        "DATABASE_URL", f"sqlite:///{(DATA_DIR / 'forensics.db').as_posix()}"
    )

    # --- Uploads ---
    MAX_UPLOAD_SIZE_MB: int = _env_int("MAX_UPLOAD_SIZE_MB", 100)
    ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
    ALLOWED_VIDEO_EXTENSIONS = {".mp4", ".mov"}
    ALLOWED_IMAGE_MIME = {"image/jpeg", "image/png", "image/webp"}
    ALLOWED_VIDEO_MIME = {"video/mp4", "video/quicktime"}

    # --- Video sampling ---
    VIDEO_FRAME_SAMPLE_SECONDS: float = _env_float("VIDEO_FRAME_SAMPLE_SECONDS", 2.0)
    VIDEO_MAX_FRAMES: int = _env_int("VIDEO_MAX_FRAMES", 24)

    # --- OSINT / real-mode providers (optional; unused in DEMO_MODE) ---
    # Default is already "" here, so the empty-vs-unset distinction doesn't
    # change behavior for these -- an empty value correctly still means
    # "not configured" either way. Kept on the same safe helper for
    # consistency (and so a stray trailing newline/space in a pasted key
    # doesn't accidentally count as "configured").
    BRAVE_API_KEY: str = _env_str("BRAVE_API_KEY", "")
    XAI_API_KEY: str = _env_str("XAI_API_KEY", "")
    REVERSE_IMAGE_SEARCH_API_KEY: str = _env_str("REVERSE_IMAGE_SEARCH_API_KEY", "")

    # --- Google Cloud Vision Web Detection (official, cheap, most reliable) ---
    # This is the same reverse-image-search technology behind Google Images'
    # own "find image source" button, via the official, supported REST API
    # -- NOT scraping. First 1000 requests/month are free; $3.50/1000 after
    # that (cloud.google.com/vision/pricing). Get a key at
    # console.cloud.google.com -> APIs & Services -> Credentials, after
    # enabling the "Cloud Vision API" for your project. When set, this is
    # checked FIRST in get_source_provider() -- ahead of PicImageSearch --
    # because it's an official API rather than an unofficial scrape, so it
    # doesn't silently break the way Google/Yandex/TinEye scraping does.
    GOOGLE_VISION_API_KEY: str = _env_str("GOOGLE_VISION_API_KEY", "")

    # Google Vision's Web Detection response has no publication/crawl dates
    # (neither does Yandex/Google via PicImageSearch -- only TinEye does,
    # and TinEye's API is paid). To approximate "earliest occurrence" for
    # ranking/origin purposes, each candidate URL missing a real date gets
    # a free, keyless lookup against the Internet Archive's Wayback Machine
    # CDX API for its earliest known capture timestamp. Best-effort: a
    # failed/empty lookup just leaves that candidate's date as "unknown",
    # it never blocks or fails the search. Capped to the top N candidates
    # per search pass (WAYBACK_ENRICH_MAX_CANDIDATES) to bound latency.
    WAYBACK_ENRICH_DATES: bool = _bool("WAYBACK_ENRICH_DATES", True)
    WAYBACK_ENRICH_MAX_CANDIDATES: int = _env_int("WAYBACK_ENRICH_MAX_CANDIDATES", 15)

    # --- PicImageSearch (free, in-process, true reverse-image search) ---
    # Uses the `PicImageSearch` pip package (github.com/kitUIN/PicImageSearch)
    # to query several real search-by-image engines (Google, Yandex, TinEye
    # by default) in one pass. This is the preferred real-mode source
    # provider -- checked before MRISA/Brave/DDG in get_source_provider() --
    # because it has no separate process to run, and one engine getting
    # blocked doesn't zero out the whole result set the way a single-engine
    # scraper does. Requires `pip install PicImageSearch`.
    PICIMAGESEARCH_ENABLED: bool = _bool("PICIMAGESEARCH_ENABLED", False)

    # Comma-separated engine names to query. Supported: google, yandex,
    # tineye. Order doesn't affect ranking (all results are merged and
    # re-ranked by source_verification.py); it just controls which engines
    # run. TinEye is the only one of the three that returns a real
    # publication/crawl date.
    PICIMAGESEARCH_ENGINES: str = _env_str("PICIMAGESEARCH_ENGINES", "google,yandex,tineye")

    # --- Openverse (free, keyless, always merged in -- see source_search.py) ---
    # No signup required for basic use. Optionally register a free client
    # id/secret at api.openverse.org for a higher rate ceiling; leave both
    # empty to run anonymously.
    OPENVERSE_CLIENT_ID: str = _env_str("OPENVERSE_CLIENT_ID", "")
    OPENVERSE_CLIENT_SECRET: str = _env_str("OPENVERSE_CLIENT_SECRET", "")

    # --- MRISA (free, self-hosted, true reverse-image search) ---
    # URL of a locally-running MRISA instance (github.com/vivithemage/mrisa).
    # Legacy fallback: only used when PICIMAGESEARCH_ENABLED is false. When
    # set (and BRAVE_API_KEY is not), this becomes the real-mode source
    # provider since it searches by image, not by derived text queries.
    # Empty = not configured, falls back to DDGSourceProvider.
    MRISA_URL: str = _env_str("MRISA_URL", "")

    # --- AI/deepfake detector (real mode) ---
    # When DEMO_MODE=false, this defaults to True: a real, local,
    # open-source Vision Transformer (AI_DETECTOR_MODEL_ID) is loaded via
    # app.services.ai_detection.HFImageDetector -- no API key, no per-call
    # cost, GPU optional. Set AI_DETECTOR_CONFIGURED=false explicitly to
    # opt out and get an honest NOT_AVAILABLE instead (e.g. if
    # torch/transformers aren't installed on this machine).
    AI_DETECTOR_CONFIGURED: bool = _bool("AI_DETECTOR_CONFIGURED", True)

    # Hugging Face model id for the real AI-image detector. Default is a
    # small ViT (~86M params) that fits comfortably in 6GB VRAM and also
    # runs on CPU; override to try a different real/AI-image classifier.
    AI_DETECTOR_MODEL_ID: str = _env_str("AI_DETECTOR_MODEL_ID", "Organika/sdxl-detector")

    # --- OpenClaw ---
    OPENCLAW_ENABLED: bool = _bool("OPENCLAW_ENABLED", False)

    # Workspace resolution: OPENCLAW_WORKSPACE may be given as a relative path
    # (e.g. "./openclaw") in .env. Resolve it against the repo root (BASE_DIR)
    # rather than the process's current working directory, so it works no
    # matter where uvicorn is launched from.
    _openclaw_workspace_raw: str = _env_str("OPENCLAW_WORKSPACE", "./openclaw")
    OPENCLAW_WORKSPACE: str = str((BASE_DIR / _openclaw_workspace_raw).resolve()) \
        if not Path(_openclaw_workspace_raw).is_absolute() \
        else str(Path(_openclaw_workspace_raw).resolve())

    # Which configured OpenClaw agent should drive investigations. Must NOT
    # default to "main" -- this project's agent is "crestodian".
    OPENCLAW_AGENT: str = _env_str("OPENCLAW_AGENT", "crestodian")

    # Base URL the dispatched OpenClaw agent should call back into for the
    # investigation/agent tool endpoints (passed to it as context, never used
    # by the backend itself to make requests).
    OPENCLAW_BACKEND_BASE_URL: str = _env_str("OPENCLAW_BACKEND_BASE_URL", "http://127.0.0.1:8000")

    # Optional shared-secret bearer token the dispatched agent must present
    # on every /agent/* call. Strongly recommended whenever the backend is
    # reachable from anything other than localhost. Empty = disabled (fine
    # for local dev only).
    OPENCLAW_API_TOKEN: str = _env_str("OPENCLAW_API_TOKEN", "")

    # Command used to notify/dispatch the OpenClaw CLI. Templated so it can
    # be adjusted to match the installed OpenClaw CLI's real flags without a
    # code change. Verified manually against the installed CLI:
    #   openclaw agent --agent crestodian --message "..."
    # IMPORTANT: the installed CLI does NOT support `--workspace` -- the
    # agent's workspace is already configured in OpenClaw's own agent
    # config, so it must not (and no longer does) appear in this template.
    # {workspace} is still available as a placeholder (e.g. for logging) but
    # is intentionally not part of the default command line.
    # Available placeholders: {agent} {workspace} {investigation_id} {base_url} {message}
    OPENCLAW_CLI_COMMAND_TEMPLATE: str = _env_str(
        "OPENCLAW_CLI_COMMAND_TEMPLATE",
        'openclaw agent --agent {agent} --message "{message}"',
    )
    # Seconds to wait for the dispatch subprocess to *launch* (not finish --
    # the agent run itself is expected to be long-lived and is never awaited
    # by the FastAPI request/response cycle).
    OPENCLAW_DISPATCH_LAUNCH_TIMEOUT_SECONDS: float = _env_float(
        "OPENCLAW_DISPATCH_LAUNCH_TIMEOUT_SECONDS", 5
    )

    # If a dispatch attempt fails outright (e.g. the openclaw binary isn't on
    # PATH), should the investigation silently continue in native mode? This
    # must be an explicit opt-in -- default is False, meaning a failed
    # dispatch marks the investigation FAILED with a clear error instead.
    OPENCLAW_ALLOW_NATIVE_FALLBACK: bool = _bool("OPENCLAW_ALLOW_NATIVE_FALLBACK", False)

    # If an OpenClaw-driven investigation sits in a non-terminal state for
    # longer than this without any new InvestigationEvent, it's considered
    # stalled (agent crashed/disconnected/never started) and is
    # automatically moved to FAILED with a recoverable error instead of
    # hanging forever. 0 disables the check.
    OPENCLAW_STALL_TIMEOUT_SECONDS: int = _env_int("OPENCLAW_STALL_TIMEOUT_SECONDS", 600)

    # --- CORS ---
    FRONTEND_ORIGIN: str = _env_str("FRONTEND_ORIGIN", "http://localhost:5173")

    # --- Confidence thresholds ---
    SOURCE_CONFIDENCE_STOP_THRESHOLD: float = _env_float("SOURCE_CONFIDENCE_STOP_THRESHOLD", 0.85)


settings = Settings()

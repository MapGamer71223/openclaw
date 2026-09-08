# OpenClaw / Crestodian backend integration

This document describes the backend-only changes made to route investigations
through an external OpenClaw agent (`crestodian`) instead of the native
orchestrator when `OPENCLAW_ENABLED=true`, and the HTTP tool surface that
agent uses to drive an investigation.

**Scope note:** only `backend.zip` was provided. No frontend files, no
`openclaw/` workspace, and no `SKILL.md` files were available to inspect, so
none of that was touched, assumed, or guessed at. Everything below is backend
only, built strictly from what's actually in this ZIP.

---

## 1. Files changed / added

| File | Change |
|---|---|
| `app/config.py` | Added `OPENCLAW_AGENT`, `OPENCLAW_BACKEND_BASE_URL`, `OPENCLAW_API_TOKEN`, `OPENCLAW_CLI_COMMAND_TEMPLATE`, `OPENCLAW_DISPATCH_LAUNCH_TIMEOUT_SECONDS`, `OPENCLAW_ALLOW_NATIVE_FALLBACK`, `OPENCLAW_STALL_TIMEOUT_SECONDS`. Made `OPENCLAW_WORKSPACE` resolve to an absolute path against the repo root instead of the process CWD. |
| `app/services/orchestrator.py` | No existing behavior removed. Extracted a shared `_score_candidates()` helper out of the native origin-search stage (used by both native and agent-driven paths — no duplicated scoring logic). Added `is_stalled()` / `mark_stalled_as_failed()` and a set of `agent_stage_*` / `agent_complete_investigation()` functions that wrap the existing `_stage_*` functions one at a time for agent-driven use. |
| `app/services/openclaw_bridge.py` | **New.** Non-blocking dispatch of the OpenClaw CLI (fire-and-forget subprocess launch, never awaited to completion). |
| `app/services/agent_auth.py` | **New.** Optional bearer-token check for `/agent/*` endpoints. |
| `app/schemas/agent.py` | **New.** Request/response schemas for the agent tool endpoints. |
| `app/api/agent.py` | **New.** The `/agent/*` tool endpoints (see §4). |
| `app/api/investigations.py` | `POST /{id}/start` now branches on `OPENCLAW_ENABLED`: native path unchanged; OpenClaw path dispatches instead of running the orchestrator. Added stall-check to `GET /{id}`, `GET /{id}/status`, and the WebSocket loop. |
| `app/main.py` | Registered the new `agent` router. `/api/health` now also reports `openclaw_agent`, `openclaw_workspace`, `openclaw_agent_auth_enabled`. Added basic logging config so dispatch/agent logs are visible. |
| `tests/test_pipeline.py` | Added tests for OpenClaw mode (see §8). All 9 original tests are untouched and still pass. |
| `.env.example` | **New.** All variables below, with comments. |
| `OPENCLAW_INTEGRATION.md` | **New.** This document. |

No files were deleted. No existing endpoint's request/response shape changed. No database migration is required — no models changed (see §9).

---

## 2. Exact environment variables

```
OPENCLAW_ENABLED=true
OPENCLAW_WORKSPACE=./openclaw                # resolved against repo root now, not CWD
OPENCLAW_AGENT=crestodian                    # NOT "main"
OPENCLAW_BACKEND_BASE_URL=http://127.0.0.1:8000
OPENCLAW_API_TOKEN=<a-real-secret>           # strongly recommended outside localhost
OPENCLAW_CLI_COMMAND_TEMPLATE=openclaw agent --agent {agent} --workspace "{workspace}" --message "{message}"
OPENCLAW_DISPATCH_LAUNCH_TIMEOUT_SECONDS=5
OPENCLAW_ALLOW_NATIVE_FALLBACK=false
OPENCLAW_STALL_TIMEOUT_SECONDS=600
DEMO_MODE=false
```

See `.env.example` for the full annotated list including unchanged existing variables.

⚠️ **`OPENCLAW_CLI_COMMAND_TEMPLATE` is a documented best guess, not a verified contract.** This sandbox has no OpenClaw CLI installed, so the dispatch command could not be executed against a real `openclaw` binary. Run it by hand once (`openclaw agent --agent crestodian --workspace "D:\All projects\media-forensics\media-forensics\openclaw" --message "test"`) on your machine and confirm Crestodian actually receives it; adjust the template in `.env` (not code) if the real CLI's flags differ.

---

## 3. What changed in the `/start` flow

**Before:** `POST /{id}/start` always called `orchestrator.run_investigation()` in the background, regardless of `OPENCLAW_ENABLED`.

**After:**

```
POST /{id}/start
  -> OPENCLAW_ENABLED=false:  unchanged, runs the native orchestrator (background task)
  -> OPENCLAW_ENABLED=true:   investigation stays in UPLOADED; a background task
                               launches (but does not await) the OpenClaw CLI
                               pointed at `crestodian` with the investigation ID.
                               Crestodian is then expected to drive the
                               investigation forward itself via the /agent/*
                               endpoints below.
```

If the dispatch itself can't even be launched (e.g. `openclaw` isn't on PATH), the investigation is marked `FAILED` with a clear `error_message` — **never** silently completed and **never** silently switched to native mode, unless you explicitly set `OPENCLAW_ALLOW_NATIVE_FALLBACK=true`, in which case the fallback is itself logged as a visible `InvestigationEvent` so it's not silent.

If a real, already-running crestodian agent dies mid-investigation (or never picks it up), the investigation would otherwise sit "running" forever. `OPENCLAW_STALL_TIMEOUT_SECONDS` (default 600s) guards against that: `GET /{id}`, `GET /{id}/status`, and the WebSocket all check `is_stalled()` on read and auto-transition to `FAILED` with an explanatory message if nothing happened for that long.

---

## 4. New `/agent/*` tool endpoints

All under `/api/investigations/{investigation_id}/agent/...`, all `POST`, all requiring `Authorization: Bearer <OPENCLAW_API_TOKEN>` if that variable is set (no-op if unset — local dev only).

Each endpoint wraps **exactly one** existing deterministic service call — no forensic/OSINT logic was duplicated or reimplemented; they call the same `_stage_*` functions `run_investigation()` already used. Each validates the investigation is in the correct precondition state and returns `409 Conflict` (not a silent no-op) on an out-of-order or duplicate call.

| Endpoint | Precondition state | Deterministic call | Resulting state |
|---|---|---|---|
| `POST /agent/hash-metadata` | `UPLOADED` | SHA-256, EXIF/video metadata, perceptual hashes | `METADATA_ANALYSIS` |
| `POST /agent/forensics-detection` | `METADATA_ANALYSIS` | ELA / noise / resampling / compression, AI-detector | `FORENSIC_ANALYSIS` |
| `POST /agent/origin-search` | `FORENSIC_ANALYSIS` | Scores + ranks + persists **agent-submitted** candidate sources (never invents URLs itself) | `SOURCE_VERIFICATION` |
| `POST /agent/propagation` | `SOURCE_VERIFICATION` | Builds propagation graph from persisted sources | `PROPAGATION_ANALYSIS` |
| `POST /agent/correlate` | `PROPAGATION_ANALYSIS` | Weighted overall score, verdict | `CORRELATION` |
| `POST /agent/report` | `CORRELATION` | Builds + persists the final report | `REPORT_GENERATION` |
| `POST /agent/events` | any | Free-form progress/reasoning log line from any skill | unchanged (unless `stage` given) |
| `POST /agent/complete` | any non-terminal | Explicit `COMPLETED` / `PARTIAL` / `FAILED` transition | terminal |

`POST /agent/complete` refuses `COMPLETED` unless the state is `REPORT_GENERATION` (i.e. the report actually exists) — this is what stops the agent from claiming success without a real report. `PARTIAL`/`FAILED` are allowed from any non-terminal state with a `reason`, matching the "explain missing/contradictory evidence" and "degrade gracefully" requirements from the skill descriptions.

This is the full new surface — **8 endpoints**, matching the "smallest clean tool surface" requirement: one per irreducible deterministic computation stage, one for OSINT candidate submission (the actual reasoning point), one generic event logger, one terminal-state setter.

### Why `origin-search` takes a request body

This is the one place OpenClaw's own reasoning (web_search/browser/x_search results) has to enter the pipeline. The agent submits what it actually found; the backend only ever scores/ranks/persists what it's given — it never fabricates a candidate itself. Example:

```http
POST /api/investigations/{id}/agent/origin-search
Authorization: Bearer <token>
Content-Type: application/json

{
  "queries_used": ["distinctive phrase from the image", "filename search"],
  "is_demo": false,
  "candidates": [
    {
      "url": "https://example-news.test/article",
      "title": "Original news coverage",
      "platform": "News Article",
      "domain": "example-news.test",
      "publication_date": "2024-01-01",
      "accessible": true
    },
    {
      "url": "https://x.com/someuser/status/123",
      "platform": "X",
      "domain": "x.com",
      "publication_date": "2024-01-03",
      "accessible": true
    }
  ]
}
```

If a source was blocked by CAPTCHA/login/paywall, submit it with `"accessible": false, "inaccessible_reason": "paywall"` instead of omitting it — this preserves the origin-investigator skill's "stop at CAPTCHA/paywall, don't bypass, record it" behavior.

### Example: full driven sequence

```http
POST /api/investigations/{id}/agent/hash-metadata
POST /api/investigations/{id}/agent/forensics-detection
POST /api/investigations/{id}/agent/origin-search      { candidates: [...] }
POST /api/investigations/{id}/agent/propagation
POST /api/investigations/{id}/agent/correlate
POST /api/investigations/{id}/agent/report
POST /api/investigations/{id}/agent/complete            { "status": "COMPLETED", "agent": "forensic-report-generator" }
```

All existing `GET` endpoints (`/status`, `/forensics`, `/detections`, `/sources`, `/timeline`, `/graph`, `/report`, `/artifacts/ela`, `/original`) and the WebSocket work identically afterward, regardless of whether the investigation was driven natively or by the agent — this was verified directly (§8).

---

## 5. Security

- `/agent/*` requires `Authorization: Bearer <OPENCLAW_API_TOKEN>` when that variable is set (`hmac.compare_digest`, no timing side-channel).
- No endpoint accepts arbitrary code, shell commands, or filesystem paths. `origin-search` only accepts structured URL/title/platform/date fields.
- No endpoint exposes `.env` contents, `GEMINI_API_KEY`, `BRAVE_API_KEY`, `XAI_API_KEY`, or the on-disk evidence path (`MediaAssetOut` never includes `original_path`).
- Every mutating call validates `investigation_id` exists (404) and the current state matches the expected precondition (409) before touching anything.
- Dispatch/agent logs (see `openclaw.dispatch` and `investigations` loggers) print investigation ID, agent name, workspace, PID, and timestamps — never secrets.

---

## 6. How to run the backend

**Native / demo mode (unchanged):**
```bash
pip install -r requirements.txt
DEMO_MODE=true OPENCLAW_ENABLED=false uvicorn app.main:app --reload
```

**OpenClaw / Crestodian mode:**
```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env: DEMO_MODE=false, OPENCLAW_ENABLED=true, OPENCLAW_AGENT=crestodian,
# OPENCLAW_API_TOKEN=<something>, and verify OPENCLAW_CLI_COMMAND_TEMPLATE
uvicorn app.main:app --reload
```

## 7. Verify Crestodian is being targeted

```bash
curl http://127.0.0.1:8000/api/health
```
```json
{
  "status": "ok",
  "demo_mode": false,
  "openclaw_enabled": true,
  "openclaw_agent": "crestodian",
  "openclaw_workspace": "D:\\All projects\\media-forensics\\media-forensics\\openclaw",
  "openclaw_agent_auth_enabled": true
}
```
`openclaw_agent` must read `crestodian`, never `main`. `openclaw_workspace` should be the fully resolved absolute path even if `.env` gave a relative one.

Then start a real investigation and watch the dispatch log line:
```
INFO openclaw.dispatch: openclaw.dispatch investigation_id=<id> agent=crestodian workspace=<path> time=...
INFO openclaw.dispatch: openclaw.dispatch_launched investigation_id=<id> agent=crestodian pid=<pid>
```

## 8. How to test one real investigation

1. Upload: `POST /api/investigations` (multipart file) → note `id`, confirm `state: UPLOADED`.
2. Start: `POST /api/investigations/{id}/start` → confirm response `state: UPLOADED` (not `COMPLETED` — that would mean it ran natively instead of dispatching).
3. Watch `GET /api/investigations/{id}/status` or the WebSocket `ws://.../api/investigations/ws/{id}` for the `openclaw-agent` "Dispatched investigation to 'crestodian'" event, then the subsequent stage events as Crestodian calls `/agent/*`.
4. On completion, confirm `GET /api/investigations/{id}/report`, `/sources`, `/graph` are populated and `state == COMPLETED`.

### Automated tests

```bash
DATA_DIR=/tmp/mf-test-data DEMO_MODE=true pytest -q
```
Covers, among the original 9: `test_start_does_not_run_native_orchestrator_when_openclaw_enabled`, `test_agent_driven_investigation_reaches_completed` (full 7-call driven sequence, token enforcement, duplicate-call 409, existing GETs still work after), `test_agent_endpoints_reject_unknown_investigation_id`, `test_stalled_openclaw_investigation_recovers_to_failed`, `test_native_mode_unaffected_by_openclaw_config_presence`. **14/14 pass.**

(The new OpenClaw-mode tests run in a subprocess with their own env vars, since `OPENCLAW_ENABLED`/`OPENCLAW_API_TOKEN` are read once into `settings` at import time — this mirrors the fact that native and OpenClaw mode really are two different backend process configurations, not two code paths chosen per-request.)

---

## 9. Database / migrations

**None required.** No SQLAlchemy model changed. All new functionality reuses the existing `Investigation`, `MediaAsset`, `ForensicResult`, `AIDetection`, `Source`, `PropagationEdge`, `InvestigationEvent`, `Report` tables exactly as they were.

---

## 10. Confirmed: native/demo mode still works

`DEMO_MODE=true OPENCLAW_ENABLED=false` — all 9 original tests pass unmodified, including `test_demo_mode_full_investigation_runs_without_external_apis`, `test_investigation_state_transitions_through_defined_states`, and `test_ela_artifact_generated_for_demo_investigation`. `/api/demo/seed` still always runs the native pipeline directly (by design — it's for offline/CI demo regardless of `OPENCLAW_ENABLED`).

---

## 11. Remaining work outside this ZIP

Not touched, because the files don't exist in this ZIP:
- **Frontend**: upload flow, live-progress page, automatic result navigation on `COMPLETED`/`PARTIAL`/`FAILED`, dashboard, WebSocket client wiring. The backend's WebSocket payload shape is unchanged, so no frontend contract was broken, but nothing was added there.
- **`openclaw/` workspace**: `README.md`, the seven `SKILL.md` files, and any OpenClaw-side config (`crestodian` agent definition, Gemini wiring). This backend now exposes the tool surface those skills are described as needing (origin-investigator → `/agent/origin-search`, social-tracer → `/agent/propagation`, evidence-correlator → `/agent/correlate`, forensic-report-generator → `/agent/report` + existing `/report` GET, ai-media-detector/forensic-analyzer → existing `/detections` + `/forensics` GETs), but the skills themselves weren't inspected or modified.
- **Verifying `OPENCLAW_CLI_COMMAND_TEMPLATE`** against the real, installed OpenClaw CLI on your machine (see §2) — this could not be executed from this sandbox.
- Wiring a real (non-demo) `MediaDetector` and OSINT provider is out of scope here and was already pluggable before this change (`app/services/ai_detection.py::get_detector()`, `app/services/source_search.py::get_source_provider()`).

# Setup

## Prerequisites

- Python 3.11+
- Node.js 18+
- ffmpeg / ffprobe on `PATH` (used for video metadata + frame extraction;
  the platform degrades gracefully and reports "Not available" if missing)
- (Optional) `exiftool` on `PATH` for richer image metadata extraction —
  Pillow's built-in EXIF reader is used automatically if it's absent
- (Optional) Node.js + `openclaw` npm package, only if you want a real
  OpenClaw agent driving investigations instead of the native orchestrator

## Quick start (recommended)

```bash
cp .env.example .env
./run.sh
```

Open http://localhost:5173. The backend runs on http://localhost:8000
(interactive API docs at http://localhost:8000/docs).

## Manual setup

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
DATA_DIR=../data DEMO_MODE=true uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api/*` (including the investigation
WebSocket) to `http://localhost:8000`, configured in `vite.config.ts`.

## Docker

```bash
docker compose up --build
```

Note: the Dockerized frontend serves a static production build via `serve`
without a reverse proxy in front of it, so `/api/*` calls from the browser
will need `backend` reachable directly (e.g. run behind your own nginx, or
just use `./run.sh` for local development/demo, which has the dev proxy).

## Running tests

```bash
cd backend
source .venv/bin/activate  # if using the manual setup
DATA_DIR=/tmp/mf-test-data DEMO_MODE=true pytest -q
```

## OpenClaw agent (optional, real-mode OSINT reasoning)

```bash
npm install -g openclaw
cd openclaw
openclaw --workspace .
```

Set `OPENCLAW_ENABLED=true` in `.env` so new investigations wait for the
external agent to drive them via the API instead of the native
orchestrator. See `openclaw/README.md` for the full explanation of both
integration modes and the tool-permission model per skill.

## Local GPU model (real AI-detection instead of the demo heuristic)

By default `DEMO_MODE=true` uses `DemoHeuristicDetector`, a transparent
combination of forensic signals -- **not** a trained classifier. To use a
real Hugging Face image-classification model on your own GPU:

```bash
cd backend
# 1. Install the CUDA build of torch that matches your GPU driver.
#    RTX 3050 (Ampere) -> CUDA 12.1 wheels work well:
pip install torch --index-url https://download.pytorch.org/whl/cu121

# 2. Install the rest of the local-model deps
pip install -r requirements-gpu.txt

# 3. Enable it
#    In .env, set:
#      USE_LOCAL_MODEL=true
#      LOCAL_MODEL_NAME=Organika/sdxl-detector
```

The model (`Organika/sdxl-detector`, ~350MB) downloads automatically on
first use and is cached under `~/.cache/huggingface`. It comfortably fits
an RTX 3050's 6GB VRAM in fp16. `LOCAL_MODEL_NAME` can be swapped for any
other HF `image-classification` checkpoint with "real"/"fake"-style labels.

If no CUDA device is detected, it automatically falls back to CPU (slower
but still works).

## Production run (no --reload, built frontend)

`./run.sh` and `npm run dev` are dev-mode tools (auto-reload, unminified,
CORS-open). For anything beyond your own machine:

```bash
# Backend -- no --reload, bind explicitly, don't leak the interactive
# reloader/debugger. Single worker is intentional here: the GPU model is
# loaded once per process, and multiple workers would each load their own
# copy into VRAM.
cd backend
set DEMO_MODE=false
set USE_LOCAL_MODEL=true
set DATA_DIR=../data
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1

# Frontend -- build static assets, then serve them (Vite's dev server is
# not meant for production)
cd frontend
npm run build
npx serve -s dist -l 5173
```

Then put a real reverse proxy (nginx / Caddy) in front of both, terminate
TLS there, and route `/api/*` and `/api/investigations/ws/*` (WebSocket)
to the backend on 8000, everything else to the frontend on 5173 -- the
Vite dev proxy config in `vite.config.ts` only applies in dev mode.

## Environment variables

See `.env.example` for the full list with comments. The platform runs with
zero external API keys by default (`DEMO_MODE=true`).
# Demo Guide

Target duration: ~60–90 seconds, no terminal commands after initial setup.

## 1. Start the stack

```bash
./run.sh
```

Wait for both "Uvicorn running on http://0.0.0.0:8000" and the Vite
"ready in Xms" message, then open http://localhost:5173.

## 2. Run the one-click offline demo

1. Click **"New Investigation"** in the sidebar.
2. Click **"Run Demo Investigation"**.
3. This calls `POST /api/demo/seed`, which generates a synthetic image with
   a deliberately spliced/resampled region, then runs it through the real
   pipeline end-to-end (hash → metadata → AI detection → forensics → OSINT →
   source verification → propagation → correlation → report) — no external
   API keys needed. It returns already-`COMPLETED` since seeding runs the
   pipeline synchronously.
4. You'll land directly on the Investigation page with the finished result.

## 3. Walk the tabs

- **Overview** — verdict badge (`LIKELY AI-ALTERED`), confidence, and the
  three weighted score bars (AI Detection / Forensic Evidence / Origin
  Evidence).
- **AI Detection** — classification, probability, confidence, and signals,
  with the DEMO/HEURISTIC disclaimer visible.
- **Forensics** — the actual generated ELA visualization image, noise/
  resampling scores, and compression notes.
- **Evidence** — the original file, perceptual hashes, raw metadata, and the
  full chain-of-custody event log.
- **Sources** — the earliest credible occurrence plus all ranked demo
  sources (clearly tagged `DEMO`), each with its similarity/confidence
  scores and reasoning.
- **Timeline** — chronological propagation.
- **Propagation** — the interactive SVG source → post/article graph;
  click a node to see its details.
- **Report** — the full structured report, including "What We Know / What
  We Suspect / What We Could Not Verify."

## 4. Upload real media (still offline-safe)

From the Upload page, drag in any JPG/PNG/WEBP/MP4/MOV. The forensic and
AI-detection pipeline runs for real on your file; OSINT results will still
be the labeled demo provider unless you've set `BRAVE_API_KEY` and
`DEMO_MODE=false`.

## 5. What's real vs. demo in this walkthrough

| Component | In DEMO_MODE |
|---|---|
| SHA-256 / metadata / perceptual hashes | **Real**, computed from the actual file |
| ELA / noise / resampling / compression | **Real** signal processing |
| AI classification | Real heuristic combination of the above, clearly labeled "demo" |
| OSINT candidate sources | **Synthetic**, clearly labeled `is_demo: true` |
| Source ranking / propagation graph / report | **Real** logic, applied to the (synthetic) sources |

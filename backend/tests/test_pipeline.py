"""
Tests for the media-forensics pipeline. Run with:
    DATA_DIR=/tmp/mf-test-data DEMO_MODE=true pytest -q
"""
import io
import os
import sys
from pathlib import Path

os.environ.setdefault("DATA_DIR", "/tmp/mf-test-data")
os.environ.setdefault("DEMO_MODE", "true")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pytest
from PIL import Image
from fastapi.testclient import TestClient

from app.main import app
from app.services.hashing import calculate_sha256
from app.services.perceptual_hash import compute_hashes, hamming_distance, classify_match
from app.services import source_verification, propagation

client = TestClient(app)
client.__enter__()  # trigger FastAPI startup (DB init) once for the whole test module


@pytest.fixture()
def sample_image(tmp_path):
    path = tmp_path / "sample.jpg"
    arr = (np.random.default_rng(1).integers(0, 255, (200, 300, 3))).astype("uint8")
    Image.fromarray(arr).save(path, "JPEG", quality=90)
    return path


def test_sha256_deterministic(sample_image):
    assert calculate_sha256(sample_image) == calculate_sha256(sample_image)


def test_phash_resized_image_is_close(sample_image, tmp_path):
    original_hashes = compute_hashes(sample_image)
    resized_path = tmp_path / "resized.jpg"
    im = Image.open(sample_image).resize((150, 100))
    im.save(resized_path, "JPEG", quality=80)
    resized_hashes = compute_hashes(resized_path)
    distance = hamming_distance(original_hashes["phash"], resized_hashes["phash"])
    assert distance <= 10
    assert classify_match(distance) in ("exact", "near_identical", "modified_copy")


def test_source_ranking_prefers_credible_over_oldest_repost():
    older_but_repost = {
        "id": "a", "source_confidence": None, "publication_date": "2020-01-01",
    }
    newer_but_credible = {
        "id": "b", "source_confidence": None, "publication_date": "2020-06-01",
    }
    older_but_repost["source_confidence"], _ = source_verification.score_candidate(
        publication_date="2020-01-01", similarity=0.7, is_demo=True, looks_like_repost=True, is_screenshot_of_post=True,
    )
    newer_but_credible["source_confidence"], _ = source_verification.score_candidate(
        publication_date="2020-06-01", similarity=0.98, is_demo=True,
    )
    ranked = source_verification.rank_sources([older_but_repost, newer_but_credible])
    assert ranked[0]["id"] == "b"


def test_propagation_graph_nodes_and_edges_consistent():
    sources = [
        {"id": "1", "platform": "News Wire", "similarity_score": 1.0, "publication_date": "2024-01-01"},
        {"id": "2", "platform": "X", "similarity_score": 0.95, "publication_date": "2024-01-02"},
        {"id": "3", "platform": "News Article", "similarity_score": 0.7, "publication_date": "2024-01-03"},
    ]
    edges = propagation.build_graph("inv1", sources)
    assert len(edges) > 0
    node_ids = {propagation._node_id(sources[0], True)} | {propagation._node_id(s, False) for s in sources[1:]}
    for e in edges:
        assert e["from_node"] in node_ids
        assert e["to_node"] in node_ids


def test_health_endpoint():
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["demo_mode"] is True


def test_demo_mode_full_investigation_runs_without_external_apis():
    resp = client.post("/api/demo/seed")
    assert resp.status_code == 200
    data = resp.json()
    assert data["state"] == "COMPLETED"
    assert data["verdict"] in ("AI_GENERATED", "AI_ALTERED", "LIKELY_AUTHENTIC", "INCONCLUSIVE")

    inv_id = data["id"]
    report = client.get(f"/api/investigations/{inv_id}/report")
    assert report.status_code == 200
    body = report.json()
    assert "what_we_know" in body and "what_we_suspect" in body and "what_we_could_not_verify" in body

    sources = client.get(f"/api/investigations/{inv_id}/sources").json()
    assert all(s["is_demo"] for s in sources)  # demo mode must clearly label mock sources

    graph = client.get(f"/api/investigations/{inv_id}/graph").json()
    node_ids = {n["id"] for n in graph["nodes"]}
    for e in graph["edges"]:
        assert e["from"] in node_ids
        assert e["to"] in node_ids


def test_investigation_state_transitions_through_defined_states():
    resp = client.post("/api/demo/seed")
    inv_id = resp.json()["id"]
    status = client.get(f"/api/investigations/{inv_id}/status").json()
    stages_seen = {e["stage"] for e in status["events"] if e["stage"]}
    assert "COMPLETED" in stages_seen
    assert status["state"] == "COMPLETED"


def test_upload_rejects_unsupported_extension(tmp_path):
    bad_file = tmp_path / "not_media.txt"
    bad_file.write_text("hello")
    with open(bad_file, "rb") as f:
        resp = client.post("/api/investigations", files={"file": ("not_media.txt", f, "text/plain")})
    assert resp.status_code == 400


def test_ela_artifact_generated_for_demo_investigation():
    resp = client.post("/api/demo/seed")
    inv_id = resp.json()["id"]
    ela_resp = client.get(f"/api/investigations/{inv_id}/artifacts/ela")
    assert ela_resp.status_code == 200
    assert ela_resp.headers["content-type"] == "image/png"


# =====================================================================
# OpenClaw agent-driven mode
#
# These tests run in a *separate* process (via subprocess) because
# OPENCLAW_ENABLED and OPENCLAW_API_TOKEN are read once into `settings` at
# import time -- reusing the already-imported `app`/`client` above (which
# was imported under OPENCLAW_ENABLED=false) would not reflect the
# different config. This mirrors how the two modes are actually run in
# practice (as separate backend processes/deployments).
# =====================================================================
import subprocess
import sys
import textwrap


def _run_in_subprocess(code: str, env_overrides: dict) -> str:
    env = os.environ.copy()
    env.update(env_overrides)
    result = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=str(Path(__file__).resolve().parent.parent),
        env=env, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    return result.stdout


def test_start_does_not_run_native_orchestrator_when_openclaw_enabled(tmp_path):
    """POST /start with OPENCLAW_ENABLED=true must leave the investigation
    in UPLOADED (dispatch happens in the background and, with no real
    OpenClaw binary on PATH in CI, fails cleanly to FAILED -- it must NOT
    silently run the native pipeline to completion)."""
    out = _run_in_subprocess(
        """
        import io, time
        import numpy as np
        from PIL import Image
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        with client:
            arr = (np.random.default_rng(1).integers(0, 255, (100, 100, 3))).astype("uint8")
            buf = io.BytesIO(); Image.fromarray(arr).save(buf, "JPEG"); buf.seek(0)
            inv = client.post("/api/investigations", files={"file": ("t.jpg", buf, "image/jpeg")}).json()
            resp = client.post(f"/api/investigations/{inv['id']}/start")
            assert resp.status_code == 200
            assert resp.json()["state"] == "UPLOADED"
            time.sleep(1.0)
            status = client.get(f"/api/investigations/{inv['id']}/status").json()
            # must NOT have completed the full native pipeline
            assert status["state"] != "COMPLETED"
            assert "report" not in [e["stage"] for e in status["events"]]
            print("OK")
        """,
        {"DATA_DIR": str(tmp_path), "DEMO_MODE": "false", "OPENCLAW_ENABLED": "true"},
    )
    assert "OK" in out


def test_agent_driven_investigation_reaches_completed(tmp_path):
    out = _run_in_subprocess(
        """
        import io
        import numpy as np
        from PIL import Image
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        H = {"Authorization": "Bearer test-token"}
        with client:
            arr = (np.random.default_rng(2).integers(0, 255, (100, 100, 3))).astype("uint8")
            buf = io.BytesIO(); Image.fromarray(arr).save(buf, "JPEG"); buf.seek(0)
            inv = client.post("/api/investigations", files={"file": ("t.jpg", buf, "image/jpeg")}).json()
            iid = inv["id"]

            r = client.post(f"/api/investigations/{iid}/agent/hash-metadata")
            assert r.status_code == 401, r.text  # token required

            r = client.post(f"/api/investigations/{iid}/agent/hash-metadata", headers=H)
            assert r.status_code == 200, r.text

            r2 = client.post(f"/api/investigations/{iid}/agent/hash-metadata", headers=H)
            assert r2.status_code == 409  # rejects out-of-order/duplicate call

            r = client.post(f"/api/investigations/{iid}/agent/forensics-detection", headers=H)
            assert r.status_code == 200, r.text

            payload = {"candidates": [
                {"url": "https://example.test/a", "platform": "News Article",
                 "domain": "example.test", "publication_date": "2024-01-01"},
            ], "is_demo": False}
            r = client.post(f"/api/investigations/{iid}/agent/origin-search", json=payload, headers=H)
            assert r.status_code == 200, r.text
            assert len(r.json()) == 1

            r = client.post(f"/api/investigations/{iid}/agent/propagation", headers=H)
            assert r.status_code == 200, r.text

            r = client.post(f"/api/investigations/{iid}/agent/correlate", headers=H)
            assert r.status_code == 200, r.text

            r = client.post(f"/api/investigations/{iid}/agent/report", headers=H)
            assert r.status_code == 200, r.text

            r = client.post(f"/api/investigations/{iid}/agent/complete",
                             json={"status": "COMPLETED", "agent": "forensic-report-generator"}, headers=H)
            assert r.status_code == 200, r.text
            assert r.json()["state"] == "COMPLETED"

            # existing GET endpoints keep working after an agent-driven run
            assert client.get(f"/api/investigations/{iid}/report").status_code == 200
            assert client.get(f"/api/investigations/{iid}/sources").status_code == 200
            assert client.get(f"/api/investigations/{iid}/graph").status_code == 200
            print("OK")
        """,
        {"DATA_DIR": str(tmp_path), "DEMO_MODE": "false", "OPENCLAW_ENABLED": "true",
         "OPENCLAW_API_TOKEN": "test-token"},
    )
    assert "OK" in out


def test_agent_endpoints_reject_unknown_investigation_id(tmp_path):
    out = _run_in_subprocess(
        """
        from fastapi.testclient import TestClient
        from app.main import app
        client = TestClient(app)
        with client:
            r = client.post("/api/investigations/does-not-exist/agent/hash-metadata")
            assert r.status_code == 404
            print("OK")
        """,
        {"DATA_DIR": str(tmp_path), "DEMO_MODE": "false", "OPENCLAW_ENABLED": "true"},
    )
    assert "OK" in out


def test_stalled_openclaw_investigation_recovers_to_failed(tmp_path):
    out = _run_in_subprocess(
        """
        import io, time
        import numpy as np
        from PIL import Image
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)
        with client:
            arr = (np.random.default_rng(4).integers(0, 255, (80, 80, 3))).astype("uint8")
            buf = io.BytesIO(); Image.fromarray(arr).save(buf, "JPEG"); buf.seek(0)
            inv = client.post("/api/investigations", files={"file": ("t.jpg", buf, "image/jpeg")}).json()
            time.sleep(1.5)
            r = client.get(f"/api/investigations/{inv['id']}")
            assert r.json()["state"] == "FAILED"
            assert "stall" in r.json()["error_message"].lower() or "disconnect" in r.json()["error_message"].lower()
            print("OK")
        """,
        {"DATA_DIR": str(tmp_path), "DEMO_MODE": "false", "OPENCLAW_ENABLED": "true",
         "OPENCLAW_STALL_TIMEOUT_SECONDS": "1"},
    )
    assert "OK" in out


def test_native_mode_unaffected_by_openclaw_config_presence():
    """Sanity check that the *default* test-suite process (OPENCLAW_ENABLED
    unset/false, imported at module load above) is completely unaffected --
    i.e. the two modes really are switched by config, not code path
    guessing."""
    resp = client.get("/api/health")
    assert resp.json()["openclaw_enabled"] is False
    assert resp.json()["openclaw_agent"] is None

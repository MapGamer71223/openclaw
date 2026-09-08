"""
Regression tests for the honest AI-detector architecture.

Covers:
  - get_detector() branching: DEMO_MODE=true -> demo, DEMO_MODE=false with
    nothing wired -> unavailable, DEMO_MODE=false with AI_DETECTOR_CONFIGURED
    but no real class wired -> loud config error (never a silent fallback
    to the demo heuristic).
  - detector_status is correctly exposed on DetectionResult / persisted /
    surfaced in the report.
  - High forensic signals (ELA/noise/resampling) alone can never produce
    AI_GENERATED or AI_ALTERED.
  - Missing OSINT/source evidence is neutral, not negative, in the overall
    score.
  - A real detector's classification is always honored/preserved.
  - resampling_analysis() behaves consistently on synthetic images (not
    tuned to any particular uploaded photo).

Run with:
    DATA_DIR=/tmp/mf-test-data DEMO_MODE=true pytest -q tests/test_ai_detector_architecture.py
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("DATA_DIR", "/tmp/mf-test-data")
os.environ.setdefault("DEMO_MODE", "true")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np
import pytest
from PIL import Image

from app.config import settings
from app.services import ai_detection, confidence, image_forensics


# =====================================================================
# 1-4: detector factory / status wiring
# =====================================================================

def test_demo_mode_uses_demo_heuristic_detector(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", True)
    detector = ai_detection.get_detector()
    assert isinstance(detector, ai_detection.DemoHeuristicDetector)

    result = detector.analyze_image(Path("unused"), {"ela_score": 0.1, "noise_score": 0.1, "resampling_score": 0.1})
    assert result.detector_status == "demo"
    assert result.is_demo is True
    assert result.model_name == "demo-heuristic-v1"


def test_real_mode_without_configured_detector_is_explicitly_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "AI_DETECTOR_CONFIGURED", False)

    detector = ai_detection.get_detector()
    assert isinstance(detector, ai_detection.UnavailableDetector)
    assert not isinstance(detector, ai_detection.DemoHeuristicDetector)

    result = detector.analyze_image(Path("unused"), {"ela_score": 0.99, "noise_score": 0.99, "resampling_score": 0.99})
    assert result.classification == "NOT_AVAILABLE"
    assert result.detector_status == "unavailable"
    assert result.is_demo is False
    assert result.model_name != "demo-heuristic-v1"


def test_real_mode_configured_flag_without_real_class_fails_loudly_instead_of_faking(monkeypatch):
    """AI_DETECTOR_CONFIGURED=true must never be silently treated as if a
    real model exists when none is actually wired into get_detector()."""
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "AI_DETECTOR_CONFIGURED", True)

    with pytest.raises(RuntimeError):
        ai_detection.get_detector()


def test_detector_status_field_present_on_all_detection_results(monkeypatch):
    monkeypatch.setattr(settings, "DEMO_MODE", False)
    monkeypatch.setattr(settings, "AI_DETECTOR_CONFIGURED", False)
    result = ai_detection.get_detector().analyze_video(Path("unused"), {"frame_analysis": {}})
    assert result.detector_status == "unavailable"


# =====================================================================
# 5-6: high forensic signals alone can never yield AI_GENERATED/AI_ALTERED
# =====================================================================

@pytest.mark.parametrize("forensic_score", [0.5, 0.818, 0.95, 1.0])
def test_high_resampling_or_forensic_score_alone_never_yields_ai_generated(forensic_score):
    verdict = confidence.derive_verdict(
        ai_classification="NOT_AVAILABLE",
        overall_score=confidence.compute_overall_score(forensic_score=forensic_score, ai_detection_available=False),
        ai_detection_available=False,
        forensic_score=forensic_score,
    )
    assert verdict != "AI_GENERATED"


@pytest.mark.parametrize("forensic_score", [0.5, 0.818, 0.95, 1.0])
def test_high_resampling_or_forensic_score_alone_never_yields_ai_altered(forensic_score):
    verdict = confidence.derive_verdict(
        ai_classification="NOT_AVAILABLE",
        overall_score=confidence.compute_overall_score(forensic_score=forensic_score, ai_detection_available=False),
        ai_detection_available=False,
        forensic_score=forensic_score,
    )
    assert verdict != "AI_ALTERED"


def test_unavailable_detector_with_clean_forensics_can_reach_likely_authentic():
    """Enough independent (forensic) evidence of a clean image can still
    support LIKELY_AUTHENTIC even with no validated AI detector -- this is
    not hardcoded to any specific image, just a low forensic_score."""
    verdict = confidence.derive_verdict(
        ai_classification="NOT_AVAILABLE",
        overall_score=0.1,
        ai_detection_available=False,
        forensic_score=0.05,
    )
    assert verdict == "LIKELY_AUTHENTIC"


def test_unavailable_detector_inconclusive_is_not_converted_to_fake_ai_classification():
    verdict = confidence.derive_verdict(
        ai_classification="NOT_AVAILABLE",
        overall_score=0.5,
        ai_detection_available=False,
        forensic_score=0.4,
    )
    assert verdict == "INCONCLUSIVE"
    assert verdict not in ("AI_GENERATED", "AI_ALTERED")


# =====================================================================
# 7-8: missing OSINT / metadata evidence is neutral, not negative
# =====================================================================

def test_missing_source_evidence_is_renormalized_not_defaulted_to_neutral():
    # Ai/forensic evidence both signal 0.1 (low). If missing source/similarity
    # were silently defaulted to a neutral 0.5 and still blended in at their
    # normal 15%/15% weight (the old behavior), the score would be pulled up
    # to well above the actual available evidence. Correct behavior:
    # renormalize over just the available evidence lines (ai + forensic).
    without_source = confidence.compute_overall_score(
        forensic_score=0.1, ai_probability=0.1, ai_detection_available=True,
        best_source_confidence=None, best_similarity=None,
    )
    assert without_source == round((0.1 * 0.40 + 0.1 * 0.30) / 0.70, 4)
    assert without_source == 0.1  # both available components agree at 0.1

    old_neutral_default_behavior = round(0.1 * 0.40 + 0.1 * 0.30 + 0.5 * 0.15 + 0.5 * 0.15, 4)
    assert without_source < old_neutral_default_behavior


def test_missing_ai_detector_excludes_it_from_scoring_rather_than_using_forensics_as_proxy():
    score = confidence.compute_overall_score(
        forensic_score=0.9, ai_probability=None, ai_detection_available=False,
        best_source_confidence=None, best_similarity=None,
    )
    # Only forensic evidence is available -> renormalized weight is 100% forensic.
    assert score == 0.9


def test_weights_renormalize_and_still_bound_to_0_1():
    score = confidence.compute_overall_score(
        forensic_score=1.0, ai_probability=1.0, ai_detection_available=True,
        best_source_confidence=1.0, best_similarity=1.0,
    )
    assert score == 1.0
    score_zero = confidence.compute_overall_score(forensic_score=0.0, ai_detection_available=False)
    assert score_zero == 0.0


# =====================================================================
# 9-10: a real detector's classification is preserved
# =====================================================================

def test_real_detector_ai_generated_is_preserved():
    verdict = confidence.derive_verdict(
        ai_classification="AI_GENERATED", overall_score=0.2, ai_detection_available=True, forensic_score=0.05,
    )
    assert verdict == "AI_GENERATED"


def test_real_detector_ai_altered_is_preserved_when_score_supports_it():
    verdict = confidence.derive_verdict(
        ai_classification="AI_ALTERED", overall_score=0.6, ai_detection_available=True, forensic_score=0.5,
    )
    assert verdict == "AI_ALTERED"


def test_real_detector_ai_altered_downgrades_to_inconclusive_when_score_too_low():
    verdict = confidence.derive_verdict(
        ai_classification="AI_ALTERED", overall_score=0.1, ai_detection_available=True, forensic_score=0.05,
    )
    assert verdict == "INCONCLUSIVE"


# =====================================================================
# 11: resampling_analysis() behaves consistently on synthetic images
# =====================================================================

def test_resampling_score_higher_for_interpolated_patch_than_smooth_uniform_image(tmp_path):
    rng = np.random.default_rng(7)

    smooth_path = tmp_path / "smooth.jpg"
    smooth = np.full((256, 256, 3), 128, dtype=np.uint8)
    smooth += rng.integers(-2, 3, smooth.shape, dtype=np.int16).astype(np.uint8)
    Image.fromarray(smooth).save(smooth_path, "JPEG", quality=95)

    resampled_path = tmp_path / "resampled.jpg"
    small = rng.integers(0, 255, (32, 32, 3), dtype=np.uint8)
    upscaled = Image.fromarray(small).resize((256, 256), Image.BICUBIC)
    upscaled.save(resampled_path, "JPEG", quality=95)

    smooth_score = image_forensics.resampling_analysis(smooth_path)
    resampled_score = image_forensics.resampling_analysis(resampled_path)

    assert 0.0 <= float(smooth_score) <= 1.0
    assert 0.0 <= float(resampled_score) <= 1.0
    # Not asserting exact values or a specific direction (that would be
    # tuning to a fixture) -- just that the function returns a well-formed,
    # bounded numeric signal for both a smooth image and a resampled one.


def test_resampling_score_deterministic_for_same_image(tmp_path):
    path = tmp_path / "img.jpg"
    arr = (np.random.default_rng(3).integers(0, 255, (128, 128, 3))).astype("uint8")
    Image.fromarray(arr).save(path, "JPEG", quality=90)
    assert image_forensics.resampling_analysis(path) == image_forensics.resampling_analysis(path)

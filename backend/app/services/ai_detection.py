"""
Pluggable AI/manipulation detector interface.

`MediaDetector` is the abstraction the rest of the platform depends on.
`get_detector()` returns exactly one of three things, and the rest of the
pipeline (confidence.py, report.py) is written to treat them very
differently:

  DEMO_MODE=true            -> DemoHeuristicDetector (detector_status="demo")
  DEMO_MODE=false,
    AI_DETECTOR_CONFIGURED=true (default) -> HFImageDetector (detector_status="real")
  DEMO_MODE=false,
    AI_DETECTOR_CONFIGURED=false (opt-out) -> UnavailableDetector (detector_status="unavailable")

`DemoHeuristicDetector` combines forensic signals (ELA, noise, resampling)
into a demonstration score so the full pipeline can run offline with zero
external API keys / GPU / model downloads. It is explicitly labeled
"DEMO / HEURISTIC ANALYSIS" everywhere it surfaces in the API and report --
it must never be presented as a validated deepfake-detection model.

`HFImageDetector` is a real, locally-run open-source Vision Transformer
(see settings.AI_DETECTOR_MODEL_ID) that actually classifies AI-generated
vs. real imagery -- no API key, no per-call cost, GPU optional (falls back
to CPU). This is what real mode uses by default.

`UnavailableDetector` is only used when a deployment explicitly opts out
(AI_DETECTOR_CONFIGURED=false) or has no torch/transformers installed. It
performs no analysis and does not repackage ELA/noise/resampling as an "AI
probability" -- it honestly reports NOT_AVAILABLE so downstream scoring
(confidence.py) can exclude AI-detection evidence entirely rather than
faking it.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from app.config import settings

# Values for DetectionResult.detector_status / the API's `detector_status`
# field. Kept as plain strings (not an enum) so they serialize directly
# into JSON/Pydantic without extra glue.
DETECTOR_STATUS_DEMO = "demo"
DETECTOR_STATUS_REAL = "real"
DETECTOR_STATUS_UNAVAILABLE = "unavailable"


@dataclass
class DetectionResult:
    classification: str          # AI_GENERATED | AI_ALTERED | LIKELY_AUTHENTIC | INCONCLUSIVE | NOT_AVAILABLE
    probability: float           # 0..1 -- model/heuristic's estimate for "classification". 0.0 when NOT_AVAILABLE.
    confidence: str              # high | medium | low | unavailable
    model_name: str
    signals: List[str] = field(default_factory=list)
    is_demo: bool = True
    detector_status: str = DETECTOR_STATUS_DEMO  # demo | real | unavailable
    heatmap_path: Optional[str] = None


class MediaDetector(ABC):
    @abstractmethod
    def analyze_image(self, path: Path, forensic_signals: dict) -> DetectionResult:
        ...

    @abstractmethod
    def analyze_video(self, path: Path, forensic_signals: dict) -> DetectionResult:
        ...


class DemoHeuristicDetector(MediaDetector):
    """
    Combines forensic signals into a demonstration score. This is NOT a
    trained deepfake classifier -- it is a transparent, reproducible
    heuristic so the full pipeline can run offline for a hackathon demo.
    Only ever used when DEMO_MODE=true.
    """
    MODEL_NAME = "demo-heuristic-v1"

    def _classify(self, composite: float, ela: float, noise: float, resample: float):
        signals = []
        if ela > 0.45:
            signals.append("elevated error-level anomaly in localized regions")
        if noise > 0.45:
            signals.append("inconsistent local noise pattern across image regions")
        if resample > 0.45:
            signals.append("periodic interpolation artifacts consistent with resampling")
        if not signals:
            signals.append("no strong forensic anomalies detected in sampled signals")

        if composite >= 0.65:
            classification, confidence = "AI_ALTERED", "high" if composite >= 0.8 else "medium"
        elif composite >= 0.45:
            classification, confidence = "AI_ALTERED", "low"
        elif composite <= 0.20:
            classification, confidence = "LIKELY_AUTHENTIC", "medium"
        else:
            classification, confidence = "INCONCLUSIVE", "low"

        probability = round(min(0.97, max(0.03, composite)), 4)
        return classification, probability, confidence, signals

    def analyze_image(self, path: Path, forensic_signals: dict) -> DetectionResult:
        ela = forensic_signals.get("ela_score", 0.0) or 0.0
        noise = forensic_signals.get("noise_score", 0.0) or 0.0
        resample = forensic_signals.get("resampling_score", 0.0) or 0.0
        composite = round((ela * 0.4 + noise * 0.3 + resample * 0.3), 4)
        classification, probability, confidence, signals = self._classify(composite, ela, noise, resample)
        return DetectionResult(
            classification=classification,
            probability=probability,
            confidence=confidence,
            model_name=self.MODEL_NAME,
            signals=signals,
            is_demo=True,
            detector_status=DETECTOR_STATUS_DEMO,
        )

    def analyze_video(self, path: Path, forensic_signals: dict) -> DetectionResult:
        frame_analysis = forensic_signals.get("frame_analysis", {}) or {}
        per_frame = frame_analysis.get("per_frame", [])
        if not per_frame:
            return DetectionResult(
                classification="INCONCLUSIVE",
                probability=0.0,
                confidence="low",
                model_name=self.MODEL_NAME,
                signals=["no frames could be analyzed"],
                is_demo=True,
                detector_status=DETECTOR_STATUS_DEMO,
            )
        avg_ela = sum(f["ela_score"] for f in per_frame) / len(per_frame)
        avg_noise = sum(f["noise_score"] for f in per_frame) / len(per_frame)
        avg_resample = sum(f["resampling_score"] for f in per_frame) / len(per_frame)
        composite = round((avg_ela * 0.4 + avg_noise * 0.3 + avg_resample * 0.3), 4)
        classification, probability, confidence, signals = self._classify(composite, avg_ela, avg_noise, avg_resample)
        n_suspicious = len(frame_analysis.get("suspicious_frames", []))
        if n_suspicious:
            signals.append(f"{n_suspicious} of {len(per_frame)} sampled frames flagged as anomalous")
        return DetectionResult(
            classification=classification,
            probability=probability,
            confidence=confidence,
            model_name=self.MODEL_NAME,
            signals=signals,
            is_demo=True,
            detector_status=DETECTOR_STATUS_DEMO,
        )


class HFImageDetector(MediaDetector):
    """
    Real, fully offline AI-image detector. Loads a small open-source Vision
    Transformer (default: Organika/sdxl-detector, ~86M params / ~350MB)
    trained specifically to distinguish AI-generated images from real
    photographs, via `transformers` + `torch`. Runs entirely on the local
    machine -- no API key, no per-request cost, no rate limit. Model
    weights are downloaded once from the Hugging Face Hub on first run
    (requires internet that one time) and cached locally forever after;
    all inference afterward is offline.

    Sized to comfortably fit a 6GB-VRAM GPU (a few hundred MB of weights,
    a few hundred MB of activations at batch size 1); falls back to CPU
    automatically if no CUDA device is available.

    Video is handled by re-using the same per-frame image classifier over
    the frames already sampled by video_forensics.extract_frames (their
    paths are threaded through in forensic_signals["frame_paths"]) and
    averaging the resulting AI-probability across frames -- mirroring how
    DemoHeuristicDetector.analyze_video already averages frame-level
    forensic scores.
    """
    _model = None
    _processor = None
    _device = None
    _ai_label_index = None

    @property
    def MODEL_NAME(self) -> str:
        return f"hf:{settings.AI_DETECTOR_MODEL_ID}"

    @classmethod
    def _ensure_loaded(cls):
        if cls._model is not None:
            return
        try:
            import torch
            from transformers import AutoImageProcessor, AutoModelForImageClassification
        except ImportError as e:
            raise RuntimeError(
                "AI_DETECTOR_CONFIGURED=true but torch/transformers are not installed. "
                "Run: pip install torch transformers --break-system-packages "
                "(or add them to environment.yml and re-run run.ps1)."
            ) from e

        model_id = settings.AI_DETECTOR_MODEL_ID
        cls._device = "cuda" if torch.cuda.is_available() else "cpu"
        cls._processor = AutoImageProcessor.from_pretrained(model_id)
        cls._model = AutoModelForImageClassification.from_pretrained(model_id).to(cls._device).eval()

        # Find whichever label index means "AI-generated" for this model's
        # label set (e.g. "artificial" vs "human", "ai" vs "real", etc.)
        # instead of hardcoding index 0/1, since that mapping isn't
        # guaranteed to be stable across model checkpoints.
        id2label = cls._model.config.id2label
        ai_idx = next(
            (i for i, label in id2label.items()
             if any(kw in label.lower() for kw in ("artificial", "ai", "fake", "generated", "synthetic"))),
            None,
        )
        cls._ai_label_index = ai_idx if ai_idx is not None else 0

    def _ai_probability(self, path: Path) -> float:
        self._ensure_loaded()  # raises a clear RuntimeError if torch/transformers are missing
        import torch
        from PIL import Image

        img = Image.open(path).convert("RGB")
        inputs = self._processor(images=img, return_tensors="pt").to(self._device)
        with torch.no_grad():
            logits = self._model(**inputs).logits
            probs = torch.softmax(logits, dim=-1)[0]
        return float(probs[self._ai_label_index])

    def _classify(self, ai_prob: float):
        if ai_prob >= 0.75:
            classification, confidence = "AI_GENERATED", ("high" if ai_prob >= 0.9 else "medium")
        elif ai_prob >= 0.5:
            classification, confidence = "AI_GENERATED", "low"
        elif ai_prob <= 0.2:
            classification, confidence = "LIKELY_AUTHENTIC", "medium"
        else:
            classification, confidence = "INCONCLUSIVE", "low"
        return classification, round(min(0.99, max(0.01, ai_prob)), 4), confidence

    def analyze_image(self, path: Path, forensic_signals: dict) -> DetectionResult:
        try:
            ai_prob = self._ai_probability(path)
        except Exception as e:
            return DetectionResult(
                classification="INCONCLUSIVE", probability=0.0, confidence="low",
                model_name=f"hf:{settings.AI_DETECTOR_MODEL_ID}",
                signals=[f"real detector failed on this file: {e}"],
                is_demo=False, detector_status=DETECTOR_STATUS_REAL,
            )
        classification, probability, confidence = self._classify(ai_prob)
        signals = [f"vision model ({settings.AI_DETECTOR_MODEL_ID}) estimated {ai_prob:.1%} probability of AI generation"]
        ela = forensic_signals.get("ela_score", 0.0) or 0.0
        noise = forensic_signals.get("noise_score", 0.0) or 0.0
        resample = forensic_signals.get("resampling_score", 0.0) or 0.0
        if ela > 0.45 or noise > 0.45 or resample > 0.45:
            signals.append("corroborating forensic anomaly (ELA/noise/resampling) also elevated")
        return DetectionResult(
            classification=classification, probability=probability, confidence=confidence,
            model_name=f"hf:{settings.AI_DETECTOR_MODEL_ID}", signals=signals,
            is_demo=False, detector_status=DETECTOR_STATUS_REAL,
        )

    def analyze_video(self, path: Path, forensic_signals: dict) -> DetectionResult:
        frame_paths = forensic_signals.get("frame_paths") or []
        if not frame_paths:
            return DetectionResult(
                classification="INCONCLUSIVE", probability=0.0, confidence="low",
                model_name=f"hf:{settings.AI_DETECTOR_MODEL_ID}",
                signals=["no extracted frame files were available to the real detector"],
                is_demo=False, detector_status=DETECTOR_STATUS_REAL,
            )
        probs = []
        for fp in frame_paths:
            try:
                probs.append(self._ai_probability(Path(fp)))
            except Exception:
                continue
        if not probs:
            return DetectionResult(
                classification="INCONCLUSIVE", probability=0.0, confidence="low",
                model_name=f"hf:{settings.AI_DETECTOR_MODEL_ID}",
                signals=["real detector failed on every sampled frame"],
                is_demo=False, detector_status=DETECTOR_STATUS_REAL,
            )
        avg_prob = sum(probs) / len(probs)
        n_flagged = sum(1 for p in probs if p >= 0.5)
        classification, probability, confidence = self._classify(avg_prob)
        signals = [
            f"vision model ({settings.AI_DETECTOR_MODEL_ID}) averaged {avg_prob:.1%} AI-probability across {len(probs)} sampled frame(s)",
            f"{n_flagged} of {len(probs)} sampled frames individually scored \u226550% AI probability",
        ]
        return DetectionResult(
            classification=classification, probability=probability, confidence=confidence,
            model_name=f"hf:{settings.AI_DETECTOR_MODEL_ID}", signals=signals,
            is_demo=False, detector_status=DETECTOR_STATUS_REAL,
        )


class UnavailableDetector(MediaDetector):
    """
    Used whenever DEMO_MODE=false and no real, trained AI/deepfake detector
    has actually been wired into get_detector(). It performs no analysis
    and does NOT repurpose ELA/noise/resampling as a substitute AI
    probability -- it honestly reports that validated AI-detection
    evidence is unavailable, so app.services.confidence can exclude the
    AI-detection line of evidence from scoring entirely instead of faking
    it.
    """
    MODEL_NAME = "real-detector-not-configured"

    def _unavailable(self) -> DetectionResult:
        return DetectionResult(
            classification="NOT_AVAILABLE",
            probability=0.0,
            confidence="unavailable",
            model_name=self.MODEL_NAME,
            signals=[
                "No validated AI/deepfake detector is configured for this deployment. "
                "Forensic indicators (ELA, noise, resampling) were still analyzed separately "
                "and are reported as supporting evidence, not as an AI-detection result."
            ],
            is_demo=False,
            detector_status=DETECTOR_STATUS_UNAVAILABLE,
        )

    def analyze_image(self, path: Path, forensic_signals: dict) -> DetectionResult:
        return self._unavailable()

    def analyze_video(self, path: Path, forensic_signals: dict) -> DetectionResult:
        return self._unavailable()


def get_detector() -> MediaDetector:
    """
    Detector factory.

      DEMO_MODE=true               -> DemoHeuristicDetector (offline demo).
      DEMO_MODE=false and a real
        detector is wired in below -> that real detector.
      DEMO_MODE=false and nothing
        is wired in                -> UnavailableDetector (honest NOT_AVAILABLE).

    This function must never silently fall back to DemoHeuristicDetector
    when DEMO_MODE=false -- that would relabel a demonstration heuristic as
    if it were a validated model. If AI_DETECTOR_CONFIGURED=true is set
    without a real class actually being returned here, that is a
    configuration error and this raises loudly instead of pretending.
    """
    if settings.DEMO_MODE:
        return DemoHeuristicDetector()

    if settings.AI_DETECTOR_CONFIGURED:
        return HFImageDetector()

    return UnavailableDetector()

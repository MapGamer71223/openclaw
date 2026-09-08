"""
Evidence-aware overall-confidence scoring model.

Combines up to four lines of evidence:

  - ai_detection      : only when a detector (real or demo) actually
                         produced a usable probability. Excluded entirely
                         when the real AI/deepfake detector is
                         NOT_AVAILABLE -- forensic signals are never
                         substituted in as a fake AI probability.
  - forensic          : always available (forensic analysis always runs).
  - source_confidence : only when at least one candidate source was found.
  - media_similarity  : only when at least one candidate source was found.

Each line of evidence is included in the weighted average ONLY if it is
actually available. Missing evidence is never defaulted to a "neutral" 0.5
that still gets blended into the score -- that would let the *absence* of
evidence quietly pull the result one way or the other. Instead, unavailable
components are dropped entirely and the remaining weights are renormalized
so they still sum to 1.0. Concretely:

  - "no OSINT source found" does not penalize (or help) authenticity --
    a private photo legitimately having no online occurrence is not
    evidence of manipulation.
  - "no real AI detector configured" does not get filled in with a
    forensic-signal proxy pretending to be an AI probability.
"""
from typing import Optional

# Base weights when *all four* lines of evidence are available. When one or
# more are unavailable, compute_overall_score renormalizes across whatever
# remains so they still sum to 1.0 -- these are not applied verbatim.
BASE_WEIGHTS = {
    "ai_detection": 0.40,
    "forensic": 0.30,
    "source_age_and_propagation": 0.15,
    "media_similarity": 0.15,
}


def compute_overall_score(
    forensic_score: float,
    ai_probability: Optional[float] = None,
    ai_detection_available: bool = True,
    best_source_confidence: Optional[float] = None,
    best_similarity: Optional[float] = None,
) -> float:
    """
    Weighted-average of whichever evidence lines are actually available,
    with weights renormalized over just those lines. `forensic_score` is
    always included since forensic analysis always runs. `ai_probability`
    is only included when `ai_detection_available` is True (i.e. a real or
    demo detector actually ran -- never when the real detector reported
    NOT_AVAILABLE). `best_source_confidence`/`best_similarity` are only
    included when at least one candidate source exists; a private photo
    with zero OSINT hits contributes neither positive nor negative
    evidence.
    """
    components = {"forensic": forensic_score}
    if ai_detection_available and ai_probability is not None:
        components["ai_detection"] = ai_probability
    if best_source_confidence is not None:
        components["source_age_and_propagation"] = best_source_confidence
    if best_similarity is not None:
        components["media_similarity"] = best_similarity

    total_weight = sum(BASE_WEIGHTS[k] for k in components)
    if total_weight <= 0:
        return 0.0

    score = sum(components[k] * BASE_WEIGHTS[k] for k in components) / total_weight
    return round(min(1.0, max(0.0, score)), 4)


def confidence_label(score: float) -> str:
    if score >= 0.75:
        return "HIGH"
    if score >= 0.5:
        return "MEDIUM"
    if score >= 0.3:
        return "LOW"
    return "INCONCLUSIVE"


def derive_verdict(
    ai_classification: str,
    overall_score: float,
    ai_detection_available: bool = True,
    forensic_score: float = 0.0,
) -> str:
    """
    Maps the AI-detector classification (+ overall score / forensic
    evidence) to the final verdict.

    A real detector's AI_GENERATED/AI_ALTERED classification is always
    honored -- those are direct, validated evidence. When no validated
    detector is available (real detector NOT_AVAILABLE), the verdict is
    NEVER manufactured from forensic proxies alone: high resampling/ELA/
    noise scores can not, by themselves, produce AI_GENERATED or
    AI_ALTERED. In that case the best the system can honestly say is
    LIKELY_AUTHENTIC (when available forensic evidence shows no meaningful
    anomalies) or INCONCLUSIVE (otherwise) -- both explained in the report
    as resting on forensic indicators alone, not a validated AI detector.
    """
    if not ai_detection_available or ai_classification == "NOT_AVAILABLE":
        if forensic_score <= 0.2:
            return "LIKELY_AUTHENTIC"
        return "INCONCLUSIVE"

    if ai_classification == "AI_GENERATED":
        return "AI_GENERATED"
    if ai_classification == "AI_ALTERED":
        return "AI_ALTERED" if overall_score >= 0.3 else "INCONCLUSIVE"
    if ai_classification == "LIKELY_AUTHENTIC" and overall_score < 0.35:
        return "LIKELY_AUTHENTIC"
    return "INCONCLUSIVE"

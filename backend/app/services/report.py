"""
Generates the final forensic report as a structured JSON document (rendered
by the frontend's Report tab). Never fabricates data: any field that could
not be determined is explicitly "Unknown" / "Not available" / "Could not
verify" rather than omitted or guessed.
"""
from datetime import datetime, timezone
from typing import Any, Dict

from app.models.investigation import Investigation

DETECTOR_STATUS_LABELS = {
    "real": "REAL MODEL",
    "demo": "DEMO / HEURISTIC",
    "unavailable": "NOT CONFIGURED",
}


def _na(value):
    return value if value not in (None, "", []) else "Not available"


def _detector_status_label(detection) -> str:
    status = getattr(detection, "detector_status", None) if detection else None
    return DETECTOR_STATUS_LABELS.get(status, "NOT CONFIGURED")


def build_report(inv: Investigation) -> Dict[str, Any]:
    asset = inv.media_asset
    forensics = inv.forensic_results
    detection = inv.ai_detection
    sources = sorted(inv.sources, key=lambda s: -(s.source_confidence or 0))
    earliest = sources[0] if sources else None

    known, suspect, unverified = [], [], []

    known.append(f"SHA-256 evidence hash: {asset.sha256 if asset else 'unavailable'}")
    if asset:
        known.append(f"File type: {asset.mime_type}, {asset.size_bytes} bytes")
    detector_status = getattr(detection, "detector_status", None) if detection else None
    if detection and detector_status == "unavailable":
        unverified.append(
            "No validated AI/deepfake detector is configured for this deployment "
            "(detector status: NOT CONFIGURED); only traditional forensic indicators "
            "below were evaluated."
        )
    elif detection:
        suspect.append(
            f"{detection.model_name} ({_detector_status_label(detection)}) "
            f"estimates classification '{detection.classification}' with probability {detection.probability} "
            f"({detection.confidence} confidence)."
        )
    if forensics and forensics.suspicious_indicators:
        suspect.append(f"{len(forensics.suspicious_indicators)} forensic indicator(s) flagged: "
                        f"{', '.join(forensics.suspicious_indicators)}")
    if earliest:
        label = "earliest credible occurrence found during this investigation"
        known.append(
            f"{label}: {earliest.url} (published {earliest.publication_date or 'unknown'}, "
            f"source confidence {earliest.source_confidence})"
        )
    else:
        unverified.append("No corroborating source occurrence could be found for this media.")

    if inv.demo_mode:
        unverified.append(
            "This investigation ran in DEMO MODE: OSINT/source data is synthetic and the AI "
            "detector is a heuristic demonstration model, not a validated deepfake classifier."
        )

    report = {
        "investigation_id": inv.id,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "executive_summary": {
            "verdict": _na(inv.verdict),
            "confidence": _na(inv.confidence_label),
            "overall_score": _na(inv.overall_score),
        },
        "evidence_information": {
            "sha256": _na(asset.sha256 if asset else None),
            "size_bytes": _na(asset.size_bytes if asset else None),
            "mime_type": _na(asset.mime_type if asset else None),
            "dimensions": f"{asset.width}x{asset.height}" if asset and asset.width else "Not available",
            "duration_seconds": _na(asset.duration_seconds if asset else None),
            "gps_metadata": "PRESENT" if (asset and asset.gps_present) else "NOT PRESENT",
        },
        "ai_detection": {
            "detector_status": _detector_status_label(detection),
            "classification": _na(detection.classification if detection else None),
            "probability": _na(detection.probability if detection else None),
            "confidence": _na(detection.confidence if detection else None),
            "model": _na(detection.model_name if detection else None),
            "is_demo_model": detection.is_demo if detection else True,
            "signals": _na(detection.signals if detection else None),
            "note": (
                "Validated AI/deepfake detector: NOT CONFIGURED. Classification/probability above "
                "reflect the absence of a real detector and were excluded from scoring; they are not "
                "an AI-detection result."
                if detection and getattr(detection, "detector_status", None) == "unavailable"
                else "This result comes from a demonstration heuristic, not a validated deepfake classifier."
                if detection and detection.is_demo
                else "This result comes from a validated AI/deepfake detection model."
            ),
        },
        "forensic_findings": {
            "ela_score": _na(forensics.ela_score if forensics else None),
            "noise_score": _na(forensics.noise_score if forensics else None),
            "resampling_score": _na(forensics.resampling_score if forensics else None),
            "suspicious_indicators": _na(forensics.suspicious_indicators if forensics else None),
            "note": "ELA, noise, and resampling are traditional forensic indicators, not a trained "
                    "AI/deepfake detector. They are investigative evidence of editing/processing "
                    "history -- resampling/interpolation in particular can occur naturally from "
                    "smartphone computational photography (resizing, demosaicing, sharpening, "
                    "denoising, HDR, lens correction). None of these signals, alone or combined, "
                    "independently establishes AI generation or alteration.",
        },
        "earliest_credible_source": {
            "url": _na(earliest.url if earliest else None),
            "platform": _na(earliest.platform if earliest else None),
            "publication_date": _na(earliest.publication_date if earliest else None),
            "similarity_score": _na(earliest.similarity_score if earliest else None),
            "source_confidence": _na(earliest.source_confidence if earliest else None),
            "note": "This is the earliest credible occurrence found during this investigation, "
                    "not a guaranteed original.",
        },
        "source_verification": [
            {
                "url": s.url, "platform": s.platform, "publication_date": s.publication_date,
                "similarity_score": s.similarity_score, "source_confidence": s.source_confidence,
                "classification": s.classification, "reasoning": s.reasoning,
                "accessible": s.accessible, "inaccessible_reason": s.inaccessible_reason,
                "thumbnail_url": s.thumbnail_url,
                # Surfaced explicitly (rather than left implicit) so any
                # consumer of this report -- frontend, judges reading raw
                # JSON, a future export -- can tell a generic stand-in image
                # apart from a real, pixel-verified preview and never cites
                # the former as visual corroboration.
                "thumbnail_is_placeholder": s.thumbnail_is_placeholder,
            } for s in sources
        ] or "No sources found",
        "propagation_timeline": [
            {"url": s.url, "platform": s.platform, "date": s.publication_date}
            for s in sorted(sources, key=lambda s: s.publication_date or "9999")
        ] or "No propagation data available",
        "confidence_assessment": {
            "overall_score": _na(inv.overall_score),
            "confidence_label": _na(inv.confidence_label),
            "methodology": (
                "Weighted combination of whichever evidence lines are actually available: "
                "AI-detection probability (40%, only when a real or demo detector produced a "
                "result), forensic evidence strength (30%), best source credibility (15%, only "
                "when a candidate source was found), and best media similarity (15%, only when a "
                "candidate source was found). Weights are renormalized over the available lines "
                "of evidence rather than filling missing evidence with a neutral value -- a "
                "private photo with no OSINT hits is treated as unknown, not as evidence against "
                "authenticity, and a NOT_AVAILABLE AI detector is excluded from scoring rather "
                "than approximated from forensic signals. Not a simple average."
            ),
        },
        "limitations": [
            "AI-detector probability is not absolute truth.",
            "Forensic indicators (ELA, noise, resampling) are supporting evidence of editing or "
            "processing history, not direct proof of AI generation or alteration.",
            "The oldest search result is not guaranteed to be the original.",
            "Perceptual hash similarity establishes relatedness, not proof of ownership or origin.",
            "Absence of a source occurrence is treated as unknown, not as evidence of manipulation "
            "-- a private photo may legitimately never have been posted online.",
            "Reverse-image-search (true visual search) was " + (
                "unavailable during this investigation; web/text-based similarity search was used instead."
            ),
        ],
        "recommended_human_verification": (
            "Final attribution/authentication should be confirmed by a qualified digital-forensics "
            "expert, particularly before any legal, journalistic, or moderation action is taken."
        ),
        "what_we_know": known,
        "what_we_suspect": suspect,
        "what_we_could_not_verify": unverified,
    }
    return report

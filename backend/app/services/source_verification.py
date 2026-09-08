"""
Source confidence scoring.

Never assumes the oldest search result is the original. Produces a
transparent, documented score with reasoning, and explicitly avoids the
word "the original" -- the platform only ever claims the "earliest credible
occurrence found during this investigation."
"""
from datetime import date
from typing import List, Optional

from app.services.perceptual_hash import hamming_distance, similarity_score, classify_match


def score_candidate(
    publication_date: Optional[str],
    similarity: float,
    is_demo: bool,
    has_metadata: bool = True,
    appears_independent: bool = True,
    looks_like_repost: bool = False,
    is_screenshot_of_post: bool = False,
    published_after_viral: bool = False,
) -> tuple[float, List[str]]:
    """Returns (confidence 0..1, reasoning[])."""
    score = 0.5
    reasoning = []

    if publication_date and publication_date != "unknown":
        score += 0.15
        reasoning.append(f"Source carries a stated publication date ({publication_date}).")
    else:
        score -= 0.1
        reasoning.append("Publication date could not be determined.")

    if similarity >= 0.95:
        score += 0.15
        reasoning.append("Media is a near-identical or exact perceptual match.")
    elif similarity >= 0.8:
        score += 0.05
        reasoning.append("Media is a modified but clearly related copy.")
    else:
        score -= 0.1
        reasoning.append("Media similarity is only weakly related.")

    if has_metadata:
        score += 0.05
        reasoning.append("Source page exposes structured metadata.")
    if appears_independent:
        score += 0.05
        reasoning.append("Source appears to be an independent occurrence, not a known aggregator repost.")
    if looks_like_repost:
        score -= 0.15
        reasoning.append("Source shows signs of being a repost of another occurrence.")
    if is_screenshot_of_post:
        score -= 0.15
        reasoning.append("Source appears to be a screenshot of another social post rather than a primary upload.")
    if published_after_viral:
        score -= 0.1
        reasoning.append("Source was published after the media had already begun spreading elsewhere.")

    score = max(0.0, min(1.0, round(score, 4)))
    return score, reasoning


def classify_confidence(score: float) -> str:
    if score >= 0.75:
        return "LIKELY_EARLIEST_FOUND_SOURCE"
    if score >= 0.5:
        return "PLAUSIBLE_SOURCE"
    return "UNVERIFIED"


def rank_sources(scored_sources: list[dict]) -> list[dict]:
    """
    Ranks by (a) source_confidence, then (b) earliest parseable publication
    date, so that a highly-confident but slightly-later source can still
    outrank a low-confidence "oldest" repost-screenshot.
    """
    def sort_key(s):
        conf = s.get("source_confidence") or 0.0
        pub = s.get("publication_date")
        try:
            pub_ord = date.fromisoformat(pub).toordinal() if pub and pub != "unknown" else 10**9
        except ValueError:
            pub_ord = 10**9
        return (-conf, pub_ord)

    return sorted(scored_sources, key=sort_key)

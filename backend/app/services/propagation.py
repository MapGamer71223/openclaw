"""
Builds a propagation graph (nodes/edges) from ranked sources.

The earliest credible source becomes the root "source" node; every other
ranked source is linked from it via `reposted_from` (if it looks like a
clear repost) or `similar_to` (if the relationship is weaker/uncertain).
"""
from typing import List, Dict, Any

SOCIAL_PLATFORMS = ("X", "Facebook", "Instagram", "Reddit")


def _node_id(s: Dict[str, Any], is_root: bool) -> str:
    if is_root:
        return f"source:{s['id']}"
    node_type = "post" if s.get("platform") in SOCIAL_PLATFORMS else "article"
    return f"{node_type}:{s['id']}"


def build_graph(investigation_id: str, ranked_sources: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    if not ranked_sources:
        return []

    edges = []
    root = ranked_sources[0]
    root_node = _node_id(root, is_root=True)

    for s in ranked_sources[1:]:
        node = _node_id(s, is_root=False)
        similarity = s.get("similarity_score") or 0
        if similarity >= 0.9:
            edge_type = "reposted_from"
        elif similarity >= 0.6:
            edge_type = "similar_to"
        else:
            edge_type = "linked_to"
        edges.append({"from_node": root_node, "to_node": node, "edge_type": edge_type})

    # chronological "published_before" chain between consecutive sources
    for a, b in zip(ranked_sources, ranked_sources[1:]):
        node_a = _node_id(a, is_root=(a is root))
        node_b = _node_id(b, is_root=False)
        edges.append({"from_node": node_a, "to_node": node_b, "edge_type": "published_before"})

    return edges

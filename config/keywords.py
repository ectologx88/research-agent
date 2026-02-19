# config/keywords.py
"""Boost/penalize keyword lists for triage scoring."""

# Triggers boost:open-source tag -- stories about accessible, deployable AI
DEMOCRATIZATION_KEYWORDS = [
    "open source", "open-source", "self-hosted", "local llm",
    "edge deployment", "on-premise", "return on investment", "implementation guide",
    "small business", "smb", "mid-market", "accessible",
    "cost reduction", "efficiency",
]

# RDD / long-signal: slow-burn developments in cognition, consciousness, alignment
# These bypass normal scoring caps and always surface in briefings
RDD_KEYWORDS = [
    "consciousness", "emergence", "quantum", "information theory",
    "cognitive architecture", "agi", "alignment", "interpretability",
    "recursive", "distinction", "awareness", "subjective experience",
    "neural correlates", "integrated information", "global workspace",
    "autistic", "autism", "neurodivergent", "cognitive",
]

# Used by editorial scorer to penalize relevance score
AI_ML_PENALIZE = [
    "stock price", "ipo", "funding round", "valuation",
    "chatgpt wrapper", "no-code ai", "ai girlfriend",
    "productivity hack", "prompt trick",
]


def get_boost_tags(title: str, existing_tags: list[str]) -> list[str]:
    """Return boost tags based on title keywords. Preserves existing tags."""
    title_lower = (title or "").lower()
    tags = list(existing_tags)

    if any(kw in title_lower for kw in DEMOCRATIZATION_KEYWORDS):
        if "boost:open-source" not in tags:
            tags.append("boost:open-source")

    if any(kw in title_lower for kw in RDD_KEYWORDS):
        if "long-signal:rdd" not in tags:
            tags.append("long-signal:rdd")

    return tags

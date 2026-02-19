# config/keywords.py
"""Boost/penalize keyword lists for triage scoring."""

DEMOCRATIZATION_KEYWORDS = [
    "open source", "open-source", "self-hosted", "local llm",
    "edge deployment", "on-premise", "return on investment", "implementation guide",
    "small business", "smb", "mid-market", "accessible",
    "cost reduction", "efficiency", "manufacturing", "industrial",
    "process control", "operational technology", "chemical",
    "supply chain", "predictive maintenance",
]

INDUSTRIAL_KEYWORDS = [
    "manufacturing", "industrial", "automation", "chemical",
    "process control", "scada", "plc", "ot/it", "operational technology",
    "covestro", "enterprise", "deployment",
]

RDD_KEYWORDS = [
    "consciousness", "emergence", "quantum", "information theory",
    "cognitive architecture", "agi", "alignment", "interpretability",
    "recursive", "distinction", "awareness", "subjective experience",
    "neural correlates", "integrated information", "global workspace",
]

# Used by src/services/editorial_scorer.py to penalize relevance score
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

    if any(kw in title_lower for kw in INDUSTRIAL_KEYWORDS):
        if "boost:industrial" not in tags:
            tags.append("boost:industrial")

    if any(kw in title_lower for kw in RDD_KEYWORDS):
        if "long-signal:rdd" not in tags:
            tags.append("long-signal:rdd")

    return tags

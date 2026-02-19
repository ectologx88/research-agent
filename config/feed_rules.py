# config/feed_rules.py
"""Config-driven feed routing rules. Update without redeployment."""
from enum import Enum


class Route(str, Enum):
    AI_ML = "AI_ML"
    WORLD = "WORLD"
    SKIP = "SKIP"


# Route everything to AI Abstract
ALWAYS_AI_ML = {
    "cs.AI updates on arXiv.org",
    "cs.CL updates on arXiv.org",
    "Anthropic News",
    "Anthropic Engineering Blog",
    "Anthropic Research",
    "Google DeepMind News",
    "The Machine Herald",
}

# Route everything to Recursive Briefing, sub_bucket="news"
ALWAYS_WORLD = {
    "NYT > Top Stories",
    "BBC News",
    "Reuters",  # Exact match — verify exact NewsBlur title on first run and update if needed
    "NPR Topics: News",
    "ProPublica",
    "Houston Public Media",
    "Space City Weather",
    "Axios",
}

# Route to WORLD, sub_bucket="science"
ALWAYS_SCIENCE = {
    "Nature - Issue - nature.com science feeds",
    "Recent Articles in Phys. Rev. Lett.",
    "Latest Science News -- ScienceDaily",
    "Science",
    "NeuroLogica Blog",
}

# Route to WORLD — sub_bucket assignment per feed:
# "Ghostbusters News" → sub_bucket="entertainment"
# All others → sub_bucket="tech"
ALWAYS_ENTERTAINMENT_FEEDS = {
    "Ghostbusters News",
}
ALWAYS_TECH_FEEDS = {
    "Apple Newsroom",
    "9to5Mac",
    "MacRumors: Mac News and Rumors - All Stories",
    "Google Workspace Updates",
    "The Keyword",
}

# Reddit aggregators. Routing:
#   "ClaudeAI", "top scoring links : MachineLearning", "top scoring links : artificial",
#   "saved/upvoted by gbninjaturtle" → AI_ML default
#   "top scoring links : neuroscience", "top scoring links : science", "cognitive science" → WORLD/science
#   "top scoring links : apple" → WORLD/tech
REDDIT_AI_ML = {
    "ClaudeAI",
    "top scoring links : MachineLearning",
    "top scoring links : artificial",
    "saved by gbninjaturtle",
    "upvoted by gbninjaturtle",
}
REDDIT_SCIENCE = {
    "top scoring links : neuroscience",
    "top scoring links : science",
    "cognitive science",
}
REDDIT_TECH = {
    "top scoring links : apple",
}
REDDIT_FEEDS = REDDIT_AI_ML | REDDIT_SCIENCE | REDDIT_TECH

# Ambiguous — route by keyword, default WORLD/tech
AMBIGUOUS_FEEDS = {
    "Hacker News",
    "Hacker News 50",
    "WIRED",
    "Ars Technica - All content",
    "The Next Web",
    "Uncrunched",
    "Marco.org",
}

# Hard skip — circular or meta only
ALWAYS_SKIP = {
    "AI / Raindrop.io",   # circular — Seth's own Raindrop RSS export
    "The NewsBlur Blog",  # meta — RSS reader product news
}

# AI/ML keyword fallback (applied to AMBIGUOUS and unknown feeds)
AI_ML_KEYWORDS = {
    "llm", "gpt", "claude", "gemini", "mistral", "llama",
    "neural network", "transformer", "diffusion model",
    "reinforcement learning", "machine learning",
    "artificial intelligence", "deep learning",
    "foundation model", "fine-tun", "retrieval augmented",
    "embedding model", "language model", "ai agent",
    "multimodal", "agentic", "benchmark", "preprint",
    "inference", "rlhf", "rag",
}


def _title_lower(title: str) -> str:
    return (title or "").lower()


def _has_ai_ml_keyword(title: str) -> bool:
    tl = _title_lower(title)
    return any(kw in tl for kw in AI_ML_KEYWORDS)


def get_route(feed_name: str, story_title: str) -> tuple[Route, str]:
    """
    Determine routing for a story.
    Returns (Route, sub_bucket).

    Precedence:
    1. ALWAYS_SKIP — immediate exit
    2. ALWAYS_AI_ML / ALWAYS_WORLD / ALWAYS_SCIENCE / ALWAYS_ENTERTAINMENT — deterministic
    3. REDDIT_FEEDS — by sub-set
    4. AMBIGUOUS_FEEDS — keyword fallback, default WORLD/tech
    5. Unknown — keyword fallback, default WORLD/news
    """
    feed = feed_name or ""

    if feed in ALWAYS_SKIP:
        return Route.SKIP, ""

    if feed in ALWAYS_AI_ML:
        return Route.AI_ML, "research"

    if feed in ALWAYS_WORLD:
        return Route.WORLD, "news"

    if feed in ALWAYS_SCIENCE:
        return Route.WORLD, "science"

    if feed in ALWAYS_ENTERTAINMENT_FEEDS:
        return Route.WORLD, "entertainment"

    if feed in ALWAYS_TECH_FEEDS:
        return Route.WORLD, "tech"

    if feed in REDDIT_AI_ML:
        return Route.AI_ML, "research"

    if feed in REDDIT_SCIENCE:
        return Route.WORLD, "science"

    if feed in REDDIT_TECH:
        return Route.WORLD, "tech"

    if feed in AMBIGUOUS_FEEDS:
        if _has_ai_ml_keyword(story_title):
            return Route.AI_ML, "research"
        return Route.WORLD, "tech"

    # Unknown feed — keyword fallback, default WORLD/news
    if _has_ai_ml_keyword(story_title):
        return Route.AI_ML, "research"
    return Route.WORLD, "news"

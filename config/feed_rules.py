# config/feed_rules.py
"""Config-driven feed routing rules. Update without redeployment."""
from enum import Enum


class Route(str, Enum):
    AI_ML = "AI_ML"
    WORLD = "WORLD"
    SKIP = "SKIP"


# Maps NewsBlur folder name → (Route, sub_bucket).
# General-Tech is absent — handled by per-story keyword routing in triage_handler.
# WORLD stream disabled (2026-04-11) — see design doc.
FOLDER_ROUTE_MAP: dict[str, tuple[Route, str]] = {
    "AI-ML-Research":  (Route.AI_ML, "research"),
    "AI-ML-Community": (Route.AI_ML, "community"),
    "AI-ML-Primary":   (Route.AI_ML, "research"),
}

# No unfolderd feeds active. Ghostbusters News was WORLD/entertainment — stream disabled.
UNFOLDERD_ROUTE_MAP: dict[str, tuple[Route, str]] = {}

# Feed titles to skip regardless of folder (circular / meta feeds).
ALWAYS_SKIP_NAMES: set[str] = {
    "AI / Raindrop.io",   # circular — Seth's own Raindrop RSS export
    "The NewsBlur Blog",  # meta — RSS reader product news
}

# AI/ML keyword set — used for per-story keyword routing inside General-Tech.
AI_ML_KEYWORDS = {
    "llm", "gpt", "claude", "gemini", "mistral", "llama",
    "neural network", "transformer", "diffusion model",
    "reinforcement learning", "machine learning",
    "artificial intelligence", "deep learning",
    "foundation model", "fine-tun", "retrieval augmented",
    "embedding model", "language model", "ai agent",
    "multimodal", "agentic", "benchmark", "preprint",
    "inference", "rlhf", "rag",
    # AI company names — catches "OpenAI releases...", "Anthropic's...", etc.
    "openai", "anthropic", "deepmind", "perplexity", "cohere", "midjourney",
    "stability ai", "hugging face", "nvidia ai", "copilot", "sora", "veo",
}


def _has_ai_ml_keyword(title: str) -> bool:
    tl = (title or "").lower()
    return any(kw in tl for kw in AI_ML_KEYWORDS)

"""Rule-based story triage — no LLM required."""
from enum import Enum
from typing import Dict, List, Tuple

from src.models.story import Story


class Bucket(str, Enum):
    AI_ML = "ai-ml"
    WORLD = "world"
    SKIP = "skip"


# Feed-name rules: lowercase substring → (bucket, sub_bucket)
FEED_RULES: Dict[str, Tuple[Bucket, str | None]] = {
    # AI/ML
    "arxiv": (Bucket.AI_ML, "research"),
    "papers with code": (Bucket.AI_ML, "research"),
    "hugging face": (Bucket.AI_ML, "industry"),
    "towards data science": (Bucket.AI_ML, "research"),
    "the gradient": (Bucket.AI_ML, "research"),
    "import ai": (Bucket.AI_ML, "research"),
    "openai": (Bucket.AI_ML, "industry"),
    "anthropic": (Bucket.AI_ML, "industry"),
    "deepmind": (Bucket.AI_ML, "research"),
    "google ai": (Bucket.AI_ML, "research"),
    # Tech → world/tech
    "the verge": (Bucket.WORLD, "tech"),
    "techcrunch": (Bucket.WORLD, "tech"),
    "ars technica": (Bucket.WORLD, "tech"),
    "wired": (Bucket.WORLD, "tech"),
    "9to5mac": (Bucket.WORLD, "tech"),
    "macrumors": (Bucket.WORLD, "tech"),
    # World/News
    "bbc": (Bucket.WORLD, "news"),
    "npr": (Bucket.WORLD, "news"),
    "reuters": (Bucket.WORLD, "news"),
    "ap news": (Bucket.WORLD, "news"),
    "associated press": (Bucket.WORLD, "news"),
    "new york times": (Bucket.WORLD, "news"),
    "washington post": (Bucket.WORLD, "news"),
    "the guardian": (Bucket.WORLD, "news"),
    # Science
    "science daily": (Bucket.WORLD, "science"),
    "nature": (Bucket.WORLD, "science"),
    "new scientist": (Bucket.WORLD, "science"),
    "science alert": (Bucket.WORLD, "science"),
    "live science": (Bucket.WORLD, "science"),
    # Weather
    "weather underground": (Bucket.WORLD, "weather"),
    "national weather service": (Bucket.WORLD, "weather"),
    "weather.gov": (Bucket.WORLD, "weather"),
    # Skip
    "espn": (Bucket.SKIP, "sports"),
    "bleacher report": (Bucket.SKIP, "sports"),
    "sports illustrated": (Bucket.SKIP, "sports"),
    "buzzfeed": (Bucket.SKIP, "lifestyle"),
}

AI_ML_KEYWORDS = [
    "llm", "gpt", "claude", "gemini", "mistral", "llama",
    "neural network", "transformer", "diffusion model",
    "reinforcement learning", "machine learning",
    "artificial intelligence", "deep learning",
    "foundation model", "fine-tun", "retrieval augmented",
    "embedding model", "language model",
]

TECH_KEYWORDS = [
    "iphone", "android", "google", "microsoft", "apple",
    "startup", "open source", "github", "developer",
    "programming", "software", "hardware", "chip",
    "semiconductor", "product launch",
]


class TriageService:
    """Categorizes stories into buckets using feed-name rules + keyword fallback."""

    def categorize(self, story) -> Bucket:
        bucket, _ = self.categorize_with_sub(story)
        return bucket

    def categorize_with_sub(self, story) -> Tuple[Bucket, str]:
        feed_lower = (story.story_feed_title or "").lower()
        title_lower = (story.story_title or "").lower()

        # Step 1: feed-name lookup (substring match)
        for pattern, (bucket, sub) in FEED_RULES.items():
            if pattern in feed_lower:
                if sub is not None:
                    return bucket, sub
                break

        # Step 2: keyword fallback
        if any(kw in title_lower for kw in AI_ML_KEYWORDS):
            return Bucket.AI_ML, "research"
        if any(kw in title_lower for kw in TECH_KEYWORDS):
            return Bucket.WORLD, "tech"

        return Bucket.WORLD, "news"

    def batch_categorize(self, stories) -> Dict[Bucket, List[Tuple]]:
        result = {
            Bucket.AI_ML: [],
            Bucket.WORLD: [],
            Bucket.SKIP: [],
        }
        for story in stories:
            bucket, sub = self.categorize_with_sub(story)
            result[bucket].append((story, sub))
        return result

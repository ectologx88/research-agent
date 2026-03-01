# src/services/triage.py
"""Story triage utilities — boost tag extraction."""
from enum import Enum

from config.keywords import get_boost_tags


class Bucket(str, Enum):
    AI_ML = "ai-ml"
    WORLD = "world"
    SKIP = "skip"


class TriageService:
    """Provides boost-tag extraction for stories. Routing is now folder-based (triage_handler)."""

    def get_boost_tags(self, story) -> list[str]:
        """Return boost tags based on feed membership and title keywords."""
        feed = story.story_feed_title or ""
        title = story.story_title or ""
        initial = []
        if "gbninjaturtle" in feed:
            initial.append("boost:user-curated")
        return get_boost_tags(title, initial)

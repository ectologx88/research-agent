# src/services/triage.py
"""Rule-based story triage — delegates to config/feed_rules.py."""
from enum import Enum
from typing import Any

from config.feed_rules import Route, get_route
from config.keywords import get_boost_tags


class Bucket(str, Enum):
    AI_ML = "ai-ml"
    WORLD = "world"
    SKIP = "skip"


_ROUTE_TO_BUCKET = {
    Route.AI_ML: Bucket.AI_ML,
    Route.WORLD: Bucket.WORLD,
    Route.SKIP: Bucket.SKIP,
}


class TriageService:
    """Categorizes stories using config/feed_rules.py. No LLM required."""

    def categorize(self, story: Any) -> Bucket:
        bucket, _ = self.categorize_with_sub(story)
        return bucket

    def categorize_with_sub(self, story: Any) -> tuple[Bucket, str]:
        feed = story.story_feed_title or ""
        title = story.story_title or ""
        route, sub_bucket = get_route(feed, title)
        return _ROUTE_TO_BUCKET[route], sub_bucket

    def get_boost_tags(self, story: Any) -> list[str]:
        """Return boost tags based on feed membership and title keywords."""
        feed = story.story_feed_title or ""
        title = story.story_title or ""
        initial = []
        if "gbninjaturtle" in feed:
            initial.append("boost:user-curated")
        return get_boost_tags(title, initial)

    def batch_categorize(self, stories: list[Any]) -> dict[Bucket, list[tuple]]:
        result: dict[Bucket, list[tuple]] = {
            Bucket.AI_ML: [],
            Bucket.WORLD: [],
            Bucket.SKIP: [],
        }
        for story in stories:
            bucket, sub = self.categorize_with_sub(story)
            result[bucket].append((story, sub))
        return result

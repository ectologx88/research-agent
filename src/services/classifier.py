"""Orchestration service: ties fetching, classifying, and storing together."""

from dataclasses import dataclass, field
from typing import List

from src.clients.bedrock import BedrockClassifier, ClassificationError
from src.clients.newsblur import NewsBlurClient
from src.config import Settings
from src.models.classification import Classification
from src.models.story import Story
from src.services.storage import ClassificationStorage
from src.utils import log_structured, utcnow


@dataclass
class RunMetrics:
    stories_fetched: int = 0
    already_classified: int = 0
    stories_classified: int = 0
    classification_failures: int = 0
    high_value_stories: int = 0
    time_sensitive_stories: int = 0
    execution_time_seconds: float = 0.0
    top_stories: list = field(default_factory=list)


class ClassificationService:
    """End-to-end pipeline: fetch → classify → store."""

    def __init__(
        self,
        newsblur: NewsBlurClient,
        classifier: BedrockClassifier,
        storage: ClassificationStorage,
        settings: Settings,
    ):
        self._newsblur = newsblur
        self._classifier = classifier
        self._storage = storage
        self._settings = settings

    def run(self) -> RunMetrics:
        metrics = RunMetrics()
        start = utcnow()

        # 1. Determine fetch window
        since = None
        if self._settings.fetch_strategy == "since_last_run":
            since = self._storage.get_last_run_timestamp()
            if since:
                log_structured("INFO", "Fetching since last run", since=since.isoformat())

        # 2. Fetch stories
        stories = self._newsblur.fetch_unread_stories(
            since_timestamp=since,
            hours_back=self._settings.hours_back_default,
            min_score=self._settings.newsblur_min_score,
            max_results=self._settings.max_stories_per_run,
        )
        metrics.stories_fetched = len(stories)
        log_structured("INFO", "Stories fetched", count=len(stories))

        # 3. Classify each story (skip duplicates)
        classified: List[Classification] = []
        hashes_to_mark: List[str] = []

        for i, story in enumerate(stories, 1):
            if self._storage.story_already_classified(story.story_hash):
                metrics.already_classified += 1
                continue

            try:
                result = self._classifier.classify_story(story)
                classified.append(result)
                metrics.stories_classified += 1

                # Store immediately so partial runs are durable
                self._storage.store_classification(story, result)
                hashes_to_mark.append(story.story_hash)

                # Track high-value
                if result.scores.overall >= self._settings.threshold_overall:
                    metrics.high_value_stories += 1
                if "time_sensitive" in [a.value for a in result.actionability]:
                    metrics.time_sensitive_stories += 1

                log_structured(
                    "INFO",
                    "Classified",
                    progress=f"{i}/{len(stories)}",
                    hash=story.story_hash,
                    title=story.story_title[:80],
                    overall=result.scores.overall,
                )
            except ClassificationError as exc:
                metrics.classification_failures += 1
                log_structured(
                    "ERROR",
                    "Classification failed",
                    hash=story.story_hash,
                    error=str(exc),
                )

        # 4. Optionally mark stories as read in NewsBlur
        if self._settings.mark_as_read and hashes_to_mark:
            self._newsblur.mark_stories_as_read(hashes_to_mark)
            log_structured("INFO", "Marked as read", count=len(hashes_to_mark))

        # 5. Update pipeline state
        self._storage.update_last_run_timestamp(utcnow())

        # 6. Build top-stories sample
        top = sorted(classified, key=lambda c: c.scores.overall, reverse=True)[:3]
        metrics.top_stories = [
            {
                "hash": c.story_hash,
                "overall": c.scores.overall,
                "type": c.content_type.value,
                "why": c.why_matters,
            }
            for c in top
        ]

        elapsed = (utcnow() - start).total_seconds()
        metrics.execution_time_seconds = round(elapsed, 2)

        log_structured(
            "INFO",
            "Pipeline complete",
            fetched=metrics.stories_fetched,
            classified=metrics.stories_classified,
            failures=metrics.classification_failures,
            high_value=metrics.high_value_stories,
            elapsed=metrics.execution_time_seconds,
        )

        return metrics

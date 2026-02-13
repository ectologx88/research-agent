"""Orchestration service: fetch, deduplicate, classify, and return in-memory results."""

from dataclasses import dataclass, field
from typing import List, Tuple

from src.clients.bedrock import BedrockClassifier, ClassificationError
from src.clients.newsblur import NewsBlurClient
from src.config import Settings
from src.models.classification import Classification
from src.models.story import Story
from src.services.storage import ProcessingStateStorage
from src.utils import log_structured, utcnow


@dataclass
class RunMetrics:
    stories_fetched: int = 0
    already_processed: int = 0
    stories_classified: int = 0
    classification_failures: int = 0
    high_value_stories: int = 0
    time_sensitive_stories: int = 0
    execution_time_seconds: float = 0.0
    top_stories: list = field(default_factory=list)


@dataclass
class PipelineResult:
    """In-memory results from a pipeline run."""

    classified: List[Tuple[Story, Classification]] = field(default_factory=list)
    metrics: RunMetrics = field(default_factory=RunMetrics)


class ClassificationService:
    """End-to-end pipeline: fetch -> batch-dedup -> classify -> return in-memory."""

    def __init__(
        self,
        newsblur: NewsBlurClient,
        classifier: BedrockClassifier,
        storage: ProcessingStateStorage,
        settings: Settings,
    ):
        self._newsblur = newsblur
        self._classifier = classifier
        self._storage = storage
        self._settings = settings

    def run(self) -> PipelineResult:
        result = PipelineResult()
        metrics = result.metrics
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

        # 3. Batch deduplication
        all_hashes = [s.story_hash for s in stories]
        processed_hashes = self._storage.batch_check_processed(all_hashes)
        new_stories = [s for s in stories if s.story_hash not in processed_hashes]
        metrics.already_processed = len(processed_hashes)

        log_structured(
            "INFO",
            "Deduplication complete",
            total_stories=len(stories),
            new_stories=len(new_stories),
            already_processed=len(processed_hashes),
        )

        # 4. Classify new stories
        hashes_to_mark: List[str] = []

        for i, story in enumerate(new_stories, 1):
            try:
                classification = self._classifier.classify_story(story)
                result.classified.append((story, classification))
                metrics.stories_classified += 1

                # Store only minimal dedup record (not full classification)
                self._storage.mark_processed(
                    story.story_hash, classification.scores.overall
                )
                hashes_to_mark.append(story.story_hash)

                # Track high-value
                if classification.scores.overall >= self._settings.threshold_overall:
                    metrics.high_value_stories += 1
                if "time_sensitive" in [a.value for a in classification.actionability]:
                    metrics.time_sensitive_stories += 1

                log_structured(
                    "INFO",
                    "Classified",
                    progress=f"{i}/{len(new_stories)}",
                    hash=story.story_hash,
                    title=story.story_title[:80],
                    overall=classification.scores.overall,
                )
            except ClassificationError as exc:
                metrics.classification_failures += 1
                log_structured(
                    "ERROR",
                    "Classification failed",
                    hash=story.story_hash,
                    error=str(exc),
                )

        # 5. Optionally mark stories as read in NewsBlur
        if self._settings.mark_as_read and hashes_to_mark:
            self._newsblur.mark_stories_as_read(hashes_to_mark)
            log_structured("INFO", "Marked as read", count=len(hashes_to_mark))

        # 6. Update pipeline state
        self._storage.update_last_run_timestamp(utcnow())

        # 7. Build top-stories sample (from in-memory results)
        top = sorted(
            result.classified, key=lambda pair: pair[1].scores.overall, reverse=True
        )[:3]
        metrics.top_stories = [
            {
                "hash": c.story_hash,
                "overall": c.scores.overall,
                "type": c.content_type.value,
                "why": c.why_matters,
            }
            for _, c in top
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

        return result

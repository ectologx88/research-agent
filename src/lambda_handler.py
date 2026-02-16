"""AWS Lambda entry point for the NewsBlur classification pipeline."""

import dataclasses
import uuid

from src.clients.bedrock import BedrockClassifier
from src.clients.newsblur import NewsBlurClient
from src.clients.raindrop import RaindropAuthError, RaindropClient
from src.config import Settings
from src.services.classifier import ClassificationService
from src.services.storage import ProcessingStateStorage
from src.utils import log_structured, timed, utcnow


def lambda_handler(event, context):
    """Phase 1+2a: NewsBlur Intelligence Pipeline with Raindrop bookmarking.

    Fetches unread stories, classifies them via Bedrock, deduplicates via
    DynamoDB, bookmarks high-value stories to Raindrop, and returns metrics.
    """
    execution_id = str(uuid.uuid4())
    settings = Settings()

    log_structured("INFO", "Pipeline starting", execution_id=execution_id)

    with timed("Full pipeline"):
        newsblur = NewsBlurClient(settings.newsblur_username, settings.newsblur_password)
        newsblur.authenticate()

        classifier = BedrockClassifier(
            region=settings.bedrock_region,
            model_id=settings.bedrock_model_id,
        )

        storage = ProcessingStateStorage(
            table_name=settings.dynamodb_table_name,
            region=settings.dynamodb_region,
        )

        service = ClassificationService(
            newsblur=newsblur,
            classifier=classifier,
            storage=storage,
            settings=settings,
        )

        result = service.run()

    # Filter high-value stories
    high_value = [
        (s, c)
        for s, c in result.classified
        if c.scores.overall >= settings.threshold_overall
    ]

    # Phase 2a: Bookmark high-value stories to Raindrop
    raindrop_sent = 0
    raindrop_skipped = 0

    if settings.raindrop_token:
        raindrop = RaindropClient(
            token=settings.raindrop_token,
            collection_id=settings.raindrop_collection_id,
        )
        auth_failed = False

        for story, classification in high_value:
            if auth_failed:
                break
            if not story.story_permalink:
                log_structured("WARNING", "Skipping story with no URL", title=story.story_title)
                raindrop_skipped += 1
                continue

            try:
                if raindrop.check_duplicate(story.story_permalink):
                    log_structured("INFO", "Raindrop duplicate skipped", url=story.story_permalink)
                    raindrop_skipped += 1
                    continue

                raindrop.create_bookmark(
                    url=story.story_permalink,
                    title=story.story_title,
                    tags=classification.concepts,
                    note=classification.why_matters,
                )
                raindrop_sent += 1

            except RaindropAuthError as exc:
                log_structured("ERROR", "Raindrop auth failed — stopping", error=str(exc))
                auth_failed = True
                raindrop_skipped += len(high_value) - raindrop_sent - raindrop_skipped

            except Exception as exc:
                log_structured(
                    "WARNING",
                    "Raindrop bookmark failed after retries",
                    url=story.story_permalink,
                    error=str(exc),
                )
                raindrop_skipped += 1
    else:
        log_structured("INFO", "Raindrop token not configured, skipping")

    # TODO Phase 2b: Generate and send daily brief via SES

    body = {
        "execution_id": execution_id,
        "timestamp": utcnow().isoformat(),
        "metrics": dataclasses.asdict(result.metrics),
        "high_value_count": len(high_value),
        "raindrop_sent": raindrop_sent,
        "raindrop_skipped": raindrop_skipped,
    }

    log_structured("INFO", "Pipeline finished", **body)

    return {"statusCode": 200, "body": body}

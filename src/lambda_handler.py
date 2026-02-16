"""AWS Lambda entry point for the NewsBlur classification pipeline."""

import dataclasses
import uuid
from datetime import datetime, timezone

from src.clients.bedrock import BedrockClassifier
from src.clients.bedrock_briefing import BedrockBriefingClient, BriefingError
from src.clients.newsblur import NewsBlurClient
from src.clients.raindrop import RaindropAuthError, RaindropClient
from src.config import Settings
from src.services.classifier import ClassificationService
from src.services.storage import ProcessingStateStorage
from src.utils import log_structured, timed, utcnow


def lambda_handler(event, context):
    """Phase 1+2b: NewsBlur Intelligence Pipeline with Raindrop bookmarking and briefing.

    Fetches unread stories, classifies them via Bedrock (Haiku), deduplicates via
    DynamoDB, bookmarks high-value stories to Raindrop with taxonomy tags, and
    synthesizes a narrative briefing via Bedrock (Sonnet 4.5) delivered as a
    Raindrop bookmark.
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

    # Phase 2a/2b: Raindrop bookmarking and briefing
    raindrop_sent = 0
    raindrop_skipped = 0
    briefing_sent = 0

    if not settings.raindrop_token:
        log_structured("INFO", "Raindrop token not configured, skipping")
    else:
        raindrop = RaindropClient(
            token=settings.raindrop_token,
            collection_id=settings.raindrop_collection_id,
        )
        auth_failed = False

        # --- Story bookmarks (high-value, with taxonomy tags) ---
        high_value = [
            (s, c)
            for s, c in result.classified
            if c.scores.overall >= settings.threshold_overall
        ]

        for story, classification in high_value:
            if auth_failed:
                break
            if not story.story_permalink:
                log_structured("WARNING", "Skipping story with no URL", title=story.story_title)
                raindrop_skipped += 1
                continue

            try:
                if raindrop.check_duplicate(story.story_permalink):
                    log_structured("INFO", "Raindrop duplicate skipped", url=str(story.story_permalink))
                    raindrop_skipped += 1
                    continue

                # Use taxonomy tags (Phase 2b) — fall back to concepts if empty
                tags = (
                    [t.value for t in classification.taxonomy_tags]
                    if classification.taxonomy_tags
                    else classification.concepts
                )

                raindrop.create_bookmark(
                    url=story.story_permalink,
                    title=story.story_title,
                    tags=tags,
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
                    url=str(story.story_permalink),
                    error=str(exc),
                )
                raindrop_skipped += 1

        # --- Briefing bookmark (Phase 2b) ---
        if not auth_failed:
            briefing_stories = [
                (s, c)
                for s, c in result.classified
                if (
                    c.scores.overall >= settings.briefing_prefilter_domain_min
                    or c.scores.importance >= settings.briefing_prefilter_importance_min
                )
            ]

            if briefing_stories:
                try:
                    run_hour_utc = datetime.now(timezone.utc).hour
                    time_of_day = "Morning" if run_hour_utc < 18 else "Evening"
                    date_str = datetime.now(timezone.utc).strftime("%b %-d, %Y")
                    briefing_title = f"{time_of_day} Briefing \u2014 {date_str}"

                    briefing_client = BedrockBriefingClient(
                        region=settings.bedrock_region,
                        model_id=settings.bedrock_briefing_model_id,
                    )
                    briefing_text = briefing_client.synthesize(briefing_stories, run_hour_utc)

                    # Use the first story's URL as the required Raindrop URL
                    first_url = str(briefing_stories[0][0].story_permalink) if briefing_stories[0][0].story_permalink else "https://newsblur.com"

                    briefing_raindrop = RaindropClient(
                        token=settings.raindrop_token,
                        collection_id=settings.raindrop_briefing_collection_id,
                    )
                    briefing_raindrop.create_bookmark(
                        url=first_url,
                        title=briefing_title,
                        tags=["briefing", "ai-generated", time_of_day.lower()],
                        note=briefing_text,
                    )
                    briefing_sent = 1
                    log_structured("INFO", "Briefing bookmark created", title=briefing_title)

                except BriefingError as exc:
                    log_structured("ERROR", "Briefing synthesis failed", error=str(exc))
                except RaindropAuthError as exc:
                    log_structured("ERROR", "Raindrop auth failed on briefing", error=str(exc))
                except Exception as exc:
                    log_structured("WARNING", "Briefing delivery failed", error=str(exc))
            else:
                log_structured("INFO", "No stories passed briefing pre-filter, skipping briefing")

    high_value_count = len([
        c for _, c in result.classified
        if c.scores.overall >= settings.threshold_overall
    ])

    body = {
        "execution_id": execution_id,
        "timestamp": utcnow().isoformat(),
        "metrics": dataclasses.asdict(result.metrics),
        "high_value_count": high_value_count,
        "raindrop_sent": raindrop_sent,
        "raindrop_skipped": raindrop_skipped,
        "briefing_sent": briefing_sent,
    }

    log_structured("INFO", "Pipeline finished", **body)

    return {"statusCode": 200, "body": body}

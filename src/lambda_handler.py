"""AWS Lambda entry point for the NewsBlur classification pipeline."""

import dataclasses
import uuid

from src.clients.bedrock import BedrockClassifier
from src.clients.newsblur import NewsBlurClient
from src.config import Settings
from src.services.classifier import ClassificationService
from src.services.storage import ProcessingStateStorage
from src.utils import log_structured, timed, utcnow


def lambda_handler(event, context):
    """Phase 1: NewsBlur Intelligence Pipeline.

    Fetches unread stories, classifies them via Bedrock (in-memory),
    stores only minimal dedup state in DynamoDB, and returns metrics.

    Environment variables (see Settings for full list):
        NEWSBLUR_USERNAME, NEWSBLUR_PASSWORD
        DYNAMODB_TABLE_NAME, DYNAMODB_REGION
        BEDROCK_REGION, BEDROCK_MODEL_ID
        MAX_STORIES_PER_RUN, NEWSBLUR_MIN_SCORE
        MARK_AS_READ
    """
    execution_id = str(uuid.uuid4())
    settings = Settings()  # reads from env / .env

    log_structured("INFO", "Pipeline starting", execution_id=execution_id)

    with timed("Full pipeline"):
        # Wire up dependencies
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

    # Filter high-value from in-memory results
    high_value = [
        (s, c)
        for s, c in result.classified
        if c.scores.overall >= settings.threshold_overall
    ]

    # TODO Phase 2: Send high-value stories to Raindrop
    # for story, classification in high_value:
    #     raindrop_client.send_story(story, classification)

    # TODO Phase 2: Generate and send daily brief
    # brief = generate_daily_brief(result.classified, high_value)
    # ses_client.send_email(brief)

    body = {
        "execution_id": execution_id,
        "timestamp": utcnow().isoformat(),
        "metrics": dataclasses.asdict(result.metrics),
        "high_value_count": len(high_value),
    }

    log_structured("INFO", "Pipeline finished", **body)

    return {"statusCode": 200, "body": body}

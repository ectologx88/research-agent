"""AWS Lambda entry point for the NewsBlur classification pipeline."""

import dataclasses
import uuid

from src.clients.bedrock import BedrockClassifier
from src.clients.newsblur import NewsBlurClient
from src.config import Settings
from src.services.classifier import ClassificationService
from src.services.storage import ClassificationStorage
from src.utils import log_structured, timed, utcnow


def lambda_handler(event, context):
    """Phase 1: NewsBlur Intelligence Pipeline.

    Fetches unread stories, classifies them via Bedrock, stores results in
    DynamoDB, and returns an execution summary.

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

        storage = ClassificationStorage(
            table_name=settings.dynamodb_table_name,
            region=settings.dynamodb_region,
        )

        service = ClassificationService(
            newsblur=newsblur,
            classifier=classifier,
            storage=storage,
            settings=settings,
        )

        metrics = service.run()

    body = {
        "execution_id": execution_id,
        "timestamp": utcnow().isoformat(),
        "metrics": dataclasses.asdict(metrics),
    }

    log_structured("INFO", "Pipeline finished", **body)

    return {"statusCode": 200, "body": body}

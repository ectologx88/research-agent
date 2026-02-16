"""Lambda 2: Summarize stories, update Raindrop notes, forward to briefing queue."""
import json
import boto3

from src.clients.bedrock_summarizer import BedrockSummarizerClient
from src.clients.raindrop import RaindropClient
from src.config import Settings
from src.services.storage import ProcessingStateStorage
from src.utils import log_structured


def lambda_handler(event, context):
    settings = Settings()
    storage = ProcessingStateStorage(settings.dynamodb_table_name, settings.dynamodb_region)
    summarizer = BedrockSummarizerClient(
        region=settings.bedrock_region,
        model_id=settings.bedrock_summarizer_model_id,
    )
    sqs = boto3.client("sqs", region_name="us-east-1")

    record = event["Records"][0]
    message = json.loads(record["body"])
    briefing_type = message["briefing_type"]
    story_hashes = message["story_hashes"]
    run_date = message["run_date"]
    time_of_day = message["time_of_day"]

    log_structured("INFO", "Summarizer starting",
                   briefing_type=briefing_type, story_count=len(story_hashes))

    # Fetch story content from DynamoDB
    stories_data = storage.get_stories_content(story_hashes)
    min_score = (settings.summarizer_aiml_min_score if briefing_type == "ai-ml"
                 else settings.summarizer_world_min_score)

    raindrop = RaindropClient(token=settings.raindrop_token) if settings.raindrop_token else None

    summarized = 0
    briefing_stories = []

    for story_hash, data in stories_data.items():
        try:
            result = summarizer.summarize(
                title=data["title"],
                content=data.get("content", ""),
                bucket=briefing_type,
            )
            summarized += 1

            # Update Raindrop note with summary
            if raindrop and data.get("raindrop_id"):
                note = f"{result.summary}\n\n**Why it matters:** {result.why_matters}"
                try:
                    raindrop.update_bookmark(raindrop_id=data["raindrop_id"], note=note)
                except Exception as exc:
                    log_structured("WARNING", "Failed to update Raindrop note",
                                   hash=story_hash, error=str(exc))

            if result.score >= min_score:
                briefing_stories.append({
                    "title": data["title"],
                    "url": data["url"],
                    "summary": result.summary,
                    "why_matters": result.why_matters,
                    "score": result.score,
                    "sub_bucket": data.get("sub_bucket", briefing_type),
                    "feed_title": data.get("feed_title", ""),
                })

        except Exception as exc:
            log_structured("WARNING", "Summarization failed",
                           hash=story_hash, error=str(exc))

    log_structured("INFO", "Summarization complete",
                   summarized=summarized, briefing_eligible=len(briefing_stories))

    # Send to briefing queue if enough stories passed threshold
    sent = 0
    if len(briefing_stories) >= 3 and settings.sqs_briefing_queue_url:
        sqs.send_message(
            QueueUrl=settings.sqs_briefing_queue_url,
            MessageBody=json.dumps({
                "briefing_type": briefing_type,
                "run_date": run_date,
                "time_of_day": time_of_day,
                "stories": briefing_stories,
            }),
        )
        sent = len(briefing_stories)
    else:
        log_structured("INFO", "Not enough stories for briefing",
                       count=len(briefing_stories))

    body = {"summarized": summarized, "sent_to_briefing": sent, "briefing_type": briefing_type}
    log_structured("INFO", "Summarizer complete", **body)
    return {"statusCode": 200, "body": body}

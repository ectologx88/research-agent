"""Lambda 1: Fetch from NewsBlur, triage stories, route to Raindrop, send SQS."""
import json
import time
import uuid

import boto3

from src.clients.newsblur import NewsBlurClient
from src.clients.raindrop import RaindropClient, RaindropAuthError
from src.config import Settings
from src.services.storage import ProcessingStateStorage
from src.services.triage import Bucket, TriageService
from src.utils import log_structured, timed, utcnow


def lambda_handler(event, context):
    execution_id = str(uuid.uuid4())
    settings = Settings()
    log_structured("INFO", "Triage pipeline starting", execution_id=execution_id)

    newsblur = NewsBlurClient(settings.newsblur_username, settings.newsblur_password)
    storage = ProcessingStateStorage(settings.dynamodb_table_name, settings.dynamodb_region)
    triage = TriageService()
    sqs = boto3.client("sqs", region_name="us-east-1")

    # 1. Fetch (NewsBlurClient auto-authenticates on first request if needed)
    with timed("NewsBlur fetch"):
        stories = newsblur.fetch_unread_stories(
            min_score=settings.newsblur_min_score,
            max_results=settings.max_stories_per_run,
        )

    # 2. Deduplicate
    all_hashes = [s.story_hash for s in stories]
    already_seen = storage.batch_check_processed(all_hashes)
    new_stories = [s for s in stories if s.story_hash not in already_seen]

    # 3. Triage
    buckets = triage.batch_categorize(new_stories)
    ai_ml_stories = buckets[Bucket.AI_ML]
    world_stories = buckets[Bucket.WORLD]
    skip_stories = buckets[Bucket.SKIP]

    # 4. Route to Raindrop + store content
    run_time = utcnow()
    time_of_day = "morning" if run_time.hour < 18 else "evening"
    date_str = run_time.strftime("%Y-%m-%d")

    if settings.raindrop_token:
        raindrop_aiml = RaindropClient(
            token=settings.raindrop_token,
            collection_id=settings.raindrop_aiml_collection_id,
        )
        raindrop_world = RaindropClient(
            token=settings.raindrop_token,
            collection_id=settings.raindrop_world_collection_id,
        )
        _route_to_raindrop(ai_ml_stories, raindrop_aiml, storage, "ai-ml")
        _route_to_raindrop(world_stories, raindrop_world, storage, "world")

    # Mark skipped stories as processed (score=0)
    for story, _ in skip_stories:
        storage.mark_processed(story.story_hash, 0)

    # 5. Send SQS messages
    ai_ml_hashes = [s.story_hash for s, _ in ai_ml_stories]
    world_hashes = [s.story_hash for s, _ in world_stories]

    if ai_ml_hashes and settings.sqs_aiml_queue_url:
        sqs.send_message(
            QueueUrl=settings.sqs_aiml_queue_url,
            MessageBody=json.dumps({
                "briefing_type": "ai-ml",
                "run_date": date_str,
                "time_of_day": time_of_day,
                "story_hashes": ai_ml_hashes,
            }),
        )

    if world_hashes and settings.sqs_world_queue_url:
        sqs.send_message(
            QueueUrl=settings.sqs_world_queue_url,
            MessageBody=json.dumps({
                "briefing_type": "world",
                "run_date": date_str,
                "time_of_day": time_of_day,
                "story_hashes": world_hashes,
            }),
        )

    # 6. Update last-run timestamp
    storage.update_last_run_timestamp(run_time)

    body = {
        "execution_id": execution_id,
        "ai_ml_count": len(ai_ml_stories),
        "world_count": len(world_stories),
        "skipped_count": len(skip_stories),
        "already_processed": len(already_seen),
    }
    log_structured("INFO", "Triage pipeline complete", **body)
    return {"statusCode": 200, "body": body}


def _route_to_raindrop(stories_with_sub, raindrop, storage, bucket_name):
    """Save stories to Raindrop and store content in DynamoDB."""
    for story, sub_bucket in stories_with_sub:
        try:
            if raindrop.check_duplicate(story.story_permalink):
                storage.mark_processed(story.story_hash, 0)
                continue
            tags = [bucket_name, sub_bucket, (story.story_feed_title or "")[:30].lower()]
            result = raindrop.create_bookmark(
                url=story.story_permalink,
                title=story.story_title,
                tags=tags,
                note="",
            )
            raindrop_id = result.get("_id") if result else None
            storage.store_story_content(story.story_hash, {
                "title": story.story_title,
                "url": str(story.story_permalink),
                "content": story.story_content or "",
                "feed_title": story.story_feed_title,
                "bucket": bucket_name,
                "sub_bucket": sub_bucket,
                "newsblur_score": getattr(story, "newsblur_score", 0),
                "raindrop_id": raindrop_id,
            })
            storage.mark_processed(story.story_hash, getattr(story, "newsblur_score", 0))
            time.sleep(0.2)  # avoid Raindrop 429 rate limiting
        except RaindropAuthError:
            log_structured("ERROR", "Raindrop auth failed", bucket=bucket_name)
            break
        except Exception as exc:
            log_structured("WARNING", "Failed to route story",
                           hash=story.story_hash, error=str(exc))
            storage.mark_processed(story.story_hash, 0)

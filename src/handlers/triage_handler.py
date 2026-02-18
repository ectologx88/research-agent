"""Lambda 1: Fetch from NewsBlur, triage stories, route to Raindrop, store in StoryStaging."""
import json
import time
import uuid

import boto3

from config.scoring_weights import CONTENT_TRUNCATE_CHARS
from shared.dynamodb_client import StoryStaging
from shared.logger import log
from src.clients.newsblur import NewsBlurClient
from src.clients.raindrop import RaindropClient, RaindropAuthError
from src.config import Settings
from src.services.context_loader import ContextLoader
from src.services.triage import Bucket, TriageService
from src.services.velocity import compute_clusters
import time as _time
from src.utils import utcnow


def _truncate_content(content: str, max_chars: int = CONTENT_TRUNCATE_CHARS) -> str:
    """Truncate at whitespace boundary, append [truncated] marker."""
    if len(content) <= max_chars:
        return content
    truncated = content[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > max_chars - 200:
        truncated = truncated[:last_space]
    return truncated + " [truncated]"


def lambda_handler(event, context):
    execution_id = str(uuid.uuid4())
    settings = Settings()
    dry_run = settings.dry_run == "true"
    log("INFO", "triage_pipeline.start", execution_id=execution_id, dry_run=dry_run)

    newsblur = NewsBlurClient(settings.newsblur_username, settings.newsblur_password)
    triage = TriageService()
    sqs = boto3.client("sqs", region_name=settings.dynamodb_region)
    dynamodb = boto3.resource("dynamodb", region_name=settings.dynamodb_region)
    story_staging = StoryStaging(dynamodb.Table(settings.dynamodb_story_staging_table))

    # 1. Load context block once per run
    context_block_json = "{}"
    try:
        context_data = ContextLoader().fetch_all()
        context_block_json = json.dumps(context_data)
    except Exception as exc:
        log("WARNING", "context_loader.failed", error=str(exc))

    # 2. Fetch stories
    _t0 = _time.time()
    stories = newsblur.fetch_unread_stories(
        min_score=settings.newsblur_min_score,
        max_results=settings.max_stories_per_run,
    )
    log("INFO", "newsblur.fetch.complete",
        elapsed_ms=int((_time.time() - _t0) * 1000), count=len(stories))

    # 3. Triage all stories
    buckets = triage.batch_categorize(stories)
    ai_ml_stories = buckets[Bucket.AI_ML]
    world_stories = buckets[Bucket.WORLD]
    skip_stories = buckets[Bucket.SKIP]

    # 4. Velocity clustering on routed stories
    routed = [s for s, _ in ai_ml_stories + world_stories]
    cluster_map = compute_clusters(routed)

    # 5. Deduplicate and process each stream
    run_time = utcnow()
    time_of_day = "AM" if run_time.hour < 18 else "PM"
    date_str = run_time.strftime("%Y-%m-%d")
    briefing_date = f"{date_str}-{time_of_day}"

    raindrop_aiml = raindrop_world = None
    if not dry_run and settings.raindrop_token:
        raindrop_aiml = RaindropClient(
            token=settings.raindrop_token,
            collection_id=settings.raindrop_aiml_collection_id,
        )
        raindrop_world = RaindropClient(
            token=settings.raindrop_token,
            collection_id=settings.raindrop_world_collection_id,
        )

    ai_ml_hashes = _process_stream(
        stories=ai_ml_stories,
        briefing_type="AI_ML",
        bucket_name="ai-ml",
        raindrop=raindrop_aiml,
        story_staging=story_staging,
        triage=triage,
        cluster_map=cluster_map,
        context_block_json=context_block_json,
        dry_run=dry_run,
    )
    world_hashes = _process_stream(
        stories=world_stories,
        briefing_type="WORLD",
        bucket_name="world",
        raindrop=raindrop_world,
        story_staging=story_staging,
        triage=triage,
        cluster_map=cluster_map,
        context_block_json=context_block_json,
        dry_run=dry_run,
    )

    # 6. Send SQS messages
    if not dry_run:
        if ai_ml_hashes and settings.sqs_aiml_queue_url:
            sqs.send_message(
                QueueUrl=settings.sqs_aiml_queue_url,
                MessageBody=json.dumps({
                    "briefing_type": "AI_ML",
                    "briefing_date": briefing_date,
                    "story_hashes": ai_ml_hashes,
                    "candidate_count": len(ai_ml_hashes),
                }),
            )
        if world_hashes and settings.sqs_world_queue_url:
            sqs.send_message(
                QueueUrl=settings.sqs_world_queue_url,
                MessageBody=json.dumps({
                    "briefing_type": "WORLD",
                    "briefing_date": briefing_date,
                    "story_hashes": world_hashes,
                    "candidate_count": len(world_hashes),
                }),
            )

    body = {
        "execution_id": execution_id,
        "dry_run": dry_run,
        "ai_ml_count": len(ai_ml_hashes),
        "world_count": len(world_hashes),
        "skipped_count": len(skip_stories),
    }
    log("INFO", "triage_pipeline.complete", **body)
    return {"statusCode": 200, "body": body}


def _process_stream(stories, briefing_type, bucket_name, raindrop, story_staging,
                    triage, cluster_map, context_block_json, dry_run):
    """Process one briefing stream. Returns list of stored story hashes."""
    hashes = []
    for story, sub_bucket in stories:
        try:
            # Dedup check (skip if already staged in this run)
            if not dry_run and story_staging.check_duplicate(story.story_hash, briefing_type):
                continue

            # Raindrop duplicate check
            if raindrop and not dry_run:
                if raindrop.check_duplicate(story.story_permalink):
                    continue

            # Compute derived fields
            boost_tags = triage.get_boost_tags(story)
            cluster_size, cluster_key = cluster_map.get(story.story_hash, (0, ""))
            content = _truncate_content(story.story_content or "")

            # Save to Raindrop
            raindrop_id = None
            if raindrop and not dry_run:
                tags = [bucket_name, sub_bucket] + boost_tags
                result = raindrop.create_bookmark(
                    url=story.story_permalink,
                    title=story.story_title,
                    tags=tags,
                    note="",
                )
                raindrop_id = result.get("_id") if result else None
                time.sleep(0.2)

            # Store in StoryStaging DDB
            if not dry_run:
                story_staging.store_story({
                    "story_hash": story.story_hash,
                    "briefing_type": briefing_type,
                    "title": story.story_title,
                    "url": str(story.story_permalink),
                    "content": content,
                    "feed_name": story.story_feed_title or "",
                    "sub_bucket": sub_bucket,
                    "boost_tags": boost_tags,
                    "cluster_size": cluster_size,
                    "cluster_key": cluster_key,
                    "context_block": context_block_json,
                    "raindrop_id": raindrop_id,
                })
            hashes.append(story.story_hash)

        except RaindropAuthError:
            log("ERROR", "raindrop.auth_failed", bucket=bucket_name)
            break
        except Exception as exc:
            log("WARNING", "story.processing_failed",
                story_hash=story.story_hash, error=str(exc))
    return hashes

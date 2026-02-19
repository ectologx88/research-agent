"""Lambda 2: Editorial scoring, Raindrop note updates, forward to briefing queue."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import boto3

from config.scoring_weights import (
    MIN_STORIES_FOR_BRIEFING,
    MAX_BRIEFING_AI_ML_STORIES,
    MAX_BRIEFING_WORLD_STORIES,
)
from shared.dynamodb_client import StoryStaging
from shared.logger import log
from src.clients.newsblur import NewsBlurClient
from src.clients.raindrop import RaindropClient
from src.config import Settings
from src.services.editorial_scorer import EditorialScorer


def lambda_handler(event, context):
    settings = Settings()
    dry_run_mode = settings.dry_run  # "false" | "true" | "writes_only"
    use_real_llm = dry_run_mode != "true"
    do_writes = dry_run_mode == "false"

    record = event["Records"][0]
    message = json.loads(record["body"])
    briefing_type = message["briefing_type"]
    story_hashes = message["story_hashes"]
    briefing_date = message["briefing_date"]
    candidate_count = message.get("candidate_count", len(story_hashes))

    log("INFO", "summarizer.start",
        briefing_type=briefing_type, story_count=len(story_hashes), dry_run=dry_run_mode)

    dynamodb = boto3.resource("dynamodb", region_name=settings.dynamodb_region)
    story_staging = StoryStaging(dynamodb.Table(settings.dynamodb_story_staging_table))
    sqs = boto3.client("sqs", region_name=settings.dynamodb_region)

    bedrock = (
        boto3.client("bedrock-runtime", region_name=settings.bedrock_region)
        if use_real_llm else None
    )
    scorer = EditorialScorer(
        bedrock_client=bedrock,
        model_id=settings.bedrock_summarizer_model_id if use_real_llm else "",
        dry_run=not use_real_llm,
    )

    raindrop = None
    if do_writes and settings.raindrop_token:
        raindrop = RaindropClient(
            token=settings.raindrop_token,
            collection_id=(
                settings.raindrop_aiml_collection_id if briefing_type == "AI_ML"
                else settings.raindrop_world_collection_id
            ),
        )

    raindrop_sem = threading.Semaphore(5)

    stories_data = story_staging.batch_get_stories(story_hashes, briefing_type)
    passed_stories = []

    def _score_story(item: dict) -> tuple[dict | None, str | None]:
        """Score a story. Returns (story_result, rejected_hash)."""
        story_hash = item["story_hash"]
        if item.get("status") != "pending":
            log("INFO", "summarizer.skip_idempotent",
                story_hash=story_hash, status=item.get("status"))
            return (None, None)

        boost_tags = item.get("boost_tags") or []
        try:
            result = scorer.score(
                briefing_type=briefing_type,
                title=item["title"],
                content=item.get("content", ""),
                feed_name=item.get("feed_name", ""),
                sub_bucket=item.get("sub_bucket", ""),
                boost_tags=boost_tags,
            )
        except Exception as exc:
            log("WARNING", "summarizer.score_failed", story_hash=story_hash, error=str(exc))
            return (None, None)

        if do_writes:
            story_staging.update_status(
                story_hash=story_hash,
                briefing_type=briefing_type,
                status="summarized" if result.passed else "rejected",
                editorial_score=result.total,
                editorial_decision=result.decision,
                editorial_summary=result.summary or "",
            )

        if not result.passed:
            return (None, story_hash)

        if raindrop and item.get("raindrop_id"):
            with raindrop_sem:
                try:
                    raindrop.update_bookmark(
                        raindrop_id=item["raindrop_id"],
                        note=result.summary or "",
                    )
                except Exception as exc:
                    log("WARNING", "summarizer.raindrop_update_failed",
                        story_hash=story_hash, error=str(exc))

        return ({
            "story_hash": story_hash,
            "title": item["title"],
            "url": item.get("url", ""),
            "summary": result.summary,
            "source_type": result.source_type,
            "reasoning": result.reasoning,
            "sub_bucket": item.get("sub_bucket", ""),
            "boost_tags": boost_tags,
            "cluster_size": int(item.get("cluster_size") or 0),
            "cluster_key": item.get("cluster_key", ""),
            "context_block": item.get("context_block", "{}"),
            "feed_name": item.get("feed_name", ""),
            "scores": {
                "integrity": result.integrity,
                "relevance": result.relevance,
                "novelty": result.novelty,
                "total": result.total,
            },
            "raindrop_id": int(item["raindrop_id"]) if item.get("raindrop_id") is not None else None,
        }, None)

    rejected_hashes = []
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {executor.submit(_score_story, item): item for item in stories_data}
        for future in as_completed(futures):
            story_result, rejected_hash = future.result()
            if story_result is not None:
                passed_stories.append(story_result)
            if rejected_hash is not None:
                rejected_hashes.append(rejected_hash)

    log("INFO", "summarizer.scoring_complete",
        scored=len(stories_data), passed=len(passed_stories))

    # Mark rejected stories as read in NewsBlur (best-effort)
    if rejected_hashes and do_writes and settings.newsblur_username:
        try:
            nb = NewsBlurClient(settings.newsblur_username, settings.newsblur_password)
            nb.mark_stories_as_read(rejected_hashes)
            log("INFO", "summarizer.newsblur_marked_read", count=len(rejected_hashes))
        except Exception as exc:
            log("WARNING", "summarizer.newsblur_mark_failed", error=str(exc))

    # Rank by score and cap before sending — keeps briefing prompts a manageable size.
    briefing_cap = MAX_BRIEFING_AI_ML_STORIES if briefing_type == "AI_ML" else MAX_BRIEFING_WORLD_STORIES
    passed_stories.sort(key=lambda s: s["scores"]["total"], reverse=True)
    passed_stories = passed_stories[:briefing_cap]

    # Send to briefing queue — always brief if at least one story passed.
    # Log thin_briefing warning when below preferred minimum so it's visible in metrics.
    sent = 0
    PREFERRED_MIN = 3
    if len(passed_stories) > 0 and do_writes:
        if 0 < len(passed_stories) < PREFERRED_MIN:
            log("WARNING", "summarizer.thin_briefing",
                passed=len(passed_stories), preferred_min=PREFERRED_MIN)
        if settings.sqs_briefing_queue_url:
            sqs.send_message(
                QueueUrl=settings.sqs_briefing_queue_url,
                MessageBody=json.dumps({
                    "briefing_type": briefing_type,
                    "briefing_date": briefing_date,
                    "candidate_count": candidate_count,
                    "stories": passed_stories,
                }),
            )
            sent = len(passed_stories)
        else:
            log("WARNING", "summarizer.no_sqs_url_configured",
                passed=len(passed_stories), briefing_type=briefing_type)
    elif len(passed_stories) == 0:
        log("INFO", "summarizer.bail_no_stories", briefing_type=briefing_type)

    body = {
        "briefing_type": briefing_type,
        "scored": len(stories_data),
        "passed": len(passed_stories),
        "sent_to_briefing": sent,
        "dry_run": dry_run_mode,
    }
    log("INFO", "summarizer.complete", **body)
    return {"statusCode": 200, "body": body}

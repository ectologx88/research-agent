"""Lambda 1: Fetch from NewsBlur, triage stories, route to Raindrop, store in StoryStaging."""
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

import boto3

from config.feed_rules import (
    ALWAYS_SKIP_NAMES,
    FOLDER_ROUTE_MAP,
    UNFOLDERD_ROUTE_MAP,
    Route,
    _has_ai_ml_keyword,
)
from config.scoring_weights import CONTENT_TRUNCATE_CHARS
from shared.dynamodb_client import StoryStaging, SignalTracker
from shared.logger import log
from src.clients.newsblur import NewsBlurClient
from src.clients.raindrop import RaindropClient, RaindropAuthError
from src.config import Settings
from src.services.context_loader import ContextLoader
from src.services.triage import Bucket, TriageService
from src.services.velocity import compute_clusters
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


def _check_hn_velocity(url: str) -> int:
    """
    Query HN Algolia API for point score of this URL.
    Returns 0 on any failure -- never blocks triage.
    Free API, no key required, 2s timeout.
    """
    import urllib.request
    import urllib.parse
    import json as _json

    try:
        encoded = urllib.parse.quote(url, safe="")
        api_url = (
            f"https://hn.algolia.com/api/v1/search"
            f"?query={encoded}"
            f"&restrictSearchableAttributes=url"
            f"&hitsPerPage=1"
        )
        req = urllib.request.Request(api_url, headers={"User-Agent": "research-agent/1.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = _json.loads(resp.read())
        hits = data.get("hits", [])
        if hits:
            return int(hits[0].get("points") or 0)
    except Exception:
        pass  # never raise -- HN lookup is best-effort
    return 0


@dataclass
class FolderConfig:
    folder_name: str
    feed_ids: list
    route: Route
    sub_bucket: str
    max_stories: int
    min_score: int
    keyword_route: bool = False  # General-Tech: route per story by keyword


def _build_folder_configs(folder_map: dict, settings: Settings) -> list[FolderConfig]:
    """Build per-folder fetch configs from the NewsBlur folder map and settings."""
    configs = []
    global_min = settings.newsblur_min_score

    for folder_name, (route, sub_bucket) in FOLDER_ROUTE_MAP.items():
        feed_ids = folder_map.get(folder_name, [])
        if not feed_ids:
            log("WARNING", "newsblur.folder_empty", folder=folder_name)
            continue

        if folder_name == "AI-ML-Research":
            max_s = settings.ai_ml_research_max_stories
            min_s = settings.ai_ml_research_min_score
        elif folder_name == "AI-ML-Community":
            max_s = settings.ai_ml_community_max_stories
            min_s = global_min
        else:
            max_s = 40
            min_s = global_min

        configs.append(FolderConfig(
            folder_name=folder_name,
            feed_ids=feed_ids,
            route=route,
            sub_bucket=sub_bucket,
            max_stories=max_s,
            min_score=min_s,
        ))

    # General-Tech — keyword-routed per story
    general_tech_ids = folder_map.get("General-Tech", [])
    if general_tech_ids:
        configs.append(FolderConfig(
            folder_name="General-Tech",
            feed_ids=general_tech_ids,
            route=Route.AI_ML,  # placeholder; overridden per story
            sub_bucket="tech",  # placeholder
            max_stories=settings.general_tech_max_stories,
            min_score=0,
            keyword_route=True,
        ))
    else:
        log("WARNING", "newsblur.folder_empty", folder="General-Tech")

    return configs


def _fetch_folder(newsblur: NewsBlurClient, cfg: FolderConfig, hours_back: int) -> tuple:
    """Fetch stories for one folder. Returns (cfg, stories, elapsed_ms)."""
    t0 = time.time()
    stories = newsblur.fetch_unread_stories(
        feed_ids=cfg.feed_ids,
        min_score=cfg.min_score,
        max_results=cfg.max_stories,
        hours_back=hours_back,
    )
    elapsed_ms = int((time.time() - t0) * 1000)
    return cfg, stories, elapsed_ms


def _route_story(story, cfg: FolderConfig) -> tuple | None:
    """Return (story, route, sub_bucket) or None if story should be skipped."""
    feed = story.story_feed_title or ""

    if cfg.keyword_route:
        # General-Tech: per-story keyword routing
        if _has_ai_ml_keyword(story.story_title or ""):
            return story, Route.AI_ML, "research"
        return None  # Non-AI/ML General-Tech stories dropped (WORLD stream disabled)

    return story, cfg.route, cfg.sub_bucket


def _route_unfolderd(stories: list, folder_map: dict) -> tuple[list[tuple], int]:
    """Route unfolderd (top-level) feed stories using UNFOLDERD_ROUTE_MAP.

    Returns (routed_stories, skip_count) where skip_count is the number of
    stories dropped because their feed title is in ALWAYS_SKIP_NAMES.
    """
    routed = []
    skip_count = 0
    for story in stories:
        feed = story.story_feed_title or ""
        if feed in ALWAYS_SKIP_NAMES:
            skip_count += 1
            continue
        entry = UNFOLDERD_ROUTE_MAP.get(feed)
        if entry:
            routed.append((story, entry[0], entry[1]))
        # Unknown unfolderd feeds are dropped (no catch-all for safety)
    return routed, skip_count


def lambda_handler(event, context):
    execution_id = str(uuid.uuid4())
    settings = Settings()
    dry_run = settings.dry_run != "false"
    run_time = utcnow()
    hours_back = 74 if run_time.weekday() == 0 else settings.newsblur_hours_back
    log("INFO", "triage_pipeline.start", execution_id=execution_id, dry_run=dry_run)

    newsblur = NewsBlurClient(settings.newsblur_username, settings.newsblur_password)
    triage = TriageService()
    sqs = boto3.client("sqs", region_name=settings.dynamodb_region)
    dynamodb = boto3.resource("dynamodb", region_name=settings.dynamodb_region)
    story_staging = StoryStaging(dynamodb.Table(settings.dynamodb_story_staging_table))
    signal_tracker = SignalTracker(dynamodb.Table(settings.dynamodb_signal_table))

    # 1. Load context block once per run
    context_block_json = ""
    try:
        loader = ContextLoader()
        context_data = loader.fetch_all()
        context_block_json = loader.format_context_block(context_data)
    except Exception as exc:
        log("WARNING", "context_loader.failed", error=str(exc))

    # 2. Get folder → feed ID map; fall back to global river on failure
    folder_map = {}
    use_folder_fetch = True
    try:
        folder_map = newsblur.get_feeds_by_folder()
    except Exception as exc:
        log("WARNING", "newsblur.folder_map_failed",
            error=str(exc), fallback="global_river")
        use_folder_fetch = False

    # 3. Fetch stories — per-folder parallel or global fallback
    all_routed: list[tuple] = []  # (story, Route, sub_bucket)
    skip_name_count = 0  # stories dropped because feed title is in ALWAYS_SKIP_NAMES

    if use_folder_fetch:
        folder_configs = _build_folder_configs(folder_map, settings)

        with ThreadPoolExecutor(max_workers=len(folder_configs) or 1) as executor:
            futures = {
                executor.submit(_fetch_folder, newsblur, cfg, hours_back): cfg
                for cfg in folder_configs
            }
            for future in as_completed(futures):
                try:
                    cfg, stories, elapsed_ms = future.result()
                    log("INFO", "newsblur.folder_fetch_complete",
                        folder=cfg.folder_name, count=len(stories), elapsed_ms=elapsed_ms)
                    for story in stories:
                        result = _route_story(story, cfg)
                        if result:
                            all_routed.append(result)
                except Exception as exc:
                    cfg = futures[future]
                    log("WARNING", "newsblur.folder_fetch_failed",
                        folder=cfg.folder_name, error=str(exc))

        # Route unfolderd feeds
        unfolderd_ids = folder_map.get("", [])
        if unfolderd_ids:
            try:
                t0 = time.time()
                unfolderd_stories = newsblur.fetch_unread_stories(
                    feed_ids=unfolderd_ids,
                    min_score=settings.newsblur_min_score,
                    max_results=20,
                    hours_back=hours_back,
                )
                elapsed_ms = int((time.time() - t0) * 1000)
                log("INFO", "newsblur.folder_fetch_complete",
                    folder="(unfolderd)", count=len(unfolderd_stories), elapsed_ms=elapsed_ms)
                unfolderd_routed, unfolderd_skipped = _route_unfolderd(unfolderd_stories, folder_map)
                all_routed.extend(unfolderd_routed)
                skip_name_count += unfolderd_skipped
            except Exception as exc:
                log("WARNING", "newsblur.unfolderd_fetch_failed", error=str(exc))

    else:
        # Global river fallback
        _t0 = time.time()
        stories = newsblur.fetch_unread_stories(
            min_score=settings.newsblur_min_score,
            max_results=settings.max_stories_per_run,
            hours_back=hours_back,
        )
        log("INFO", "newsblur.fetch.complete",
            elapsed_ms=int((time.time() - _t0) * 1000), count=len(stories))
        # Keyword-route all stories in fallback mode
        for story in stories:
            feed = story.story_feed_title or ""
            if feed in ALWAYS_SKIP_NAMES:
                skip_name_count += 1
                continue
            if _has_ai_ml_keyword(story.story_title or ""):
                all_routed.append((story, Route.AI_ML, "research"))
            # Non-AI/ML stories in global fallback are dropped (WORLD stream disabled)

    # 4. Deduplicate by story_hash (keep first occurrence)
    seen_hashes: set[str] = set()
    deduped: list[tuple] = []
    for story, route, sub_bucket in all_routed:
        if story.story_hash not in seen_hashes:
            seen_hashes.add(story.story_hash)
            deduped.append((story, route, sub_bucket))

    # 5. Route to AI_ML stream only (WORLD stream disabled)
    ai_ml_stories: list[tuple] = []
    skip_count = skip_name_count

    for story, route, sub_bucket in deduped:
        if route == Route.SKIP:
            skip_count += 1
        elif route == Route.AI_ML:
            ai_ml_stories.append((story, sub_bucket))

    log("INFO", "triage.routed", ai_ml=len(ai_ml_stories), skipped=skip_count)

    # 6. Velocity clustering on all routed stories
    routed_stories = [s for s, _ in ai_ml_stories]
    cluster_map = compute_clusters(routed_stories)

    # 7. Deduplicate and process each stream
    time_of_day = "AM" if run_time.hour < 18 else "PM"
    date_str = run_time.strftime("%Y-%m-%d")
    briefing_date = f"{date_str}-{time_of_day}"

    raindrop_aiml = None
    if not dry_run and settings.raindrop_token:
        raindrop_aiml = RaindropClient(
            token=settings.raindrop_token,
            collection_id=settings.raindrop_aiml_collection_id,
        )

    ai_ml_hashes = _process_stream(
        stories=ai_ml_stories,
        briefing_type="AI_ML",
        bucket_name="ai-ml",
        raindrop=raindrop_aiml,
        story_staging=story_staging,
        signal_tracker=signal_tracker,
        triage=triage,
        cluster_map=cluster_map,
        context_block_json=context_block_json,
        dry_run=dry_run,
    )
    # 8. Send SQS message for AI_ML stream
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

    body = {
        "execution_id": execution_id,
        "dry_run": dry_run,
        "ai_ml_count": len(ai_ml_hashes),
        "skipped_count": skip_count,
    }
    log("INFO", "triage_pipeline.complete", **body)
    return {"statusCode": 200, "body": body}


def _process_stream(stories, briefing_type, bucket_name, raindrop, story_staging,
                    signal_tracker, triage, cluster_map, context_block_json, dry_run):
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
            # HN velocity -- best-effort, never blocks routing
            if briefing_type == "AI_ML":
                hn_score = _check_hn_velocity(str(story.story_permalink))
                if hn_score >= 200:
                    boost_tags.append("velocity:hn-high")
                elif hn_score >= 50:
                    boost_tags.append("velocity:hn-medium")
            cluster_size, cluster_key = cluster_map.get(story.story_hash, (0, ""))
            content = _truncate_content(story.story_content or "")

            # Upsert signal tracker for non-empty cluster keys
            if not dry_run and cluster_key:
                signal_tracker.upsert(cluster_key, story.story_hash)

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

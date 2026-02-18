"""Lambda 3: Synthesize narrative briefing and post to Raindrop."""
import json

import boto3

from shared.dynamodb_client import BriefingArchive, SignalTracker
from shared.logger import log
from src.clients.raindrop import RaindropClient, RaindropAuthError
from src.config import Settings
from src.services.synthesizer import BriefingSynthesizer


def lambda_handler(event, context):
    settings = Settings()
    dry_run_mode = settings.dry_run  # "false" | "true" | "writes_only"
    do_writes = dry_run_mode == "false"

    record = event["Records"][0]
    message = json.loads(record["body"])
    briefing_type = message["briefing_type"]
    briefing_date = message["briefing_date"]  # "2026-02-17-AM"
    candidate_count = message.get("candidate_count", 0)
    stories = message["stories"]

    # Parse briefing_date into run_date and time_of_day
    run_date, time_of_day = briefing_date.rsplit("-", 1)

    log("INFO", "briefing.start",
        briefing_type=briefing_type, briefing_date=briefing_date, story_count=len(stories))

    # Duplicate check first — bail out before any expensive work
    collection_id = (
        settings.raindrop_aiml_collection_id if briefing_type == "AI_ML"
        else settings.raindrop_world_collection_id
    )
    briefing_url = f"https://newsblur.com/briefing/{briefing_date}-{briefing_type}"

    raindrop = None
    if do_writes and settings.raindrop_token:
        raindrop = RaindropClient(token=settings.raindrop_token, collection_id=collection_id)
        if raindrop.check_duplicate(briefing_url):
            log("INFO", "briefing.duplicate", url=briefing_url)
            return {"statusCode": 200, "body": {"briefing_sent": 0, "reason": "duplicate"}}

    dynamodb = boto3.resource("dynamodb", region_name=settings.dynamodb_region)
    signal_tracker = SignalTracker(dynamodb.Table(settings.dynamodb_signal_table))
    briefing_archive = BriefingArchive(dynamodb.Table(settings.dynamodb_briefing_table))

    # Query signals for cluster_keys in this batch (deduplicated)
    cluster_keys = list({s["cluster_key"] for s in stories if s.get("cluster_key")})
    signals = signal_tracker.get_signals(cluster_keys) if cluster_keys else []

    # Context block: WORLD briefings only (from first story's context_block field)
    context_block = ""
    if briefing_type == "WORLD" and stories:
        context_block = stories[0].get("context_block", "")

    # Set up synthesizer
    use_real_llm = dry_run_mode != "true"
    synth = BriefingSynthesizer(
        bedrock_client=boto3.client("bedrock-runtime", region_name=settings.bedrock_region)
        if use_real_llm else None,
        model_id=settings.bedrock_briefing_model_id,
        dry_run=not use_real_llm,
    )

    # Query prior briefing for trend continuity
    prior_key, prior_type = synth._prior_briefing_key(run_date, time_of_day)
    prior_briefing = briefing_archive.get_prior(prior_key, prior_type)

    # Synthesize the briefing
    briefing_text = synth.synthesize(
        stories=stories,
        run_date=run_date,
        time_of_day=time_of_day,
        briefing_type=briefing_type,
        context_block=context_block,
        signals=signals,
        prior_briefing=prior_briefing,
    )

    # Post to Raindrop
    raindrop_id = None
    if raindrop:
        type_label = "AI Abstract" if briefing_type == "AI_ML" else "Recursive Briefing"
        briefing_title = f"{type_label} — {briefing_date}"
        tags = ["briefing", "ai-generated", time_of_day.lower(), briefing_type.lower()]
        try:
            result = raindrop.create_bookmark(
                url=briefing_url,
                title=briefing_title,
                tags=tags,
                note=briefing_text,
            )
            raindrop_id = result.get("_id") if result else None
            log("INFO", "briefing.raindrop_created",
                title=briefing_title, raindrop_id=raindrop_id)
        except RaindropAuthError as exc:
            log("ERROR", "briefing.raindrop_auth_failed", error=str(exc))
            return {"statusCode": 500, "body": {"briefing_sent": 0, "error": str(exc)}}

    # Write to briefing archive
    if do_writes:
        briefing_archive.store_briefing(
            briefing_date=briefing_date,
            briefing_type=briefing_type,
            content=briefing_text,
            candidate_count=candidate_count,
            passed_count=len(stories),
            story_count=len(stories),
            raindrop_id=str(raindrop_id) if raindrop_id is not None else None,
        )

    # FUTURE: Post briefing to recursiveintelligence-website
    # Requires blog feature to be built first — see docs/plans/website-integration.md
    # IMPORTANT: AI Abstract (AI_ML) only — Recursive Briefing NEVER publishes to website
    # if briefing_type == "AI_ML":
    #     payload = {"briefing_type": briefing_type, "content": briefing_text,
    #                "date": run_date, "is_public": True}
    #     requests.post(WEBSITE_WEBHOOK_URL, json=payload,
    #                   headers={"X-Secret": WEBSITE_WEBHOOK_SECRET})

    body = {
        "briefing_type": briefing_type,
        "briefing_sent": 1 if raindrop_id is not None else 0,
        "dry_run": dry_run_mode,
    }
    log("INFO", "briefing.complete", **body)
    return {"statusCode": 200, "body": body}

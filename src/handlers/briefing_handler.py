"""Lambda 3: Synthesize narrative briefing and publish."""
import json
import urllib.error
import urllib.parse
import urllib.request

import boto3
from botocore.config import Config

from shared.dynamodb_client import BriefingArchive, SignalTracker
from shared.logger import log
from src.clients.raindrop import RaindropAuthError, RaindropClient
from src.config import Settings
from src.services.synthesizer import BriefingSynthesizer


def _briefing_date_to_iso(briefing_date: str) -> str:
    """Convert "2026-02-17-AM" → "2026-02-17T06:00:00Z", "-PM" → "T18:00:00Z"."""
    run_date, time_of_day = briefing_date.rsplit("-", 1)
    hour = "06" if time_of_day == "AM" else "18"
    return f"{run_date}T{hour}:00:00Z"


def _extract_description(briefing_text: str) -> tuple[str, str]:
    """Extract DESCRIPTION: sentinel line as the clean summary.

    Returns (description, clean_body) where clean_body has the sentinel line removed.
    Falls back to first non-heading line if no sentinel found (e.g. WORLD briefings).
    """
    lines = briefing_text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("DESCRIPTION:"):
            description = line[len("DESCRIPTION:"):].strip()
            remaining = lines[i + 1:]
            if remaining and remaining[0].strip() == "":
                remaining = remaining[1:]
            clean_body = "\n".join(remaining)
            return description, clean_body
    # Fallback: no sentinel found — grab first non-empty non-heading line
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped, briefing_text
    return briefing_text[:500], briefing_text


def _source_from_url(url: str) -> str:
    """Derive a human-readable source label from a URL's hostname."""
    try:
        host = urllib.parse.urlparse(url).hostname or ""
        return host.removeprefix("www.")
    except Exception:
        return ""


def _build_items(stories: list) -> list:
    """Map story dicts to BriefItem dicts for the ingest payload."""
    items = []
    for s in stories:
        url = s.get("url", "")
        if not url or not s.get("summary"):
            continue
        # isSafeUrl on the site requires https — skip http stories silently
        if not url.startswith("https://"):
            log("WARNING", "briefing.item_skipped_unsafe_url", url=url)
            continue
        source = s.get("feed_name", "") or _source_from_url(url)
        items.append({
            "title": s["title"],
            "url": url,
            "source": source,
            "snippet": s["summary"],
        })
    return items


def _post_to_site(settings: Settings, briefing_date: str, stories: list,
                  briefing_text: str, *, category: str, title: str,
                  description: str) -> None:
    """POST briefing to the website ingest endpoint.

    Treats 200/201 as success and 409 as idempotent success (already ingested).
    Raises RuntimeError on any other status so the Lambda retries via DLQ.
    """
    payload = json.dumps({
        "title": title,
        "date": _briefing_date_to_iso(briefing_date),
        "category": category,
        "summary": description,
        "body": briefing_text,
        "items": _build_items(stories),
    }).encode()

    req = urllib.request.Request(
        url=f"{settings.site_url}/api/briefs/ingest",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.brief_api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            status = resp.status
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        status = exc.code
        body = exc.read().decode("utf-8", errors="replace")

    if status in (200, 201):
        log("INFO", "briefing.site_ingest_ok", briefing_date=briefing_date)
    else:
        log("ERROR", "briefing.site_ingest_failed", status=status, body=body,
            briefing_date=briefing_date)
        raise RuntimeError(f"Site ingest returned unexpected status {status}")


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
        bedrock_client=boto3.client(
            "bedrock-runtime",
            region_name=settings.bedrock_region,
            config=Config(read_timeout=580),  # just under Lambda's 600s timeout
        ) if use_real_llm else None,
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

    # Publish
    published = False
    raindrop_id = None
    if do_writes:
        if briefing_type == "AI_ML":
            edition = "Morning Edition" if time_of_day == "AM" else "Evening Edition"
            description, clean_body = _extract_description(briefing_text)
            _post_to_site(settings, briefing_date, stories, clean_body,
                          category="AI/ML",
                          title=f"The AI Abstract — {edition}",
                          description=description)
            published = True
        else:  # WORLD — post to private site page + update Raindrop bookmark
            # Site post is non-fatal for WORLD; Raindrop is the primary delivery
            description, clean_body = _extract_description(briefing_text)
            try:
                _post_to_site(settings, briefing_date, stories, clean_body,
                              category="World",
                              title=f"The Recursive Briefing — {briefing_date}",
                              description=description)
            except RuntimeError as exc:
                log("WARNING", "briefing.world_site_ingest_failed", error=str(exc))
            if settings.raindrop_token:
                raindrop = RaindropClient(
                    token=settings.raindrop_token,
                    collection_id=0,  # not used by update_bookmark
                )
                try:
                    raindrop.update_bookmark(
                        raindrop_id=settings.raindrop_personal_brief_id,
                        note=briefing_text,
                    )
                    raindrop_id = str(settings.raindrop_personal_brief_id)
                    published = True
                    log("INFO", "briefing.raindrop_updated",
                        raindrop_id=settings.raindrop_personal_brief_id)
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
            raindrop_id=raindrop_id,
        )

    body = {
        "briefing_type": briefing_type,
        "briefing_sent": 1 if published else 0,
        "dry_run": dry_run_mode,
    }
    log("INFO", "briefing.complete", **body)
    return {"statusCode": 200, "body": body}

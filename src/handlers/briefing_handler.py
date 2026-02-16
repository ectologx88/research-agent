"""Lambda 3: Synthesize narrative briefing and post to Raindrop."""
import json
from datetime import datetime

from src.clients.bedrock_briefing import BedrockBriefingClient, BriefingError
from src.clients.raindrop import RaindropClient, RaindropAuthError
from src.config import Settings
from src.utils import log_structured


def lambda_handler(event, context):
    settings = Settings()

    record = event["Records"][0]
    message = json.loads(record["body"])
    briefing_type = message["briefing_type"]
    run_date = message["run_date"]
    time_of_day = message["time_of_day"]
    stories = message["stories"]

    log_structured("INFO", "Briefing handler starting",
                   briefing_type=briefing_type, story_count=len(stories))

    type_label = "AI/ML" if briefing_type == "ai-ml" else "World"
    time_label = time_of_day.capitalize()
    formatted_date = datetime.strptime(run_date, "%Y-%m-%d").strftime("%b %-d, %Y")
    briefing_title = f"{type_label} {time_label} Briefing \u2014 {formatted_date}"
    briefing_url = f"https://newsblur.com/briefing/{run_date}-{time_of_day}-{briefing_type}"

    raindrop = RaindropClient(
        token=settings.raindrop_token,
        collection_id=settings.raindrop_briefing_collection_id,
    )

    if raindrop.check_duplicate(briefing_url):
        log_structured("INFO", "Briefing already exists, skipping", url=briefing_url)
        return {"statusCode": 200, "body": {"briefing_sent": 0, "reason": "duplicate"}}

    run_hour_utc = 11 if time_of_day == "morning" else 23

    try:
        briefing_client = BedrockBriefingClient(
            region=settings.bedrock_region,
            model_id=settings.bedrock_briefing_model_id,
        )
        briefing_text = briefing_client.synthesize(stories, run_hour_utc, briefing_type)

        raindrop.create_bookmark(
            url=briefing_url,
            title=briefing_title,
            tags=["briefing", "ai-generated", time_of_day, briefing_type],
            note=briefing_text,
        )
        log_structured("INFO", "Briefing created", title=briefing_title)
        return {"statusCode": 200, "body": {"briefing_sent": 1, "title": briefing_title}}

    except (BriefingError, RaindropAuthError) as exc:
        log_structured("ERROR", "Briefing failed", error=str(exc))
        return {"statusCode": 500, "body": {"briefing_sent": 0, "error": str(exc)}}

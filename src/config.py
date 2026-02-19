"""Centralized configuration loaded from environment / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # NewsBlur
    newsblur_username: str = ""
    newsblur_password: str = ""
    newsblur_min_score: int = 1  # -1, 0, or 1

    # Fetch strategy
    fetch_strategy: str = "since_last_run"  # or "hours_back"
    hours_back_default: int = 36
    max_stories_per_run: int = 100

    # Bedrock
    bedrock_region: str = "us-east-1"
    bedrock_summarizer_model_id: str = "us.anthropic.claude-3-5-haiku-20241022-v1:0"

    # Storage
    dynamodb_table_name: str = "newsblur-processing-state"
    dynamodb_region: str = "us-east-1"

    # Features
    mark_as_read: bool = False

    # Raindrop
    raindrop_token: str = ""
    raindrop_aiml_collection_id: int = -1
    raindrop_world_collection_id: int = -1
    raindrop_briefing_collection_id: int = -1
    raindrop_personal_brief_id: int = -1

    # Website integration (AI_ML briefings → site ingest endpoint)
    site_url: str = ""
    brief_api_key: str = ""

    # SQS queues
    sqs_aiml_queue_url: str = ""
    sqs_world_queue_url: str = ""
    sqs_briefing_queue_url: str = ""

    # Briefing synthesis
    bedrock_briefing_model_id: str = "us.anthropic.claude-sonnet-4-6"

    # Summarizer thresholds
    summarizer_aiml_min_score: int = 6
    summarizer_world_min_score: int = 5

    # New DynamoDB tables (v2 pipeline)
    dynamodb_story_staging_table: str = "story-staging"
    dynamodb_signal_table: str = "signal-tracker"
    dynamodb_briefing_table: str = "briefing-archive"

    # DRY_RUN modes: "false" | "true" | "writes_only"
    # "true"         = no LLM calls, no writes, no SQS (pure dry run)
    # "writes_only"  = real LLM calls but no writes/SQS
    dry_run: str = "false"

    # Cost monitoring
    cost_alert_daily_threshold: float = 3.00

    # Pipeline caps (match config/scoring_weights.py constants)
    max_ai_ml_stories: int = 15
    max_world_stories: int = 10
    newsblur_hours_back: int = 12

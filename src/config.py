"""Centralized configuration loaded from environment / .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # NewsBlur
    newsblur_username: str
    newsblur_password: str
    newsblur_min_score: int = 0  # -1, 0, or 1

    # Fetch strategy
    fetch_strategy: str = "since_last_run"  # or "hours_back"
    hours_back_default: int = 36
    max_stories_per_run: int = 100

    # Bedrock
    bedrock_region: str = "us-east-1"
    bedrock_model_id: str = "anthropic.claude-3-5-haiku-20241022-v1:0"

    # Storage
    dynamodb_table_name: str = "newsblur-processing-state"
    dynamodb_region: str = "us-east-1"

    # Features
    mark_as_read: bool = False

    # Classification thresholds (for metrics / logging)
    threshold_overall: int = 8
    threshold_dimension: int = 9

    # Raindrop
    raindrop_token: str = ""
    raindrop_collection_id: int = -1  # -1 = Raindrop "Unsorted"
    raindrop_briefing_collection_id: int = -1  # collection for briefing bookmarks

    # Briefing synthesis
    bedrock_briefing_model_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    briefing_prefilter_domain_min: int = 5
    briefing_prefilter_importance_min: int = 6

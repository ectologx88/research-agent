"""Tests for Settings config."""
import pytest
from src.config import Settings


def test_raindrop_defaults(monkeypatch):
    monkeypatch.setenv("NEWSBLUR_USERNAME", "u")
    monkeypatch.setenv("NEWSBLUR_PASSWORD", "p")
    monkeypatch.setenv("RAINDROP_TOKEN", "tok123")
    from importlib import reload
    import src.config as cfg_mod
    # Reload after setting env vars so Settings() picks them up fresh
    reload(cfg_mod)
    s = cfg_mod.Settings()
    assert s.raindrop_token == "tok123"
    assert s.raindrop_aiml_collection_id == -1


def test_raindrop_custom_aiml_collection(monkeypatch):
    monkeypatch.setenv("NEWSBLUR_USERNAME", "u")
    monkeypatch.setenv("NEWSBLUR_PASSWORD", "p")
    monkeypatch.setenv("RAINDROP_TOKEN", "tok123")
    monkeypatch.setenv("RAINDROP_AIML_COLLECTION_ID", "42")
    from importlib import reload
    import src.config as cfg_mod
    # Reload after setting env vars so Settings() picks them up fresh
    reload(cfg_mod)
    s = cfg_mod.Settings()
    assert s.raindrop_aiml_collection_id == 42


def test_raindrop_briefing_collection_id_default(monkeypatch):
    monkeypatch.setenv("NEWSBLUR_USERNAME", "u")
    monkeypatch.setenv("NEWSBLUR_PASSWORD", "p")
    monkeypatch.delenv("RAINDROP_BRIEFING_COLLECTION_ID", raising=False)
    s = Settings()
    assert s.raindrop_briefing_collection_id == -1


def test_bedrock_briefing_model_id_default(monkeypatch):
    monkeypatch.setenv("NEWSBLUR_USERNAME", "u")
    monkeypatch.setenv("NEWSBLUR_PASSWORD", "p")
    monkeypatch.delenv("BEDROCK_BRIEFING_MODEL_ID", raising=False)
    s = Settings()
    assert s.bedrock_briefing_model_id == "us.anthropic.claude-sonnet-4-6"


def test_aiml_collection_id_defaults_to_minus_one(monkeypatch):
    monkeypatch.setenv("NEWSBLUR_USERNAME", "u")
    monkeypatch.setenv("NEWSBLUR_PASSWORD", "p")
    import importlib, src.config
    importlib.reload(src.config)
    from src.config import Settings
    s = Settings()
    assert s.raindrop_aiml_collection_id == -1


def test_world_collection_id_defaults_to_minus_one(monkeypatch):
    monkeypatch.setenv("NEWSBLUR_USERNAME", "u")
    monkeypatch.setenv("NEWSBLUR_PASSWORD", "p")
    from src.config import Settings
    s = Settings()
    assert s.raindrop_world_collection_id == -1


def test_newsblur_min_score_defaults_to_one(monkeypatch):
    monkeypatch.setenv("NEWSBLUR_USERNAME", "u")
    monkeypatch.setenv("NEWSBLUR_PASSWORD", "p")
    from src.config import Settings
    s = Settings()
    assert s.newsblur_min_score == 1


def test_summarizer_model_id_has_default(monkeypatch):
    monkeypatch.setenv("NEWSBLUR_USERNAME", "u")
    monkeypatch.setenv("NEWSBLUR_PASSWORD", "p")
    from src.config import Settings
    s = Settings()
    assert s.bedrock_summarizer_model_id != ""


def test_new_ddb_table_defaults(monkeypatch):
    monkeypatch.setenv("NEWSBLUR_USERNAME", "u")
    monkeypatch.setenv("NEWSBLUR_PASSWORD", "p")
    from src.config import Settings
    s = Settings()
    assert s.dynamodb_story_staging_table == "story-staging"
    assert s.dynamodb_signal_table == "signal-tracker"
    assert s.dynamodb_briefing_table == "briefing-archive"


def test_dry_run_default_is_false(monkeypatch):
    monkeypatch.setenv("NEWSBLUR_USERNAME", "u")
    monkeypatch.setenv("NEWSBLUR_PASSWORD", "p")
    from src.config import Settings
    s = Settings()
    assert s.dry_run == "false"


def test_cost_alert_threshold_default(monkeypatch):
    monkeypatch.setenv("NEWSBLUR_USERNAME", "u")
    monkeypatch.setenv("NEWSBLUR_PASSWORD", "p")
    from src.config import Settings
    s = Settings()
    assert s.cost_alert_daily_threshold == 3.00


def test_pipeline_cap_defaults(monkeypatch):
    monkeypatch.setenv("NEWSBLUR_USERNAME", "u")
    monkeypatch.setenv("NEWSBLUR_PASSWORD", "p")
    from src.config import Settings
    s = Settings()
    assert s.ai_ml_research_max_stories == 40
    assert s.ai_ml_community_max_stories == 25
    assert s.world_news_max_stories == 50
    assert s.world_science_max_stories == 30
    assert s.world_tech_max_stories == 25
    assert s.general_tech_max_stories == 40
    assert s.ai_ml_research_min_score == 0
    assert s.newsblur_hours_back == 12

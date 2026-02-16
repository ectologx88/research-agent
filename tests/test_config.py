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
    assert s.raindrop_collection_id == -1


def test_raindrop_custom_collection(monkeypatch):
    monkeypatch.setenv("NEWSBLUR_USERNAME", "u")
    monkeypatch.setenv("NEWSBLUR_PASSWORD", "p")
    monkeypatch.setenv("RAINDROP_TOKEN", "tok123")
    monkeypatch.setenv("RAINDROP_COLLECTION_ID", "42")
    from importlib import reload
    import src.config as cfg_mod
    # Reload after setting env vars so Settings() picks them up fresh
    reload(cfg_mod)
    s = cfg_mod.Settings()
    assert s.raindrop_collection_id == 42


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
    assert s.bedrock_briefing_model_id == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"


def test_briefing_prefilter_defaults(monkeypatch):
    monkeypatch.setenv("NEWSBLUR_USERNAME", "u")
    monkeypatch.setenv("NEWSBLUR_PASSWORD", "p")
    monkeypatch.delenv("BRIEFING_PREFILTER_DOMAIN_MIN", raising=False)
    monkeypatch.delenv("BRIEFING_PREFILTER_IMPORTANCE_MIN", raising=False)
    s = Settings()
    assert s.briefing_prefilter_domain_min == 5
    assert s.briefing_prefilter_importance_min == 6

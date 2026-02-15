"""Tests for Settings config."""
import pytest
from pydantic import ValidationError


def test_raindrop_defaults(monkeypatch):
    monkeypatch.setenv("NEWSBLUR_USERNAME", "u")
    monkeypatch.setenv("NEWSBLUR_PASSWORD", "p")
    monkeypatch.setenv("RAINDROP_TOKEN", "tok123")
    from importlib import reload
    import src.config as cfg_mod
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
    reload(cfg_mod)
    s = cfg_mod.Settings()
    assert s.raindrop_collection_id == 42

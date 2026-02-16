"""Tests for BedrockBriefingClient."""
import json
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import pytest

from src.clients.bedrock_briefing import BedrockBriefingClient, BriefingError
from src.models.classification import (
    Classification, RelevanceScores, ContentType, TaxonomyTag,
)
from src.models.story import Story


def _make_story(title="Test Story", url="https://example.com/story"):
    return Story(
        story_hash="abc123",
        story_title=title,
        story_permalink=url,
        story_content="<p>Content</p>",
        story_date=datetime(2026, 2, 16, 11, 0, tzinfo=timezone.utc),
        story_feed_title="Test Feed",
        story_authors="Author",
        newsblur_score=1,
        fetched_at=datetime(2026, 2, 16, 11, 0, tzinfo=timezone.utc),
    )


def _make_classification(domain=7, importance=6):
    return Classification(
        story_hash="abc123",
        scores=RelevanceScores(
            ai_ml=domain, neuroscience=2, theory=3,
            content_craft=6, overall=8, importance=importance,
        ),
        content_type=ContentType.RESEARCH,
        actionability=[],
        taxonomy_tags=[TaxonomyTag.AI_RESEARCH],
        priority_flag=None,
        concepts=["transformers"],
        why_matters="Key advance in AI.",
        summary="A summary.",
        classified_at=datetime.now(timezone.utc),
        model_version="test",
    )


def _mock_invoke_text(text: str):
    """Patch BedrockBriefingClient._invoke to return given text."""
    return patch(
        "src.clients.bedrock_briefing.BedrockBriefingClient._invoke",
        return_value=text,
    )


def test_synthesize_returns_string():
    stories = [(_make_story(), _make_classification())]
    with _mock_invoke_text("## Executive Summary\nTest briefing content."):
        client = BedrockBriefingClient()
        result = client.synthesize(stories, run_hour_utc=11)
    assert isinstance(result, str)
    assert len(result) > 0


def test_synthesize_empty_stories_raises():
    client = BedrockBriefingClient()
    with pytest.raises(BriefingError, match="no stories"):
        client.synthesize([], run_hour_utc=11)


def test_synthesize_morning_label():
    stories = [(_make_story(), _make_classification())]
    captured_prompt = {}

    def fake_invoke(self, system, user):
        captured_prompt["system"] = system
        captured_prompt["user"] = user
        return "briefing text"

    with patch.object(BedrockBriefingClient, "_invoke", fake_invoke):
        client = BedrockBriefingClient()
        client.synthesize(stories, run_hour_utc=11)

    combined = (captured_prompt.get("system", "") + captured_prompt.get("user", "")).lower()
    assert "morning" in combined


def test_synthesize_evening_label():
    stories = [(_make_story(), _make_classification())]
    captured_prompt = {}

    def fake_invoke(self, system, user):
        captured_prompt["user"] = user
        return "briefing text"

    with patch.object(BedrockBriefingClient, "_invoke", fake_invoke):
        client = BedrockBriefingClient()
        client.synthesize(stories, run_hour_utc=23)

    assert "evening" in captured_prompt["user"].lower()


def test_invoke_raises_briefing_error_on_exception():
    client = BedrockBriefingClient()
    with patch.object(client, "_client") as mock_boto:
        mock_boto.invoke_model.side_effect = Exception("Bedrock down")
        with pytest.raises(BriefingError):
            client._invoke("sys", "user")


def test_world_briefing_uses_world_prompt():
    stories = [(_make_story(), _make_classification())]
    captured_prompt = {}

    def fake_invoke(self, system, user):
        captured_prompt["system"] = system
        captured_prompt["user"] = user
        return "world briefing text"

    with patch.object(BedrockBriefingClient, "_invoke", fake_invoke):
        client = BedrockBriefingClient()
        client.synthesize(stories, 11, briefing_type="world")

    system = captured_prompt.get("system", "").lower()
    assert "digest" in system or "world" in system

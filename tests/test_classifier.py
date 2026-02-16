"""Tests for the Bedrock classifier client and response parsing."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.clients.bedrock import (
    BedrockClassifier,
    ClassificationError,
    PROMPT_VERSION,
)
from src.models.classification import ContentType, Actionability
from src.models.story import Story


@pytest.fixture
def story() -> Story:
    return Story(
        story_hash="abc123:feed1",
        story_title="GPT-5 Released: A New Era of Reasoning",
        story_permalink="https://example.com/gpt5-release",
        story_content="<p>OpenAI today announced GPT-5...</p>",
        story_date=datetime(2026, 2, 12, 9, 30, tzinfo=timezone.utc),
        story_feed_title="TechCrunch",
        story_authors="Sarah Chen",
        newsblur_score=1,
        fetched_at=datetime(2026, 2, 12, 12, 0, tzinfo=timezone.utc),
    )


class TestClassifyStory:
    def test_successful_classification(self, story, sample_bedrock_response):
        classifier = BedrockClassifier.__new__(BedrockClassifier)
        classifier._model_id = "test-model"

        with patch.object(classifier, "_invoke", return_value=sample_bedrock_response):
            result = classifier.classify_story(story)

        assert result.story_hash == "abc123:feed1"
        assert result.scores.ai_ml == 9
        assert result.scores.overall == 8
        assert result.content_type == ContentType.BREAKING_NEWS
        assert Actionability.CITATION_WORTHY in result.actionability
        assert len(result.concepts) == 4
        assert "GPT-5" in result.concepts
        assert result.model_version.endswith(f"prompt={PROMPT_VERSION}")

    def test_strips_markdown_fences(self, story):
        classifier = BedrockClassifier.__new__(BedrockClassifier)
        classifier._model_id = "test-model"

        fenced = '```json\n{"scores":{"ai_ml":5,"neuroscience":1,"theory":1,"content_craft":5,"overall":4,"importance":5},"content_type":"industry","actionability":["time_sensitive"],"concepts":["funding","enterprise AI"],"why_matters":"Another funding round.","summary":"A startup raised money.","taxonomy_tags":[],"priority_flag":null}\n```'

        with patch.object(classifier, "_invoke", return_value=fenced):
            result = classifier.classify_story(story)
            assert result.scores.overall == 4

    def test_invalid_json_raises_classification_error(self, story):
        classifier = BedrockClassifier.__new__(BedrockClassifier)
        classifier._model_id = "test-model"

        with patch.object(classifier, "_invoke", return_value="not json at all"):
            with pytest.raises(ClassificationError, match="Invalid JSON"):
                classifier.classify_story(story)

    def test_missing_fields_raises_classification_error(self, story):
        classifier = BedrockClassifier.__new__(BedrockClassifier)
        classifier._model_id = "test-model"

        incomplete = json.dumps({"scores": {"ai_ml": 5}})  # missing required fields

        with patch.object(classifier, "_invoke", return_value=incomplete):
            with pytest.raises(ClassificationError, match="Failed to build"):
                classifier.classify_story(story)


class TestClassifyBatch:
    def test_collects_results_and_logs_failures(self, story, sample_bedrock_response):
        classifier = BedrockClassifier.__new__(BedrockClassifier)
        classifier._model_id = "test-model"

        second_story = story.model_copy(update={"story_hash": "def456:feed2"})

        call_count = 0

        def mock_invoke(prompt):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return sample_bedrock_response
            raise ClassificationError("Bedrock timeout")

        with patch.object(classifier, "_invoke", side_effect=mock_invoke):
            results = classifier.classify_batch([story, second_story])

        assert len(results) == 1
        assert results[0].story_hash == "abc123:feed1"


class TestContentTruncation:
    def test_short_content_unchanged(self):
        s = Story(
            story_hash="x",
            story_title="T",
            story_permalink="https://example.com",
            story_content="short",
            story_date=datetime.now(timezone.utc),
            story_feed_title="F",
            newsblur_score=0,
            fetched_at=datetime.now(timezone.utc),
        )
        assert s.content_truncated == "short"

    def test_long_content_truncated(self):
        s = Story(
            story_hash="x",
            story_title="T",
            story_permalink="https://example.com",
            story_content="a" * 5000,
            story_date=datetime.now(timezone.utc),
            story_feed_title="F",
            newsblur_score=0,
            fetched_at=datetime.now(timezone.utc),
        )
        assert len(s.content_truncated) == 4000 + len("\n[...truncated]")
        assert s.content_truncated.endswith("[...truncated]")

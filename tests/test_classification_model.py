"""Tests for updated Classification model with importance score and taxonomy tags."""
import pytest
from pydantic import ValidationError
from src.models.classification import (
    Classification,
    RelevanceScores,
    ContentType,
    TaxonomyTag,
    PriorityFlag,
)
from datetime import datetime, timezone


def _base_scores(**overrides):
    data = {"ai_ml": 5, "neuroscience": 2, "theory": 3, "content_craft": 6, "overall": 7}
    data.update(overrides)
    return data


def test_importance_required_on_scores():
    with pytest.raises(ValidationError):
        RelevanceScores(**_base_scores())  # missing importance


def test_importance_valid_range():
    scores = RelevanceScores(**_base_scores(), importance=7)
    assert scores.importance == 7


def test_importance_out_of_range():
    with pytest.raises(ValidationError):
        RelevanceScores(**_base_scores(), importance=11)


def test_taxonomy_tag_values():
    assert TaxonomyTag.AI_RESEARCH.value == "#ai-research"
    assert TaxonomyTag.CONSCIOUSNESS.value == "#consciousness"
    assert TaxonomyTag.WORLD_NEWS.value == "#world-news"


def test_priority_flag_values():
    assert PriorityFlag.BREAKING.value == "⚡"
    assert PriorityFlag.RISK.value == "🚨"


def _valid_classification(**overrides):
    base = dict(
        story_hash="abc123",
        scores=RelevanceScores(**_base_scores(), importance=5),
        content_type=ContentType.RESEARCH,
        actionability=[],
        taxonomy_tags=[TaxonomyTag.AI_RESEARCH],
        priority_flag=None,
        concepts=["concept1"],
        why_matters="It matters.",
        summary="A short summary.",
        classified_at=datetime.now(timezone.utc),
        model_version="test",
    )
    base.update(overrides)
    return Classification(**base)


def test_classification_with_taxonomy_and_flag():
    c = _valid_classification(
        taxonomy_tags=[TaxonomyTag.AI_RESEARCH, TaxonomyTag.AI_POLICY],
        priority_flag=PriorityFlag.BREAKING,
    )
    assert len(c.taxonomy_tags) == 2
    assert c.priority_flag == PriorityFlag.BREAKING


def test_classification_no_priority_flag():
    c = _valid_classification(priority_flag=None)
    assert c.priority_flag is None


def test_classification_empty_taxonomy_tags():
    c = _valid_classification(taxonomy_tags=[])
    assert c.taxonomy_tags == []

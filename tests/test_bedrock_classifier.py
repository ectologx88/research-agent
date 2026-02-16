"""Tests for BedrockClassifier prompt parsing with Phase 2b fields."""
import json

import pytest

from src.clients.bedrock import BedrockClassifier, ClassificationError
from src.models.classification import TaxonomyTag, PriorityFlag


def _base_payload(**overrides):
    data = {
        "scores": {
            "ai_ml": 8, "neuroscience": 2, "theory": 3,
            "content_craft": 7, "overall": 8, "importance": 6,
        },
        "content_type": "research",
        "actionability": ["citation_worthy"],
        "taxonomy_tags": ["#ai-research", "#ai-policy"],
        "priority_flag": "⚡",
        "concepts": ["transformers", "RLHF"],
        "why_matters": "Key advance.",
        "summary": "Summary here.",
    }
    data.update(overrides)
    return data


def test_parse_importance_score():
    classifier = BedrockClassifier()
    result = classifier._parse(json.dumps(_base_payload()), "hash1")
    assert result.scores.importance == 6


def test_parse_taxonomy_tags():
    classifier = BedrockClassifier()
    result = classifier._parse(json.dumps(_base_payload()), "hash1")
    assert TaxonomyTag.AI_RESEARCH in result.taxonomy_tags
    assert TaxonomyTag.AI_POLICY in result.taxonomy_tags


def test_parse_priority_flag():
    classifier = BedrockClassifier()
    result = classifier._parse(json.dumps(_base_payload()), "hash1")
    assert result.priority_flag == PriorityFlag.BREAKING


def test_parse_no_priority_flag():
    classifier = BedrockClassifier()
    result = classifier._parse(json.dumps(_base_payload(priority_flag=None)), "hash1")
    assert result.priority_flag is None


def test_parse_unknown_taxonomy_tag_ignored():
    """Unknown tags should be silently dropped, not raise an error."""
    payload = _base_payload(taxonomy_tags=["#ai-research", "#unknown-tag"])
    classifier = BedrockClassifier()
    result = classifier._parse(json.dumps(payload), "hash1")
    assert result.taxonomy_tags == [TaxonomyTag.AI_RESEARCH]


def test_parse_missing_importance_raises():
    payload = _base_payload()
    del payload["scores"]["importance"]
    classifier = BedrockClassifier()
    with pytest.raises(ClassificationError):
        classifier._parse(json.dumps(payload), "hash1")

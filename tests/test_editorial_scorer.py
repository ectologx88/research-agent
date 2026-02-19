# tests/test_editorial_scorer.py
import json
import pytest
from unittest.mock import MagicMock, patch
from src.services.editorial_scorer import EditorialScorer, ScoringResult


class TestScoringResultParsing:
    def test_parses_valid_pass_response(self):
        raw = json.dumps({
            "integrity": 4, "relevance": 5, "novelty": 4, "total": 13,
            "decision": "PASS", "source_type": "peer-reviewed",
            "reasoning": "First open-source release with deployment guide.",
            "summary": "Sentence one. Sentence two."
        })
        result = ScoringResult.from_json(raw)
        assert result.decision == "PASS"
        assert result.total == 13
        assert result.source_type == "peer-reviewed"
        assert result.summary == "Sentence one. Sentence two."

    def test_parses_reject_response(self):
        raw = json.dumps({
            "integrity": 2, "relevance": 2, "novelty": 2, "total": 6,
            "decision": "REJECT", "source_type": "commentary",
            "reasoning": "Pure funding announcement, no technical content.",
            "summary": None
        })
        result = ScoringResult.from_json(raw)
        assert result.decision == "REJECT"
        assert result.summary is None

    def test_raises_on_malformed_json(self):
        with pytest.raises(ValueError):
            ScoringResult.from_json("not valid json {{{")

    def test_raises_on_missing_decision_field(self):
        with pytest.raises(ValueError):
            ScoringResult.from_json(json.dumps({"integrity": 3}))


class TestScoringPromptContent:
    def test_ai_ml_prompt_includes_rdd_context(self):
        scorer = EditorialScorer()
        prompt = scorer._build_prompt("AI_ML", "title", "content", "feed", "research", [])
        assert "RDD" in prompt or "consciousness" in prompt.lower()

    def test_world_prompt_includes_entertainment_clause(self):
        scorer = EditorialScorer()
        prompt = scorer._build_prompt("WORLD", "title", "content", "feed", "entertainment", [])
        assert "Ghostbusters" in prompt or "Wake" in prompt

    def test_boost_tags_included_in_prompt(self):
        scorer = EditorialScorer()
        prompt = scorer._build_prompt("AI_ML", "title", "content", "feed", "research",
                                      ["boost:open-source", "long-signal:rdd"])
        assert "boost:open-source" in prompt

    def test_dry_run_returns_mock_pass(self):
        scorer = EditorialScorer(dry_run=True)
        result = scorer.score(
            briefing_type="AI_ML",
            title="Any title",
            content="Any content",
            feed_name="cs.AI updates on arXiv.org",
            sub_bucket="research",
            boost_tags=[],
        )
        assert result.decision == "PASS"
        assert result.total == 9
        assert result.integrity == 3

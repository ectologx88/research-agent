import json
from unittest.mock import MagicMock, patch
import pytest
from src.clients.bedrock_summarizer import BedrockSummarizerClient, SummaryResult


class TestSummarize:
    def _client(self):
        return BedrockSummarizerClient(region="us-east-1", model_id="test-model")

    def _mock_bedrock_response(self, summary, why_matters, score):
        payload = json.dumps({
            "summary": summary,
            "why_matters": why_matters,
            "score": score,
        })
        return {
            "body": MagicMock(read=lambda: json.dumps({
                "content": [{"text": payload}]
            }).encode())
        }

    def test_returns_summary_result(self):
        client = self._client()
        with patch.object(client, "_bedrock") as mock_bedrock:
            mock_bedrock.invoke_model.return_value = self._mock_bedrock_response(
                summary="A new approach to training LLMs.",
                why_matters="Reduces compute cost by 40%.",
                score=8
            )
            result = client.summarize(
                title="Efficient LLM Training",
                content="Full article text...",
                bucket="ai-ml",
            )
        assert isinstance(result, SummaryResult)
        assert result.summary == "A new approach to training LLMs."
        assert result.why_matters == "Reduces compute cost by 40%."
        assert result.score == 8

    def test_score_clamped_to_1_10(self):
        client = self._client()
        with patch.object(client, "_bedrock") as mock_bedrock:
            mock_bedrock.invoke_model.return_value = self._mock_bedrock_response(
                summary="test", why_matters="test", score=15
            )
            result = client.summarize("title", "content", "ai-ml")
        assert result.score == 10

    def test_handles_malformed_json_gracefully(self):
        client = self._client()
        with patch.object(client, "_bedrock") as mock_bedrock:
            mock_bedrock.invoke_model.return_value = {
                "body": MagicMock(read=lambda: json.dumps({
                    "content": [{"text": "Not valid JSON at all"}]
                }).encode())
            }
            result = client.summarize("title", "content", "ai-ml")
        assert result.score == 5  # default fallback
        assert result.summary != ""

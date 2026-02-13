"""Shared pytest fixtures for the research-agent test suite."""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_stories_raw() -> list[dict]:
    return json.loads((FIXTURES / "sample_stories.json").read_text())


@pytest.fixture
def sample_bedrock_response() -> str:
    """A realistic JSON response from Claude via Bedrock."""
    return json.dumps(
        {
            "scores": {
                "ai_ml": 9,
                "neuroscience": 2,
                "theory": 3,
                "content_craft": 7,
                "overall": 8,
            },
            "content_type": "breaking_news",
            "actionability": ["citation_worthy", "time_sensitive"],
            "concepts": [
                "GPT-5",
                "mixture-of-experts",
                "retrieval-augmented generation",
                "reasoning benchmarks",
            ],
            "why_matters": "A new frontier model with dramatically improved reasoning sets the stage for disruption across knowledge-work industries.",
            "summary": "OpenAI released GPT-5 with a 1M-token context window and near-human graduate-level science performance. The architecture combines sparse MoE with RAG, yielding a 40% reasoning improvement over GPT-4.",
        }
    )

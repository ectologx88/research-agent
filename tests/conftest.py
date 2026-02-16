"""Shared pytest fixtures for the research-agent test suite."""

import json
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def sample_stories_raw() -> list[dict]:
    return json.loads((FIXTURES / "sample_stories.json").read_text())



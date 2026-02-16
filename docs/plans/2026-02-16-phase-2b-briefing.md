# Phase 2b: Briefing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an `importance` score and Seth's taxonomy tags to classification, then synthesize filtered stories into a narrative briefing via Claude Sonnet 4.5 and deliver it as a Raindrop bookmark twice daily.

**Architecture:** Five independent tasks touching classification models, the Bedrock prompt, a new Bedrock briefing client, config, and the Lambda handler. All tasks are TDD — write failing test first, then implement. Tasks 1–3 build the data model and classification changes; Task 4 adds the briefing synthesizer; Task 5 wires everything in the handler and updates Terraform.

**Tech Stack:** Python 3.12, pydantic v2, boto3 (Bedrock + DynamoDB), tenacity, pytest, Terraform (AWS Lambda/EventBridge/SSM)

---

## Background: key files to understand first

Before starting, skim these files to understand what already exists:

- `src/models/classification.py` — `Classification`, `RelevanceScores`, `ContentType`, `Actionability` models
- `src/clients/bedrock.py` — `BedrockClassifier`, `CLASSIFICATION_PROMPT_V1`, `_parse()` method
- `src/config.py` — `Settings` (pydantic-settings); all env vars
- `src/lambda_handler.py` — Phase 2a wiring; the `# TODO Phase 2b` comment is where briefing goes
- `terraform/lambda.tf` — Lambda env vars, EventBridge schedule, SSM data sources

---

## Task 1: Add `importance` score and taxonomy tags to the data model

**Files:**
- Modify: `src/models/classification.py`
- Test: `tests/test_classification_model.py` (new file)

### Step 1: Write failing tests

Create `tests/test_classification_model.py`:

```python
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
```

### Step 2: Run tests to confirm they fail

```bash
cd /home/r3crsvint3llgnz/01_Projects/research-agent
pytest tests/test_classification_model.py -v 2>&1 | head -30
```
Expected: ImportError on `TaxonomyTag`, `PriorityFlag` — tests fail.

### Step 3: Update `src/models/classification.py`

Replace the entire file with:

```python
"""Classification result models for scored stories."""

from datetime import datetime
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


class ContentType(str, Enum):
    BREAKING_NEWS = "breaking_news"
    RESEARCH = "research"
    THOUGHT_LEADERSHIP = "thought_leadership"
    INDUSTRY = "industry"
    WORLD_NEWS = "world_news"


class Actionability(str, Enum):
    CITATION_WORTHY = "citation_worthy"
    THOUGHT_PROVOKING = "thought_provoking"
    TIME_SENSITIVE = "time_sensitive"
    EVERGREEN = "evergreen"


class TaxonomyTag(str, Enum):
    AI_RESEARCH = "#ai-research"
    AI_POLICY = "#ai-policy"
    CONSCIOUSNESS = "#consciousness"
    RDD_FRAMEWORK = "#rdd-framework"
    CLIENT_WORK = "#client-work"
    NEURODIVERGENT_TECH = "#neurodivergent-tech"
    INDUSTRY_NEWS = "#industry-news"
    WORLD_NEWS = "#world-news"


class PriorityFlag(str, Enum):
    BREAKING = "⚡"
    ACTIONABLE = "🎯"
    CONCEPTUAL = "🧠"
    CONNECTIVE = "🔗"
    DATA_DRIVEN = "📊"
    RISK = "🚨"


class RelevanceScores(BaseModel):
    ai_ml: int = Field(ge=1, le=10)
    neuroscience: int = Field(ge=1, le=10)
    theory: int = Field(ge=1, le=10)
    content_craft: int = Field(ge=1, le=10)
    overall: int = Field(ge=1, le=10)
    importance: int = Field(ge=1, le=10)


class Classification(BaseModel):
    story_hash: str
    scores: RelevanceScores
    content_type: ContentType
    actionability: List[Actionability]
    taxonomy_tags: List[TaxonomyTag] = Field(default_factory=list)
    priority_flag: Optional[PriorityFlag] = None
    concepts: List[str] = Field(min_length=1, max_length=7)
    why_matters: str
    summary: str
    classified_at: datetime
    model_version: str
```

### Step 4: Run tests to confirm they pass

```bash
pytest tests/test_classification_model.py -v
```
Expected: all 9 tests PASS.

### Step 5: Run existing tests to check for regressions

```bash
pytest tests/ -v --ignore=tests/test_classification_model.py
```
Expected: all existing tests still pass. If `test_classifier.py` or `conftest.py` fail because `sample_bedrock_response` fixture doesn't include `importance`, note it — we fix that in Task 2.

### Step 6: Commit

```bash
git add src/models/classification.py tests/test_classification_model.py
git commit -m "feat: add importance score and taxonomy/priority-flag fields to Classification"
```

---

## Task 2: Update Bedrock classification prompt and parser

**Files:**
- Modify: `src/clients/bedrock.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_bedrock_classifier.py` (new file — check if it exists first; add tests to it)

**Context:** `CLASSIFICATION_PROMPT_V1` defines what Claude returns. `_parse()` builds the `Classification` object from the JSON response. Both need updating for `importance`, `taxonomy_tags`, and `priority_flag`.

### Step 1: Write failing tests

Create `tests/test_bedrock_classifier.py` (check if it exists first with `ls tests/`):

```python
"""Tests for BedrockClassifier prompt parsing with Phase 2b fields."""
import json
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import pytest

from src.clients.bedrock import BedrockClassifier, ClassificationError
from src.models.classification import TaxonomyTag, PriorityFlag


def _mock_bedrock_response(payload: dict) -> MagicMock:
    """Wrap a dict in the shape BedrockClassifier._invoke expects."""
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp["body"].read.return_value = json.dumps(
        {"content": [{"text": json.dumps(payload)}]}
    ).encode()
    mock_client.invoke_model.return_value = mock_resp
    return mock_client


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
```

### Step 2: Run to confirm failures

```bash
pytest tests/test_bedrock_classifier.py -v 2>&1 | head -40
```
Expected: 6 failures (importance, taxonomy_tags, priority_flag not yet parsed).

### Step 3: Update `conftest.py` fixture to include `importance`

In `tests/conftest.py`, find `sample_bedrock_response` fixture and add `"importance": 7` to the `scores` dict. Also add `"taxonomy_tags": ["#ai-research"]` and `"priority_flag": null` keys to the outer dict.

Updated fixture:
```python
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
                "importance": 7,
            },
            "content_type": "breaking_news",
            "actionability": ["citation_worthy", "time_sensitive"],
            "taxonomy_tags": ["#ai-research"],
            "priority_flag": "⚡",
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
```

### Step 4: Update `src/clients/bedrock.py`

**4a. Update `CLASSIFICATION_PROMPT_V1`** — replace the `## Actionability Tags` section and `## Response Format` section with the following (leave everything before `## Actionability Tags` unchanged):

```
## Importance (1-10)
Strategic significance independent of domain relevance.
- 9-10: World-changing event (paradigm-shifting model release, landmark legislation, existential-risk signal)
- 7-8: High strategic significance (major policy shift, widely-adopted new technique, industry restructuring)
- 5-6: Moderate significance (notable but not landmark, useful to track)
- 3-4: Low broader significance, niche interest
- 1-2: Routine/low-signal

## Actionability Tags (choose all that apply)
- citation_worthy: Contains specific claims, data, or quotes worth referencing
- thought_provoking: Challenges assumptions or introduces novel framing
- time_sensitive: Relevance diminishes significantly after 48 hours
- evergreen: Will remain relevant for months / years

## Taxonomy Tags (choose all that apply from this exact list)
- #ai-research — papers, benchmarks, capabilities advances
- #ai-policy — regulation, governance, safety policy
- #consciousness — philosophy of mind, sentience, phenomenology
- #rdd-framework — Recursive Developmental Design methodology
- #client-work — practical AI adoption, enterprise deployment
- #neurodivergent-tech — ADHD/autism/accessibility tooling
- #industry-news — market moves, funding, launches, acquisitions
- #world-news — geopolitical/economic events with AI implications

## Priority Flag (choose at most one, or null)
- ⚡ breaking / time-sensitive
- 🎯 directly actionable for an AI adoption consultant
- 🧠 deep conceptual value
- 🔗 connects multiple threads in AI/consciousness/RDD thinking
- 📊 data/evidence-driven
- 🚨 risk or threat signal

## Response Format
Respond with ONLY valid JSON — no markdown fences, no commentary.
{{
  "scores": {{
    "ai_ml": <int>,
    "neuroscience": <int>,
    "theory": <int>,
    "content_craft": <int>,
    "overall": <int>,
    "importance": <int>
  }},
  "content_type": "<string>",
  "actionability": ["<string>", ...],
  "taxonomy_tags": ["<string>", ...],
  "priority_flag": "<string or null>",
  "concepts": ["<3-5 specific concepts extracted from the story>"],
  "why_matters": "<one sentence>",
  "summary": "<2-3 sentences>"
}}
```

**4b. Update `_parse()` in `BedrockClassifier`** — after building `actionability`, add taxonomy and priority parsing before building the `Classification` object:

```python
# Parse taxonomy tags — silently drop unknown values
raw_tags = data.get("taxonomy_tags", [])
taxonomy_tags = []
for t in raw_tags:
    try:
        taxonomy_tags.append(TaxonomyTag(t))
    except ValueError:
        pass

# Parse priority flag — None if absent or unrecognized
raw_flag = data.get("priority_flag")
priority_flag = None
if raw_flag:
    try:
        priority_flag = PriorityFlag(raw_flag)
    except ValueError:
        pass

return Classification(
    story_hash=story_hash,
    scores=scores,
    content_type=content_type,
    actionability=actionability,
    taxonomy_tags=taxonomy_tags,
    priority_flag=priority_flag,
    concepts=data.get("concepts", [])[:7],
    why_matters=data.get("why_matters", ""),
    summary=data.get("summary", ""),
    classified_at=utcnow(),
    model_version=f"{self._model_id}|prompt={PROMPT_VERSION}",
)
```

Also update the imports at the top of `bedrock.py`:
```python
from src.models.classification import (
    Actionability,
    Classification,
    ContentType,
    PriorityFlag,
    RelevanceScores,
    TaxonomyTag,
)
```

And bump the prompt version constant:
```python
PROMPT_VERSION = "v2"
```

### Step 5: Run new tests

```bash
pytest tests/test_bedrock_classifier.py -v
```
Expected: all 6 PASS.

### Step 6: Run full test suite

```bash
pytest tests/ -v
```
Expected: all tests pass. Fix any fixture mismatches in `test_classifier.py` if `sample_bedrock_response` caused failures (the conftest update in Step 3 should cover it).

### Step 7: Commit

```bash
git add src/clients/bedrock.py src/models/classification.py tests/conftest.py tests/test_bedrock_classifier.py
git commit -m "feat: update classification prompt and parser for importance score and taxonomy tags"
```

---

## Task 3: Update config with new env vars

**Files:**
- Modify: `src/config.py`
- Modify: `tests/test_config.py`

**Context:** Need three new settings:
- `raindrop_briefing_collection_id: int = -1` — collection for briefing bookmarks
- `bedrock_briefing_model_id: str` — Sonnet 4.5 inference profile ARN
- `briefing_prefilter_domain_min: int = 5` and `briefing_prefilter_importance_min: int = 6` — pre-filter thresholds

### Step 1: Write failing tests

Add to `tests/test_config.py`:

```python
def test_raindrop_briefing_collection_id_default():
    # Ensure env is clear of this var before testing
    import os
    os.environ.pop("RAINDROP_BRIEFING_COLLECTION_ID", None)
    s = Settings()
    assert s.raindrop_briefing_collection_id == -1


def test_bedrock_briefing_model_id_default():
    import os
    os.environ.pop("BEDROCK_BRIEFING_MODEL_ID", None)
    s = Settings()
    assert s.bedrock_briefing_model_id == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"


def test_briefing_prefilter_defaults():
    import os
    os.environ.pop("BRIEFING_PREFILTER_DOMAIN_MIN", None)
    os.environ.pop("BRIEFING_PREFILTER_IMPORTANCE_MIN", None)
    s = Settings()
    assert s.briefing_prefilter_domain_min == 5
    assert s.briefing_prefilter_importance_min == 6
```

### Step 2: Run to confirm failures

```bash
pytest tests/test_config.py -v -k "briefing"
```
Expected: 3 failures (fields don't exist yet).

### Step 3: Update `src/config.py`

Add to the `Settings` class after the existing `raindrop_collection_id` line:

```python
    raindrop_briefing_collection_id: int = -1  # collection for briefing bookmarks

    # Briefing synthesis
    bedrock_briefing_model_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
    briefing_prefilter_domain_min: int = 5
    briefing_prefilter_importance_min: int = 6
```

### Step 4: Run tests

```bash
pytest tests/test_config.py -v
```
Expected: all pass.

### Step 5: Commit

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: add briefing config fields (collection id, model, pre-filter thresholds)"
```

---

## Task 4: Build `BedrockBriefingClient`

**Files:**
- Create: `src/clients/bedrock_briefing.py`
- Test: `tests/test_bedrock_briefing.py` (new file)

**Context:** This client takes a list of `(Story, Classification)` pairs, builds a prompt, calls Claude Sonnet 4.5 via Bedrock, and returns the briefing as a plain string. It uses a system prompt embedding Seth's reader profile.

### Step 1: Write failing tests

Create `tests/test_bedrock_briefing.py`:

```python
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
        story_id="123",
        story_hash="abc123",
        story_title=title,
        story_permalink=url,
        story_feed_id=1,
        story_feed_title="Test Feed",
        story_authors="Author",
        story_date=datetime(2026, 2, 16, 11, 0, tzinfo=timezone.utc),
        story_content="<p>Content</p>",
        story_score=1,
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


def test_synthesize_morning_label(monkeypatch):
    stories = [(_make_story(), _make_classification())]
    captured_prompt = {}

    def fake_invoke(self, system, user):
        captured_prompt["system"] = system
        captured_prompt["user"] = user
        return "briefing text"

    with patch("src.clients.bedrock_briefing.BedrockBriefingClient._invoke", fake_invoke):
        client = BedrockBriefingClient()
        client.synthesize(stories, run_hour_utc=11)

    assert "morning" in captured_prompt["user"].lower() or "morning" in captured_prompt["system"].lower()


def test_synthesize_evening_label(monkeypatch):
    stories = [(_make_story(), _make_classification())]
    captured_prompt = {}

    def fake_invoke(self, system, user):
        captured_prompt["user"] = user
        return "briefing text"

    with patch("src.clients.bedrock_briefing.BedrockBriefingClient._invoke", fake_invoke):
        client = BedrockBriefingClient()
        client.synthesize(stories, run_hour_utc=23)

    assert "evening" in captured_prompt["user"].lower()


def test_invoke_raises_briefing_error_on_exception():
    client = BedrockBriefingClient()
    with patch.object(client, "_client") as mock_boto:
        mock_boto.invoke_model.side_effect = Exception("Bedrock down")
        with pytest.raises(BriefingError):
            client._invoke("sys", "user")
```

### Step 2: Run to confirm failures

```bash
pytest tests/test_bedrock_briefing.py -v 2>&1 | head -20
```
Expected: ImportError — module doesn't exist yet.

### Step 3: Create `src/clients/bedrock_briefing.py`

```python
"""Amazon Bedrock client for briefing synthesis via Claude Sonnet 4.5."""

import json

import boto3
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.models.classification import Classification, TaxonomyTag, PriorityFlag
from src.models.story import Story
from typing import List, Tuple

SETH_SYSTEM_PROMPT = """\
You are an intelligence analyst writing a personal briefing for Seth Holloway.

About Seth:
- AI adoption consultant helping organizations integrate AI into knowledge work
- Creator of the Recursive Developmental Design (RDD) framework — a methodology for \
structuring human-AI collaborative projects
- Deep interest in consciousness, philosophy of mind, and the intersection of \
neuroscience with AI
- Neurodivergent (autism + ADHD); values clarity, directness, and signal over noise
- Skeptical of hype; prizes epistemic rigor and journalistic integrity
- Monitors AI policy, safety, and governance as professionally relevant
- Tracks neurodivergent-friendly tooling and accessibility in tech

Your job: synthesize today's coverage into a crisp, opinionated briefing that \
respects Seth's time and intelligence. No filler. No hedging. Connect dots \
across stories where patterns exist. Flag what matters and why, from Seth's \
specific vantage point.

Write in clear prose — no bullet-point dumps. Use section headers.
"""

BRIEFING_PROMPT_TEMPLATE = """\
It is the {time_of_day} of {date}. Below are {count} stories that passed the \
relevance filter for this {time_of_day} briefing.

{story_list}

---

Write Seth's {time_of_day} intelligence briefing with these five sections:

## Executive Summary
3–5 sentences. The big-picture narrative of what today's coverage means.

## Must-Know Today
The 3–5 stories with the most immediate relevance to Seth. For each: what it is, \
why it matters to Seth specifically, and what (if anything) he should do with it.

## Deep Dives
2–3 stories worth Seth's extended reading time. What makes them worth it? \
What conceptual hooks or connections to his frameworks should he look for?

## Weak Signals
Emerging patterns or under-covered themes across today's stories that may become \
significant. What's the connective tissue?

## Notable Omissions
What is the coverage conspicuously missing or underselling today?
"""


class BriefingError(Exception):
    """Raised when briefing synthesis fails."""


class BedrockBriefingClient:
    """Synthesizes a narrative briefing from classified stories using Claude Sonnet 4.5."""

    def __init__(
        self,
        region: str = "us-east-1",
        model_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    ):
        self._model_id = model_id
        self._client = boto3.client("bedrock-runtime", region_name=region)

    def synthesize(
        self,
        stories: List[Tuple[Story, Classification]],
        run_hour_utc: int,
    ) -> str:
        """Return briefing text for the given stories.

        Args:
            stories: Pre-filtered (Story, Classification) pairs.
            run_hour_utc: UTC hour of the Lambda invocation (determines morning/evening label).

        Raises:
            BriefingError: If stories is empty or Bedrock call fails.
        """
        if not stories:
            raise BriefingError("Cannot synthesize briefing: no stories provided")

        time_of_day = "morning" if run_hour_utc < 18 else "evening"
        from datetime import datetime, timezone
        date_str = datetime.now(timezone.utc).strftime("%B %-d, %Y")

        story_list = self._format_stories(stories)
        user_prompt = BRIEFING_PROMPT_TEMPLATE.format(
            time_of_day=time_of_day,
            date=date_str,
            count=len(stories),
            story_list=story_list,
        )

        return self._invoke(SETH_SYSTEM_PROMPT, user_prompt)

    def _format_stories(self, stories: List[Tuple[Story, Classification]]) -> str:
        lines = []
        for i, (story, c) in enumerate(stories, 1):
            tags = " ".join(t.value for t in c.taxonomy_tags)
            flag = c.priority_flag.value if c.priority_flag else ""
            lines.append(
                f"{i}. [{flag}{tags}] **{story.story_title}** ({story.story_feed_title})\n"
                f"   Scores: overall={c.scores.overall} importance={c.scores.importance}\n"
                f"   Why it matters: {c.why_matters}\n"
                f"   Summary: {c.summary}"
            )
        return "\n\n".join(lines)

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,
    )
    def _invoke(self, system_prompt: str, user_prompt: str) -> str:
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            }
        )
        try:
            resp = self._client.invoke_model(
                modelId=self._model_id,
                body=body,
                contentType="application/json",
                accept="application/json",
            )
            result = json.loads(resp["body"].read())
            return result["content"][0]["text"]
        except Exception as exc:
            raise BriefingError(f"Bedrock briefing synthesis failed: {exc}") from exc
```

### Step 4: Run new tests

```bash
pytest tests/test_bedrock_briefing.py -v
```
Expected: all 5 tests PASS.

### Step 5: Run full suite

```bash
pytest tests/ -v
```
Expected: all tests pass.

### Step 6: Commit

```bash
git add src/clients/bedrock_briefing.py tests/test_bedrock_briefing.py
git commit -m "feat: add BedrockBriefingClient for Sonnet 4.5 narrative synthesis"
```

---

## Task 5: Wire briefing into Lambda handler and update Terraform

**Files:**
- Modify: `src/lambda_handler.py`
- Modify: `terraform/lambda.tf`
- Test: `tests/test_lambda_briefing.py` (new file)

**Context:** The handler needs to:
1. Pre-filter classified stories (domain_relevance >= 5 OR importance >= 6)
2. Call `BedrockBriefingClient.synthesize()` with filtered stories
3. Build briefing bookmark title ("Morning/Evening Briefing — date")
4. Send briefing bookmark to Raindrop with `raindrop_briefing_collection_id`
5. Update story bookmarks to use taxonomy tags instead of concepts

Terraform needs: SSM data source for `RAINDROP_BRIEFING_COLLECTION_ID`, schedule change to cron 6AM/6PM UTC-5, `MAX_STORIES_PER_RUN=200`, `BEDROCK_BRIEFING_MODEL_ID`, briefing collection env var.

**Note on domain_relevance:** The pre-filter uses `domain_relevance` which in the current model is `scores.overall` — wait, no. Look at `RelevanceScores`: there's no `domain_relevance` field. The closest is `ai_ml` for "domain" in the design. Per the design doc: "domain_relevance ≥ 5 OR importance ≥ 6". Map `domain_relevance` to `scores.overall` (the holistic score) since there's no separate field by that name. Use `overall >= 5 OR importance >= 6`.

### Step 1: Write failing tests

Create `tests/test_lambda_briefing.py`:

```python
"""Tests for Phase 2b briefing wiring in lambda_handler."""
import json
from unittest.mock import MagicMock, patch
from datetime import datetime, timezone

import pytest


def _make_mock_result(stories_and_classifications):
    """Build a mock PipelineResult."""
    mock_result = MagicMock()
    mock_result.classified = stories_and_classifications
    mock_result.metrics = MagicMock()
    mock_result.metrics.stories_fetched = len(stories_and_classifications)
    mock_result.metrics.already_processed = 0
    mock_result.metrics.stories_classified = len(stories_and_classifications)
    mock_result.metrics.classification_failures = 0
    mock_result.metrics.dedup_write_failures = 0
    mock_result.metrics.high_value_stories = 0
    mock_result.metrics.time_sensitive_stories = 0
    mock_result.metrics.execution_time_seconds = 1.0
    mock_result.metrics.top_stories = []
    return mock_result


def _make_story(url="https://example.com/1", title="Story"):
    s = MagicMock()
    s.story_permalink = url
    s.story_title = title
    s.story_hash = "hash1"
    return s


def _make_classification(overall=9, importance=7, domain=7):
    c = MagicMock()
    c.scores.overall = overall
    c.scores.importance = importance
    c.scores.ai_ml = domain
    c.taxonomy_tags = []
    c.priority_flag = None
    c.concepts = ["concept1"]
    c.why_matters = "Why it matters."
    return c


def _base_patches():
    return {
        "src.lambda_handler.NewsBlurClient": MagicMock(),
        "src.lambda_handler.BedrockClassifier": MagicMock(),
        "src.lambda_handler.ProcessingStateStorage": MagicMock(),
        "src.lambda_handler.ClassificationService": MagicMock(),
        "src.lambda_handler.RaindropClient": MagicMock(),
        "src.lambda_handler.BedrockBriefingClient": MagicMock(),
    }


def test_briefing_sent_when_token_set():
    """If raindrop_token is set and stories pass pre-filter, briefing bookmark is created."""
    import os
    os.environ.update({
        "NEWSBLUR_USERNAME": "u", "NEWSBLUR_PASSWORD": "p",
        "DYNAMODB_TABLE_NAME": "t", "RAINDROP_TOKEN": "tok",
        "RAINDROP_BRIEFING_COLLECTION_ID": "42",
    })

    patches = _base_patches()
    story = _make_story()
    clf = _make_classification(overall=9, importance=7)
    mock_result = _make_mock_result([(story, clf)])

    with patch.multiple("src.lambda_handler", **patches):
        from src.lambda_handler import (
            ClassificationService, RaindropClient, BedrockBriefingClient
        )
        ClassificationService.return_value.run.return_value = mock_result
        BedrockBriefingClient.return_value.synthesize.return_value = "Briefing text here."
        RaindropClient.return_value.check_duplicate.return_value = False

        from src import lambda_handler
        resp = lambda_handler.lambda_handler({}, {})

    assert resp["statusCode"] == 200
    assert resp["body"]["briefing_sent"] == 1


def test_briefing_skipped_when_no_token():
    import os
    os.environ.update({
        "NEWSBLUR_USERNAME": "u", "NEWSBLUR_PASSWORD": "p",
        "DYNAMODB_TABLE_NAME": "t",
    })
    os.environ.pop("RAINDROP_TOKEN", None)

    patches = _base_patches()
    mock_result = _make_mock_result([])

    with patch.multiple("src.lambda_handler", **patches):
        from src.lambda_handler import ClassificationService
        ClassificationService.return_value.run.return_value = mock_result

        from src import lambda_handler
        resp = lambda_handler.lambda_handler({}, {})

    assert resp["body"]["briefing_sent"] == 0


def test_stories_use_taxonomy_tags_for_raindrop():
    """Story bookmarks should pass taxonomy_tags (not concepts) to create_bookmark."""
    import os
    os.environ.update({
        "NEWSBLUR_USERNAME": "u", "NEWSBLUR_PASSWORD": "p",
        "DYNAMODB_TABLE_NAME": "t", "RAINDROP_TOKEN": "tok",
    })
    os.environ.pop("RAINDROP_BRIEFING_COLLECTION_ID", None)

    from src.models.classification import TaxonomyTag
    patches = _base_patches()
    story = _make_story()
    clf = _make_classification(overall=9, importance=7)
    clf.taxonomy_tags = [TaxonomyTag.AI_RESEARCH, TaxonomyTag.AI_POLICY]

    mock_result = _make_mock_result([(story, clf)])

    with patch.multiple("src.lambda_handler", **patches):
        from src.lambda_handler import ClassificationService, RaindropClient, BedrockBriefingClient
        ClassificationService.return_value.run.return_value = mock_result
        BedrockBriefingClient.return_value.synthesize.return_value = "Briefing."
        RaindropClient.return_value.check_duplicate.return_value = False

        from src import lambda_handler
        lambda_handler.lambda_handler({}, {})

    call_kwargs = RaindropClient.return_value.create_bookmark.call_args
    tags_used = call_kwargs[1]["tags"] if call_kwargs[1] else call_kwargs[0][2]
    assert "#ai-research" in tags_used or TaxonomyTag.AI_RESEARCH in tags_used


def test_prefilter_excludes_low_scores():
    """Stories with overall < 5 AND importance < 6 should not go to briefing."""
    import os
    os.environ.update({
        "NEWSBLUR_USERNAME": "u", "NEWSBLUR_PASSWORD": "p",
        "DYNAMODB_TABLE_NAME": "t", "RAINDROP_TOKEN": "tok",
    })

    patches = _base_patches()
    story = _make_story()
    clf = _make_classification(overall=4, importance=5)  # Both below threshold
    mock_result = _make_mock_result([(story, clf)])

    with patch.multiple("src.lambda_handler", **patches):
        from src.lambda_handler import ClassificationService, BedrockBriefingClient
        ClassificationService.return_value.run.return_value = mock_result

        from src import lambda_handler
        lambda_handler.lambda_handler({}, {})

    BedrockBriefingClient.return_value.synthesize.assert_not_called()
```

### Step 2: Run to confirm failures

```bash
pytest tests/test_lambda_briefing.py -v 2>&1 | head -30
```
Expected: ImportError on `BedrockBriefingClient` in lambda_handler (not imported yet).

### Step 3: Update `src/lambda_handler.py`

Replace the file contents:

```python
"""AWS Lambda entry point for the NewsBlur classification pipeline."""

import dataclasses
import uuid
from datetime import datetime, timezone

from src.clients.bedrock import BedrockClassifier
from src.clients.bedrock_briefing import BedrockBriefingClient, BriefingError
from src.clients.newsblur import NewsBlurClient
from src.clients.raindrop import RaindropAuthError, RaindropClient
from src.config import Settings
from src.services.classifier import ClassificationService
from src.services.storage import ProcessingStateStorage
from src.utils import log_structured, timed, utcnow


def lambda_handler(event, context):
    """Phase 1+2b: NewsBlur Intelligence Pipeline with Raindrop bookmarking and briefing.

    Fetches unread stories, classifies them via Bedrock (Haiku), deduplicates via
    DynamoDB, bookmarks high-value stories to Raindrop with taxonomy tags, and
    synthesizes a narrative briefing via Bedrock (Sonnet 4.5) delivered as a
    Raindrop bookmark.
    """
    execution_id = str(uuid.uuid4())
    settings = Settings()

    log_structured("INFO", "Pipeline starting", execution_id=execution_id)

    with timed("Full pipeline"):
        newsblur = NewsBlurClient(settings.newsblur_username, settings.newsblur_password)
        newsblur.authenticate()

        classifier = BedrockClassifier(
            region=settings.bedrock_region,
            model_id=settings.bedrock_model_id,
        )

        storage = ProcessingStateStorage(
            table_name=settings.dynamodb_table_name,
            region=settings.dynamodb_region,
        )

        service = ClassificationService(
            newsblur=newsblur,
            classifier=classifier,
            storage=storage,
            settings=settings,
        )

        result = service.run()

    # Phase 2a/2b: Raindrop bookmarking and briefing
    raindrop_sent = 0
    raindrop_skipped = 0
    briefing_sent = 0

    if not settings.raindrop_token:
        log_structured("INFO", "Raindrop token not configured, skipping")
    else:
        raindrop = RaindropClient(
            token=settings.raindrop_token,
            collection_id=settings.raindrop_collection_id,
        )
        auth_failed = False

        # --- Story bookmarks (high-value, with taxonomy tags) ---
        high_value = [
            (s, c)
            for s, c in result.classified
            if c.scores.overall >= settings.threshold_overall
        ]

        for story, classification in high_value:
            if auth_failed:
                break
            if not story.story_permalink:
                log_structured("WARNING", "Skipping story with no URL", title=story.story_title)
                raindrop_skipped += 1
                continue

            try:
                if raindrop.check_duplicate(story.story_permalink):
                    log_structured("INFO", "Raindrop duplicate skipped", url=story.story_permalink)
                    raindrop_skipped += 1
                    continue

                # Use taxonomy tags (Phase 2b) — fall back to concepts if empty
                tags = (
                    [t.value for t in classification.taxonomy_tags]
                    if classification.taxonomy_tags
                    else classification.concepts
                )

                raindrop.create_bookmark(
                    url=story.story_permalink,
                    title=story.story_title,
                    tags=tags,
                    note=classification.why_matters,
                )
                raindrop_sent += 1

            except RaindropAuthError as exc:
                log_structured("ERROR", "Raindrop auth failed — stopping", error=str(exc))
                auth_failed = True
                raindrop_skipped += len(high_value) - raindrop_sent - raindrop_skipped

            except Exception as exc:
                log_structured(
                    "WARNING",
                    "Raindrop bookmark failed after retries",
                    url=story.story_permalink,
                    error=str(exc),
                )
                raindrop_skipped += 1

        # --- Briefing bookmark (Phase 2b) ---
        if not auth_failed:
            briefing_stories = [
                (s, c)
                for s, c in result.classified
                if (
                    c.scores.overall >= settings.briefing_prefilter_domain_min
                    or c.scores.importance >= settings.briefing_prefilter_importance_min
                )
            ]

            if briefing_stories:
                try:
                    run_hour_utc = datetime.now(timezone.utc).hour
                    time_of_day = "Morning" if run_hour_utc < 18 else "Evening"
                    date_str = datetime.now(timezone.utc).strftime("%b %-d, %Y")
                    briefing_title = f"{time_of_day} Briefing \u2014 {date_str}"

                    briefing_client = BedrockBriefingClient(
                        region=settings.bedrock_region,
                        model_id=settings.bedrock_briefing_model_id,
                    )
                    briefing_text = briefing_client.synthesize(briefing_stories, run_hour_utc)

                    # Use the first story's URL as the required Raindrop URL
                    first_url = briefing_stories[0][0].story_permalink or "https://newsblur.com"

                    briefing_raindrop = RaindropClient(
                        token=settings.raindrop_token,
                        collection_id=settings.raindrop_briefing_collection_id,
                    )
                    briefing_raindrop.create_bookmark(
                        url=first_url,
                        title=briefing_title,
                        tags=["briefing", "ai-generated", time_of_day.lower()],
                        note=briefing_text,
                    )
                    briefing_sent = 1
                    log_structured("INFO", "Briefing bookmark created", title=briefing_title)

                except BriefingError as exc:
                    log_structured("ERROR", "Briefing synthesis failed", error=str(exc))
                except RaindropAuthError as exc:
                    log_structured("ERROR", "Raindrop auth failed on briefing", error=str(exc))
                except Exception as exc:
                    log_structured("WARNING", "Briefing delivery failed", error=str(exc))
            else:
                log_structured("INFO", "No stories passed briefing pre-filter, skipping briefing")

    body = {
        "execution_id": execution_id,
        "timestamp": utcnow().isoformat(),
        "metrics": dataclasses.asdict(result.metrics),
        "high_value_count": len([c for _, c in result.classified if c.scores.overall >= settings.threshold_overall]),
        "raindrop_sent": raindrop_sent,
        "raindrop_skipped": raindrop_skipped,
        "briefing_sent": briefing_sent,
    }

    log_structured("INFO", "Pipeline finished", **body)

    return {"statusCode": 200, "body": body}
```

### Step 4: Run new tests

```bash
pytest tests/test_lambda_briefing.py -v
```
Expected: all 4 PASS. Fix any env var leakage issues between tests if needed (add `os.environ.pop("RAINDROP_TOKEN", None)` at start of tests that shouldn't have it).

### Step 5: Run full suite

```bash
pytest tests/ -v
```
Expected: all tests pass.

### Step 6: Update `terraform/lambda.tf`

Make these changes:

**a. Add SSM data source** (after existing `raindrop_token` data source):
```hcl
data "aws_ssm_parameter" "raindrop_briefing_collection_id" {
  name            = "/prod/ResearchAgent/Raindrop_Briefing_Collection_Id"
  with_decryption = false
}
```

**b. Change EventBridge schedule** from `rate(12 hours)` to:
```hcl
schedule_expression = "cron(0 11,23 * * ? *)"
```

**c. Update Lambda environment variables** — change `MAX_STORIES_PER_RUN` and add new vars:
```hcl
MAX_STORIES_PER_RUN             = "200"
BEDROCK_BRIEFING_MODEL_ID       = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
RAINDROP_BRIEFING_COLLECTION_ID = data.aws_ssm_parameter.raindrop_briefing_collection_id.value
```

### Step 7: Add SSM parameter for briefing collection ID

Before `terraform apply`, create the SSM parameter. Run this AWS CLI command (substitute your actual Raindrop briefing collection ID):

```bash
aws ssm put-parameter \
  --name "/prod/ResearchAgent/Raindrop_Briefing_Collection_Id" \
  --value "YOUR_COLLECTION_ID_HERE" \
  --type "String" \
  --profile seth-dev \
  --region us-east-1
```

To find your Raindrop collection ID: log into raindrop.io, open the collection you want, and look at the URL — it ends in the numeric collection ID. Use `-1` for the unsorted inbox.

### Step 8: Commit code changes (before terraform apply)

```bash
git add src/lambda_handler.py terraform/lambda.tf
git commit -m "feat: wire Phase 2b briefing into Lambda handler; update Terraform schedule and volume"
```

### Step 9: Build and deploy

```bash
# From project root
sudo rm -rf dist && mkdir dist

docker run --rm \
  --user $(id -u):$(id -g) \
  --platform linux/amd64 \
  -v "$(pwd)":/var/task \
  -w /var/task \
  --entrypoint pip \
  public.ecr.aws/lambda/python:3.12 \
  install -r requirements.txt -t dist/packages --quiet

cp -r src dist/packages/
cp -r dist/packages/* dist/ 2>/dev/null || true

cd dist && zip -r lambda.zip . -x "packages/*" > /dev/null && cd ..

cd terraform && terraform apply -auto-approve && cd ..
```

### Step 10: Smoke test

Invoke the Lambda asynchronously and check CloudWatch logs:

```bash
aws lambda invoke \
  --function-name research-agent-classifier \
  --invocation-type Event \
  --payload '{}' \
  --profile seth-dev \
  /tmp/invoke_out.json

echo "Invocation queued — check CloudWatch in ~3 minutes"
```

Check logs:
```bash
aws logs tail /aws/lambda/research-agent-classifier \
  --since 5m \
  --profile seth-dev \
  --region us-east-1
```

Look for: `"Briefing bookmark created"` or `"No stories passed briefing pre-filter"`.

---

## Commit summary

| Commit | Content |
|--------|---------|
| `feat: add importance score and taxonomy/priority-flag fields to Classification` | Task 1 |
| `feat: update classification prompt and parser for importance score and taxonomy tags` | Task 2 |
| `feat: add briefing config fields` | Task 3 |
| `feat: add BedrockBriefingClient for Sonnet 4.5 narrative synthesis` | Task 4 |
| `feat: wire Phase 2b briefing into Lambda handler; update Terraform schedule and volume` | Task 5 |

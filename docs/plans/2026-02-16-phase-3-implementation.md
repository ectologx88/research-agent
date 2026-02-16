# Phase 3 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the monolithic Lambda with a three-Lambda pipeline (Triage → Summarizer → Briefing) connected by SQS, with rule-based story categorization routing to separate public/private Raindrop collections.

**Architecture:** Lambda 1 fetches from NewsBlur (min_score=1), triages stories into AI/ML vs World buckets via feed-name rules + keyword fallback, routes to Raindrop immediately, stores story content in DynamoDB (24h TTL), and sends SQS messages. Lambda 2 reads SQS, summarizes each story with Haiku, updates Raindrop notes, and forwards to briefing queue. Lambda 3 reads SQS and synthesizes a narrative briefing with Sonnet 4.5.

**Tech Stack:** Python 3.12, Pydantic v2, boto3, AWS Lambda, SQS, DynamoDB, Bedrock (Haiku + Sonnet 4.5), Raindrop.io API, Terraform, pytest

---

## What's Being Removed

- `src/clients/bedrock.py` — old Haiku classifier (replaced by summarizer)
- `src/models/classification.py` — TaxonomyTag, PriorityFlag, RelevanceScores, Classification
- `src/services/classifier.py` — ClassificationService
- `src/lambda_handler.py` — monolithic handler (replaced by three handlers)
- `tests/test_classifier.py`, `tests/test_classification_model.py`, `tests/test_bedrock_classifier.py`, `tests/test_lambda_briefing.py`, `tests/test_lambda_raindrop.py`

## What's Being Kept (and updated)

- `src/models/story.py` — unchanged
- `src/clients/newsblur.py` — unchanged
- `src/clients/raindrop.py` — add `update_bookmark()` method
- `src/clients/bedrock_briefing.py` — update prompts for two briefing types
- `src/services/storage.py` — add `store_story_content()` / `get_story_content()` methods
- `src/config.py` — replace old classification fields with new ones
- `src/utils.py` — unchanged
- `terraform/` — updated throughout
- `tests/conftest.py` — update fixtures
- `tests/test_storage.py`, `tests/test_newsblur_client.py`, `tests/test_raindrop_client.py` — extend, don't delete

---

## Task 1: Triage Service

**Goal:** Rule-based categorization engine that maps stories to buckets using feed-name rules + keyword fallback. Pure Python, no AWS dependencies.

**Files:**
- Create: `src/services/triage.py`
- Create: `tests/test_triage.py`

**Step 1: Write the failing tests**

```python
# tests/test_triage.py
from src.services.triage import TriageService, Bucket

class TestFeedNameRules:
    def _story(self, feed_title, story_title="Some title"):
        from unittest.mock import MagicMock
        s = MagicMock()
        s.story_feed_title = feed_title
        s.story_title = story_title
        return s

    def test_arxiv_feed_routes_to_ai_ml(self):
        svc = TriageService()
        assert svc.categorize(self._story("arXiv AI")) == Bucket.AI_ML

    def test_bbc_feed_routes_to_world(self):
        svc = TriageService()
        assert svc.categorize(self._story("BBC News")) == Bucket.WORLD

    def test_espn_routes_to_skip(self):
        svc = TriageService()
        assert svc.categorize(self._story("ESPN")) == Bucket.SKIP

    def test_weather_feed_routes_to_world_with_weather_sub(self):
        svc = TriageService()
        bucket, sub = svc.categorize_with_sub(self._story("Weather Underground"))
        assert bucket == Bucket.WORLD
        assert sub == "weather"

class TestKeywordFallback:
    def _story(self, title, feed="Unknown Feed"):
        from unittest.mock import MagicMock
        s = MagicMock()
        s.story_feed_title = feed
        s.story_title = title
        return s

    def test_llm_keyword_routes_to_ai_ml(self):
        svc = TriageService()
        assert svc.categorize(self._story("New LLM beats GPT-4 on benchmarks")) == Bucket.AI_ML

    def test_iphone_keyword_routes_to_world(self):
        svc = TriageService()
        bucket, sub = svc.categorize_with_sub(self._story("iPhone 17 announced"))
        assert bucket == Bucket.WORLD
        assert sub == "tech"

    def test_unrecognized_routes_to_world_news(self):
        svc = TriageService()
        bucket, sub = svc.categorize_with_sub(self._story("Local election results"))
        assert bucket == Bucket.WORLD
        assert sub == "news"

    def test_feed_name_takes_priority_over_keyword(self):
        # Even if title has AI keywords, a skip feed wins
        svc = TriageService()
        assert svc.categorize(self._story("LLM beats everything", feed="ESPN")) == Bucket.SKIP

class TestBatchCategorize:
    def test_returns_dict_of_bucket_to_stories(self):
        from unittest.mock import MagicMock
        svc = TriageService()
        stories = []
        for feed, title in [
            ("arXiv AI", "Neural networks"),
            ("BBC News", "Election results"),
            ("ESPN", "Game recap"),
        ]:
            s = MagicMock()
            s.story_feed_title = feed
            s.story_title = title
            stories.append(s)
        result = svc.batch_categorize(stories)
        assert len(result[Bucket.AI_ML]) == 1
        assert len(result[Bucket.WORLD]) == 1
        assert len(result[Bucket.SKIP]) == 1
```

**Step 2: Run to verify RED**
```bash
cd research-agent
python -m pytest tests/test_triage.py -v --tb=short
```
Expected: `ImportError: cannot import name 'TriageService'`

**Step 3: Implement**

```python
# src/services/triage.py
"""Rule-based story triage — no LLM required."""
from enum import Enum
from typing import Dict, List, Tuple

from src.models.story import Story


class Bucket(str, Enum):
    AI_ML = "ai-ml"
    WORLD = "world"
    SKIP = "skip"


# Feed-name rules: lowercase substring → (bucket, sub_bucket)
# None sub_bucket means "use keyword fallback for sub"
FEED_RULES: Dict[str, Tuple[Bucket, str | None]] = {
    # AI/ML
    "arxiv": (Bucket.AI_ML, "research"),
    "papers with code": (Bucket.AI_ML, "research"),
    "hugging face": (Bucket.AI_ML, "industry"),
    "towards data science": (Bucket.AI_ML, "research"),
    "the gradient": (Bucket.AI_ML, "research"),
    "import ai": (Bucket.AI_ML, "research"),
    "openai": (Bucket.AI_ML, "industry"),
    "anthropic": (Bucket.AI_ML, "industry"),
    "deepmind": (Bucket.AI_ML, "research"),
    "google ai": (Bucket.AI_ML, "research"),
    # Tech → world/tech
    "the verge": (Bucket.WORLD, "tech"),
    "techcrunch": (Bucket.WORLD, "tech"),
    "ars technica": (Bucket.WORLD, "tech"),
    "wired": (Bucket.WORLD, "tech"),
    "9to5mac": (Bucket.WORLD, "tech"),
    "macrumors": (Bucket.WORLD, "tech"),
    # World/News
    "bbc": (Bucket.WORLD, "news"),
    "npr": (Bucket.WORLD, "news"),
    "reuters": (Bucket.WORLD, "news"),
    "ap news": (Bucket.WORLD, "news"),
    "associated press": (Bucket.WORLD, "news"),
    "new york times": (Bucket.WORLD, "news"),
    "washington post": (Bucket.WORLD, "news"),
    "the guardian": (Bucket.WORLD, "news"),
    # Science
    "science daily": (Bucket.WORLD, "science"),
    "nature": (Bucket.WORLD, "science"),
    "new scientist": (Bucket.WORLD, "science"),
    "science alert": (Bucket.WORLD, "science"),
    "live science": (Bucket.WORLD, "science"),
    # Weather
    "weather underground": (Bucket.WORLD, "weather"),
    "national weather service": (Bucket.WORLD, "weather"),
    "weather.gov": (Bucket.WORLD, "weather"),
    # Skip
    "espn": (Bucket.SKIP, "sports"),
    "bleacher report": (Bucket.SKIP, "sports"),
    "sports illustrated": (Bucket.SKIP, "sports"),
    "buzzfeed": (Bucket.SKIP, "lifestyle"),
}

AI_ML_KEYWORDS = [
    "llm", "gpt", "claude", "gemini", "mistral", "llama",
    "neural network", "transformer", "diffusion model",
    "reinforcement learning", "machine learning",
    "artificial intelligence", "deep learning",
    "foundation model", "fine-tun", "retrieval augmented",
    "embedding model", "language model",
]

TECH_KEYWORDS = [
    "iphone", "android", "google", "microsoft", "apple",
    "startup", "open source", "github", "developer",
    "programming", "software", "hardware", "chip",
    "semiconductor", "product launch",
]


class TriageService:
    """Categorizes stories into buckets using feed-name rules + keyword fallback."""

    def categorize(self, story: Story) -> Bucket:
        bucket, _ = self.categorize_with_sub(story)
        return bucket

    def categorize_with_sub(self, story: Story) -> Tuple[Bucket, str]:
        feed_lower = (story.story_feed_title or "").lower()
        title_lower = (story.story_title or "").lower()

        # Step 1: feed-name lookup (substring match)
        for pattern, (bucket, sub) in FEED_RULES.items():
            if pattern in feed_lower:
                if sub is not None:
                    return bucket, sub
                # sub is None — fall through to keyword for sub-bucket
                break

        # Step 2: keyword fallback
        if any(kw in title_lower for kw in AI_ML_KEYWORDS):
            return Bucket.AI_ML, "research"
        if any(kw in title_lower for kw in TECH_KEYWORDS):
            return Bucket.WORLD, "tech"

        return Bucket.WORLD, "news"

    def batch_categorize(self, stories: List[Story]) -> Dict[Bucket, List[Tuple[Story, str]]]:
        result: Dict[Bucket, List[Tuple[Story, str]]] = {
            Bucket.AI_ML: [],
            Bucket.WORLD: [],
            Bucket.SKIP: [],
        }
        for story in stories:
            bucket, sub = self.categorize_with_sub(story)
            result[bucket].append((story, sub))
        return result
```

**Step 4: Run to verify GREEN**
```bash
python -m pytest tests/test_triage.py -v
```
Expected: All tests pass.

**Step 5: Commit**
```bash
git add src/services/triage.py tests/test_triage.py
git commit -m "feat: add rule-based triage service with feed-name rules and keyword fallback"
```

---

## Task 2: DynamoDB Story Content Storage

**Goal:** Add `store_story_content()` and `get_story_content()` / `get_stories_content()` to `ProcessingStateStorage` for passing story data between Lambda 1 and Lambda 2.

**Files:**
- Modify: `src/services/storage.py`
- Modify: `tests/test_storage.py`

**Step 1: Write failing tests**

```python
# Add to tests/test_storage.py in a new class TestStoryContent:

class TestStoryContent:
    def test_stores_and_retrieves_story_content(self, storage, mock_table):
        mock_table.put_item.return_value = {}
        mock_table.get_item.return_value = {
            "Item": {
                "record_type": "story_content",
                "identifier": "hash1",
                "data": {
                    "title": "Test Story",
                    "url": "https://example.com",
                    "content": "Article body",
                    "feed_title": "arXiv AI",
                    "bucket": "ai-ml",
                    "sub_bucket": "research",
                    "newsblur_score": 1,
                    "raindrop_id": None,
                }
            }
        }
        storage.store_story_content("hash1", {
            "title": "Test Story",
            "url": "https://example.com",
            "content": "Article body",
            "feed_title": "arXiv AI",
            "bucket": "ai-ml",
            "sub_bucket": "research",
            "newsblur_score": 1,
            "raindrop_id": None,
        })
        result = storage.get_story_content("hash1")
        assert result["title"] == "Test Story"
        assert result["bucket"] == "ai-ml"

    def test_returns_none_for_missing_story(self, storage, mock_table):
        mock_table.get_item.return_value = {}
        assert storage.get_story_content("nonexistent") is None

    def test_get_stories_content_returns_all_found(self, storage, mock_dynamo):
        mock_dynamo.batch_get_item.return_value = {
            "Responses": {
                "test-table": [
                    {"record_type": "story_content", "identifier": "hash1",
                     "data": {"title": "Story 1", "bucket": "ai-ml"}},
                    {"record_type": "story_content", "identifier": "hash2",
                     "data": {"title": "Story 2", "bucket": "world"}},
                ]
            },
            "UnprocessedKeys": {}
        }
        result = storage.get_stories_content(["hash1", "hash2", "hash3"])
        assert len(result) == 2
        assert result["hash1"]["title"] == "Story 1"
```

**Step 2: Verify RED**
```bash
python -m pytest tests/test_storage.py::TestStoryContent -v --tb=short
```
Expected: `AttributeError: 'ProcessingStateStorage' object has no attribute 'store_story_content'`

**Step 3: Implement** — add to end of `ProcessingStateStorage` class in `src/services/storage.py`:

```python
# ------------------------------------------------------------------
# Story content (temporary, 24h TTL — for Lambda 1 → Lambda 2 handoff)
# ------------------------------------------------------------------

STORY_CONTENT_TTL_HOURS = 24

def store_story_content(self, story_hash: str, data: dict) -> bool:
    """Store story content temporarily for cross-Lambda handoff."""
    ttl = int(time.time()) + (self.STORY_CONTENT_TTL_HOURS * 3600)
    try:
        self._table.put_item(Item={
            "record_type": "story_content",
            "identifier": story_hash,
            "data": data,
            "ttl": ttl,
        })
        return True
    except Exception as exc:
        log_structured("ERROR", "Failed to store story content", hash=story_hash, error=str(exc))
        return False

def get_story_content(self, story_hash: str) -> dict | None:
    """Retrieve story content by hash. Returns None if not found."""
    resp = self._table.get_item(
        Key={"record_type": "story_content", "identifier": story_hash}
    )
    item = resp.get("Item")
    return item["data"] if item else None

def get_stories_content(self, story_hashes: list[str]) -> dict[str, dict]:
    """Batch-fetch story content records. Returns {hash: data} for found items."""
    if not story_hashes:
        return {}
    results = {}
    for i in range(0, len(story_hashes), 100):
        chunk = story_hashes[i:i + 100]
        resp = self._dynamo.batch_get_item(
            RequestItems={
                self._table_name: {
                    "Keys": [
                        {"record_type": "story_content", "identifier": h}
                        for h in chunk
                    ]
                }
            }
        )
        for item in resp.get("Responses", {}).get(self._table_name, []):
            results[item["identifier"]] = item["data"]
    return results
```

**Step 4: Verify GREEN**
```bash
python -m pytest tests/test_storage.py -v
```
Expected: All tests pass.

**Step 5: Commit**
```bash
git add src/services/storage.py tests/test_storage.py
git commit -m "feat: add story_content store/retrieve methods to ProcessingStateStorage"
```

---

## Task 3: Raindrop Update Bookmark

**Goal:** Add `update_bookmark(raindrop_id, note)` to `RaindropClient` so Lambda 2 can add summaries to existing bookmarks.

**Files:**
- Modify: `src/clients/raindrop.py`
- Modify: `tests/test_raindrop_client.py`

**Step 1: Write failing test**

```python
# Add to tests/test_raindrop_client.py in TestCreateBookmark class (or new class):

class TestUpdateBookmark:
    def _client(self):
        return RaindropClient(token="tok", collection_id=99)

    def test_sends_put_with_note(self):
        client = self._client()
        with patch.object(client, "_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"result": True, "item": {"_id": 123}}
            mock_resp.raise_for_status = MagicMock()
            mock_session.put.return_value = mock_resp

            result = client.update_bookmark(raindrop_id=123, note="Summary text here.")

            call_kwargs = mock_session.put.call_args
            assert "/raindrop/123" in call_kwargs[0][0]
            assert call_kwargs[1]["json"]["note"] == "Summary text here."
            assert result["_id"] == 123

    def test_raises_auth_error_on_401(self):
        client = self._client()
        with patch.object(client, "_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_resp)
            mock_session.put.return_value = mock_resp
            with pytest.raises(RaindropAuthError):
                client.update_bookmark(raindrop_id=123, note="text")
```

**Step 2: Verify RED**
```bash
python -m pytest tests/test_raindrop_client.py::TestUpdateBookmark -v --tb=short
```
Expected: `AttributeError: 'RaindropClient' object has no attribute 'update_bookmark'`

**Step 3: Implement** — add to `src/clients/raindrop.py` after `create_bookmark`:

```python
@retry(
    retry=retry_if_exception_type(requests.exceptions.RequestException),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=15),
    reraise=True,
)
def update_bookmark(self, raindrop_id: int, note: str) -> dict:
    """Update the note field on an existing Raindrop bookmark.

    Raises:
        RaindropAuthError: On 401.
        RaindropError: On persistent failure.
    """
    resp = self._session.put(
        f"{self._base}/raindrop/{raindrop_id}",
        json={"note": note},
        timeout=15,
    )
    if resp.status_code == 401:
        raise RaindropAuthError("Raindrop token invalid or expired (401)")
    resp.raise_for_status()
    return resp.json()["item"]
```

**Step 4: Verify GREEN**
```bash
python -m pytest tests/test_raindrop_client.py -v
```
Expected: All tests pass.

**Step 5: Commit**
```bash
git add src/clients/raindrop.py tests/test_raindrop_client.py
git commit -m "feat: add update_bookmark method to RaindropClient for adding summaries"
```

---

## Task 4: Bedrock Summarizer Client

**Goal:** New `BedrockSummarizerClient` that produces a per-story summary + relevance score using Haiku. Replaces the old `BedrockClassifier`.

**Files:**
- Create: `src/clients/bedrock_summarizer.py`
- Create: `tests/test_bedrock_summarizer.py`

**Step 1: Write failing tests**

```python
# tests/test_bedrock_summarizer.py
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
```

**Step 2: Verify RED**
```bash
python -m pytest tests/test_bedrock_summarizer.py -v --tb=short
```
Expected: `ImportError: cannot import name 'BedrockSummarizerClient'`

**Step 3: Implement**

```python
# src/clients/bedrock_summarizer.py
"""Per-story summarizer using Claude Haiku via Amazon Bedrock."""
import json
from dataclasses import dataclass

import boto3
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.utils import log_structured


@dataclass
class SummaryResult:
    summary: str
    why_matters: str
    score: int  # 1-10


AI_ML_SYSTEM_PROMPT = """You are an expert AI/ML analyst. Summarize research papers and AI industry news
for a technically informed audience interested in the AI/ML field broadly.
Focus on what the work does, why it matters to the field, and how it connects to the evolving AI landscape.
Do NOT personalize — write for any informed reader following AI/ML."""

WORLD_SYSTEM_PROMPT = """You are a concise news editor. Summarize articles clearly for an informed general reader.
Focus on what happened, why it matters, and what people should know.
Be direct and brief."""

SUMMARY_PROMPT = """Summarize this article. Return ONLY valid JSON, no markdown fences.

Title: {title}

Content: {content}

Return this exact JSON structure:
{{
  "summary": "2-3 sentence summary of the article",
  "why_matters": "1 sentence on significance",
  "score": <integer 1-10 for relevance/importance>
}}"""


class BedrockSummarizerClient:
    """Summarizes individual stories using Claude Haiku."""

    def __init__(self, region: str = "us-east-1", model_id: str = "us.anthropic.claude-3-5-haiku-20241022-v1:0"):
        self._model_id = model_id
        self._bedrock = boto3.client("bedrock-runtime", region_name=region)

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,
    )
    def summarize(self, title: str, content: str, bucket: str) -> SummaryResult:
        """Summarize a single story. Returns SummaryResult with graceful fallback on parse failure."""
        system = AI_ML_SYSTEM_PROMPT if bucket == "ai-ml" else WORLD_SYSTEM_PROMPT
        user = SUMMARY_PROMPT.format(
            title=title,
            content=(content or "")[:3000],  # cap content length
        )

        resp = self._bedrock.invoke_model(
            modelId=self._model_id,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 512,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            }),
        )
        raw = json.loads(resp["body"].read())
        text = raw["content"][0]["text"].strip()

        try:
            # Strip markdown fences if present
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
            score = max(1, min(10, int(data.get("score", 5))))
            return SummaryResult(
                summary=str(data.get("summary", title)),
                why_matters=str(data.get("why_matters", "")),
                score=score,
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            log_structured("WARNING", "Failed to parse summarizer response", title=title)
            return SummaryResult(summary=title, why_matters="", score=5)
```

**Step 4: Verify GREEN**
```bash
python -m pytest tests/test_bedrock_summarizer.py -v
```
Expected: All tests pass.

**Step 5: Commit**
```bash
git add src/clients/bedrock_summarizer.py tests/test_bedrock_summarizer.py
git commit -m "feat: add BedrockSummarizerClient for per-story Haiku summarization"
```

---

## Task 5: Update Config + Briefing Client

**Goal:** Update `Settings` for Phase 3 (new collection IDs, remove old classification fields). Update `BedrockBriefingClient` to support both `ai-ml` and `world` briefing types.

**Files:**
- Modify: `src/config.py`
- Modify: `src/clients/bedrock_briefing.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_bedrock_briefing.py`

**Step 1: Write failing tests for config**

```python
# Add to tests/test_config.py:

def test_aiml_collection_id_defaults_to_minus_one():
    import os
    os.environ.setdefault("NEWSBLUR_USERNAME", "u")
    os.environ.setdefault("NEWSBLUR_PASSWORD", "p")
    from src.config import Settings
    s = Settings()
    assert s.raindrop_aiml_collection_id == -1

def test_world_collection_id_defaults_to_minus_one():
    import os
    os.environ.setdefault("NEWSBLUR_USERNAME", "u")
    os.environ.setdefault("NEWSBLUR_PASSWORD", "p")
    from src.config import Settings
    s = Settings()
    assert s.raindrop_world_collection_id == -1

def test_newsblur_min_score_defaults_to_one():
    import os
    os.environ.setdefault("NEWSBLUR_USERNAME", "u")
    os.environ.setdefault("NEWSBLUR_PASSWORD", "p")
    from src.config import Settings
    s = Settings()
    assert s.newsblur_min_score == 1

def test_summarizer_model_id_has_default():
    import os
    os.environ.setdefault("NEWSBLUR_USERNAME", "u")
    os.environ.setdefault("NEWSBLUR_PASSWORD", "p")
    from src.config import Settings
    s = Settings()
    assert "haiku" in s.bedrock_summarizer_model_id.lower() or s.bedrock_summarizer_model_id != ""
```

**Step 2: Verify RED**
```bash
python -m pytest tests/test_config.py -v --tb=short
```
Expected: `AttributeError: 'Settings' object has no attribute 'raindrop_aiml_collection_id'`

**Step 3: Update `src/config.py`** — replace the old classification/raindrop fields:

```python
"""Centralized configuration loaded from environment / .env file."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    # NewsBlur
    newsblur_username: str
    newsblur_password: str
    newsblur_min_score: int = 1  # Phase 3: focus-only by default

    # Fetch strategy
    fetch_strategy: str = "since_last_run"
    hours_back_default: int = 36
    max_stories_per_run: int = 150

    # Bedrock
    bedrock_region: str = "us-east-1"
    bedrock_summarizer_model_id: str = "us.anthropic.claude-3-5-haiku-20241022-v1:0"
    bedrock_briefing_model_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

    # Storage
    dynamodb_table_name: str = "newsblur-processing-state"
    dynamodb_region: str = "us-east-1"

    # Features
    mark_as_read: bool = False

    # Raindrop
    raindrop_token: str = ""
    raindrop_aiml_collection_id: int = -1    # public AI/ML feed
    raindrop_world_collection_id: int = -1   # private world digest
    raindrop_briefing_collection_id: int = -1  # both briefings land here

    # SQS
    sqs_aiml_queue_url: str = ""
    sqs_world_queue_url: str = ""
    sqs_briefing_queue_url: str = ""

    # Summarizer thresholds
    summarizer_aiml_min_score: int = 6    # min score to include in AI/ML briefing
    summarizer_world_min_score: int = 5   # min score to include in World briefing
```

**Step 4: Update `src/clients/bedrock_briefing.py`** — replace `SETH_SYSTEM_PROMPT` with two system prompts and update `synthesize()` to accept `briefing_type`:

The method signature changes from:
```python
def synthesize(self, stories, run_hour_utc) -> str:
```
to:
```python
def synthesize(self, stories, run_hour_utc, briefing_type="ai-ml") -> str:
```

Add `WORLD_SYSTEM_PROMPT` constant and `WORLD_BRIEFING_PROMPT_TEMPLATE` alongside the existing AI/ML ones. Route by `briefing_type` param.

**World system prompt:**
```python
WORLD_SYSTEM_PROMPT = """You are a concise daily briefing editor producing a morning/evening digest
for an informed, curious reader. Cover world events, science, tech culture, and weather.
Be direct, accessible, and brief. Prioritize what matters most today."""
```

**World briefing template sections:** World & Nation, Science, Tech & Geek Culture, Local & Weather.

**Step 5: Update `tests/test_bedrock_briefing.py`** — add test that `briefing_type="world"` uses world prompt (check system prompt contains "digest" or "weather").

**Step 6: Verify GREEN**
```bash
python -m pytest tests/test_config.py tests/test_bedrock_briefing.py -v
```
Expected: All pass.

**Step 7: Commit**
```bash
git add src/config.py src/clients/bedrock_briefing.py tests/test_config.py tests/test_bedrock_briefing.py
git commit -m "feat: update Settings and BedrockBriefingClient for Phase 3 dual-briefing"
```

---

## Task 6: Lambda 1 — Triage Handler

**Goal:** New Lambda 1 entry point. Fetches from NewsBlur, deduplicates, triages, routes to Raindrop, stores content in DynamoDB, sends SQS messages.

**Files:**
- Create: `src/handlers/triage_handler.py`
- Create: `tests/test_triage_handler.py`

**Step 1: Write failing tests**

```python
# tests/test_triage_handler.py
from unittest.mock import MagicMock, patch


def _make_story(feed="arXiv AI", title="Neural nets", url="https://arxiv.org/1", hash="h1"):
    s = MagicMock()
    s.story_feed_title = feed
    s.story_title = title
    s.story_permalink = url
    s.story_hash = hash
    s.story_content = "Article body"
    s.story_authors = "Author"
    s.newsblur_score = 1
    return s


@patch("src.handlers.triage_handler.boto3")
@patch("src.handlers.triage_handler.RaindropClient")
@patch("src.handlers.triage_handler.ProcessingStateStorage")
@patch("src.handlers.triage_handler.NewsBlurClient")
@patch("src.handlers.triage_handler.Settings")
def test_routes_aiml_story_to_aiml_collection(
    mock_settings_cls, mock_nb_cls, mock_storage_cls, mock_raindrop_cls, mock_boto3
):
    settings = MagicMock()
    settings.raindrop_token = "tok"
    settings.raindrop_aiml_collection_id = 11
    settings.raindrop_world_collection_id = 22
    settings.sqs_aiml_queue_url = "https://sqs/aiml"
    settings.sqs_world_queue_url = "https://sqs/world"
    settings.newsblur_min_score = 1
    settings.max_stories_per_run = 150
    settings.mark_as_read = False
    settings.fetch_strategy = "hours_back"
    settings.hours_back_default = 12
    settings.dynamodb_table_name = "table"
    settings.dynamodb_region = "us-east-1"
    mock_settings_cls.return_value = settings

    story = _make_story(feed="arXiv AI", hash="h1")
    mock_nb_cls.return_value.fetch_unread_stories.return_value = [story]
    mock_storage_cls.return_value.batch_check_processed.return_value = set()
    mock_storage_cls.return_value.store_story_content.return_value = True
    mock_raindrop_cls.return_value.check_duplicate.return_value = False
    mock_raindrop_cls.return_value.create_bookmark.return_value = {"_id": 999}

    from src.handlers import triage_handler
    resp = triage_handler.lambda_handler({}, {})

    assert resp["statusCode"] == 200
    assert resp["body"]["ai_ml_count"] == 1
    assert resp["body"]["world_count"] == 0

    # Verify Raindrop was called with aiml collection
    raindrop_instance = mock_raindrop_cls.return_value
    assert raindrop_instance.create_bookmark.called


@patch("src.handlers.triage_handler.boto3")
@patch("src.handlers.triage_handler.RaindropClient")
@patch("src.handlers.triage_handler.ProcessingStateStorage")
@patch("src.handlers.triage_handler.NewsBlurClient")
@patch("src.handlers.triage_handler.Settings")
def test_skip_stories_are_not_saved(
    mock_settings_cls, mock_nb_cls, mock_storage_cls, mock_raindrop_cls, mock_boto3
):
    settings = MagicMock()
    settings.raindrop_token = "tok"
    settings.sqs_aiml_queue_url = "https://sqs/aiml"
    settings.sqs_world_queue_url = "https://sqs/world"
    mock_settings_cls.return_value = settings

    story = _make_story(feed="ESPN", title="Game recap")
    mock_nb_cls.return_value.fetch_unread_stories.return_value = [story]
    mock_storage_cls.return_value.batch_check_processed.return_value = set()

    from src.handlers import triage_handler
    resp = triage_handler.lambda_handler({}, {})

    assert resp["body"]["skipped_count"] == 1
    mock_raindrop_cls.return_value.create_bookmark.assert_not_called()
```

**Step 2: Verify RED**
```bash
python -m pytest tests/test_triage_handler.py -v --tb=short
```
Expected: `ImportError: No module named 'src.handlers'`

**Step 3: Create `src/handlers/__init__.py`** (empty)

**Step 4: Implement `src/handlers/triage_handler.py`**

```python
"""Lambda 1: Fetch from NewsBlur, triage stories, route to Raindrop, send SQS."""
import json
import uuid
from datetime import timezone, datetime

import boto3

from src.clients.newsblur import NewsBlurClient
from src.clients.raindrop import RaindropClient, RaindropAuthError
from src.config import Settings
from src.services.storage import ProcessingStateStorage
from src.services.triage import Bucket, TriageService
from src.utils import log_structured, timed, utcnow


def lambda_handler(event, context):
    execution_id = str(uuid.uuid4())
    settings = Settings()
    log_structured("INFO", "Triage pipeline starting", execution_id=execution_id)

    newsblur = NewsBlurClient(settings.newsblur_username, settings.newsblur_password)
    storage = ProcessingStateStorage(settings.dynamodb_table_name, settings.dynamodb_region)
    triage = TriageService()
    sqs = boto3.client("sqs", region_name="us-east-1")

    # 1. Fetch
    with timed("NewsBlur fetch"):
        stories = newsblur.fetch_unread_stories(
            min_score=settings.newsblur_min_score,
            max_results=settings.max_stories_per_run,
        )

    # 2. Deduplicate
    all_hashes = [s.story_hash for s in stories]
    already_seen = storage.batch_check_processed(all_hashes)
    new_stories = [s for s in stories if s.story_hash not in already_seen]
    log_structured("INFO", "Dedup complete",
                   total=len(stories), new=len(new_stories), seen=len(already_seen))

    # 3. Triage
    buckets = triage.batch_categorize(new_stories)
    ai_ml_stories = buckets[Bucket.AI_ML]
    world_stories = buckets[Bucket.WORLD]
    skip_stories = buckets[Bucket.SKIP]

    log_structured("INFO", "Triage complete",
                   ai_ml=len(ai_ml_stories), world=len(world_stories), skip=len(skip_stories))

    # 4. Route to Raindrop + store content
    run_time = utcnow()
    time_of_day = "morning" if run_time.hour < 18 else "evening"
    date_str = run_time.strftime("%Y-%m-%d")

    if settings.raindrop_token:
        raindrop_aiml = RaindropClient(
            token=settings.raindrop_token,
            collection_id=settings.raindrop_aiml_collection_id,
        )
        raindrop_world = RaindropClient(
            token=settings.raindrop_token,
            collection_id=settings.raindrop_world_collection_id,
        )
        _route_to_raindrop(ai_ml_stories, raindrop_aiml, storage, "ai-ml")
        _route_to_raindrop(world_stories, raindrop_world, storage, "world")

    # Mark skipped stories as processed (so we don't re-fetch them)
    skip_hashes = [s.story_hash for s, _ in skip_stories]
    if skip_hashes:
        storage.mark_processed_batch(skip_hashes)

    # 5. Send SQS messages
    ai_ml_hashes = [s.story_hash for s, _ in ai_ml_stories]
    world_hashes = [s.story_hash for s, _ in world_stories]

    if ai_ml_hashes and settings.sqs_aiml_queue_url:
        sqs.send_message(
            QueueUrl=settings.sqs_aiml_queue_url,
            MessageBody=json.dumps({
                "briefing_type": "ai-ml",
                "run_date": date_str,
                "time_of_day": time_of_day,
                "story_hashes": ai_ml_hashes,
            }),
        )

    if world_hashes and settings.sqs_world_queue_url:
        sqs.send_message(
            QueueUrl=settings.sqs_world_queue_url,
            MessageBody=json.dumps({
                "briefing_type": "world",
                "run_date": date_str,
                "time_of_day": time_of_day,
                "story_hashes": world_hashes,
            }),
        )

    # 6. Update last-run timestamp
    storage.update_last_run_timestamp(run_time)

    # 7. Mark read if configured
    if settings.mark_as_read:
        all_new_hashes = [s.story_hash for s in new_stories]
        newsblur.mark_stories_as_read(all_new_hashes)

    body = {
        "execution_id": execution_id,
        "ai_ml_count": len(ai_ml_stories),
        "world_count": len(world_stories),
        "skipped_count": len(skip_stories),
        "already_processed": len(already_seen),
    }
    log_structured("INFO", "Triage pipeline complete", **body)
    return {"statusCode": 200, "body": body}


def _route_to_raindrop(stories_with_sub, raindrop, storage, bucket_name):
    """Save stories to Raindrop and store content in DynamoDB. Skips duplicates."""
    for story, sub_bucket in stories_with_sub:
        try:
            if raindrop.check_duplicate(story.story_permalink):
                storage.mark_processed(story.story_hash)
                continue
            tags = [bucket_name, sub_bucket, story.story_feed_title.lower()[:30]]
            result = raindrop.create_bookmark(
                url=story.story_permalink,
                title=story.story_title,
                tags=tags,
                note="",  # note added by summarizer
            )
            raindrop_id = result.get("_id") if result else None
            storage.store_story_content(story.story_hash, {
                "title": story.story_title,
                "url": str(story.story_permalink),
                "content": story.story_content or "",
                "feed_title": story.story_feed_title,
                "bucket": bucket_name,
                "sub_bucket": sub_bucket,
                "newsblur_score": story.newsblur_score,
                "raindrop_id": raindrop_id,
            })
            storage.mark_processed(story.story_hash)
        except RaindropAuthError:
            log_structured("ERROR", "Raindrop auth failed", bucket=bucket_name)
            break
        except Exception as exc:
            log_structured("WARNING", "Failed to route story",
                           hash=story.story_hash, error=str(exc))
            storage.mark_processed(story.story_hash)
```

Note: `storage.mark_processed()` and `storage.mark_processed_batch()` — check if these exist in `storage.py` or add them as thin wrappers around `mark_as_processed`.

**Step 5: Verify GREEN**
```bash
python -m pytest tests/test_triage_handler.py -v
```
Expected: All tests pass.

**Step 6: Commit**
```bash
git add src/handlers/__init__.py src/handlers/triage_handler.py tests/test_triage_handler.py
git commit -m "feat: add Lambda 1 triage handler"
```

---

## Task 7: Lambda 2 — Summarizer Handler

**Goal:** SQS-triggered handler that summarizes stories, updates Raindrop notes, and sends to briefing queue.

**Files:**
- Create: `src/handlers/summarizer_handler.py`
- Create: `tests/test_summarizer_handler.py`

**Step 1: Write failing tests**

```python
# tests/test_summarizer_handler.py
import json
from unittest.mock import MagicMock, patch


def _sqs_event(briefing_type="ai-ml", hashes=("h1", "h2")):
    body = json.dumps({
        "briefing_type": briefing_type,
        "run_date": "2026-02-16",
        "time_of_day": "morning",
        "story_hashes": list(hashes),
    })
    return {"Records": [{"body": body}]}


@patch("src.handlers.summarizer_handler.boto3")
@patch("src.handlers.summarizer_handler.RaindropClient")
@patch("src.handlers.summarizer_handler.BedrockSummarizerClient")
@patch("src.handlers.summarizer_handler.ProcessingStateStorage")
@patch("src.handlers.summarizer_handler.Settings")
def test_summarizes_stories_and_sends_to_briefing_queue(
    mock_settings_cls, mock_storage_cls, mock_summarizer_cls, mock_raindrop_cls, mock_boto3
):
    settings = MagicMock()
    settings.raindrop_token = "tok"
    settings.sqs_briefing_queue_url = "https://sqs/briefing"
    settings.summarizer_aiml_min_score = 6
    settings.summarizer_world_min_score = 5
    mock_settings_cls.return_value = settings

    mock_storage_cls.return_value.get_stories_content.return_value = {
        "h1": {"title": "LLM paper", "url": "https://arxiv.org/1",
               "content": "body", "bucket": "ai-ml", "sub_bucket": "research",
               "raindrop_id": 123, "feed_title": "arXiv"},
    }
    mock_summarizer_cls.return_value.summarize.return_value = MagicMock(
        summary="A great paper.", why_matters="Important.", score=8
    )

    from src.handlers import summarizer_handler
    resp = summarizer_handler.lambda_handler(_sqs_event(hashes=["h1"]), {})

    assert resp["statusCode"] == 200
    assert resp["body"]["summarized"] == 1
    assert resp["body"]["sent_to_briefing"] == 1
    # Raindrop note should be updated
    mock_raindrop_cls.return_value.update_bookmark.assert_called_once()


@patch("src.handlers.summarizer_handler.boto3")
@patch("src.handlers.summarizer_handler.RaindropClient")
@patch("src.handlers.summarizer_handler.BedrockSummarizerClient")
@patch("src.handlers.summarizer_handler.ProcessingStateStorage")
@patch("src.handlers.summarizer_handler.Settings")
def test_low_score_stories_not_sent_to_briefing(
    mock_settings_cls, mock_storage_cls, mock_summarizer_cls, mock_raindrop_cls, mock_boto3
):
    settings = MagicMock()
    settings.raindrop_token = "tok"
    settings.sqs_briefing_queue_url = "https://sqs/briefing"
    settings.summarizer_aiml_min_score = 6
    mock_settings_cls.return_value = settings

    mock_storage_cls.return_value.get_stories_content.return_value = {
        "h1": {"title": "Minor update", "url": "https://example.com",
               "content": "body", "bucket": "ai-ml", "raindrop_id": 123, "feed_title": "Blog"},
    }
    mock_summarizer_cls.return_value.summarize.return_value = MagicMock(
        summary="Minor.", why_matters="Not much.", score=3
    )

    from src.handlers import summarizer_handler
    resp = summarizer_handler.lambda_handler(_sqs_event(hashes=["h1"]), {})

    assert resp["body"]["sent_to_briefing"] == 0
```

**Step 2: Verify RED**
```bash
python -m pytest tests/test_summarizer_handler.py -v --tb=short
```

**Step 3: Implement `src/handlers/summarizer_handler.py`**

```python
"""Lambda 2: Summarize stories, update Raindrop notes, forward to briefing queue."""
import json
import boto3

from src.clients.bedrock_summarizer import BedrockSummarizerClient
from src.clients.raindrop import RaindropClient
from src.config import Settings
from src.services.storage import ProcessingStateStorage
from src.utils import log_structured


def lambda_handler(event, context):
    settings = Settings()
    storage = ProcessingStateStorage(settings.dynamodb_table_name, settings.dynamodb_region)
    summarizer = BedrockSummarizerClient(
        region=settings.bedrock_region,
        model_id=settings.bedrock_summarizer_model_id,
    )
    sqs = boto3.client("sqs", region_name="us-east-1")

    record = event["Records"][0]
    message = json.loads(record["body"])
    briefing_type = message["briefing_type"]
    story_hashes = message["story_hashes"]
    run_date = message["run_date"]
    time_of_day = message["time_of_day"]

    log_structured("INFO", "Summarizer starting",
                   briefing_type=briefing_type, story_count=len(story_hashes))

    # Fetch story content from DynamoDB
    stories_data = storage.get_stories_content(story_hashes)
    min_score = (settings.summarizer_aiml_min_score if briefing_type == "ai-ml"
                 else settings.summarizer_world_min_score)

    raindrop = RaindropClient(token=settings.raindrop_token) if settings.raindrop_token else None

    summarized = 0
    briefing_stories = []

    for story_hash, data in stories_data.items():
        try:
            result = summarizer.summarize(
                title=data["title"],
                content=data.get("content", ""),
                bucket=briefing_type,
            )
            summarized += 1

            # Update Raindrop note with summary
            if raindrop and data.get("raindrop_id"):
                note = f"{result.summary}\n\n**Why it matters:** {result.why_matters}"
                try:
                    raindrop.update_bookmark(raindrop_id=data["raindrop_id"], note=note)
                except Exception as exc:
                    log_structured("WARNING", "Failed to update Raindrop note",
                                   hash=story_hash, error=str(exc))

            if result.score >= min_score:
                briefing_stories.append({
                    "title": data["title"],
                    "url": data["url"],
                    "summary": result.summary,
                    "why_matters": result.why_matters,
                    "score": result.score,
                    "sub_bucket": data.get("sub_bucket", briefing_type),
                    "feed_title": data.get("feed_title", ""),
                })

        except Exception as exc:
            log_structured("WARNING", "Summarization failed",
                           hash=story_hash, error=str(exc))

    log_structured("INFO", "Summarization complete",
                   summarized=summarized, briefing_eligible=len(briefing_stories))

    # Send to briefing queue if enough stories
    sent = 0
    if len(briefing_stories) >= 3 and settings.sqs_briefing_queue_url:
        sqs.send_message(
            QueueUrl=settings.sqs_briefing_queue_url,
            MessageBody=json.dumps({
                "briefing_type": briefing_type,
                "run_date": run_date,
                "time_of_day": time_of_day,
                "stories": briefing_stories,
            }),
        )
        sent = len(briefing_stories)
    else:
        log_structured("INFO", "Not enough stories for briefing, skipping",
                       count=len(briefing_stories))

    body = {"summarized": summarized, "sent_to_briefing": sent, "briefing_type": briefing_type}
    log_structured("INFO", "Summarizer complete", **body)
    return {"statusCode": 200, "body": body}
```

**Step 4: Verify GREEN**
```bash
python -m pytest tests/test_summarizer_handler.py -v
```

**Step 5: Commit**
```bash
git add src/handlers/summarizer_handler.py tests/test_summarizer_handler.py
git commit -m "feat: add Lambda 2 summarizer handler"
```

---

## Task 8: Lambda 3 — Briefing Handler

**Goal:** SQS-triggered handler that synthesizes narrative briefing and posts to Raindrop.

**Files:**
- Create: `src/handlers/briefing_handler.py`
- Create: `tests/test_briefing_handler.py`

**Step 1: Write failing tests**

```python
# tests/test_briefing_handler.py
import json
from unittest.mock import MagicMock, patch


def _sqs_event(briefing_type="ai-ml", stories=None):
    if stories is None:
        stories = [
            {"title": f"Story {i}", "url": f"https://example.com/{i}",
             "summary": "Summary.", "why_matters": "Important.", "score": 8,
             "sub_bucket": "research", "feed_title": "arXiv"}
            for i in range(5)
        ]
    body = json.dumps({
        "briefing_type": briefing_type,
        "run_date": "2026-02-16",
        "time_of_day": "morning",
        "stories": stories,
    })
    return {"Records": [{"body": body}]}


@patch("src.handlers.briefing_handler.RaindropClient")
@patch("src.handlers.briefing_handler.BedrockBriefingClient")
@patch("src.handlers.briefing_handler.Settings")
def test_creates_briefing_bookmark(mock_settings_cls, mock_briefing_cls, mock_raindrop_cls):
    settings = MagicMock()
    settings.raindrop_token = "tok"
    settings.raindrop_briefing_collection_id = 42
    settings.bedrock_region = "us-east-1"
    settings.bedrock_briefing_model_id = "model"
    mock_settings_cls.return_value = settings

    mock_briefing_cls.return_value.synthesize.return_value = "Full briefing text."
    mock_raindrop_cls.return_value.check_duplicate.return_value = False

    from src.handlers import briefing_handler
    resp = briefing_handler.lambda_handler(_sqs_event(), {})

    assert resp["statusCode"] == 200
    assert resp["body"]["briefing_sent"] == 1
    mock_raindrop_cls.return_value.create_bookmark.assert_called_once()

    call_kwargs = mock_raindrop_cls.return_value.create_bookmark.call_args
    url = call_kwargs.kwargs.get("url") or call_kwargs.args[0]
    assert "newsblur.com/briefing/" in url
    assert "ai-ml" in url


@patch("src.handlers.briefing_handler.RaindropClient")
@patch("src.handlers.briefing_handler.BedrockBriefingClient")
@patch("src.handlers.briefing_handler.Settings")
def test_skips_duplicate_briefing(mock_settings_cls, mock_briefing_cls, mock_raindrop_cls):
    settings = MagicMock()
    settings.raindrop_token = "tok"
    settings.raindrop_briefing_collection_id = 42
    mock_settings_cls.return_value = settings

    mock_raindrop_cls.return_value.check_duplicate.return_value = True  # already exists

    from src.handlers import briefing_handler
    resp = briefing_handler.lambda_handler(_sqs_event(), {})

    assert resp["body"]["briefing_sent"] == 0
    mock_briefing_cls.return_value.synthesize.assert_not_called()
```

**Step 2: Verify RED**
```bash
python -m pytest tests/test_briefing_handler.py -v --tb=short
```

**Step 3: Implement `src/handlers/briefing_handler.py`**

```python
"""Lambda 3: Synthesize narrative briefing and post to Raindrop."""
import json
from datetime import datetime, timezone

from src.clients.bedrock_briefing import BedrockBriefingClient, BriefingError
from src.clients.raindrop import RaindropClient, RaindropAuthError
from src.config import Settings
from src.utils import log_structured


def lambda_handler(event, context):
    settings = Settings()

    record = event["Records"][0]
    message = json.loads(record["body"])
    briefing_type = message["briefing_type"]
    run_date = message["run_date"]
    time_of_day = message["time_of_day"]
    stories = message["stories"]

    log_structured("INFO", "Briefing handler starting",
                   briefing_type=briefing_type, story_count=len(stories))

    type_label = "AI/ML" if briefing_type == "ai-ml" else "World"
    time_label = time_of_day.capitalize()
    formatted_date = datetime.strptime(run_date, "%Y-%m-%d").strftime("%b %-d, %Y")
    briefing_title = f"{type_label} {time_label} Briefing \u2014 {formatted_date}"
    briefing_url = f"https://newsblur.com/briefing/{run_date}-{time_of_day}-{briefing_type}"

    raindrop = RaindropClient(
        token=settings.raindrop_token,
        collection_id=settings.raindrop_briefing_collection_id,
    )

    if raindrop.check_duplicate(briefing_url):
        log_structured("INFO", "Briefing already exists, skipping", url=briefing_url)
        return {"statusCode": 200, "body": {"briefing_sent": 0, "reason": "duplicate"}}

    run_hour_utc = 11 if time_of_day == "morning" else 23

    try:
        briefing_client = BedrockBriefingClient(
            region=settings.bedrock_region,
            model_id=settings.bedrock_briefing_model_id,
        )
        briefing_text = briefing_client.synthesize(stories, run_hour_utc, briefing_type)

        raindrop.create_bookmark(
            url=briefing_url,
            title=briefing_title,
            tags=["briefing", "ai-generated", time_of_day, briefing_type],
            note=briefing_text,
        )
        log_structured("INFO", "Briefing created", title=briefing_title)
        return {"statusCode": 200, "body": {"briefing_sent": 1, "title": briefing_title}}

    except (BriefingError, RaindropAuthError) as exc:
        log_structured("ERROR", "Briefing failed", error=str(exc))
        return {"statusCode": 500, "body": {"briefing_sent": 0, "error": str(exc)}}
```

**Step 4: Verify GREEN**
```bash
python -m pytest tests/test_briefing_handler.py -v
```

**Step 5: Commit**
```bash
git add src/handlers/briefing_handler.py tests/test_briefing_handler.py
git commit -m "feat: add Lambda 3 briefing handler"
```

---

## Task 9: Terraform Infrastructure

**Goal:** Add SQS queues, two new Lambda functions, update IAM permissions, add SSM parameters, update EventBridge to target triage Lambda.

**Files:**
- Create: `terraform/sqs.tf`
- Modify: `terraform/lambda.tf`
- Modify: `terraform/iam.tf`

**Step 1: Create `terraform/sqs.tf`**

```hcl
resource "aws_sqs_queue" "ai_ml" {
  name                       = "research-agent-ai-ml"
  visibility_timeout_seconds = 900
  message_retention_seconds  = 86400  # 1 day

  tags = { Project = "research-agent" }
}

resource "aws_sqs_queue" "world" {
  name                       = "research-agent-world"
  visibility_timeout_seconds = 900
  message_retention_seconds  = 86400

  tags = { Project = "research-agent" }
}

resource "aws_sqs_queue" "briefing" {
  name                       = "research-agent-briefing"
  visibility_timeout_seconds = 300
  message_retention_seconds  = 86400

  tags = { Project = "research-agent" }
}

# Allow Lambda 1 to send to ai-ml and world queues
resource "aws_sqs_queue_policy" "ai_ml" {
  queue_url = aws_sqs_queue.ai_ml.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = aws_iam_role.lambda.arn }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.ai_ml.arn
    }]
  })
}

resource "aws_sqs_queue_policy" "world" {
  queue_url = aws_sqs_queue.world.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = aws_iam_role.lambda.arn }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.world.arn
    }]
  })
}

resource "aws_sqs_queue_policy" "briefing" {
  queue_url = aws_sqs_queue.briefing.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = aws_iam_role.lambda.arn }
      Action    = "sqs:SendMessage"
      Resource  = aws_sqs_queue.briefing.arn
    }]
  })
}

# SQS → Lambda 2 trigger
resource "aws_lambda_event_source_mapping" "summarizer_ai_ml" {
  event_source_arn = aws_sqs_queue.ai_ml.arn
  function_name    = aws_lambda_function.summarizer.arn
  batch_size       = 1
}

resource "aws_lambda_event_source_mapping" "summarizer_world" {
  event_source_arn = aws_sqs_queue.world.arn
  function_name    = aws_lambda_function.summarizer.arn
  batch_size       = 1
}

# SQS → Lambda 3 trigger
resource "aws_lambda_event_source_mapping" "briefing" {
  event_source_arn = aws_sqs_queue.briefing.arn
  function_name    = aws_lambda_function.briefing.arn
  batch_size       = 1
}
```

**Step 2: Add new SSM parameters** (run manually before `terraform apply`):

```bash
# Get collection IDs from Raindrop app URL when clicking each collection

aws ssm put-parameter \
  --name "/prod/ResearchAgent/Raindrop_AiMl_Collection_Id" \
  --value "<your-aiml-collection-id>" \
  --type String --profile seth-dev --region us-east-1

aws ssm put-parameter \
  --name "/prod/ResearchAgent/Raindrop_World_Collection_Id" \
  --value "<your-world-collection-id>" \
  --type String --profile seth-dev --region us-east-1
```

**Step 3: Update `terraform/lambda.tf`** — replace the single `classifier` Lambda with three Lambdas:

- Rename `aws_lambda_function.classifier` → `aws_lambda_function.triage`
  - Handler: `src.handlers.triage_handler.lambda_handler`
  - Timeout: 60s
  - Add SQS queue URLs and new collection IDs as env vars
  - Remove old classification env vars

- Add `aws_lambda_function.summarizer`
  - Handler: `src.handlers.summarizer_handler.lambda_handler`
  - Timeout: 900s
  - Env vars: Raindrop token, DynamoDB, Bedrock, SQS briefing queue URL

- Add `aws_lambda_function.briefing`
  - Handler: `src.handlers.briefing_handler.lambda_handler`
  - Timeout: 300s
  - Env vars: Raindrop token + briefing collection ID, Bedrock

- Update EventBridge target to point to `aws_lambda_function.triage`

**Step 4: Update `terraform/iam.tf`** — add SQS permissions to Lambda role:

```hcl
# Add to existing policy or create new one:
{
  "Effect": "Allow",
  "Action": [
    "sqs:SendMessage",
    "sqs:ReceiveMessage",
    "sqs:DeleteMessage",
    "sqs:GetQueueAttributes"
  ],
  "Resource": [
    aws_sqs_queue.ai_ml.arn,
    aws_sqs_queue.world.arn,
    aws_sqs_queue.briefing.arn
  ]
}
```

**Step 5: Plan and apply**
```bash
cd terraform
terraform plan   # review carefully
terraform apply
```

**Step 6: Commit**
```bash
git add terraform/
git commit -m "feat: add SQS queues and three-Lambda infrastructure for Phase 3"
```

---

## Task 10: Cleanup — Remove Phase 2 Code

**Goal:** Delete old classification pipeline, update deploy.sh, update README.

**Files to delete:**
- `src/clients/bedrock.py`
- `src/models/classification.py`
- `src/services/classifier.py`
- `src/lambda_handler.py`
- `tests/test_classifier.py`
- `tests/test_classification_model.py`
- `tests/test_bedrock_classifier.py`
- `tests/test_lambda_briefing.py`
- `tests/test_lambda_raindrop.py`

**Files to update:**
- `tests/conftest.py` — remove `sample_bedrock_response` fixture (no longer needed)
- `deploy.sh` — no code changes needed, just verify it still works
- `README.md` — update for Phase 3 architecture

**Steps:**

```bash
# Delete old files
rm src/clients/bedrock.py src/models/classification.py src/services/classifier.py src/lambda_handler.py
rm tests/test_classifier.py tests/test_classification_model.py tests/test_bedrock_classifier.py
rm tests/test_lambda_briefing.py tests/test_lambda_raindrop.py

# Run full suite to confirm nothing broken
python -m pytest tests/ -v
```

Expected: All remaining tests pass. If anything imports the deleted modules, fix the imports now.

```bash
git add -A
git commit -m "chore: remove Phase 2 classification pipeline, clean up old tests"
```

Update `README.md` to reflect Phase 3 architecture (three Lambdas, SQS, triage, dual briefings).

```bash
git add README.md
git commit -m "docs: update README for Phase 3 multi-lambda architecture"
```

---

## Final Verification

```bash
# Full test suite
python -m pytest tests/ -v

# Deploy
./deploy.sh
cd terraform && terraform apply

# Manual invoke of triage Lambda
aws lambda invoke \
  --function-name research-agent-triage \
  --payload '{}' \
  --profile seth-dev \
  --region us-east-1 \
  --cli-read-timeout 120 \
  /tmp/triage-output.json && cat /tmp/triage-output.json

# Monitor logs
aws logs tail /aws/lambda/research-agent-triage --profile seth-dev --region us-east-1
aws logs tail /aws/lambda/research-agent-summarizer --profile seth-dev --region us-east-1
aws logs tail /aws/lambda/research-agent-briefing --profile seth-dev --region us-east-1
```

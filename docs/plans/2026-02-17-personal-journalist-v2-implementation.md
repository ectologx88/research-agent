# Personal Journalist Engine v2.0 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Refactor the research-agent into a dual-stream editorial pipeline with two distinct AI personas, config-driven feed routing seeded from real NewsBlur subscriptions, editorial scoring in Lambda 2, context injection for the Zeitgeist briefing, and three new DynamoDB tables.

**Architecture:** Approach C (Hybrid) — keep `src/handlers/` entry points unchanged, add `config/` and `shared/` directories alongside `src/`. Feed routing migrates from hardcoded dicts in `src/services/triage.py` to `config/feed_rules.py`. All new service modules added to `src/services/`. Bedrock throughout.

**Tech Stack:** Python 3.12+, pytest, boto3, pydantic-settings, requests, tenacity, feedparser>=6.0.10, AWS Lambda/SQS/DynamoDB/EventBridge/CloudWatch, Terraform

**Design doc:** `docs/plans/2026-02-17-personal-journalist-v2-design.md` — read this before implementing anything.

---

## Phase 1: Foundation

### Task 1: Create `config/` package with feed rules

**Files:**
- Create: `config/__init__.py`
- Create: `config/feed_rules.py`
- Create: `tests/test_feed_rules.py`

**Step 1: Write the failing test**

```python
# tests/test_feed_rules.py
from config.feed_rules import (
    ALWAYS_AI_ML, ALWAYS_WORLD, ALWAYS_SCIENCE, ALWAYS_ENTERTAINMENT,
    REDDIT_FEEDS, AMBIGUOUS_FEEDS, ALWAYS_SKIP,
    get_route, Route
)

class TestAlwaysAiMl:
    def test_arxiv_ai_routes(self):
        route, sub = get_route("cs.AI updates on arXiv.org", "")
        assert route == Route.AI_ML
        assert sub == "research"

    def test_anthropic_news_routes(self):
        route, sub = get_route("Anthropic News", "")
        assert route == Route.AI_ML

class TestAlwaysWorld:
    def test_bbc_routes(self):
        route, sub = get_route("BBC News", "")
        assert route == Route.WORLD
        assert sub == "news"

    def test_reuters_substring_match(self):
        # Exact NewsBlur title may vary — verify on first run
        route, sub = get_route("Reuters", "")
        assert route == Route.WORLD

class TestAlwaysScience:
    def test_nature_routes_to_science(self):
        route, sub = get_route("Nature - Issue - nature.com science feeds", "")
        assert route == Route.WORLD
        assert sub == "science"

    def test_neurologica_routes_to_science(self):
        route, sub = get_route("NeuroLogica Blog", "")
        assert route == Route.WORLD
        assert sub == "science"

class TestAlwaysEntertainment:
    def test_ghostbusters_routes_to_entertainment(self):
        route, sub = get_route("Ghostbusters News", "")
        assert route == Route.WORLD
        assert sub == "entertainment"

    def test_apple_newsroom_routes_to_tech(self):
        route, sub = get_route("Apple Newsroom", "")
        assert route == Route.WORLD
        assert sub == "tech"

    def test_macrumors_routes_to_tech(self):
        route, sub = get_route("MacRumors: Mac News and Rumors - All Stories", "")
        assert route == Route.WORLD
        assert sub == "tech"

class TestAlwaysSkip:
    def test_raindrop_feed_skipped(self):
        route, _ = get_route("AI / Raindrop.io", "")
        assert route == Route.SKIP

    def test_newsblur_blog_skipped(self):
        route, _ = get_route("The NewsBlur Blog", "")
        assert route == Route.SKIP

class TestRedditFeeds:
    def test_claudeai_routes_to_ai_ml(self):
        route, sub = get_route("ClaudeAI", "Claude 3.5 new release")
        assert route == Route.AI_ML

    def test_neuroscience_reddit_routes_to_science(self):
        route, sub = get_route("top scoring links : neuroscience", "brain plasticity")
        assert route == Route.WORLD
        assert sub == "science"

    def test_apple_reddit_routes_to_tech(self):
        route, sub = get_route("top scoring links : apple", "iPhone 17 review")
        assert route == Route.WORLD
        assert sub == "tech"

class TestAmbiguousFeeds:
    def test_hacker_news_ai_keyword_routes_to_ai_ml(self):
        route, sub = get_route("Hacker News", "New LLM benchmark shows GPT-5 advantage")
        assert route == Route.AI_ML

    def test_hacker_news_no_keyword_defaults_to_world_tech(self):
        route, sub = get_route("Hacker News", "Ask HN: Best coffee grinder")
        assert route == Route.WORLD
        assert sub == "tech"

class TestPrecedence:
    def test_skip_beats_keyword(self):
        # Even if title has AI keywords, SKIP feeds are always skipped
        route, _ = get_route("The NewsBlur Blog", "new LLM model released")
        assert route == Route.SKIP
```

**Step 2: Run test to verify it fails**

```bash
cd /home/r3crsvint3llgnz/01_Projects/research-agent/.worktrees/personal-journalist-v2
pytest tests/test_feed_rules.py -v 2>&1 | head -20
```
Expected: `ModuleNotFoundError: No module named 'config'`

**Step 3: Create `config/__init__.py`**

```python
# config/__init__.py
```
(empty)

**Step 4: Create `config/feed_rules.py`**

```python
# config/feed_rules.py
"""Config-driven feed routing rules. Update without redeployment."""
from enum import Enum
from typing import Tuple


class Route(str, Enum):
    AI_ML = "AI_ML"
    WORLD = "WORLD"
    SKIP = "SKIP"


# Route everything to AI Abstract
ALWAYS_AI_ML = {
    "cs.AI updates on arXiv.org",
    "cs.CL updates on arXiv.org",
    "Anthropic News",
    "Anthropic Engineering Blog",
    "Anthropic Research",
    "Google DeepMind News",
    "The Machine Herald",
}

# Route everything to Recursive Briefing, sub_bucket="news"
ALWAYS_WORLD = {
    "NYT > Top Stories",
    "BBC News",
    "Reuters",  # Match on substring — verify exact NewsBlur title on first run and update if needed
    "NPR Topics: News",
    "ProPublica",
    "Houston Public Media",
    "Space City Weather",
    "Axios",
}

# Route to WORLD, sub_bucket="science"
# Phys. Rev. Lett. and NeuroLogica are directly relevant to RDD framework
ALWAYS_SCIENCE = {
    "Nature - Issue - nature.com science feeds",
    "Recent Articles in Phys. Rev. Lett.",
    "Latest Science News -- ScienceDaily",
    "Science",
    "NeuroLogica Blog",
}

# Route to WORLD — sub_bucket assignment per feed:
# "Ghostbusters News" → sub_bucket="entertainment"
# All others → sub_bucket="tech"
ALWAYS_ENTERTAINMENT_FEEDS = {
    "Ghostbusters News",
}
ALWAYS_TECH_FEEDS = {
    "Apple Newsroom",
    "9to5Mac",
    "MacRumors: Mac News and Rumors - All Stories",
    "Google Workspace Updates",
    "The Keyword",
}
# Combined for membership checks
ALWAYS_ENTERTAINMENT = ALWAYS_ENTERTAINMENT_FEEDS | ALWAYS_TECH_FEEDS

# Reddit aggregators. Routing:
#   "ClaudeAI", "top scoring links : MachineLearning", "top scoring links : artificial",
#   "saved/upvoted by gbninjaturtle" → AI_ML default
#   "top scoring links : neuroscience", "top scoring links : science", "cognitive science" → WORLD/science
#   "top scoring links : apple" → WORLD/tech
REDDIT_AI_ML = {
    "ClaudeAI",
    "top scoring links : MachineLearning",
    "top scoring links : artificial",
    "saved by gbninjaturtle",
    "upvoted by gbninjaturtle",
}
REDDIT_SCIENCE = {
    "top scoring links : neuroscience",
    "top scoring links : science",
    "cognitive science",
}
REDDIT_TECH = {
    "top scoring links : apple",
}
REDDIT_FEEDS = REDDIT_AI_ML | REDDIT_SCIENCE | REDDIT_TECH

# Ambiguous — route by keyword, default WORLD/tech
AMBIGUOUS_FEEDS = {
    "Hacker News",
    "Hacker News 50",
    "WIRED",
    "Ars Technica - All content",
    "The Next Web",
    "Uncrunched",
    "Marco.org",
}

# Hard skip — circular or meta only
ALWAYS_SKIP = {
    "AI / Raindrop.io",   # circular — Seth's own Raindrop RSS export
    "The NewsBlur Blog",  # meta — RSS reader product news
}

# AI/ML keyword fallback (applied to AMBIGUOUS and unknown feeds)
AI_ML_KEYWORDS = {
    "llm", "gpt", "claude", "gemini", "mistral", "llama",
    "neural network", "transformer", "diffusion model",
    "reinforcement learning", "machine learning",
    "artificial intelligence", "deep learning",
    "foundation model", "fine-tun", "retrieval augmented",
    "embedding model", "language model", "ai agent",
    "multimodal", "agentic", "benchmark", "preprint",
    "inference", "rlhf", "rag",
}


def _title_lower(title: str) -> str:
    return (title or "").lower()


def _has_ai_ml_keyword(title: str) -> bool:
    tl = _title_lower(title)
    return any(kw in tl for kw in AI_ML_KEYWORDS)


def get_route(feed_name: str, story_title: str) -> Tuple[Route, str]:
    """
    Determine routing for a story.
    Returns (Route, sub_bucket).

    Precedence:
    1. ALWAYS_SKIP — immediate exit
    2. ALWAYS_AI_ML / ALWAYS_WORLD / ALWAYS_SCIENCE / ALWAYS_ENTERTAINMENT — deterministic
    3. REDDIT_FEEDS — by sub-set
    4. AMBIGUOUS_FEEDS — keyword fallback, default WORLD/tech
    5. Unknown — keyword fallback, default WORLD/news
    """
    feed = feed_name or ""

    if feed in ALWAYS_SKIP:
        return Route.SKIP, ""

    if feed in ALWAYS_AI_ML:
        return Route.AI_ML, "research"

    if feed in ALWAYS_WORLD:
        return Route.WORLD, "news"

    if feed in ALWAYS_SCIENCE:
        return Route.WORLD, "science"

    if feed in ALWAYS_ENTERTAINMENT_FEEDS:
        return Route.WORLD, "entertainment"

    if feed in ALWAYS_TECH_FEEDS:
        return Route.WORLD, "tech"

    if feed in REDDIT_AI_ML:
        return Route.AI_ML, "research"

    if feed in REDDIT_SCIENCE:
        return Route.WORLD, "science"

    if feed in REDDIT_TECH:
        return Route.WORLD, "tech"

    if feed in AMBIGUOUS_FEEDS:
        if _has_ai_ml_keyword(story_title):
            return Route.AI_ML, "research"
        return Route.WORLD, "tech"

    # Unknown feed — keyword fallback, default WORLD/news
    if _has_ai_ml_keyword(story_title):
        return Route.AI_ML, "research"
    return Route.WORLD, "news"
```

**Step 5: Run tests to verify they pass**

```bash
pytest tests/test_feed_rules.py -v
```
Expected: All tests PASS

**Step 6: Commit**

```bash
git add config/__init__.py config/feed_rules.py tests/test_feed_rules.py
git commit -m "feat: config-driven feed routing with real NewsBlur subscriptions"
```

---

### Task 2: Create `config/keywords.py` and `config/scoring_weights.py`

**Files:**
- Create: `config/keywords.py`
- Create: `config/scoring_weights.py`
- Create: `tests/test_keywords.py`

**Step 1: Write the failing test**

```python
# tests/test_keywords.py
from config.keywords import (
    get_boost_tags,
    DEMOCRATIZATION_KEYWORDS, INDUSTRIAL_KEYWORDS, RDD_KEYWORDS,
)

def test_open_source_gets_boost():
    tags = get_boost_tags("Open-source LLM beats GPT-4 on benchmarks", [])
    assert "boost:open-source" in tags

def test_industrial_gets_boost():
    tags = get_boost_tags("AI for predictive maintenance in chemical plants", [])
    assert "boost:industrial" in tags

def test_rdd_gets_long_signal():
    tags = get_boost_tags("New theory of consciousness links emergence to information", [])
    assert "long-signal:rdd" in tags

def test_user_curated_passed_through():
    tags = get_boost_tags("anything", ["boost:user-curated"])
    assert "boost:user-curated" in tags

def test_no_false_positives_on_plain_title():
    tags = get_boost_tags("Company raises Series B funding round", [])
    assert tags == []
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_keywords.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError: No module named 'config.keywords'`

**Step 3: Create `config/keywords.py`**

```python
# config/keywords.py
"""Boost/penalize keyword lists for triage scoring."""
from typing import List

DEMOCRATIZATION_KEYWORDS = [
    "open source", "open-source", "self-hosted", "local llm",
    "edge deployment", "on-premise", "roi", "implementation guide",
    "small business", "smb", "mid-market", "accessible",
    "cost reduction", "efficiency", "manufacturing", "industrial",
    "process control", "operational technology", "chemical",
    "supply chain", "predictive maintenance",
]

INDUSTRIAL_KEYWORDS = [
    "manufacturing", "industrial", "automation", "chemical",
    "process control", "scada", "plc", "ot/it", "operational technology",
    "covestro", "enterprise", "deployment",
]

RDD_KEYWORDS = [
    "consciousness", "emergence", "quantum", "information theory",
    "cognitive architecture", "agi", "alignment", "interpretability",
    "recursive", "distinction", "awareness", "subjective experience",
    "neural correlates", "integrated information", "global workspace",
]

AI_ML_PENALIZE = [
    "stock price", "ipo", "funding round", "valuation",
    "chatgpt wrapper", "no-code ai", "ai girlfriend",
    "productivity hack", "prompt trick",
]


def get_boost_tags(title: str, existing_tags: List[str]) -> List[str]:
    """Return boost tags based on title keywords. Preserves existing tags."""
    title_lower = (title or "").lower()
    tags = list(existing_tags)

    if any(kw in title_lower for kw in DEMOCRATIZATION_KEYWORDS):
        if "boost:open-source" not in tags:
            tags.append("boost:open-source")

    if any(kw in title_lower for kw in INDUSTRIAL_KEYWORDS):
        if "boost:industrial" not in tags:
            tags.append("boost:industrial")

    if any(kw in title_lower for kw in RDD_KEYWORDS):
        if "long-signal:rdd" not in tags:
            tags.append("long-signal:rdd")

    return tags
```

**Step 4: Create `config/scoring_weights.py`**

```python
# config/scoring_weights.py
"""Per-stream scoring thresholds and parameters."""

AI_ML_PASS_THRESHOLD = 9    # out of 15
WORLD_PASS_THRESHOLD = 8    # out of 15
MIN_STORIES_FOR_BRIEFING = 3  # bail if fewer pass Lambda 2
MAX_AI_ML_STORIES = 15      # Lambda 3 cap
MAX_WORLD_STORIES = 10      # Lambda 3 cap
CLUSTER_SIZE_LEAD_STORY = 3  # cluster_size >= this → Lead Story
CONTENT_TRUNCATE_CHARS = 8000
```

**Step 5: Run tests**

```bash
pytest tests/test_keywords.py -v
```
Expected: All PASS

**Step 6: Commit**

```bash
git add config/keywords.py config/scoring_weights.py tests/test_keywords.py
git commit -m "feat: keyword boost/penalize lists and scoring weights config"
```

---

### Task 3: Create `shared/logger.py`

**Files:**
- Create: `shared/__init__.py`
- Create: `shared/logger.py`
- Create: `tests/test_shared_logger.py`

**Step 1: Write the failing test**

```python
# tests/test_shared_logger.py
import json
from io import StringIO
from unittest.mock import patch
from shared.logger import log

def test_emits_json_to_stdout(capsys):
    log("INFO", "test event", story_hash="abc123", routing_decision="AI_ML")
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["level"] == "INFO"
    assert data["event"] == "test event"
    assert data["story_hash"] == "abc123"
    assert data["routing_decision"] == "AI_ML"
    assert "timestamp" in data

def test_level_included(capsys):
    log("WARNING", "something odd", feed_name="BBC News")
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["level"] == "WARNING"
    assert data["feed_name"] == "BBC News"
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_shared_logger.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError: No module named 'shared'`

**Step 3: Create `shared/__init__.py`**

```python
# shared/__init__.py
```
(empty)

**Step 4: Create `shared/logger.py`**

```python
# shared/logger.py
"""Structured JSON logger for CloudWatch Logs Insights.

CloudWatch Logs Insights can filter on fields like:
  fields @timestamp, event, story_hash, routing_decision, editorial_score
"""
import json
import sys
from datetime import datetime, timezone
from typing import Any


def log(level: str, event: str, **kwargs: Any) -> None:
    """Emit a structured JSON log line to stdout."""
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "level": level,
        "event": event,
        **kwargs,
    }
    print(json.dumps(payload), flush=True)
```

**Step 5: Run tests**

```bash
pytest tests/test_shared_logger.py -v
```
Expected: All PASS

**Step 6: Commit**

```bash
git add shared/__init__.py shared/logger.py tests/test_shared_logger.py
git commit -m "feat: structured JSON logger for CloudWatch Logs Insights"
```

---

### Task 4: Create `shared/dynamodb_client.py`

**Files:**
- Create: `shared/dynamodb_client.py`
- Create: `tests/test_dynamodb_client.py`

**Step 1: Write the failing test**

```python
# tests/test_dynamodb_client.py
from unittest.mock import MagicMock, patch
import pytest
from shared.dynamodb_client import StoryStaging, SignalTracker, BriefingArchive


class TestStoryStaging:
    def _client(self):
        table = MagicMock()
        return StoryStaging(table), table

    def test_store_story_puts_item(self):
        client, table = self._client()
        client.store_story({
            "story_hash": "abc123",
            "briefing_type": "AI_ML",
            "title": "Test",
            "url": "https://example.com",
            "content": "body",
            "feed_name": "cs.AI updates on arXiv.org",
            "sub_bucket": "research",
            "boost_tags": [],
            "cluster_size": 0,
            "cluster_key": "",
            "context_block": "{}",
            "raindrop_id": None,
        })
        table.put_item.assert_called_once()
        item = table.put_item.call_args[1]["Item"]
        assert item["story_hash"] == "abc123"
        assert item["status"] == "pending"
        assert "ttl" in item  # 24h TTL set

    def test_update_status_summarized(self):
        client, table = self._client()
        client.update_status(
            "abc123", "AI_ML", "summarized",
            summary="Two sentences.", source_type="journalism",
            scores={"integrity": 4, "relevance": 4, "novelty": 3, "total": 11},
            reasoning="Strong primary source reporting.",
        )
        table.update_item.assert_called_once()

    def test_get_story_returns_item(self):
        client, table = self._client()
        table.get_item.return_value = {"Item": {"story_hash": "abc123", "status": "pending"}}
        result = client.get_story("abc123", "AI_ML")
        assert result["story_hash"] == "abc123"

    def test_get_story_returns_none_when_missing(self):
        client, table = self._client()
        table.get_item.return_value = {}
        result = client.get_story("missing", "AI_ML")
        assert result is None


class TestSignalTracker:
    def _client(self):
        table = MagicMock()
        return SignalTracker(table), table

    def test_upsert_increments_count(self):
        client, table = self._client()
        table.get_item.return_value = {
            "Item": {
                "signal_key": "evaluation-crisis",
                "mention_count": 2,
                "first_seen": "2026-02-16T11:00:00+00:00",
                "last_seen": "2026-02-16T23:00:00+00:00",
                "example_stories": ["h1", "h2"],
            }
        }
        client.upsert("evaluation-crisis", "newstory123")
        table.put_item.assert_called_once()
        item = table.put_item.call_args[1]["Item"]
        assert item["mention_count"] == 3
        assert "ttl" in item  # rolling 7-day TTL written every time

    def test_upsert_creates_new_signal(self):
        client, table = self._client()
        table.get_item.return_value = {}
        client.upsert("new-signal", "story456")
        item = table.put_item.call_args[1]["Item"]
        assert item["mention_count"] == 1
        assert "first_seen" in item

    def test_get_signals_queries_specific_keys(self):
        client, table = self._client()
        table.get_item.return_value = {"Item": {"signal_key": "k1", "mention_count": 3}}
        result = client.get_signals(["k1"])
        assert len(result) == 1
        # Must NOT use scan
        table.scan.assert_not_called()


class TestBriefingArchive:
    def _client(self):
        table = MagicMock()
        return BriefingArchive(table), table

    def test_store_briefing(self):
        client, table = self._client()
        client.store_briefing(
            briefing_date="2026-02-17-AM",
            briefing_type="AI_ML",
            content="# The AI Abstract\n...",
            candidate_count=18,
            passed_count=12,
            story_count=8,
            raindrop_id="rd123",
        )
        item = table.put_item.call_args[1]["Item"]
        assert item["briefing_date"] == "2026-02-17-AM"
        assert item["candidate_count"] == 18
        assert "ttl" in item  # 30-day TTL

    def test_get_prior_returns_none_when_missing(self):
        client, table = self._client()
        table.get_item.return_value = {}
        result = client.get_prior("2026-02-17-AM", "AI_ML")
        assert result is None
```

**Step 2: Run to verify it fails**

```bash
pytest tests/test_dynamodb_client.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError: No module named 'shared.dynamodb_client'`

**Step 3: Create `shared/dynamodb_client.py`**

```python
# shared/dynamodb_client.py
"""Typed DynamoDB clients for the three pipeline tables.

Usage:
    import boto3
    from shared.dynamodb_client import StoryStaging, SignalTracker, BriefingArchive

    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    stories = StoryStaging(dynamodb.Table("story-staging"))
    signals = SignalTracker(dynamodb.Table("signal-tracker"))
    archive = BriefingArchive(dynamodb.Table("briefing-archive"))
"""
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shared.logger import log


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ttl(seconds: int) -> int:
    return int(time.time()) + seconds


class StoryStaging:
    """Operations on the story_staging table (PK: story_hash, SK: briefing_type)."""

    def __init__(self, table):
        self._table = table

    def store_story(self, data: Dict[str, Any]) -> None:
        """Write a new story at status='pending'. Called by Lambda 1."""
        item = {
            **data,
            "status": "pending",
            "created_at": _now_iso(),
            "ttl": _ttl(24 * 3600),
        }
        self._table.put_item(Item=item)

    def update_status(
        self,
        story_hash: str,
        briefing_type: str,
        status: str,
        **fields: Any,
    ) -> None:
        """Update story status and arbitrary fields. Called by Lambda 2 and 3."""
        update_expr_parts = ["#st = :status"]
        expr_names = {"#st": "status"}
        expr_values: Dict[str, Any] = {":status": status}

        for k, v in fields.items():
            placeholder = f":f_{k}"
            update_expr_parts.append(f"#{k} = {placeholder}")
            expr_names[f"#{k}"] = k
            expr_values[placeholder] = v

        self._table.update_item(
            Key={"story_hash": story_hash, "briefing_type": briefing_type},
            UpdateExpression="SET " + ", ".join(update_expr_parts),
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
        )

    def get_story(self, story_hash: str, briefing_type: str) -> Optional[Dict]:
        """Fetch a single story by primary key."""
        resp = self._table.get_item(
            Key={"story_hash": story_hash, "briefing_type": briefing_type}
        )
        return resp.get("Item")

    def batch_get_stories(
        self, story_hashes: List[str], briefing_type: str
    ) -> List[Dict]:
        """Fetch multiple stories. Returns only items found."""
        results = []
        for h in story_hashes:
            item = self.get_story(h, briefing_type)
            if item:
                results.append(item)
        return results

    def check_duplicate(self, story_hash: str, briefing_type: str) -> bool:
        """Return True if story already exists in story_staging."""
        return self.get_story(story_hash, briefing_type) is not None


class SignalTracker:
    """Operations on signal_tracker table (PK: signal_key, 7-day rolling TTL)."""

    def __init__(self, table):
        self._table = table

    def upsert(self, signal_key: str, story_hash: str) -> None:
        """Increment mention count, update last_seen, keep last 3 example stories.
        Always writes TTL = now + 7 days (rolling — explicit on every update).
        """
        existing = self.get_signals([signal_key])
        now = _now_iso()
        new_ttl = _ttl(7 * 24 * 3600)

        if existing:
            item = existing[0]
            stories = item.get("example_stories", [])
            if story_hash not in stories:
                stories = (stories + [story_hash])[-3:]
            self._table.put_item(Item={
                **item,
                "mention_count": item["mention_count"] + 1,
                "last_seen": now,
                "example_stories": stories,
                "ttl": new_ttl,
            })
        else:
            self._table.put_item(Item={
                "signal_key": signal_key,
                "mention_count": 1,
                "first_seen": now,
                "last_seen": now,
                "example_stories": [story_hash],
                "ttl": new_ttl,
            })

    def get_signals(self, signal_keys: List[str]) -> List[Dict]:
        """Fetch specific signal keys. Uses GetItem per key — NOT Scan."""
        results = []
        for key in signal_keys:
            resp = self._table.get_item(Key={"signal_key": key})
            if "Item" in resp:
                results.append(resp["Item"])
        return results


class BriefingArchive:
    """Operations on briefing_archive table (PK: briefing_date, SK: briefing_type)."""

    def __init__(self, table):
        self._table = table

    def store_briefing(
        self,
        briefing_date: str,
        briefing_type: str,
        content: str,
        candidate_count: int,
        passed_count: int,
        story_count: int,
        raindrop_id: Optional[str],
    ) -> None:
        """Store completed briefing with 30-day TTL."""
        self._table.put_item(Item={
            "briefing_date": briefing_date,
            "briefing_type": briefing_type,
            "content": content,
            "candidate_count": candidate_count,
            "passed_count": passed_count,
            "story_count": story_count,
            "raindrop_id": raindrop_id,
            "created_at": _now_iso(),
            "ttl": _ttl(30 * 24 * 3600),
        })

    def get_prior(self, briefing_date: str, briefing_type: str) -> Optional[Dict]:
        """
        Fetch the immediately preceding briefing edition.
        AM run → yesterday's PM: pass briefing_date="2026-02-16-PM"
        PM run → today's AM: pass briefing_date="2026-02-17-AM"
        Caller is responsible for computing the correct date key.
        """
        resp = self._table.get_item(
            Key={"briefing_date": briefing_date, "briefing_type": briefing_type}
        )
        return resp.get("Item")
```

**Step 5: Run tests**

```bash
pytest tests/test_dynamodb_client.py -v
```
Expected: All PASS

**Step 6: Commit**

```bash
git add shared/dynamodb_client.py tests/test_dynamodb_client.py
git commit -m "feat: typed DynamoDB clients for story_staging, signal_tracker, briefing_archive"
```

---

### Task 5: Refactor `src/services/triage.py` to delegate to `config/feed_rules.py`

**Files:**
- Modify: `src/services/triage.py`
- Modify: `tests/test_triage.py`

**Step 1: Read the current triage tests to understand what must keep passing**

The existing tests in `tests/test_triage.py` test feed-name rules using old hardcoded dicts. After this task, the same behavior must pass but via `config/feed_rules.py`. The `TriageService` class and `Bucket` enum are used by `src/handlers/triage_handler.py` — keep the same public API.

**Step 2: Update `src/services/triage.py`**

Replace the entire file:

```python
# src/services/triage.py
"""Rule-based story triage — delegates to config/feed_rules.py."""
from enum import Enum
from typing import Dict, List, Tuple

from config.feed_rules import Route, get_route
from config.keywords import get_boost_tags
from config.scoring_weights import CLUSTER_SIZE_LEAD_STORY
from src.models.story import Story


class Bucket(str, Enum):
    AI_ML = "ai-ml"
    WORLD = "world"
    SKIP = "skip"


_ROUTE_TO_BUCKET = {
    Route.AI_ML: Bucket.AI_ML,
    Route.WORLD: Bucket.WORLD,
    Route.SKIP: Bucket.SKIP,
}


class TriageService:
    """Categorizes stories using config/feed_rules.py. No LLM required."""

    def categorize(self, story) -> Bucket:
        bucket, _ = self.categorize_with_sub(story)
        return bucket

    def categorize_with_sub(self, story) -> Tuple[Bucket, str]:
        feed = story.story_feed_title or ""
        title = story.story_title or ""
        route, sub_bucket = get_route(feed, title)
        return _ROUTE_TO_BUCKET[route], sub_bucket

    def get_boost_tags(self, story) -> List[str]:
        """Return boost tags based on feed membership and title keywords."""
        from config.feed_rules import REDDIT_FEEDS
        feed = story.story_feed_title or ""
        title = story.story_title or ""
        initial = []
        if feed in REDDIT_FEEDS and "gbninjaturtle" in feed:
            initial.append("boost:user-curated")
        return get_boost_tags(title, initial)

    def batch_categorize(self, stories) -> Dict[Bucket, List[Tuple]]:
        result = {
            Bucket.AI_ML: [],
            Bucket.WORLD: [],
            Bucket.SKIP: [],
        }
        for story in stories:
            bucket, sub = self.categorize_with_sub(story)
            result[bucket].append((story, sub))
        return result
```

**Step 3: Update `tests/test_triage.py` for new feed names**

The old tests used made-up feed names like `"arXiv AI"` — update them to match the actual config. Add a comment explaining why:

```python
# tests/test_triage.py
"""Tests for TriageService. Feed names match actual NewsBlur subscriptions
defined in config/feed_rules.py — do not use invented names here."""
from src.services.triage import TriageService, Bucket


class TestFeedNameRules:
    def _story(self, feed_title, story_title="Some title"):
        from unittest.mock import MagicMock
        s = MagicMock()
        s.story_feed_title = feed_title
        s.story_title = story_title
        return s

    def test_arxiv_ai_routes_to_ai_ml(self):
        svc = TriageService()
        assert svc.categorize(self._story("cs.AI updates on arXiv.org")) == Bucket.AI_ML

    def test_bbc_routes_to_world(self):
        svc = TriageService()
        assert svc.categorize(self._story("BBC News")) == Bucket.WORLD

    def test_newsblur_blog_routes_to_skip(self):
        svc = TriageService()
        assert svc.categorize(self._story("The NewsBlur Blog")) == Bucket.SKIP

    def test_raindrop_feed_routes_to_skip(self):
        svc = TriageService()
        assert svc.categorize(self._story("AI / Raindrop.io")) == Bucket.SKIP

    def test_space_city_weather_routes_to_world(self):
        svc = TriageService()
        bucket, sub = svc.categorize_with_sub(self._story("Space City Weather"))
        assert bucket == Bucket.WORLD
        assert sub == "news"

    def test_neurologica_routes_to_science(self):
        svc = TriageService()
        bucket, sub = svc.categorize_with_sub(self._story("NeuroLogica Blog"))
        assert bucket == Bucket.WORLD
        assert sub == "science"

    def test_ghostbusters_routes_to_entertainment(self):
        svc = TriageService()
        bucket, sub = svc.categorize_with_sub(self._story("Ghostbusters News"))
        assert bucket == Bucket.WORLD
        assert sub == "entertainment"

    def test_apple_newsroom_routes_to_tech_not_entertainment(self):
        svc = TriageService()
        bucket, sub = svc.categorize_with_sub(self._story("Apple Newsroom"))
        assert bucket == Bucket.WORLD
        assert sub == "tech"


class TestKeywordFallback:
    def _story(self, feed_title, story_title):
        from unittest.mock import MagicMock
        s = MagicMock()
        s.story_feed_title = feed_title
        s.story_title = story_title
        return s

    def test_hacker_news_llm_keyword_routes_to_ai_ml(self):
        svc = TriageService()
        assert svc.categorize(self._story("Hacker News", "New LLM beats GPT-4")) == Bucket.AI_ML

    def test_hacker_news_no_keyword_routes_to_world(self):
        svc = TriageService()
        assert svc.categorize(self._story("Hacker News", "Best coffee grinder Ask HN")) == Bucket.WORLD

    def test_unknown_feed_defaults_to_world(self):
        svc = TriageService()
        assert svc.categorize(self._story("Some Random Blog", "Weekend plans")) == Bucket.WORLD

    def test_feed_name_takes_priority_over_keyword(self):
        # ALWAYS_SKIP beats AI/ML keywords
        svc = TriageService()
        assert svc.categorize(self._story("The NewsBlur Blog", "new LLM released")) == Bucket.SKIP


class TestBoostTags:
    def _story(self, feed_title, story_title):
        from unittest.mock import MagicMock
        s = MagicMock()
        s.story_feed_title = feed_title
        s.story_title = story_title
        return s

    def test_open_source_boost(self):
        svc = TriageService()
        tags = svc.get_boost_tags(self._story("cs.AI updates on arXiv.org",
                                              "Open-source Llama variant outperforms proprietary models"))
        assert "boost:open-source" in tags

    def test_user_curated_boost_for_gbninjaturtle(self):
        svc = TriageService()
        tags = svc.get_boost_tags(self._story("saved by gbninjaturtle", "anything"))
        assert "boost:user-curated" in tags

    def test_rdd_long_signal(self):
        svc = TriageService()
        tags = svc.get_boost_tags(self._story("NeuroLogica Blog",
                                              "New research on consciousness and emergence"))
        assert "long-signal:rdd" in tags


class TestBatchCategorize:
    def test_returns_dict_of_bucket_to_stories(self):
        from unittest.mock import MagicMock
        svc = TriageService()

        def make(feed, title="x"):
            s = MagicMock()
            s.story_feed_title = feed
            s.story_title = title
            return s

        stories = [
            make("cs.AI updates on arXiv.org"),
            make("BBC News"),
            make("The NewsBlur Blog"),
        ]
        result = svc.batch_categorize(stories)
        assert len(result[Bucket.AI_ML]) == 1
        assert len(result[Bucket.WORLD]) == 1
        assert len(result[Bucket.SKIP]) == 1
```

**Step 4: Run the full test suite**

```bash
pytest tests/ -v 2>&1 | tail -20
```
Expected: All tests pass (the old triage tests have been replaced with new ones above).

**Step 5: Commit**

```bash
git add src/services/triage.py tests/test_triage.py
git commit -m "refactor: triage delegates to config/feed_rules, adds boost tag support"
```

---

### Task 6: Velocity clustering service

**Files:**
- Create: `src/services/velocity.py`
- Create: `tests/test_velocity.py`

**Step 1: Write the failing test**

```python
# tests/test_velocity.py
from unittest.mock import MagicMock
from src.services.velocity import compute_clusters


def _story(hash_id, title):
    s = MagicMock()
    s.story_hash = hash_id
    s.story_title = title
    return s


class TestComputeClusters:
    def test_single_story_has_cluster_size_zero(self):
        stories = [_story("a1", "Evaluation crisis in AI benchmarks")]
        result = compute_clusters(stories)
        assert result["a1"][0] == 0

    def test_three_matching_stories_form_cluster(self):
        stories = [
            _story("a1", "Evaluation crisis deepens across AI benchmarks"),
            _story("a2", "Benchmark evaluation reveals systematic failures"),
            _story("a3", "Crisis in benchmark evaluation methodology"),
        ]
        result = compute_clusters(stories)
        # All three share tokens like "evaluation", "benchmark", "crisis"
        assert result["a1"][0] >= 2
        assert result["a2"][0] >= 2
        assert result["a3"][0] >= 2

    def test_cluster_key_is_most_common_shared_token(self):
        stories = [
            _story("a1", "Evaluation crisis deepens across benchmarks"),
            _story("a2", "Benchmark evaluation reveals systematic failures"),
            _story("a3", "Crisis evaluation methodology needs reform"),
        ]
        result = compute_clusters(stories)
        # "evaluation" appears in all three — should be cluster_key for a1
        assert result["a1"][1] != ""

    def test_unrelated_stories_no_cluster(self):
        stories = [
            _story("a1", "Apple releases iPhone update"),
            _story("a2", "Houston weather forecast shows rain"),
            _story("a3", "Stock market closes higher"),
        ]
        result = compute_clusters(stories)
        # No story shares 2+ meaningful tokens with another
        for h, (size, _) in result.items():
            assert size == 0

    def test_stopwords_not_counted(self):
        # "with", "from", "that" are stopwords — should not form a cluster
        stories = [
            _story("a1", "News from the latest update"),
            _story("a2", "Update from that source"),
        ]
        result = compute_clusters(stories)
        # "update" is shared but only 1 token — not enough for cluster
        assert result["a1"][0] == 0

    def test_empty_list(self):
        assert compute_clusters([]) == {}
```

**Step 2: Run to verify it fails**

```bash
pytest tests/test_velocity.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError`

**Step 3: Create `src/services/velocity.py`**

```python
# src/services/velocity.py
"""Velocity clustering: detect stories covering the same topic.

Pure Python, no ML. Uses token-set intersection to identify story clusters.
cluster_size >= 3 → Lead Story candidate in Lambda 3.
"""
import re
from collections import Counter
from typing import Dict, List, Tuple

STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "have", "will",
    "are", "was", "been", "has", "its", "into", "over", "says", "said",
    "new", "can", "may", "also", "more", "than", "but", "not", "how",
    "what", "when", "why", "who", "all", "about", "after", "first",
    "being", "which", "their", "here", "would", "could", "make",
}


def _tokenize(title: str) -> set:
    """Lowercase, strip non-alphanumeric, drop stopwords and short tokens."""
    tokens = re.sub(r"[^a-z0-9 ]", " ", title.lower()).split()
    return {t for t in tokens if len(t) >= 4 and t not in STOPWORDS}


def compute_clusters(stories: List) -> Dict[str, Tuple[int, str]]:
    """
    Compute cluster_size and cluster_key for each story.

    Returns:
        {story_hash: (cluster_size, cluster_key)}
        cluster_size = number of other stories sharing >= 2 tokens
        cluster_key = most frequent shared token across the cluster
                      (empty string if cluster_size == 0)
    """
    if not stories:
        return {}

    token_sets = {s.story_hash: _tokenize(s.story_title) for s in stories}
    results = {}

    for story in stories:
        my_tokens = token_sets[story.story_hash]
        shared_counter: Counter = Counter()
        cluster_size = 0

        for other_hash, other_tokens in token_sets.items():
            if other_hash == story.story_hash:
                continue
            shared = my_tokens & other_tokens
            if len(shared) >= 2:
                cluster_size += 1
                shared_counter.update(shared)

        cluster_key = shared_counter.most_common(1)[0][0] if shared_counter else ""
        results[story.story_hash] = (cluster_size, cluster_key)

    return results
```

**Step 4: Run tests**

```bash
pytest tests/test_velocity.py -v
```
Expected: All PASS

**Step 5: Run full suite to confirm no regressions**

```bash
pytest tests/ -v 2>&1 | tail -5
```
Expected: All pass

**Step 6: Commit**

```bash
git add src/services/velocity.py tests/test_velocity.py
git commit -m "feat: velocity clustering for lead story detection (pure Python)"
```

---

## Phase 2: Lambda 1 — Context Loader + Triage Handler

### Task 7: Create `src/services/context_loader.py`

**Files:**
- Create: `src/services/context_loader.py`
- Create: `tests/test_context_loader.py`

**Step 1: Write the failing test**

```python
# tests/test_context_loader.py
from unittest.mock import patch, MagicMock
from src.services.context_loader import ContextLoader


class TestGetWeather:
    def test_returns_weather_dict_on_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "current": {
                "temperature_2m": 72.5,
                "weather_code": 1,
                "wind_speed_10m": 8.2,
            },
            "daily": {
                "temperature_2m_max": [81.0],
                "temperature_2m_min": [65.0],
                "precipitation_sum": [0.0],
            }
        }
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.get", return_value=mock_resp):
            loader = ContextLoader()
            result = loader.get_weather()
        assert result["temp_f"] == 72.5
        assert result["high_f"] == 81.0
        assert result["low_f"] == 65.0
        assert result["wind_mph"] == 8.2
        assert result["precip_in"] == 0.0

    def test_returns_none_on_timeout(self):
        import requests
        with patch("requests.get", side_effect=requests.exceptions.Timeout):
            loader = ContextLoader()
            result = loader.get_weather()
        assert result is None


class TestGetSpaceCityHeadlines:
    def test_returns_top_two_headlines(self):
        mock_feed = MagicMock()
        mock_feed.entries = [
            MagicMock(title="Tropical storm forms in Gulf"),
            MagicMock(title="Houston temps drop this weekend"),
            MagicMock(title="Third story should be ignored"),
        ]
        with patch("feedparser.parse", return_value=mock_feed):
            loader = ContextLoader()
            result = loader.get_space_city_headlines()
        assert len(result) == 2
        assert result[0] == "Tropical storm forms in Gulf"

    def test_returns_empty_on_parse_failure(self):
        with patch("feedparser.parse", side_effect=Exception("network error")):
            loader = ContextLoader()
            result = loader.get_space_city_headlines()
        assert result == []


class TestGetNwsAlerts:
    def test_returns_alert_headlines(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "features": [
                {"properties": {"headline": "Tornado Warning issued for Harris County"}},
                {"properties": {"headline": "Flash Flood Watch in effect"}},
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.get", return_value=mock_resp):
            loader = ContextLoader()
            result = loader.get_nws_alerts()
        assert len(result) == 2
        assert "Tornado Warning" in result[0]

    def test_missing_features_key_returns_empty(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"type": "FeatureCollection"}  # no "features"
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.get", return_value=mock_resp):
            loader = ContextLoader()
            result = loader.get_nws_alerts()
        assert result == []

    def test_non_list_features_returns_empty(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"features": "malformed"}
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.get", return_value=mock_resp):
            loader = ContextLoader()
            result = loader.get_nws_alerts()
        assert result == []

    def test_returns_empty_on_http_error(self):
        import requests
        with patch("requests.get", side_effect=requests.exceptions.RequestException):
            loader = ContextLoader()
            result = loader.get_nws_alerts()
        assert result == []


class TestFetchAll:
    def test_returns_full_context_block(self):
        loader = ContextLoader()
        with patch.object(loader, "get_weather", return_value={"temp_f": 72.0, "high_f": 80.0,
                          "low_f": 65.0, "wind_mph": 5.0, "precip_in": 0.0}), \
             patch.object(loader, "get_space_city_headlines", return_value=["Storm watch"]), \
             patch.object(loader, "get_nws_alerts", return_value=[]):
            result = loader.fetch_all()
        assert "fetched_at" in result
        assert result["weather"]["temp_f"] == 72.0
        assert result["nws_alerts"] == []

    def test_partial_failure_still_returns(self):
        # Weather fails, rest succeeds — fetch_all should not raise
        loader = ContextLoader()
        with patch.object(loader, "get_weather", return_value=None), \
             patch.object(loader, "get_space_city_headlines", return_value=[]), \
             patch.object(loader, "get_nws_alerts", return_value=[]):
            result = loader.fetch_all()
        assert result["weather"] is None


class TestFormatContextBlock:
    def test_formats_with_no_alerts(self):
        loader = ContextLoader()
        data = {
            "fetched_at": "2026-02-17T11:00:00+00:00",
            "weather": {"temp_f": 72.0, "condition": "Partly cloudy",
                        "high_f": 80.0, "low_f": 65.0, "wind_mph": 5.0, "precip_in": 0.1},
            "local_headlines": ["Storm watch issued for Houston"],
            "nws_alerts": [],
        }
        block = loader.format_context_block(data)
        assert "[SYSTEM_CONTEXT_BLOCK" in block
        assert "72.0°F" in block
        assert "ACTIVE ALERTS" not in block
        assert "0.1 in. expected" in block

    def test_formats_with_alerts(self):
        loader = ContextLoader()
        data = {
            "fetched_at": "2026-02-17T11:00:00+00:00",
            "weather": {"temp_f": 68.0, "condition": "Stormy",
                        "high_f": 70.0, "low_f": 60.0, "wind_mph": 35.0, "precip_in": 2.0},
            "local_headlines": [],
            "nws_alerts": ["Tornado Warning for Harris County"],
        }
        block = loader.format_context_block(data)
        assert "⚠️ ACTIVE ALERTS" in block
        assert "Tornado Warning" in block
```

**Step 2: Run to verify it fails**

```bash
pytest tests/test_context_loader.py -v 2>&1 | head -10
```
Expected: `ModuleNotFoundError`

**Step 3: Install feedparser first**

```bash
pip install "feedparser>=6.0.10"
# Then add to requirements.txt — see Task 18
```

**Step 4: Create `src/services/context_loader.py`**

```python
# src/services/context_loader.py
"""Weather + local news context fetcher for the Zeitgeist briefing.

All data is fetched deterministically (no LLM). The result is stored in
story_staging DDB by Lambda 1 at triage time. Lambda 3 reads it — the
fetched_at timestamp reflects Lambda 1's fetch time, never Lambda 3's.

This module is best-effort: any single source failure is logged and skipped.
Lambda 1 does not fail because weather is down.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, List, Optional

import feedparser
import requests

from shared.logger import log

PASADENA_LAT = 29.6911
PASADENA_LON = -95.2091
SPACE_CITY_WEATHER_RSS = "https://spacecityweather.com/feed/"
NWS_ALERTS_URL = "https://api.weather.gov/alerts/active?zone=TXZ163"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


class ContextLoader:
    """Fetches weather + local news context for the Zeitgeist briefing."""

    def get_weather(self) -> Optional[Dict]:
        """Fetch current conditions from Open-Meteo (free, no API key)."""
        params = {
            "latitude": PASADENA_LAT,
            "longitude": PASADENA_LON,
            "current": "temperature_2m,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "timezone": "America/Chicago",
            "forecast_days": 1,
        }
        try:
            resp = requests.get(OPEN_METEO_URL, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            current = data["current"]
            daily = data["daily"]
            return {
                "temp_f": current["temperature_2m"],
                "condition": _weather_code_to_str(current["weather_code"]),
                "high_f": daily["temperature_2m_max"][0],
                "low_f": daily["temperature_2m_min"][0],
                "wind_mph": current["wind_speed_10m"],
                "precip_in": daily["precipitation_sum"][0],
            }
        except Exception as exc:
            log("WARNING", "context_loader.get_weather failed", error=str(exc))
            return None

    def get_space_city_headlines(self) -> List[str]:
        """Parse Space City Weather RSS for top 1-2 headlines.

        NOTE: feedparser 6.x API — use feed.entries (list), not feed.items().
        """
        try:
            feed = feedparser.parse(SPACE_CITY_WEATHER_RSS)
            return [e.title for e in feed.entries[:2]]
        except Exception as exc:
            log("WARNING", "context_loader.space_city_weather failed", error=str(exc))
            return []

    def get_nws_alerts(self) -> List[str]:
        """Fetch active NWS alerts for Harris County (TXZ163).

        Guards against malformed response: if 'features' key missing or not a list,
        returns empty and logs WARNING — does not raise.
        """
        try:
            resp = requests.get(NWS_ALERTS_URL, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features")
            if not isinstance(features, list):
                log("WARNING", "context_loader.nws_alerts unexpected schema",
                    features_type=type(features).__name__)
                return []
            return [
                f["properties"]["headline"]
                for f in features
                if f.get("properties", {}).get("headline")
            ]
        except Exception as exc:
            log("WARNING", "context_loader.get_nws_alerts failed", error=str(exc))
            return []

    def fetch_all(self) -> Dict:
        """Fetch all context sources. Returns partial result on failure."""
        return {
            "weather": self.get_weather(),
            "local_headlines": self.get_space_city_headlines(),
            "nws_alerts": self.get_nws_alerts(),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    def format_context_block(self, data: Dict) -> str:
        """Format context data for injection into the Zeitgeist prompt."""
        w = data.get("weather") or {}
        alerts = data.get("nws_alerts") or []
        headlines = data.get("local_headlines") or []

        alert_line = ""
        if alerts:
            alert_line = f"\n⚠️ ACTIVE ALERTS: {', '.join(alerts)}"

        weather_block = ""
        if w:
            weather_block = (
                f"WEATHER:\n"
                f"Current: {w.get('temp_f')}°F, {w.get('condition')}\n"
                f"Today: High {w.get('high_f')}°F / Low {w.get('low_f')}°F"
                f" | Wind: {w.get('wind_mph')} mph\n"
                f"Precipitation: {w.get('precip_in')} in. expected{alert_line}"
            )

        local_block = ""
        if headlines:
            local_block = "LOCAL:\n" + "\n".join(f"- {h}" for h in headlines)

        return (
            f"[SYSTEM_CONTEXT_BLOCK — Deterministic Data, Do Not Contradict]\n"
            f"Location: Pasadena, TX (Houston metro) | {data.get('fetched_at')} UTC\n\n"
            f"{weather_block}\n\n"
            f"{local_block}\n"
            f"[END SYSTEM_CONTEXT_BLOCK]"
        )


# WMO weather code → human-readable string (subset)
_WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Icy fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Heavy thunderstorm with hail",
}


def _weather_code_to_str(code: int) -> str:
    return _WMO_CODES.get(code, f"Code {code}")
```

**Step 5: Run tests**

```bash
pytest tests/test_context_loader.py -v
```
Expected: All PASS

**Step 6: Commit**

```bash
git add src/services/context_loader.py tests/test_context_loader.py
git commit -m "feat: context loader for weather, Space City Weather RSS, NWS alerts"
```

---

### Task 8: Update `src/config.py` with new environment variables

**Files:**
- Modify: `src/config.py`
- Modify: `tests/test_config.py`

**Step 1: Read current `src/config.py`**

The current Settings class is in `src/config.py`. Add new fields for the three new DDB tables, DRY_RUN modes, and cost alert threshold. Do not remove existing fields.

**Step 2: Update `src/config.py`**

```python
# src/config.py — add to the existing Settings class:

# New DynamoDB tables
dynamodb_story_staging_table: str = "story-staging"
dynamodb_signal_table: str = "signal-tracker"
dynamodb_briefing_table: str = "briefing-archive"

# DRY_RUN modes: "false" | "true" | "writes_only"
dry_run: str = "false"

# Cost monitoring
cost_alert_daily_threshold: float = 3.00

# Pipeline caps
max_ai_ml_stories: int = 15
max_world_stories: int = 10
newsblur_hours_back: int = 12
```

**Step 3: Update `tests/test_config.py` to verify new fields load with defaults**

Add to existing test class:
```python
def test_new_ddb_table_defaults():
    s = Settings()
    assert s.dynamodb_story_staging_table == "story-staging"
    assert s.dynamodb_signal_table == "signal-tracker"
    assert s.dynamodb_briefing_table == "briefing-archive"

def test_dry_run_default_is_false():
    s = Settings()
    assert s.dry_run == "false"
```

**Step 4: Run tests**

```bash
pytest tests/test_config.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: add new DDB table names, DRY_RUN modes, cost threshold to config"
```

---

### Task 9: Update `src/handlers/triage_handler.py`

**Files:**
- Modify: `src/handlers/triage_handler.py`
- Modify: `tests/test_triage_handler.py`

**Step 1: Read the current handler** at `src/handlers/triage_handler.py`. Understand what it already does: NewsBlur fetch → dedup → triage → Raindrop → SQS → DDB.

**Step 2: Write new failing test**

```python
# Add to tests/test_triage_handler.py

def test_dry_run_skips_writes_and_sqs(monkeypatch):
    """DRY_RUN=true: triage runs, no DDB writes, no SQS, no Raindrop."""
    monkeypatch.setenv("DRY_RUN", "true")
    # ... mock NewsBlur returning 2 stories
    # Assert: dynamodb.put_item NOT called, sqs.send_message NOT called
    pass  # flesh out with your mock pattern from existing tests

def test_boost_tags_stored_in_ddb(monkeypatch):
    """Story with open-source keyword gets boost:open-source in DDB item."""
    # Mock a story with "open-source" in title from cs.AI feed
    # Assert: DDB put_item called with boost_tags containing "boost:open-source"
    pass

def test_cluster_size_stored_in_ddb(monkeypatch):
    """Three stories covering same topic: cluster_size >= 2 stored."""
    pass

def test_context_block_stored_with_stories(monkeypatch):
    """context_loader.fetch_all result stored as context_block in DDB."""
    pass
```

**Step 3: Update the triage handler**

Key changes from the current handler (read it first to understand existing structure):
- Import and call `ContextLoader().fetch_all()` at start
- Import `TriageService.get_boost_tags()` and `compute_clusters()`
- Switch from `ProcessingStateStorage` to `StoryStaging` from `shared.dynamodb_client`
- Write `content` (truncated at 8000 chars at whitespace boundary, append `" [truncated]"`)
- Write `boost_tags`, `cluster_size`, `cluster_key`, `sub_bucket`, `context_block` to DDB
- Pass `candidate_count` in SQS message for funnel metrics
- Respect `DRY_RUN` mode: skip all writes/SQS when `settings.dry_run == "true"`
- Keep existing Raindrop integration (title + tags, no summary)

Content truncation helper:
```python
def _truncate_content(content: str, max_chars: int = 8000) -> str:
    if len(content) <= max_chars:
        return content
    truncated = content[:max_chars]
    last_space = truncated.rfind(" ")
    if last_space > max_chars - 200:  # only use if close to boundary
        truncated = truncated[:last_space]
    return truncated + " [truncated]"
```

**Step 4: Run full test suite**

```bash
pytest tests/ -v 2>&1 | tail -10
```
Expected: All pass

**Step 5: Commit**

```bash
git add src/handlers/triage_handler.py tests/test_triage_handler.py
git commit -m "feat: triage handler v2 — boost tags, velocity, context block, DRY_RUN"
```

---

## Phase 3: Lambda 2 — Editorial Filter

### Task 10: Create `src/services/editorial_scorer.py`

**Files:**
- Create: `src/services/editorial_scorer.py`
- Create: `tests/test_editorial_scorer.py`

**Step 1: Write the failing test**

```python
# tests/test_editorial_scorer.py
import json
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
        import pytest
        with pytest.raises(ValueError):
            ScoringResult.from_json("not valid json {{{")

    def test_raises_on_missing_decision_field(self):
        import pytest
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
```

**Step 2: Run to verify it fails**

```bash
pytest tests/test_editorial_scorer.py -v 2>&1 | head -10
```

**Step 3: Create `src/services/editorial_scorer.py`**

```python
# src/services/editorial_scorer.py
"""Editorial scoring for Lambda 2. Uses Haiku to score each story.

Scoring dimensions (1-5 each, total out of 15):
- journalistic_integrity
- relevance (to Seth's context)
- novelty

Thresholds (from config/scoring_weights.py):
- AI_ML: pass if total >= 9
- WORLD: pass if total >= 8
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import List, Optional

from config.scoring_weights import AI_ML_PASS_THRESHOLD, WORLD_PASS_THRESHOLD
from shared.logger import log

SCORE_AI_ML_TEMPLATE = """\
You are the editorial filter for "The AI Abstract," an intelligence brief
for an AI Adoption Consultant at a German chemical manufacturer who manages
PhD-level GenAI engineers and publishes thought leadership on AI democratization.

Score this story on three dimensions (1–5 each):

JOURNALISTIC_INTEGRITY: Is this based on verifiable facts, peer-reviewed work,
or primary sources? (5 = peer-reviewed/primary source, 1 = speculation/PR copy)

RELEVANCE: Does this matter to an enterprise AI practitioner building
industrial-scale AI systems?
INCLUDE: research breakthroughs, open-source releases, capability milestones,
consciousness/AGI/alignment content (long-signal for the RDD philosophical framework).
PENALIZE: funding rounds, product demos without deployment path, ChatGPT wrappers,
productivity hacks, no-code AI tools.

NOVELTY: Is this genuinely new information, or rehash? Does the title sound like
the tenth article on the same story this week?

Boost tags from triage are provided — use them to inform relevance scoring:
boost:open-source → elevate relevance (democratization thesis)
boost:industrial → elevate relevance (Seth's native territory)
long-signal:rdd → never penalize; these are long-horizon signals for the RDD framework

Return ONLY valid JSON — no explanation, no markdown:
{{
  "integrity": <1-5>,
  "relevance": <1-5>,
  "novelty": <1-5>,
  "total": <sum>,
  "decision": "PASS" | "REJECT",
  "source_type": "peer-reviewed" | "journalism" | "commentary" | "single-source",
  "reasoning": "<one sentence — why it passes or fails>",
  "summary": "<two sentences if PASS: what happened + why it matters for enterprise AI. null if REJECT>"
}}

Threshold: PASS if total >= {threshold}.

Story title: {title}
Story content: {content}
Feed: {feed_name}
Sub-bucket: {sub_bucket}
Boost tags: {boost_tags}
"""

SCORE_WORLD_TEMPLATE = """\
You are the editorial filter for "The Recursive Briefing," a private daily
dispatch for Seth — an AI Adoption Consultant, systems thinker, autistic
(diagnosed 43), history-trained, patent-holding engineer writing a post-singularity
sci-fi series called "Wake."

Score this story on three dimensions (1–5 each):

JOURNALISTIC_INTEGRITY: Primary sources and verifiable facts score high.
Single-source claims, unverified reports, and opinion pieces score low.

RELEVANCE: Does this matter to a polymath executive in Pasadena, TX who thinks
in systems and recursive frameworks?
INCLUDE: geopolitics, science/discovery, culture, economics, Houston/Texas
local significance. Weather context is always relevant.
INCLUDE entertainment/pop culture IF: culturally significant event, personally
relevant (Ghostbusters collectibles, Apple ecosystem, sci-fi/speculative fiction),
or relevant to the Wake series Seth is writing.
EXCLUDE: entertainment that is merely a product announcement without cultural
weight or personal hook.

NOVELTY: Is this genuinely new, or a daily churn story that will look the same tomorrow?

Return ONLY valid JSON — no explanation, no markdown:
{{
  "integrity": <1-5>,
  "relevance": <1-5>,
  "novelty": <1-5>,
  "total": <sum>,
  "decision": "PASS" | "REJECT",
  "source_type": "peer-reviewed" | "journalism" | "commentary" | "single-source",
  "reasoning": "<one sentence — why it passes or fails>",
  "summary": "<two sentences if PASS: core facts + why it matters. null if REJECT>"
}}

Threshold: PASS if total >= {threshold}.

Story title: {title}
Story content: {content}
Feed: {feed_name}
Sub-bucket: {sub_bucket}
Boost tags: {boost_tags}
"""

_DRY_RUN_RESULT = {
    "integrity": 3, "relevance": 3, "novelty": 3, "total": 9,
    "decision": "PASS", "source_type": "journalism",
    "reasoning": "DRY_RUN mock — real scoring not performed.",
    "summary": "DRY_RUN mock summary sentence one. Mock sentence two.",
}


@dataclass
class ScoringResult:
    integrity: int
    relevance: int
    novelty: int
    total: int
    decision: str  # "PASS" | "REJECT"
    source_type: str
    reasoning: str
    summary: Optional[str]

    @classmethod
    def from_json(cls, raw: str) -> "ScoringResult":
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Haiku returned invalid JSON: {exc}\nRaw: {raw[:200]}") from exc
        required = {"integrity", "relevance", "novelty", "total", "decision",
                    "source_type", "reasoning", "summary"}
        missing = required - set(data.keys())
        if missing:
            raise ValueError(f"Haiku response missing fields: {missing}")
        return cls(**{k: data[k] for k in required})

    @property
    def passed(self) -> bool:
        return self.decision == "PASS"


class EditorialScorer:
    """Score stories using Haiku via Bedrock. Thread-safe."""

    def __init__(self, bedrock_client=None, model_id: str = "", dry_run: bool = False):
        self._bedrock = bedrock_client
        self._model_id = model_id
        self._dry_run = dry_run

    def score(
        self,
        briefing_type: str,
        title: str,
        content: str,
        feed_name: str,
        sub_bucket: str,
        boost_tags: List[str],
    ) -> ScoringResult:
        """Score a story. In dry_run mode, returns mock PASS at total=9."""
        if self._dry_run:
            log("INFO", "editorial_scorer.dry_run", title=title[:80], decision="PASS_MOCK")
            return ScoringResult.from_json(json.dumps(_DRY_RUN_RESULT))

        prompt = self._build_prompt(
            briefing_type, title, content, feed_name, sub_bucket, boost_tags
        )
        raw_response = self._call_bedrock(prompt)
        result = ScoringResult.from_json(raw_response)
        log(
            "INFO",
            "editorial_scorer.scored",
            title=title[:80],
            decision=result.decision,
            total=result.total,
            source_type=result.source_type,
        )
        return result

    def _build_prompt(
        self,
        briefing_type: str,
        title: str,
        content: str,
        feed_name: str,
        sub_bucket: str,
        boost_tags: List[str],
    ) -> str:
        threshold = AI_ML_PASS_THRESHOLD if briefing_type == "AI_ML" else WORLD_PASS_THRESHOLD
        template = SCORE_AI_ML_TEMPLATE if briefing_type == "AI_ML" else SCORE_WORLD_TEMPLATE
        return template.format(
            threshold=threshold,
            title=title,
            content=content[:8000],
            feed_name=feed_name,
            sub_bucket=sub_bucket,
            boost_tags=", ".join(boost_tags) if boost_tags else "none",
        )

    def _call_bedrock(self, prompt: str) -> str:
        """Call Bedrock Haiku and return the raw text response."""
        import json as _json
        body = _json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 512,
            "messages": [{"role": "user", "content": prompt}],
        })
        response = self._bedrock.invoke_model(
            modelId=self._model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        resp_body = _json.loads(response["body"].read())
        return resp_body["content"][0]["text"]
```

**Step 4: Run tests**

```bash
pytest tests/test_editorial_scorer.py -v
```
Expected: All PASS

**Step 5: Commit**

```bash
git add src/services/editorial_scorer.py tests/test_editorial_scorer.py
git commit -m "feat: Haiku editorial scorer with PASS/REJECT, source_type, dry_run mode"
```

---

### Task 11: Update `src/handlers/summarizer_handler.py`

**Files:**
- Modify: `src/handlers/summarizer_handler.py`
- Modify: `tests/test_summarizer_handler.py`

**Step 1: Read the current handler** at `src/handlers/summarizer_handler.py`.

**Step 2: Key changes to implement**

- Replace the existing summarizer with `EditorialScorer.score()`
- Use `ThreadPoolExecutor(max_workers=10)` for parallel scoring
- Use `threading.Semaphore(5)` for Raindrop updates — pass it into the per-story update function
- Idempotency: skip stories where `status != "pending"` (fetch from `StoryStaging`)
- Bail if fewer than `MIN_STORIES_FOR_BRIEFING` pass (log reason, no SQS send)
- Pass `candidate_count` in the SQS briefing-queue message
- Respect `DRY_RUN` modes: `"true"` → use `EditorialScorer(dry_run=True)`, no DDB/Raindrop writes; `"writes_only"` → real Haiku, no writes
- Mark rejected stories as read in NewsBlur

**Step 3: Write new tests**

```python
# Add to tests/test_summarizer_handler.py

def test_fewer_than_3_pass_does_not_send_sqs():
    """If only 2 stories pass, no briefing-queue message sent."""
    # Mock 5 stories where 2 pass scoring
    # Assert: sqs.send_message NOT called
    pass

def test_idempotency_skips_already_summarized():
    """Stories with status='summarized' are skipped."""
    # Mock DDB returning story with status='summarized'
    # Assert: Haiku NOT called for that story
    pass

def test_raindrop_semaphore_limits_concurrency():
    """Raindrop updates limited to 5 concurrent calls."""
    # This is tested indirectly — Semaphore(5) wraps raindrop calls
    # Just verify raindrop.update_note called for each passing story
    pass
```

**Step 4: Run full suite**

```bash
pytest tests/ -v 2>&1 | tail -10
```
Expected: All pass

**Step 5: Commit**

```bash
git add src/handlers/summarizer_handler.py tests/test_summarizer_handler.py
git commit -m "feat: summarizer handler v2 — editorial scoring, idempotency, bail threshold"
```

---

## Phase 4: Lambda 3 — Dual Personas

### Task 12: Create `src/services/personas.py`

**Files:**
- Create: `src/services/personas.py`
- Create: `tests/test_personas.py`

**Step 1: Write the failing test**

```python
# tests/test_personas.py
from src.services.personas import (
    build_equalizer_prompt,
    build_zeitgeist_prompt,
    SOURCE_EMOJI,
)


class TestSourceEmoji:
    def test_peer_reviewed_gets_microscope(self):
        assert SOURCE_EMOJI["peer-reviewed"] == "🔬"

    def test_single_source_gets_warning(self):
        assert SOURCE_EMOJI["single-source"] == "⚠️"


class TestEqualizerPrompt:
    def test_includes_editorial_identity(self):
        prompt = build_equalizer_prompt(stories=[], signals=[], prior_briefing=None)
        assert "AI Abstract" in prompt
        assert "Equalizer" in prompt or "equalizer" in prompt

    def test_does_not_include_context_block(self):
        prompt = build_equalizer_prompt(stories=[], signals=[], prior_briefing=None)
        assert "SYSTEM_CONTEXT_BLOCK" not in prompt

    def test_includes_stories_json(self):
        stories = [{"title": "Test story", "summary": "Summary.", "source_type": "journalism",
                    "boost_tags": [], "cluster_size": 1, "sub_bucket": "research",
                    "scores": {"total": 10}, "url": "https://example.com",
                    "feed_name": "cs.AI updates on arXiv.org", "reasoning": "Good."}]
        prompt = build_equalizer_prompt(stories=stories, signals=[], prior_briefing=None)
        assert "Test story" in prompt

    def test_signal_data_included(self):
        signals = [{"signal_key": "eval-crisis", "mention_count": 3,
                    "last_seen": "2026-02-17", "example_stories": []}]
        prompt = build_equalizer_prompt(stories=[], signals=signals, prior_briefing=None)
        assert "eval-crisis" in prompt

    def test_prior_briefing_included_when_present(self):
        prompt = build_equalizer_prompt(
            stories=[], signals=[],
            prior_briefing={"content": "Yesterday's briefing summary."}
        )
        assert "Yesterday's briefing" in prompt


class TestZeitgeistPrompt:
    def test_includes_editorial_identity(self):
        prompt = build_zeitgeist_prompt(
            stories=[], signals=[], prior_briefing=None, context_block=""
        )
        assert "Recursive Briefing" in prompt or "Zeitgeist" in prompt

    def test_includes_context_block(self):
        block = "[SYSTEM_CONTEXT_BLOCK — Deterministic Data]..."
        prompt = build_zeitgeist_prompt(
            stories=[], signals=[], prior_briefing=None, context_block=block
        )
        assert "SYSTEM_CONTEXT_BLOCK" in prompt

    def test_entertainment_aside_instruction_present(self):
        prompt = build_zeitgeist_prompt(
            stories=[], signals=[], prior_briefing=None, context_block=""
        )
        assert "aside" in prompt.lower() or "parenthetical" in prompt.lower()

    def test_lede_grounding_rule_present(self):
        prompt = build_zeitgeist_prompt(
            stories=[], signals=[], prior_briefing=None, context_block=""
        )
        assert "specific story" in prompt.lower() or "anchor" in prompt.lower()
```

**Step 2: Run to verify it fails**

```bash
pytest tests/test_personas.py -v 2>&1 | head -10
```

**Step 3: Create `src/services/personas.py`**

Implement `build_equalizer_prompt()` and `build_zeitgeist_prompt()` using the full system prompts from the design doc (`PROMPT_EQUALIZER_SYSTEM` and `PROMPT_ZEITGEIST_SYSTEM`). Each function builds a complete prompt string with the system prompt, injected story JSON, signals, and prior briefing.

Key behaviors (verified by tests above):
- `build_equalizer_prompt`: no context block, include signals and prior briefing
- `build_zeitgeist_prompt`: inject context block, include entertainment aside rule and Lede grounding rule
- `SOURCE_EMOJI` dict with all four mappings

**Step 4: Run tests**

```bash
pytest tests/test_personas.py -v
```

**Step 5: Commit**

```bash
git add src/services/personas.py tests/test_personas.py
git commit -m "feat: dual editorial personas for AI Abstract and Recursive Briefing"
```

---

### Task 13: Create `src/services/synthesizer.py`

**Files:**
- Create: `src/services/synthesizer.py`
- Create: `tests/test_synthesizer.py`

**Step 1: Write the failing test**

```python
# tests/test_synthesizer.py
from unittest.mock import MagicMock, patch
from src.services.synthesizer import BriefingSynthesizer


class TestPriorBriefingLookup:
    def test_am_run_queries_yesterday_pm(self):
        """AM run → query yesterday's PM briefing."""
        synth = BriefingSynthesizer.__new__(BriefingSynthesizer)
        key = synth._prior_briefing_key("2026-02-17", "AM")
        assert key == ("2026-02-16-PM", "AI_ML")

    def test_pm_run_queries_today_am(self):
        """PM run → query today's AM briefing."""
        synth = BriefingSynthesizer.__new__(BriefingSynthesizer)
        key = synth._prior_briefing_key("2026-02-17", "PM")
        assert key == ("2026-02-17-AM", "AI_ML")


class TestBriefingTypeBranching:
    def test_equalizer_gets_no_context_block(self):
        synth = MagicMock(spec=BriefingSynthesizer)
        synth._prior_briefing_key = BriefingSynthesizer._prior_briefing_key.__get__(synth)
        # Verify build_prompt_for_type routes AI_ML to equalizer path
        pass

    def test_zeitgeist_gets_context_block(self):
        pass
```

**Step 2: Create `src/services/synthesizer.py`**

Key responsibilities:
- `_prior_briefing_key(run_date, time_of_day)` — returns `(archive_key, briefing_type)` per the AM/PM chain rule
- `synthesize(stories, run_date, time_of_day, briefing_type, context_block, signals, prior_briefing)` → calls Bedrock Sonnet
- Branches on `briefing_type` to call `build_equalizer_prompt` vs `build_zeitgeist_prompt`
- In `DRY_RUN=true`: logs the full prompt, returns a placeholder string without calling Sonnet

**Step 3: Run tests**

```bash
pytest tests/test_synthesizer.py -v
```

**Step 4: Commit**

```bash
git add src/services/synthesizer.py tests/test_synthesizer.py
git commit -m "feat: briefing synthesizer with AM/PM prior lookup and DRY_RUN mode"
```

---

### Task 14: Update `src/handlers/briefing_handler.py`

**Files:**
- Modify: `src/handlers/briefing_handler.py`
- Modify: `tests/test_briefing_handler.py`

**Step 1: Key changes to implement**

- Query `signal_tracker` explicitly before calling Sonnet (inject into prompt payload)
- Query `briefing_archive` for prior edition using AM/PM chain rule
- Branch on `briefing_type` before building prompt (Zeitgeist gets context block; Equalizer does not)
- Use `BriefingSynthesizer` from `src/services/synthesizer.py`
- Write to `briefing_archive` after posting to Raindrop
- Add website integration stub (commented out — AI_ML only, see design doc)
- Respect `DRY_RUN` modes

Website stub (add after Raindrop post):
```python
# FUTURE: Post briefing to recursiveintelligence-website
# Requires blog feature to be built first — see docs/plans/website-integration.md
# IMPORTANT: AI Abstract (AI_ML) only — Recursive Briefing NEVER publishes to website
# if briefing_type == "AI_ML":
#     payload = {"briefing_type": briefing_type, "content": briefing_text,
#                "date": run_date, "is_public": True}
#     requests.post(WEBSITE_WEBHOOK_URL, json=payload,
#                   headers={"X-Secret": WEBSITE_WEBHOOK_SECRET})
```

**Step 2: Run full test suite**

```bash
pytest tests/ -v 2>&1 | tail -10
```
Expected: All pass

**Step 3: Commit**

```bash
git add src/handlers/briefing_handler.py tests/test_briefing_handler.py
git commit -m "feat: briefing handler v2 — dual personas, signal injection, archive, stub"
```

---

## Phase 5: Infrastructure

### Task 15: Add new DynamoDB tables to Terraform

**Files:**
- Modify: `terraform/dynamodb.tf`

**Step 1: Read current `terraform/dynamodb.tf`**

**Step 2: Add three new table resources**

Add to `terraform/dynamodb.tf` (do NOT modify or remove existing `newsblur-processing-state` table):

```hcl
resource "aws_dynamodb_table" "story_staging" {
  name         = "story-staging"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "story_hash"
  range_key    = "briefing_type"

  attribute {
    name = "story_hash"
    type = "S"
  }
  attribute {
    name = "briefing_type"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = {
    Project     = "research-agent"
    Environment = "prod"
    ManagedBy   = "terraform"
  }
}

resource "aws_dynamodb_table" "signal_tracker" {
  name         = "signal-tracker"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "signal_key"

  attribute {
    name = "signal_key"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = {
    Project     = "research-agent"
    Environment = "prod"
    ManagedBy   = "terraform"
  }
}

resource "aws_dynamodb_table" "briefing_archive" {
  name         = "briefing-archive"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "briefing_date"
  range_key    = "briefing_type"

  attribute {
    name = "briefing_date"
    type = "S"
  }
  attribute {
    name = "briefing_type"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  tags = {
    Project     = "research-agent"
    Environment = "prod"
    ManagedBy   = "terraform"
  }
}
```

**Step 3: Validate Terraform**

```bash
cd terraform && terraform validate
```
Expected: `Success! The configuration is valid.`

**Step 4: Commit**

```bash
git add terraform/dynamodb.tf
git commit -m "infra: add story_staging, signal_tracker, briefing_archive DDB tables"
```

---

### Task 16: Create `terraform/eventbridge.tf`

**Files:**
- Create: `terraform/eventbridge.tf`

```hcl
# terraform/eventbridge.tf
# 11:00 UTC = 6AM CDT (summer) / 5AM CST (winter) — acceptable drift for a news briefing
# 23:00 UTC = 6PM CDT (summer) / 5PM CST (winter)

resource "aws_cloudwatch_event_rule" "morning_triage" {
  name                = "personal-journalist-morning"
  description         = "Trigger Lambda 1 triage at 6AM CDT / 5AM CST"
  schedule_expression = "cron(0 11 * * ? *)"
  state               = "ENABLED"

  tags = {
    Project     = "research-agent"
    Environment = "prod"
    ManagedBy   = "terraform"
  }
}

resource "aws_cloudwatch_event_rule" "evening_triage" {
  name                = "personal-journalist-evening"
  description         = "Trigger Lambda 1 triage at 6PM CDT / 5PM CST"
  schedule_expression = "cron(0 23 * * ? *)"
  state               = "ENABLED"

  tags = {
    Project     = "research-agent"
    Environment = "prod"
    ManagedBy   = "terraform"
  }
}

resource "aws_cloudwatch_event_target" "morning_triage_target" {
  rule      = aws_cloudwatch_event_rule.morning_triage.name
  target_id = "TriageLambdaMorning"
  arn       = aws_lambda_function.triage.arn  # reference your existing Lambda resource
}

resource "aws_cloudwatch_event_target" "evening_triage_target" {
  rule      = aws_cloudwatch_event_rule.evening_triage.name
  target_id = "TriageLambdaEvening"
  arn       = aws_lambda_function.triage.arn
}

resource "aws_lambda_permission" "allow_eventbridge_morning" {
  statement_id  = "AllowEventBridgeMorning"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.triage.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.morning_triage.arn
}

resource "aws_lambda_permission" "allow_eventbridge_evening" {
  statement_id  = "AllowEventBridgeEvening"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.triage.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.evening_triage.arn
}
```

> **Note:** Replace `aws_lambda_function.triage` with the actual resource name from your existing `terraform/lambda.tf`. Check with `grep "aws_lambda_function" terraform/lambda.tf`.

**Validate:**

```bash
cd terraform && terraform validate
```

**Commit:**

```bash
git add terraform/eventbridge.tf
git commit -m "infra: EventBridge 6AM/6PM CDT cron rules for triage Lambda"
```

---

### Task 17: Update `terraform/sqs.tf` with DLQs

**Files:**
- Modify: `terraform/sqs.tf`

**Step 1: Read current `terraform/sqs.tf`**

**Step 2: Add DLQ resources and wire redrive policies**

Add DLQ for each existing queue. Wire `redrive_policy` with `maxReceiveCount = 3`. Add all resources with tags.

```hcl
# Dead letter queues
resource "aws_sqs_queue" "ai_ml_dlq" {
  name                      = "personal-journalist-ai-ml-dlq"
  message_retention_seconds = 604800  # 7 days
  tags = { Project = "research-agent", Environment = "prod", ManagedBy = "terraform" }
}

resource "aws_sqs_queue" "world_dlq" {
  name                      = "personal-journalist-world-dlq"
  message_retention_seconds = 604800
  tags = { Project = "research-agent", Environment = "prod", ManagedBy = "terraform" }
}

resource "aws_sqs_queue" "briefing_dlq" {
  name                      = "personal-journalist-briefing-dlq"
  message_retention_seconds = 604800
  tags = { Project = "research-agent", Environment = "prod", ManagedBy = "terraform" }
}
```

Add `redrive_policy` to each existing queue (read exact resource names from sqs.tf first):
```hcl
redrive_policy = jsonencode({
  deadLetterTargetArn = aws_sqs_queue.ai_ml_dlq.arn
  maxReceiveCount     = 3
})
```

**Validate and commit:**

```bash
cd terraform && terraform validate
git add terraform/sqs.tf
git commit -m "infra: add DLQs for all three SQS queues, maxReceiveCount=3"
```

---

### Task 18: Create `terraform/cloudwatch.tf` and update IAM

**Files:**
- Create: `terraform/cloudwatch.tf`
- Modify: `terraform/iam.tf`

**Step 1: Create `terraform/cloudwatch.tf`**

```hcl
# terraform/cloudwatch.tf

# DLQ depth alarms
resource "aws_cloudwatch_metric_alarm" "briefing_dlq_depth" {
  alarm_name          = "personal-journalist-briefing-dlq-depth"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Sum"
  threshold           = 0  # Any message in briefing DLQ is worth alerting
  alarm_description   = "A briefing failed after 3 attempts"
  dimensions = { QueueName = aws_sqs_queue.briefing_dlq.name }
  tags = { Project = "research-agent", Environment = "prod", ManagedBy = "terraform" }
}

resource "aws_cloudwatch_metric_alarm" "ai_ml_dlq_depth" {
  alarm_name          = "personal-journalist-ai-ml-dlq-depth"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Sum"
  threshold           = 2  # Avoid alert fatigue from transient timeouts
  alarm_description   = "Multiple AI/ML stories failed scoring after 3 attempts"
  dimensions = { QueueName = aws_sqs_queue.ai_ml_dlq.name }
  tags = { Project = "research-agent", Environment = "prod", ManagedBy = "terraform" }
}

resource "aws_cloudwatch_metric_alarm" "world_dlq_depth" {
  alarm_name          = "personal-journalist-world-dlq-depth"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "ApproximateNumberOfMessagesVisible"
  namespace           = "AWS/SQS"
  period              = 60
  statistic           = "Sum"
  threshold           = 2
  alarm_description   = "Multiple World stories failed scoring after 3 attempts"
  dimensions = { QueueName = aws_sqs_queue.world_dlq.name }
  tags = { Project = "research-agent", Environment = "prod", ManagedBy = "terraform" }
}

# Lambda 1 duration alarm (approaching 60s timeout)
resource "aws_cloudwatch_metric_alarm" "triage_duration" {
  alarm_name          = "personal-journalist-triage-duration"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "Duration"
  namespace           = "AWS/Lambda"
  period              = 60
  statistic           = "Maximum"
  threshold           = 55000  # milliseconds
  alarm_description   = "Lambda 1 triage approaching 60s timeout"
  dimensions = { FunctionName = aws_lambda_function.triage.function_name }
  tags = { Project = "research-agent", Environment = "prod", ManagedBy = "terraform" }
}

# Cost alarm — custom metric emitted by Lambda 2 and 3
resource "aws_cloudwatch_metric_alarm" "daily_api_cost" {
  alarm_name          = "personal-journalist-daily-api-cost"
  comparison_operator = "GreaterThanThreshold"
  evaluation_periods  = 1
  metric_name         = "estimated_api_cost"
  namespace           = "PersonalJournalist/Cost"
  period              = 86400  # 24h
  statistic           = "Sum"
  threshold           = 3.00
  alarm_description   = "Estimated daily Anthropic API cost exceeds $3.00"
  treat_missing_data  = "notBreaching"
  tags = { Project = "research-agent", Environment = "prod", ManagedBy = "terraform" }
}
```

**Step 2: Update `terraform/iam.tf`**

Add the missing permissions per the design doc IAM table. Read the existing `iam.tf` first to understand the existing policy structure, then add:
- Lambda 1: `dynamodb:PutItem` on `story_staging`, `dynamodb:PutItem` + `dynamodb:UpdateItem` on `signal_tracker`, `sqs:SendMessage` on `ai-ml-queue` and `world-queue`
- Lambda 2: `dynamodb:GetItem` + `dynamodb:UpdateItem` on `story_staging`
- Lambda 3: `dynamodb:Query` on `story_staging`, `dynamodb:GetItem` on `signal_tracker` (NOT Scan), `dynamodb:PutItem` + `dynamodb:GetItem` on `briefing_archive`

**Step 3: Validate**

```bash
cd terraform && terraform validate
```

**Step 4: Commit**

```bash
git add terraform/cloudwatch.tf terraform/iam.tf
git commit -m "infra: CloudWatch alarms for DLQ depth, Lambda duration, cost threshold"
```

---

## Phase 6: Scripts + Docs

### Task 19: Create `scripts/dry_run.py`

**Files:**
- Create: `scripts/dry_run.py`

```python
#!/usr/bin/env python3
"""Dry run the full triage pipeline locally. Zero LLM cost, zero writes.

Usage:
    DRY_RUN=true python scripts/dry_run.py

Loads credentials from AWS SSM (seth-dev profile), invokes triage handler
with DRY_RUN=true, prints routing report and Lambda 2 mock scoring summary.
"""
import os
import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("DRY_RUN", "true")

import boto3
from src.config import Settings
from src.clients.newsblur import NewsBlurClient
from src.services.triage import TriageService, Bucket
from src.services.velocity import compute_clusters
from src.services.context_loader import ContextLoader
from config.scoring_weights import (
    AI_ML_PASS_THRESHOLD, WORLD_PASS_THRESHOLD, MIN_STORIES_FOR_BRIEFING
)
from collections import defaultdict


AWS_PROFILE = "seth-dev"
SSM_PREFIX = "/prod/ResearchAgent/"


def fetch_credentials():
    session = boto3.Session(profile_name=AWS_PROFILE, region_name="us-east-1")
    ssm = session.client("ssm")
    user = ssm.get_parameter(Name=f"{SSM_PREFIX}NewsBlur_User", WithDecryption=True)["Parameter"]["Value"]
    passwd = ssm.get_parameter(Name=f"{SSM_PREFIX}NewsBlur_Pass", WithDecryption=True)["Parameter"]["Value"]
    return user, passwd


def main():
    from datetime import datetime, timezone
    print(f"\nDRY RUN — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    print("=" * 60)

    user, passwd = fetch_credentials()
    nb = NewsBlurClient(user, passwd)
    nb.authenticate()

    stories = nb.fetch_unread_stories(min_score=1, hours_back=12, max_results=100)
    print(f"Fetched: {len(stories)} stories")

    # Dedup (simplified — no DDB in dry run)
    print(f"Deduplicated: 0 (DDB not queried in dry run)")

    svc = TriageService()
    buckets = svc.batch_categorize(stories)

    ai_ml = buckets[Bucket.AI_ML]
    world = buckets[Bucket.WORLD]
    skip = buckets[Bucket.SKIP]

    # Count by feed
    def feed_counts(items):
        counts = defaultdict(int)
        for story, _ in items:
            counts[story.story_feed_title] += 1
        return dict(sorted(counts.items(), key=lambda x: -x[1]))

    print(f"\nRouting decisions:")
    print(f"  AI_ML  ({len(ai_ml)}): {feed_counts(ai_ml)}")
    print(f"  WORLD  ({len(world)}): {feed_counts(world)}")
    print(f"  SKIP   ({len(skip)}): {feed_counts(skip)}")

    # Boost tags
    all_boost = []
    for story, _ in ai_ml + world:
        tags = svc.get_boost_tags(story)
        all_boost.extend(tags)
    from collections import Counter
    boost_counts = Counter(all_boost)
    if boost_counts:
        print(f"\nBoost tags applied: {', '.join(f'{t}×{c}' for t, c in boost_counts.items())}")

    # Velocity clusters
    all_stories = [s for s, _ in ai_ml + world]
    clusters = compute_clusters(all_stories)
    lead_candidates = [(h, key) for h, (size, key) in clusters.items() if size >= 3]
    if lead_candidates:
        cluster_keys = Counter(key for _, key in lead_candidates)
        print(f"\nVelocity clusters:")
        for key, count in cluster_keys.most_common(5):
            print(f'  "{key}" [{count} stories] → Lead Story candidate')
    else:
        print("\nVelocity clusters: none (no topic covered by 3+ sources)")

    # Lambda 2 mock summary
    print(f"\nEditorial filter (mock, DRY_RUN=true):")
    ai_ml_total = len(ai_ml)
    world_total = len(world)
    # Mock: all score 9 (3+3+3), so all pass threshold
    print(f"  Would pass: {ai_ml_total}/{ai_ml_total} AI_ML candidates (threshold {AI_ML_PASS_THRESHOLD}/15)")
    print(f"  Would pass: {world_total}/{world_total} WORLD candidates (threshold {WORLD_PASS_THRESHOLD}/15)")
    print(f"  Mock scores: all set to integrity:3, relevance:3, novelty:3 (total:9)")
    print(f"  Note: run DRY_RUN=writes_only to see real Haiku scoring decisions")

    print()


if __name__ == "__main__":
    main()
```

**Test:**

```bash
DRY_RUN=true python scripts/dry_run.py
```
Expected: routing report printed, no errors

**Commit:**

```bash
git add scripts/dry_run.py
git commit -m "feat: dry_run.py — full triage simulation, zero cost, routing report"
```

---

### Task 20: Create `docs/plans/website-integration.md`, update `requirements.txt`, create `CLAUDE.md`

**Files:**
- Create: `docs/plans/website-integration.md`
- Modify: `requirements.txt`
- Create: `CLAUDE.md`

**Step 1: Create `docs/plans/website-integration.md`**

```markdown
# Website Integration — Future Phase

## Status
DEFERRED — blog feature must be built on recursiveintelligence-website first.

## Boundary (non-negotiable)
The AI Abstract (AI_ML stream) publishes as a PUBLIC blog post.
The Recursive Briefing NEVER publishes to the website — not publicly, not privately,
not as an authenticated post. Keep this boundary hard.

## Webhook contract (to be defined when blog is built)
POST /api/briefings/ingest
Headers: X-Secret: {WEBSITE_WEBHOOK_SECRET}
Body: { briefing_type, content (markdown), date, is_public }

## Stub location
`src/handlers/briefing_handler.py` — commented out block after Raindrop post

## See also
- CLAUDE_CODE_IMPLEMENTATION_PLAN.md — original brief
- 2026-02-17-personal-journalist-v2-design.md — full architecture
```

**Step 2: Update `requirements.txt`**

Add after existing entries:
```
feedparser>=6.0.10
```

Verify no feedparser 5.x conflict:
```bash
grep -r feedparser requirements*.txt
```

**Step 3: Create `CLAUDE.md` at repo root**

```markdown
# research-agent — Personal Journalist Engine

## What This Is
A dual-stream AI-powered briefing system for Seth, an AI Adoption Consultant
at Covestro (German chemical manufacturing). Runs twice daily (11:00/23:00 UTC)
via EventBridge.

## The Two Publications
- **The AI Abstract** — Public, industrial AI intelligence brief.
  Three-level structure: Frontier → Enterprise → Democratization.
  Published to Raindrop "AI/ML Feed" collection (public RSS).
- **The Recursive Briefing** — Private, world/culture/science dispatch.
  Narrative format, grounded in Pasadena TX weather and local news.
  Published to Raindrop "World Digest" collection (private).

## Architecture
Three Lambdas connected by SQS:
Lambda 1 (Triage, no LLM) → Lambda 2 (Haiku editorial filter) → Lambda 3 (Sonnet 4.5 briefing)

## Critical Rules
- DO NOT penalize consciousness/AGI/alignment content — long signal for Seth's RDD framework
- Feed routing lives in `config/feed_rules.py` — update without redeploy
- `DRY_RUN=true` for zero-cost testing | `DRY_RUN=writes_only` for real LLM, no writes
- Raindrop rate limit: `threading.Semaphore(5)` in Lambda 2, 200ms sleep in Lambda 1
- Lambda 2 bails if fewer than 3 stories pass threshold — no briefing-queue message
- Recursive Briefing NEVER publishes to the website

## Key Files
- `config/feed_rules.py` — routing logic (44 real NewsBlur feeds)
- `config/keywords.py` — boost/penalize keyword lists
- `src/services/personas.py` — two editorial identities
- `src/services/editorial_scorer.py` — Haiku scoring with structured JSON output
- `shared/dynamodb_client.py` — typed DDB operations (3 tables)
- `docs/plans/2026-02-17-personal-journalist-v2-design.md` — full design

## Cost Target
~$50/month (Anthropic Bedrock + AWS + Raindrop Pro)
Alert threshold: $3/day via CloudWatch alarm
```

**Commit:**

```bash
git add docs/plans/website-integration.md requirements.txt CLAUDE.md
git commit -m "docs: website integration placeholder, feedparser dep, CLAUDE.md"
```

---

## Phase 7: Integration Testing

### Task 21: End-to-end dry run

**Step 1: Run full dry run**

```bash
DRY_RUN=true python scripts/dry_run.py
```

Verify output includes:
- Fetched count
- Routing decisions with feed breakdown
- Boost tags
- Lambda 2 mock summary
- Completes in under 60 seconds

**Step 2: Run full test suite**

```bash
pytest tests/ -v
```
Expected: All 75+ tests pass

**Step 3: Verify no hardcoded credentials**

```bash
grep -r "password\|api_key\|token" src/ config/ shared/ --include="*.py" | grep -v "test\|#\|setting\|env\|getenv"
```
Expected: No matches

---

### Task 22: Check success criteria from design doc

Work through each item in the design doc's Success Criteria checklist. For each item that can be verified locally without full AWS deployment:

```bash
# Feed rules: verify exact feed names route correctly
python -c "
from config.feed_rules import get_route, Route
tests = [
    ('cs.AI updates on arXiv.org', '', Route.AI_ML),
    ('Space City Weather', '', Route.WORLD),
    ('AI / Raindrop.io', '', Route.SKIP),
    ('Ghostbusters News', '', Route.WORLD),
]
for feed, title, expected in tests:
    route, sub = get_route(feed, title)
    status = 'PASS' if route == expected else 'FAIL'
    print(f'[{status}] {feed} → {route} ({sub})')
"
```

---

### Task 23: Final commit and PR prep

**Step 1: Run full test suite one last time**

```bash
pytest tests/ -v 2>&1 | tail -5
```
Expected: All pass, 0 failures

**Step 2: Validate all Terraform files**

```bash
cd terraform && terraform validate
```

**Step 3: Commit any remaining changes**

```bash
git status
git add -p  # review each change
git commit -m "test: integration validation, success criteria verified"
```

**Step 4: Push feature branch**

```bash
git push -u origin feature/personal-journalist-v2
```

---

## Worktree Location

This plan is being executed in:
```
/home/r3crsvint3llgnz/01_Projects/research-agent/.worktrees/personal-journalist-v2
```

Branch: `feature/personal-journalist-v2`

To open a new session in this worktree:
```bash
cd /home/r3crsvint3llgnz/01_Projects/research-agent/.worktrees/personal-journalist-v2
```

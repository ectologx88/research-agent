# Raindrop Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a `RaindropClient` that bookmarks high-value classified stories to Raindrop.io with key concepts as tags and "why it matters" as the note, wired into the existing Lambda handler.

**Architecture:** New `src/clients/raindrop.py` mirrors the existing `newsblur.py` client pattern — a class with typed methods, tenacity retry logic, and structured logging. It is instantiated in `lambda_handler.py` and called for each high-value story after classification. Duplicate detection uses Raindrop's own search API before creating a bookmark.

**Tech Stack:** `requests`, `tenacity`, `pydantic-settings` (config), `unittest.mock` (tests) — all already in the project.

---

### Task 1: Add Raindrop config fields to `src/config.py`

**Files:**
- Modify: `src/config.py`

**Step 1: Write the failing test**

Add to a new test file `tests/test_config.py`:

```python
"""Tests for Settings config."""
import pytest
from pydantic import ValidationError


def test_raindrop_defaults(monkeypatch):
    monkeypatch.setenv("NEWSBLUR_USERNAME", "u")
    monkeypatch.setenv("NEWSBLUR_PASSWORD", "p")
    monkeypatch.setenv("RAINDROP_TOKEN", "tok123")
    from importlib import reload
    import src.config as cfg_mod
    reload(cfg_mod)
    s = cfg_mod.Settings()
    assert s.raindrop_token == "tok123"
    assert s.raindrop_collection_id == -1


def test_raindrop_custom_collection(monkeypatch):
    monkeypatch.setenv("NEWSBLUR_USERNAME", "u")
    monkeypatch.setenv("NEWSBLUR_PASSWORD", "p")
    monkeypatch.setenv("RAINDROP_TOKEN", "tok123")
    monkeypatch.setenv("RAINDROP_COLLECTION_ID", "42")
    from importlib import reload
    import src.config as cfg_mod
    reload(cfg_mod)
    s = cfg_mod.Settings()
    assert s.raindrop_collection_id == 42
```

**Step 2: Run test to verify it fails**

```bash
cd /home/r3crsvint3llgnz/01_Projects/research-agent
pytest tests/test_config.py -v
```

Expected: `FAILED` — `Settings` has no `raindrop_token` field.

**Step 3: Add fields to `src/config.py`**

Add at the end of the `Settings` class (after `threshold_dimension`):

```python
    # Raindrop
    raindrop_token: str = ""
    raindrop_collection_id: int = -1  # -1 = Raindrop "Unsorted"
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_config.py -v
```

Expected: 2 PASSED.

**Step 5: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: add Raindrop config fields to Settings"
```

---

### Task 2: Create `src/clients/raindrop.py`

**Files:**
- Create: `src/clients/raindrop.py`
- Create: `tests/test_raindrop_client.py`

#### 2a — `check_duplicate`

**Step 1: Write the failing test**

Create `tests/test_raindrop_client.py`:

```python
"""Tests for the Raindrop API client."""
from unittest.mock import MagicMock, patch, call

import pytest
import requests

from src.clients.raindrop import RaindropClient, RaindropAuthError


class TestCheckDuplicate:
    def _client(self):
        return RaindropClient(token="tok", collection_id=-1)

    def test_returns_true_when_url_found(self):
        client = self._client()
        with patch.object(client, "_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"result": True, "count": 1, "items": [{"link": "https://example.com/story"}]}
            mock_resp.raise_for_status = MagicMock()
            mock_session.get.return_value = mock_resp

            assert client.check_duplicate("https://example.com/story") is True

    def test_returns_false_when_url_not_found(self):
        client = self._client()
        with patch.object(client, "_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"result": True, "count": 0, "items": []}
            mock_resp.raise_for_status = MagicMock()
            mock_session.get.return_value = mock_resp

            assert client.check_duplicate("https://example.com/new") is False

    def test_returns_false_on_empty_url(self):
        client = self._client()
        assert client.check_duplicate("") is False
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_raindrop_client.py::TestCheckDuplicate -v
```

Expected: `FAILED` — `src.clients.raindrop` does not exist.

**Step 3: Create `src/clients/raindrop.py` with `check_duplicate`**

```python
"""Raindrop.io API client with bookmark creation and duplicate detection."""

from typing import List

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.utils import log_structured


class RaindropError(Exception):
    """Base exception for Raindrop client errors."""


class RaindropAuthError(RaindropError):
    """Authentication failed (401)."""


class RaindropClient:
    """Client for the Raindrop.io REST API v1."""

    BASE_URL = "https://api.raindrop.io/rest/v1"

    def __init__(self, token: str, collection_id: int = -1, base_url: str | None = None):
        self._token = token
        self._collection_id = collection_id
        self._base = (base_url or self.BASE_URL).rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {token}"})

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    def check_duplicate(self, url: str) -> bool:
        """Return True if *url* already exists in the target collection."""
        if not url:
            return False
        resp = self._session.get(
            f"{self._base}/raindrops/{self._collection_id}",
            params={"search": f"link:{url}", "perpage": 1},
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("count", 0) > 0
```

**Step 4: Run test to verify it passes**

```bash
pytest tests/test_raindrop_client.py::TestCheckDuplicate -v
```

Expected: 3 PASSED.

---

#### 2b — `create_bookmark`

**Step 1: Write the failing test**

Append to `tests/test_raindrop_client.py`:

```python
class TestCreateBookmark:
    def _client(self):
        return RaindropClient(token="tok", collection_id=99)

    def test_sends_correct_payload(self):
        client = self._client()
        with patch.object(client, "_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"result": True, "item": {"_id": 123}}
            mock_resp.raise_for_status = MagicMock()
            mock_session.post.return_value = mock_resp

            result = client.create_bookmark(
                url="https://example.com/story",
                title="Test Story",
                tags=["ai", "research"],
                note="This matters because of X.",
            )

            call_kwargs = mock_session.post.call_args
            payload = call_kwargs[1]["json"]
            assert payload["link"] == "https://example.com/story"
            assert payload["title"] == "Test Story"
            assert payload["tags"] == ["ai", "research"]
            assert payload["note"] == "This matters because of X."
            assert payload["collection"]["$id"] == 99
            assert result["_id"] == 123

    def test_raises_auth_error_on_401(self):
        client = self._client()
        with patch.object(client, "_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
                response=mock_resp
            )
            mock_session.post.return_value = mock_resp

            with pytest.raises(RaindropAuthError):
                client.create_bookmark("https://x.com", "T", [], "note")

    def test_retries_on_5xx_then_succeeds(self):
        client = self._client()
        with patch.object(client, "_session") as mock_session:
            fail_resp = MagicMock()
            fail_resp.status_code = 503
            fail_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
                response=fail_resp
            )
            ok_resp = MagicMock()
            ok_resp.json.return_value = {"result": True, "item": {"_id": 42}}
            ok_resp.raise_for_status = MagicMock()
            mock_session.post.side_effect = [fail_resp, ok_resp]

            # Patch tenacity to not actually wait
            with patch("src.clients.raindrop.wait_exponential", return_value=lambda *a, **k: 0):
                result = client.create_bookmark("https://x.com", "T", [], "note")
            assert result["_id"] == 42
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_raindrop_client.py::TestCreateBookmark -v
```

Expected: `FAILED` — `create_bookmark` not defined.

**Step 3: Add `create_bookmark` to `src/clients/raindrop.py`**

Add after `check_duplicate`:

```python
    # ------------------------------------------------------------------
    # Bookmark creation
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type(requests.exceptions.RequestException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,
    )
    def create_bookmark(
        self,
        url: str,
        title: str,
        tags: List[str],
        note: str,
    ) -> dict:
        """Create a bookmark in Raindrop. Returns the created item dict.

        Raises:
            RaindropAuthError: On 401 (credentials invalid — do not retry).
            RaindropError: On persistent failure after retries.
        """
        payload = {
            "link": url,
            "title": title,
            "tags": tags,
            "note": note,
            "collection": {"$id": self._collection_id},
        }
        resp = self._session.post(
            f"{self._base}/raindrop",
            json=payload,
            timeout=15,
        )
        if resp.status_code == 401:
            raise RaindropAuthError("Raindrop token invalid or expired (401)")
        resp.raise_for_status()
        data = resp.json()
        log_structured("INFO", "Raindrop bookmark created", url=url, title=title)
        return data["item"]
```

**Step 4: Run all raindrop tests**

```bash
pytest tests/test_raindrop_client.py -v
```

Expected: 6 PASSED.

**Step 5: Commit**

```bash
git add src/clients/raindrop.py tests/test_raindrop_client.py
git commit -m "feat: add RaindropClient with duplicate check and bookmark creation"
```

---

### Task 3: Wire RaindropClient into `lambda_handler.py`

**Files:**
- Modify: `src/lambda_handler.py`

**Step 1: Write the failing test**

Create `tests/test_lambda_raindrop.py`:

```python
"""Integration tests for Raindrop wiring in lambda_handler."""
from unittest.mock import MagicMock, patch, call
import pytest


def _make_story(url="https://example.com/story"):
    s = MagicMock()
    s.story_permalink = url
    s.story_title = "Test Story"
    return s


def _make_classification(overall=9, concepts=["ai"], why="It matters."):
    c = MagicMock()
    c.scores.overall = overall
    c.concepts = concepts
    c.why_matters = why
    return c


def _make_result(pairs):
    r = MagicMock()
    r.classified = pairs
    r.metrics = MagicMock()
    r.metrics.__dict__ = {}
    import dataclasses
    with patch("dataclasses.asdict", return_value={}):
        pass
    return r


@patch("src.lambda_handler.RaindropClient")
@patch("src.lambda_handler.ClassificationService")
@patch("src.lambda_handler.ProcessingStateStorage")
@patch("src.lambda_handler.BedrockClassifier")
@patch("src.lambda_handler.NewsBlurClient")
@patch("src.lambda_handler.Settings")
def test_high_value_stories_sent_to_raindrop(
    mock_settings_cls, mock_nb_cls, mock_bedrock_cls,
    mock_storage_cls, mock_svc_cls, mock_raindrop_cls
):
    import dataclasses

    settings = MagicMock()
    settings.newsblur_username = "u"
    settings.newsblur_password = "p"
    settings.bedrock_region = "us-east-1"
    settings.bedrock_model_id = "model"
    settings.dynamodb_table_name = "table"
    settings.dynamodb_region = "us-east-1"
    settings.threshold_overall = 8
    settings.raindrop_token = "tok"
    settings.raindrop_collection_id = -1
    mock_settings_cls.return_value = settings

    story = _make_story()
    classification = _make_classification(overall=9)
    result = MagicMock()
    result.classified = [(story, classification)]
    result.metrics = MagicMock()
    mock_svc_cls.return_value.run.return_value = result

    raindrop_instance = MagicMock()
    raindrop_instance.check_duplicate.return_value = False
    mock_raindrop_cls.return_value = raindrop_instance

    with patch("dataclasses.asdict", return_value={}):
        from src import lambda_handler
        import importlib
        importlib.reload(lambda_handler)
        response = lambda_handler.lambda_handler({}, {})

    raindrop_instance.check_duplicate.assert_called_once_with(story.story_permalink)
    raindrop_instance.create_bookmark.assert_called_once_with(
        url=story.story_permalink,
        title=story.story_title,
        tags=classification.concepts,
        note=classification.why_matters,
    )
    assert response["body"]["raindrop_sent"] == 1
    assert response["body"]["raindrop_skipped"] == 0


@patch("src.lambda_handler.RaindropClient")
@patch("src.lambda_handler.ClassificationService")
@patch("src.lambda_handler.ProcessingStateStorage")
@patch("src.lambda_handler.BedrockClassifier")
@patch("src.lambda_handler.NewsBlurClient")
@patch("src.lambda_handler.Settings")
def test_duplicate_stories_skipped(
    mock_settings_cls, mock_nb_cls, mock_bedrock_cls,
    mock_storage_cls, mock_svc_cls, mock_raindrop_cls
):
    settings = MagicMock()
    settings.threshold_overall = 8
    settings.raindrop_token = "tok"
    settings.raindrop_collection_id = -1
    mock_settings_cls.return_value = settings

    story = _make_story()
    classification = _make_classification(overall=9)
    result = MagicMock()
    result.classified = [(story, classification)]
    result.metrics = MagicMock()
    mock_svc_cls.return_value.run.return_value = result

    raindrop_instance = MagicMock()
    raindrop_instance.check_duplicate.return_value = True  # already in Raindrop
    mock_raindrop_cls.return_value = raindrop_instance

    with patch("dataclasses.asdict", return_value={}):
        from src import lambda_handler
        import importlib
        importlib.reload(lambda_handler)
        response = lambda_handler.lambda_handler({}, {})

    raindrop_instance.create_bookmark.assert_not_called()
    assert response["body"]["raindrop_skipped"] == 1
```

**Step 2: Run test to verify it fails**

```bash
pytest tests/test_lambda_raindrop.py -v
```

Expected: `FAILED` — `lambda_handler` has no `RaindropClient` import or Raindrop logic.

**Step 3: Update `src/lambda_handler.py`**

Replace the file content with:

```python
"""AWS Lambda entry point for the NewsBlur classification pipeline."""

import dataclasses
import uuid

from src.clients.bedrock import BedrockClassifier
from src.clients.newsblur import NewsBlurClient
from src.clients.raindrop import RaindropAuthError, RaindropClient
from src.config import Settings
from src.services.classifier import ClassificationService
from src.services.storage import ProcessingStateStorage
from src.utils import log_structured, timed, utcnow


def lambda_handler(event, context):
    """Phase 1+2a: NewsBlur Intelligence Pipeline with Raindrop bookmarking.

    Fetches unread stories, classifies them via Bedrock, deduplicates via
    DynamoDB, bookmarks high-value stories to Raindrop, and returns metrics.
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

    # Filter high-value stories
    high_value = [
        (s, c)
        for s, c in result.classified
        if c.scores.overall >= settings.threshold_overall
    ]

    # Phase 2a: Bookmark high-value stories to Raindrop
    raindrop_sent = 0
    raindrop_skipped = 0

    if settings.raindrop_token:
        raindrop = RaindropClient(
            token=settings.raindrop_token,
            collection_id=settings.raindrop_collection_id,
        )
        auth_failed = False

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

                raindrop.create_bookmark(
                    url=story.story_permalink,
                    title=story.story_title,
                    tags=classification.concepts,
                    note=classification.why_matters,
                )
                raindrop_sent += 1

            except RaindropAuthError as exc:
                log_structured("ERROR", "Raindrop auth failed — stopping", error=str(exc))
                auth_failed = True
                raindrop_skipped += len(high_value) - raindrop_sent - 1

            except Exception as exc:
                log_structured(
                    "WARNING",
                    "Raindrop bookmark failed after retries",
                    url=story.story_permalink,
                    error=str(exc),
                )
                raindrop_skipped += 1
    else:
        log_structured("INFO", "Raindrop token not configured, skipping")

    # TODO Phase 2b: Generate and send daily brief via SES

    body = {
        "execution_id": execution_id,
        "timestamp": utcnow().isoformat(),
        "metrics": dataclasses.asdict(result.metrics),
        "high_value_count": len(high_value),
        "raindrop_sent": raindrop_sent,
        "raindrop_skipped": raindrop_skipped,
    }

    log_structured("INFO", "Pipeline finished", **body)

    return {"statusCode": 200, "body": body}
```

**Step 4: Run all tests**

```bash
pytest tests/ -v
```

Expected: All existing tests + new tests PASS. No regressions.

**Step 5: Commit**

```bash
git add src/lambda_handler.py tests/test_lambda_raindrop.py
git commit -m "feat: wire RaindropClient into lambda handler (Phase 2a)"
```

---

### Task 4: Verify IAM policy covers Raindrop SSM parameter

**Files:**
- Inspect: `terraform/iam.tf`

**Step 1: Check the existing IAM policy**

```bash
grep -n "Raindrop\|ssm\|GetParameter" /home/r3crsvint3llgnz/01_Projects/research-agent/terraform/iam.tf
```

**Step 2: If `/prod/ResearchAgent/Raindrop_Token` is NOT covered**

Add it to the SSM `Resource` list in `iam.tf`. Look for the `ssm:GetParameter` action block and add:

```
"arn:aws:ssm:*:*:parameter/prod/ResearchAgent/Raindrop_Token"
```

**Step 3: If already covered (wildcard like `/prod/ResearchAgent/*`)**

No change needed — skip to Task 5.

**Step 4: Commit if changed**

```bash
git add terraform/iam.tf
git commit -m "chore: ensure IAM policy covers Raindrop SSM parameter"
```

---

### Task 5: Run full test suite and verify

**Step 1: Run all tests**

```bash
cd /home/r3crsvint3llgnz/01_Projects/research-agent
pytest tests/ -v --tb=short
```

Expected: All tests PASS (existing 30 + new ~9 = ~39 total).

**Step 2: Verify no import errors**

```bash
python -c "from src.clients.raindrop import RaindropClient; print('OK')"
```

Expected: `OK`

**Step 3: Final commit if any loose files**

```bash
git status
# If clean, nothing to do. If any untracked docs:
git add docs/
git commit -m "docs: update plans with Raindrop integration"
```

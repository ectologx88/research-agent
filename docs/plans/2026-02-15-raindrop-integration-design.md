# Raindrop Integration Design

**Date:** 2026-02-15
**Phase:** 2 (partial — Raindrop only)
**Status:** Approved

## Overview

Add Raindrop.io bookmarking for high-value stories classified by the research-agent pipeline. High-value stories (overall score ≥ `THRESHOLD_OVERALL`, default 8) are automatically bookmarked after classification, with key concepts as tags and the "why it matters" summary as the note.

## Architecture

A new `src/clients/raindrop.py` is added alongside the existing `newsblur.py` and `bedrock.py` clients. It mirrors their structure: a class with typed methods, tenacity retry logic, and structured logging.

`lambda_handler.py` is updated to instantiate the client and process the existing `high_value` list after classification (where the Phase 2 TODO already lives).

No new service layer — the client is wired directly into the handler, consistent with the current architecture.

## Components

### `src/clients/raindrop.py`
- `check_duplicate(url: str) -> bool` — `GET /raindrops/{collection_id}?search=<url>`, returns True if URL already exists
- `create_bookmark(url, title, tags, note) -> dict` — `POST /raindrop` with metadata
- Retry: 3 attempts, exponential backoff 2–15s (tenacity), consistent with existing clients
- Auth failure (401): fail fast, no retry

### `src/config.py`
- Add `RAINDROP_TOKEN: str` — loaded from SSM `/prod/ResearchAgent/Raindrop_Token` (already stored)
- Add `RAINDROP_COLLECTION_ID: int = -1` — defaults to Raindrop "Unsorted" collection

### `src/lambda_handler.py`
- Uncomment/implement Phase 2 TODO block
- For each `(story, classification)` in `high_value`:
  1. Check duplicate by URL
  2. If not duplicate, create bookmark
  3. On failure after retries: log + skip
- Add `raindrop_sent` and `raindrop_skipped` to execution metrics

## Data Flow

```
classifier.py → high_value list → lambda_handler.py
                                        │
                                        ▼
                              for each (story, classification):
                                1. raindrop.check_duplicate(story.url)
                                2. if not duplicate → raindrop.create_bookmark(
                                       url=story.url,
                                       title=story.title,
                                       tags=classification.key_concepts,
                                       note=classification.why_it_matters
                                   )
                                3. retry up to 3x on failure, then skip + log
```

## Bookmark Shape

| Field | Source |
|-------|--------|
| `link` | `story.url` |
| `title` | `story.title` |
| `tags` | `classification.key_concepts` (3–7 strings) |
| `note` | `classification.why_it_matters` (1 sentence) |
| `collection.$id` | `config.RAINDROP_COLLECTION_ID` (default: -1) |

## Error Handling

| Scenario | Behavior |
|----------|----------|
| 5xx / network error | Retry up to 3x with exponential backoff (2–15s), then skip + log |
| 401 Unauthorized | Fail fast, log clearly, skip remaining Raindrop calls for this run |
| Duplicate URL found | Skip silently, increment `raindrop_skipped` |
| Story missing URL | Skip, log warning |

## Metrics

Two new fields added to the Lambda execution response:
- `raindrop_sent`: count of successfully bookmarked stories
- `raindrop_skipped`: count of duplicates + failures

## Testing

New `tests/test_raindrop_client.py`:
- Successful bookmark creation → correct API payload shape
- Duplicate detected → returns True, no POST made
- 5xx triggers retry → succeeds on second attempt
- 3x failure → raises, caller skips story
- 401 → fails fast without retry
- Tag and note correctly mapped from classification model

Uses `unittest.mock` — no new test dependencies.

## IAM

The existing Lambda execution role needs `ssm:GetParameter` for `/prod/ResearchAgent/Raindrop_Token` — verify it's already covered by `terraform/iam.tf` (likely is, given `verify_connections.py` already validates it).

## Out of Scope

- Daily email brief (Phase 2, separate task)
- Zotero integration (Phase 3)
- Raindrop collection auto-creation
- Multiple collections / smart routing by content type

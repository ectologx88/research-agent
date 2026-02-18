# Phase 3 Design: Multi-Lambda Pipeline with Triage and Dual Briefings

**Date:** 2026-02-16
**Status:** Approved

## Overview

Refactor the single monolithic Lambda into a three-Lambda pipeline connected by SQS queues. Replace the LLM-first classification pass with a fast rule-based triage stage. Route stories to separate Raindrop collections. Produce two distinct daily briefings — AI/ML and World — both delivered to the existing briefing collection.

**North star:** The AI/ML briefing eventually publishes daily to the Recursive Intelligence website as an agent-authored post.

---

## Architecture

```
EventBridge (6AM/6PM UTC: cron(0 11,23 * * ? *))
        ↓
┌─────────────────────────┐
│  Lambda 1: Triage       │  < 60s, no LLM
│  - Fetch NewsBlur       │  min_score=1 (focus only)
│  - Deduplicate (DDB)    │
│  - Rule-based triage    │  feed-name → bucket, keyword fallback
│  - Route → Raindrop     │  title + tags immediately, no summary
│  - Store story content  │  DDB story_content records, 24h TTL
└────────────┬────────────┘
             │ two SQS messages
       ┌─────┴──────┐
       ↓            ↓
  ai-ml-queue   world-queue
       ↓            ↓  (parallel, independent)
┌─────────────────────────┐
│  Lambda 2: Summarizer   │  Haiku per story
│  - Fetch stories (DDB)  │
│  - Summarize + score    │
│  - Update Raindrop note │
│  - Send to briefing Q   │
└────────────┬────────────┘
             ↓
       briefing-queue
             ↓
┌─────────────────────────┐
│  Lambda 3: Briefing     │  Sonnet 4.5
│  - Synthesize narrative │
│  - Post to Raindrop     │  → briefing collection
└─────────────────────────┘
```

---

## Lambda 1: Fetch + Triage

**Trigger:** EventBridge cron `cron(0 11,23 * * ? *)` (6AM/6PM US Central)
**Timeout:** 60s
**No LLM calls**

### NewsBlur Fetch
- `min_score=1` — focus-scored stories only (user-trained signal)
- `max_results=150`
- Deduplication via DynamoDB as today

### Triage Buckets

| Bucket | Raindrop Collection | SQS Queue |
|--------|--------------------|-----------|
| `ai-ml` | AI/ML Feed (public) | `research-agent-ai-ml` |
| `world` | World Digest (private) | `research-agent-world` |
| `skip` | Nowhere | — |

**Tech, Science, Weather all route to `world` bucket** (sub-tagged for briefing sections).

### Triage Rules

**Step 1 — Feed-name lookup** (configurable dict, no deploy needed to update):
```python
FEED_RULES = {
    # AI/ML
    "arxiv": "ai-ml",
    "papers with code": "ai-ml",
    "hugging face": "ai-ml",
    "towards data science": "ai-ml",
    "the gradient": "ai-ml",
    "import ai": "ai-ml",
    # Tech → world/tech
    "hacker news": None,          # ambiguous — use keyword fallback
    "the verge": "world/tech",
    "techcrunch": "world/tech",
    "ars technica": "world/tech",
    "wired": None,                # ambiguous
    # Science → world/science
    "science daily": "world/science",
    "nature": "world/science",
    "new scientist": "world/science",
    # World/News → world/news
    "bbc": "world/news",
    "npr": "world/news",
    "reuters": "world/news",
    "ap news": "world/news",
    "new york times": "world/news",
    # Weather → world/weather
    "weather underground": "world/weather",
    "national weather service": "world/weather",
    # Skip
    "espn": "skip",
    "bleacher report": "skip",
}
```
Matching is case-insensitive substring match on `story_feed_title`.

**Step 2 — Keyword fallback** (for ambiguous feeds or unrecognized sources):
```python
AI_ML_KEYWORDS = [
    "llm", "gpt", "claude", "gemini", "mistral", "llama",
    "neural", "transformer", "diffusion", "reinforcement learning",
    "machine learning", "artificial intelligence", " ai ", "deep learning",
    "foundation model", "fine-tun", "rag ", "embedding",
]
TECH_KEYWORDS = [
    "iphone", "android", "google", "microsoft", "apple",
    "startup", "open source", "github", "developer", "programming",
    "software", "hardware", "chip", "semiconductor",
]
```
If title matches AI_ML_KEYWORDS → `ai-ml`
If title matches TECH_KEYWORDS → `world/tech`
Otherwise → `world/news`

### Raindrop Routing (immediate, no summary)
- Story saved with: title, URL, tags = [bucket, sub-bucket, feed_title]
- No `note` field yet — added by Lambda 2

### DynamoDB Story Content Record
```
record_type: "story_content"
identifier:  <story_hash>
TTL:         now + 86400 (24h)
data: {
  title, url, content, feed_title,
  bucket, sub_bucket, newsblur_score,
  raindrop_id  (returned by create_bookmark)
}
```

### SQS Messages
One message per briefing type per run:
```json
{
  "briefing_type": "ai-ml",
  "run_date": "2026-02-16",
  "time_of_day": "morning",
  "story_hashes": ["abc123", "def456"]
}
```

---

## Lambda 2: Summarizer

**Trigger:** SQS (`research-agent-ai-ml` and `research-agent-world`)
**Timeout:** 900s
**Model:** Claude Haiku (`us.anthropic.claude-3-5-haiku-20241022-v1:0`)

### Per-Story Summary

**AI/ML stories** — field-wide perspective, audience-agnostic:
- 2-3 sentence summary of the work/announcement
- 1 sentence on why it matters to the AI/ML field and how it connects to the evolving landscape
- Score 1-10: significance to the broader AI/ML field

**World stories** — digestible, general reader:
- 2-3 sentence summary
- 1 sentence on significance to an informed person
- Score 1-10: newsworthiness/importance

### Score Thresholds for Briefing
- AI/ML: pass to briefing if score ≥ 6
- World: pass to briefing if score ≥ 5

Stories below threshold: still saved in Raindrop, not included in briefing.

### Raindrop Update
Updates the existing bookmark's `note` field with the summary (using Raindrop's PUT /raindrop/{id} endpoint).

### SQS Output to Briefing Queue
```json
{
  "briefing_type": "ai-ml",
  "run_date": "2026-02-16",
  "time_of_day": "morning",
  "stories": [
    {
      "title": "...",
      "url": "...",
      "summary": "...",
      "why_matters": "...",
      "score": 8,
      "sub_bucket": "ai-ml",
      "tags": ["#ai-research"]
    }
  ]
}
```

Sends message even if some stories failed summarization (partial is better than no briefing).
Skips sending if fewer than 3 stories passed threshold.

---

## Lambda 3: Briefing

**Trigger:** SQS (`research-agent-briefing`)
**Timeout:** 300s
**Model:** Claude Sonnet 4.5 (`us.anthropic.claude-sonnet-4-5-20250929-v1:0`)

> **Model upgrade note (2026-02-17):** Production now uses Sonnet 4.6. See `docs/plans/2026-02-17-upgrade-briefing-model-sonnet-4-6.md`.

### AI/ML Briefing Sections
1. **Executive Summary** — 3-5 bullets, most critical items
2. **Key Research** — top papers/findings with context
3. **Industry Moves** — company news, product launches, funding
4. **Policy & Society** — regulation, ethics, societal impact
5. **Weak Signals** — emerging patterns worth watching

**Tone:** Thoughtful technology analyst writing for an informed AI/ML audience. Broad and accessible — not personalized to any individual.

### World Briefing Sections
1. **World & Nation** — top geopolitical and national stories
2. **Science** — notable discoveries and breakthroughs
3. **Tech & Geek Culture** — important product launches, developer news, hype events worth knowing
4. **Local & Weather** — local conditions and forecast

**Tone:** Concise morning/evening digest — what an informed person needs to know today.

### Delivery
- Both briefings → existing Raindrop briefing collection
- Synthetic duplicate-safe URL: `https://newsblur.com/briefing/{date}-{morning|evening}-{ai-ml|world}`
- Duplicate check before synthesis
- Title format: `"AI/ML Morning Briefing — Feb 16, 2026"` / `"World Morning Briefing — Feb 16, 2026"`

---

## Raindrop Collections

| Collection | Visibility | Contents |
|------------|------------|---------|
| AI/ML Feed | **Public** (shareable RSS) | AI/ML stories with summaries |
| World Digest | Private | World/Tech/Science/Weather stories with summaries |
| Briefings | Private (for now) | Both daily briefings |

**Future:** AI/ML briefing published to Recursive Intelligence website as a daily agent-authored post.

---

## Infrastructure Changes

### New SQS Queues (Terraform)
- `research-agent-ai-ml` — standard queue, 15min visibility timeout
- `research-agent-world` — standard queue, 15min visibility timeout
- `research-agent-briefing` — standard queue, 5min visibility timeout

### New SSM Parameters
- `/prod/ResearchAgent/Raindrop_AiMl_Collection_Id`
- `/prod/ResearchAgent/Raindrop_World_Collection_Id`

### Lambda Changes
- `research-agent-triage` — replaces `research-agent-classifier`
- `research-agent-summarizer` — new
- `research-agent-briefing` — new (extracted from current handler)

### DynamoDB
- New item type `story_content` alongside existing `story` and `config` records
- Same table, same composite key schema

---

## What Gets Removed

- Current Bedrock classification pass (importance scores, taxonomy tags, priority flags)
- `RAINDROP_BRIEFING_COLLECTION_ID` env var replaced by `RAINDROP_AIML_COLLECTION_ID` + `RAINDROP_WORLD_COLLECTION_ID`
- `src/clients/bedrock.py` classification prompt (replaced by summarizer prompt)
- `src/models/classification.py` TaxonomyTag, PriorityFlag, RelevanceScores

---

## Out of Scope (Phase 3)

- Publishing AI/ML briefing to website
- Email/SMS delivery
- User-facing feed configuration UI
- Feedback loop from Raindrop engagement back to triage rules

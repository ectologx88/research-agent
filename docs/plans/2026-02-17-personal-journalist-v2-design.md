# Personal Journalist Engine v2.0 — Design Document
**Date**: 2026-02-17
**Branch**: `feature/personal-journalist-v2`
**Status**: Approved, ready for implementation planning

---

## Mission

Refactor the research-agent from a content aggregator into a dual-stream daily "Personal Journalist" system. Two publications, two editorial voices, one AWS pipeline. The system must feel like two dedicated editors — not a feed reader.

**The AI Abstract** — public, industrial AI intelligence brief for an AI Adoption Consultant at a German chemical manufacturer. Three-level structure: Frontier → Enterprise → Equalizer Angle. The thesis: AI is the great equalizer.

**The Recursive Briefing** — private, personal morning/evening dispatch for Seth. Narrative format. Grounded in Pasadena, TX weather and local news. Synthesizes the texture of the day across technology, culture, science, and the human experience.

---

## Architecture Decision: Approach C (Hybrid)

**What stays the same:**
- `src/handlers/` — three Lambda entry points at paths Terraform already knows
- `src/clients/` — `newsblur.py`, `raindrop.py`, Bedrock clients
- `src/services/` — enhanced in place
- `terraform/` — existing files updated, new files added
- **Bedrock for all LLM calls** (Haiku for Lambda 2, ~~Sonnet 4.5~~ **Sonnet 4.6** for Lambda 3) — no switch to direct Anthropic API

> **Model upgrade note (2026-02-17):** Updated from Sonnet 4.5 → 4.6. See `docs/plans/2026-02-17-upgrade-briefing-model-sonnet-4-6.md`.

**What gets added:**
```
research-agent/
├── config/
│   ├── feed_rules.py        # routing rules, seeded from actual NewsBlur feeds
│   ├── keywords.py          # boost/penalize keyword lists
│   └── scoring_weights.py   # per-stream thresholds and parameters
│
├── shared/
│   ├── dynamodb_client.py   # unified typed DDB operations (3 tables)
│   └── logger.py            # structured JSON logger for CloudWatch Logs Insights
│
├── src/
│   ├── handlers/            # unchanged entry points
│   │   ├── triage_handler.py      # + context injection, scoring passthrough
│   │   ├── summarizer_handler.py  # + editorial scoring, idempotency, parallel
│   │   └── briefing_handler.py    # + dual personas, templates, archive, stub
│   ├── clients/             # unchanged
│   └── services/
│       ├── triage.py        # delegates to config/feed_rules.py
│       ├── context_loader.py     # NEW: weather + local RSS
│       ├── personas.py           # NEW: two editorial system prompts
│       ├── synthesizer.py        # NEW: template rendering + Sonnet call
│       └── storage.py            # enhanced: 3-table schema
│
├── terraform/
│   ├── dynamodb.tf          # + 3 new tables
│   ├── eventbridge.tf       # NEW: 11:00 UTC / 23:00 UTC crons
│   ├── cloudwatch.tf        # NEW: cost alarms, DLQ alarms, funnel dashboard
│   └── iam.tf               # expanded Lambda permissions
│
├── scripts/
│   └── dry_run.py           # NEW: full pipeline simulation, zero cost
│
└── docs/plans/
    └── website-integration.md  # NEW: placeholder for future blog integration
```

---

## Data Flow

```
EventBridge (11:00 UTC / 23:00 UTC)
    → Lambda 1: Triage (no LLM, <60s)
        Fetch NewsBlur (min_score=1, last 12h)
        Deduplicate against story_staging DDB (24h window)
        Route each story → AI_ML | WORLD | SKIP
        Apply boost/penalize tags + velocity clustering
        Fetch context block (weather + local RSS) — stored with batch
        Save to Raindrop (title + tags only, no summary yet)
        Write to story_staging DDB (status: "pending")
        Update signal_tracker DDB for keyword clusters
        Send story_ids to ai-ml-queue AND world-queue

    → Lambda 2: Editorial Filter + Summarizer (Haiku, parallel×10)
        Triggered by SQS (ai-ml-queue or world-queue)
        Fetch stories from story_staging DDB (reads content field)
        Skip status != "pending" (idempotency)
        Score each story: integrity + relevance + novelty (1–5 each)
        PASS: AI_ML threshold 9/15, WORLD threshold 8/15
        Set source_type field per story
        If fewer than 3 pass → log, bail, do NOT send to briefing-queue
        Update DDB: status → "summarized" | "rejected"
        Update Raindrop bookmark note with summary (PASS only)
        Mark rejected stories as read in NewsBlur
        Send passing story_ids to briefing-queue

    → Lambda 3: Briefing Synthesizer (Sonnet 4.5)
        Triggered by SQS (briefing-queue)
        Fetch summarized stories from story_staging DDB
        Query signal_tracker for current Weak Signals state → inject into prompt
        Query briefing_archive for prior edition → inject for continuity
        Branch on briefing_type → select persona + template
        Branch on briefing_type → inject context block (Zeitgeist ONLY)
        Call Sonnet 4.5 → render briefing markdown
        Post to Raindrop briefing collection
        Write to briefing_archive DDB (30d TTL)
        Update story status → "briefed"
        [FUTURE: POST to website webhook — see docs/plans/website-integration.md]
```

---

## Section 1: Config Layer

### `config/feed_rules.py` — seeded from actual NewsBlur subscriptions (44 feeds)

```python
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

# Route everything to Recursive Briefing
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

# Route to WORLD with sub-tag "science"
# Phys. Rev. Lett. and NeuroLogica are directly relevant to RDD framework
ALWAYS_SCIENCE = {
    "Nature - Issue - nature.com science feeds",
    "Recent Articles in Phys. Rev. Lett.",
    "Latest Science News -- ScienceDaily",
    "Science",
    "NeuroLogica Blog",
}

# Route to WORLD with sub-tag "entertainment"
# Lambda 2 clears or rejects based on cultural weight / personal relevance
ALWAYS_ENTERTAINMENT = {
    "Ghostbusters News",
    "Apple Newsroom",
    "9to5Mac",
    "MacRumors: Mac News and Rumors - All Stories",
    "Google Workspace Updates",
    "The Keyword",
}

# Reddit aggregators — route by keyword, default AI_ML
# saved/upvoted by gbninjaturtle: Seth's own curated picks → boost:user-curated
REDDIT_FEEDS = {
    "top scoring links : MachineLearning",  # → AI_ML
    "top scoring links : artificial",       # → AI_ML (keyword fallback)
    "top scoring links : neuroscience",     # → WORLD/science
    "top scoring links : science",          # → WORLD/science
    "top scoring links : apple",            # → WORLD/tech
    "ClaudeAI",                             # → AI_ML
    "cognitive science",                    # → WORLD/science
    "saved by gbninjaturtle",               # → AI_ML default, boost:user-curated
    "upvoted by gbninjaturtle",             # → AI_ML default, boost:user-curated
}

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
# These are the only feeds that never enter the pipeline
ALWAYS_SKIP = {
    "AI / Raindrop.io",   # circular — Seth's own Raindrop RSS export
    "The NewsBlur Blog",  # meta — RSS reader product news
}
```

**Routing precedence:**
1. `ALWAYS_SKIP` — immediate exit, no DDB write
2. `ALWAYS_AI_ML` / `ALWAYS_WORLD` / `ALWAYS_SCIENCE` / `ALWAYS_ENTERTAINMENT` — deterministic
3. `REDDIT_FEEDS` — route by keyword, apply `boost:user-curated` for saved/upvoted feeds
4. `AMBIGUOUS_FEEDS` — keyword fallback, default WORLD/tech
5. All others — keyword fallback, default WORLD/news

### Boost tag assignment (Lambda 1)

```python
# Applied during triage, stored in DDB, passed through to Lambda 3
boost_tags = []

if feed in REDDIT_FEEDS and "gbninjaturtle" in feed:
    boost_tags.append("boost:user-curated")

if any(kw in title_lower for kw in DEMOCRATIZATION_KEYWORDS):
    boost_tags.append("boost:open-source")

if any(kw in title_lower for kw in INDUSTRIAL_KEYWORDS):
    boost_tags.append("boost:industrial")

if any(kw in title_lower for kw in RDD_KEYWORDS):
    # consciousness, emergence, quantum, information theory, cognitive architecture
    boost_tags.append("long-signal:rdd")
```

### Velocity clustering algorithm (Lambda 1)

Pure Python — no ML libraries.

```python
import re
from collections import Counter

STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "have", "will",
    "are", "was", "been", "has", "its", "into", "over", "says", "said",
    "new", "can", "may", "also", "more", "than", "but", "not", "how",
}

def tokenize(title: str) -> set[str]:
    """Lowercase, strip non-alpha, drop stopwords, keep tokens >= 4 chars."""
    tokens = re.sub(r"[^a-z0-9 ]", " ", title.lower()).split()
    return {t for t in tokens if len(t) >= 4 and t not in STOPWORDS}

def compute_clusters(stories: list) -> dict[str, tuple[int, str]]:
    """
    Returns: {story_hash: (cluster_size, cluster_key)}
    cluster_size = number of stories sharing >= 2 tokens with this story
    cluster_key = most frequent shared token across the cluster
    """
    token_sets = {s.story_hash: tokenize(s.story_title) for s in stories}
    results = {}
    for story in stories:
        my_tokens = token_sets[story.story_hash]
        shared_token_counts: Counter = Counter()
        cluster_size = 0
        for other_hash, other_tokens in token_sets.items():
            if other_hash == story.story_hash:
                continue
            shared = my_tokens & other_tokens
            if len(shared) >= 2:
                cluster_size += 1
                shared_token_counts.update(shared)
        cluster_key = shared_token_counts.most_common(1)[0][0] if shared_token_counts else ""
        results[story.story_hash] = (cluster_size, cluster_key)
    return results
```

- `cluster_size >= 3` → tag as Lead Story candidate; highest-scoring story in cluster wins in Lambda 3
- `cluster_key` is written to `story_staging` DDB and used by Lambda 3 to group Lead Stories
- Lambda 3 uses `cluster_size >= 3` to float a story to the top of its section regardless of score rank

### Sub-bucket assignment table

| Feed set | briefing_type | sub_bucket |
|---|---|---|
| ALWAYS_AI_ML | AI_ML | "research" |
| REDDIT_FEEDS → AI_ML | AI_ML | "research" |
| AMBIGUOUS_FEEDS → AI_ML (keyword) | AI_ML | "research" |
| ALWAYS_WORLD | WORLD | "news" |
| ALWAYS_SCIENCE | WORLD | "science" |
| Ghostbusters News (ALWAYS_ENTERTAINMENT) | WORLD | "entertainment" |
| Apple Newsroom, 9to5Mac, MacRumors, Google Workspace, The Keyword | WORLD | "tech" |
| REDDIT_FEEDS → WORLD/science | WORLD | "science" |
| REDDIT_FEEDS → WORLD/tech | WORLD | "tech" |
| AMBIGUOUS_FEEDS → WORLD (default) | WORLD | "tech" |

Note: `sub_bucket = "entertainment"` is reserved for Ghostbusters News only. Apple/Google product feeds are `sub_bucket = "tech"` and render as normal `Dispatch: Technology` entries in Zeitgeist, not parenthetical asides.

---

## Section 2: Lambda 2 — Editorial Filter + Summarizer

Lambda 2 is the real editorial filter. Lambda 1 passes ~30–40 raw candidates per stream. Lambda 2 reduces this to ≤15 AI/ML + ≤10 World for the briefing.

### Scoring prompts

```python
SCORE_AI_ML = """
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

Boost tags from triage are provided — use them to inform relevance scoring.
boost:open-source → elevate relevance (democratization thesis)
boost:industrial → elevate relevance (Seth's native territory)
long-signal:rdd → never penalize; these are long-horizon signals

Return ONLY valid JSON — no explanation, no markdown:
{
  "integrity": <1-5>,
  "relevance": <1-5>,
  "novelty": <1-5>,
  "total": <sum>,
  "decision": "PASS" | "REJECT",
  "source_type": "peer-reviewed" | "journalism" | "commentary" | "single-source",
  "reasoning": "<one sentence — why it passes or fails>",
  "summary": "<two sentences if PASS: what happened + why it matters for enterprise AI. null if REJECT>"
}

Threshold: PASS if total >= 9.

Story title: {title}
Story content: {content}
Feed: {feed_name}
Sub-bucket: {sub_bucket}
Boost tags: {boost_tags}
"""

SCORE_WORLD = """
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

NOVELTY: Is this genuinely new, or a daily churn story that will look the same
tomorrow?

Return ONLY valid JSON — no explanation, no markdown:
{
  "integrity": <1-5>,
  "relevance": <1-5>,
  "novelty": <1-5>,
  "total": <sum>,
  "decision": "PASS" | "REJECT",
  "source_type": "peer-reviewed" | "journalism" | "commentary" | "single-source",
  "reasoning": "<one sentence — why it passes or fails>",
  "summary": "<two sentences if PASS: core facts + why it matters. null if REJECT>"
}

Threshold: PASS if total >= 8.

Story title: {title}
Story content: {content}
Feed: {feed_name}
Sub-bucket: {sub_bucket}
Boost tags: {boost_tags}
"""
```

### Lambda 2 handler logic

```python
# Parallel Haiku calls via ThreadPoolExecutor(max_workers=10)
# For each story:
#   → score_and_summarize(story, stream_type)
#   → PASS: update DDB status="summarized", store summary + scores + source_type
#            update Raindrop bookmark note with summary
#   → REJECT: update DDB status="rejected", store reasoning
#              newsblur_client.mark_as_read(story_hash)
#
# Raindrop updates (PASS stories only): use threading.Semaphore(5) to cap
# concurrent Raindrop API calls at 5. Do not fire-and-forget from ThreadPoolExecutor
# without the semaphore — flaky behavior under load.
#
# If fewer than 3 stories pass threshold → log + bail, do NOT send to briefing-queue
#   Cleanup: Lambda 1 Raindrop bookmarks for this batch are left as-is (title + tags, no note).
#   They will drain from story_staging on 24h TTL. This is acceptable — documented behavior,
#   not a bug. Do not add a cleanup step.
#
# Send to briefing-queue: passing story_ids only
```

### Story payload to Lambda 3

```json
{
  "story_hash": "...",
  "title": "...",
  "url": "...",
  "feed_name": "...",
  "sub_bucket": "research",
  "summary": "Two-sentence editorial summary.",
  "source_type": "peer-reviewed",
  "scores": { "integrity": 5, "relevance": 4, "novelty": 4, "total": 13 },
  "reasoning": "First open-source release of a distilled Llama variant with deployment guide.",
  "boost_tags": ["boost:open-source", "long-signal:rdd"],
  "cluster_size": 2
}
```

---

## Section 3: Context Injection Layer

**`src/services/context_loader.py`** — runs in Lambda 1 at triage time. Result stored in `story_staging` DDB with the batch. Lambda 3 reads it — the timestamp reflects Lambda 1's fetch time, never Lambda 3's run time.

### Data sources

**Open-Meteo API** (free, no key required):
- lat: 29.6911, lon: -95.2091 (Pasadena, TX)
- Current temp °F, today high/low, conditions, wind mph, precipitation expected

**Space City Weather RSS** (`https://spacecityweather.com/feed/`):
- Independent RSS pull — does NOT depend on whether the feed scored in triage
- Top 1–2 headlines for the context block regardless of story score
- Space City Weather also comes through normal triage as a scoreable story — both paths are intentional

**NWS Alerts API** (`https://api.weather.gov/alerts/active?zone=TXZ163`):
- Harris County active alerts
- Explicit guard: if `features` key missing or not a list → treat as no alerts, log WARNING, do not raise
- Empty list = no mention in context block

### Context block format

```
[SYSTEM_CONTEXT_BLOCK — Deterministic Data, Do Not Contradict]
Location: Pasadena, TX (Houston metro) | {fetched_at} UTC

WEATHER:
Current: {temp_f}°F, {condition}
Today: High {high_f}°F / Low {low_f}°F | Wind: {wind_mph} mph
Precipitation: {precip_in} in. expected
⚠️ ACTIVE ALERTS: {alert_headlines}   ← omitted entirely if none

LOCAL:
- {space_city_headline_1}
- {space_city_headline_2}
[END SYSTEM_CONTEXT_BLOCK]
```

### Injection scope

The `[SYSTEM_CONTEXT_BLOCK]` is injected **only into the Zeitgeist (Recursive Briefing) prompt**. It is never injected into the Equalizer (AI Abstract) prompt. Lambda 3 branches on `briefing_type` before building the prompt.

### Failure handling

Any single source failure (timeout, 503, parse error, schema surprise) is logged and skipped. Lambda 1 does not fail because weather is down. The context block is best-effort.

### Behavioral rules in Zeitgeist persona prompt

- If `ACTIVE ALERTS` present: weather surfaces in The Local Beat regardless of news day weight
- If alert contains `TORNADO_WARNING` or `HURRICANE`: surfaces in The Lede, not just The Local Beat

---

## Section 4: Dual Personas + Output Templates

### `src/services/personas.py`

**`PROMPT_EQUALIZER`** — The AI Abstract persona:
- Voice: authoritative practitioner, "from inside the enterprise" — not "experts say"
- Three-level structure per story: Frontier → Enterprise → Equalizer Angle
- `source_type` → emoji indicator rendered inline on every link
- `integrity <= 2` → explicit `⚠️ single-source/unverified` flag in body text
- `long-signal:rdd` stories → dedicated RDD Signal section (omitted entirely if empty — no filler)
- `boost:user-curated` → Lambda 3 calls out explicitly ("you saved this")
- `cluster_size >= 3` → Lead Story, rises to top regardless of score rank
- Context block: NOT injected

Source type emoji mapping:
```
peer-reviewed  → 🔬
journalism     → 📰
commentary     → 🎙️
single-source  → ⚠️
```

**`PROMPT_ZEITGEIST`** — The Recursive Briefing persona:
- Voice: seasoned foreign correspondent, narrative not list
- Context block injected — woven naturally, never announced mechanically
- `sub_bucket == "entertainment"` → write as one-sentence aside woven into an adjacent section (Lede parenthetical or Read List). Never a standalone Dispatch section.
- Same source credibility emoji rendering
- Identifies emotional register of the news cycle explicitly

### Output templates in `src/services/synthesizer.py`

**Equalizer structure:**
```
# ⚖️ The AI Abstract
**Making the Future Evenly Distributed.**
*{date} | {edition} Edition*

Editorial: State of Play         (150 words, dominant shift in last 12h)
The Level Playing Field Report   (up to 8 stories, three-level structure)
RDD Signal                       (long-signal:rdd stories — OMIT SECTION IF EMPTY)
Open Source Watch                (boost:open-source stories)
Weak Signals                     (from signal_tracker — injected into prompt)
For Your Raindrop Collection     (max 5 curated links)
Notable Omissions
Action Items                     (Today / This Week)
```

**Zeitgeist structure:**
```
# 🌍 The {day} Dispatch
**{date} | Pasadena, TX**

The Lede                         (2 paragraphs, must anchor to ≥1 specific story)
The Local Beat                   (weather + Houston, correspondent on the ground)
Dispatch: [Domain 1]             (2–3 stories, rotating by importance)
Dispatch: Science & Discovery    (always present)
The Read List                    (max 5 links with source indicators)
Notable Omissions
One thing to carry into the day  (single sentence — not a list)
```

### Prior briefing continuity

Lambda 3 queries `briefing_archive` for the immediately preceding edition before calling Sonnet:
- AM run → query yesterday's PM briefing (`{yesterday}-PM`)
- PM run → query today's AM briefing (`{today}-AM`)

If no prior briefing exists, omit silently. Sonnet can reference the prior edition for trend continuity (e.g., "Third mention of evaluation crisis this week").

### Weak Signals injection

Lambda 3 explicitly queries `signal_tracker` DDB and injects current signal state into the prompt payload before calling Sonnet. If signal data is not fetched and injected, Sonnet must not attempt to generate this section. The data is in the payload — not an assumption.

---

## Section 5: DynamoDB Schema

### `story_staging` (new table — coexists with `newsblur-processing-state` during transition)

```
PK: story_hash (String)
SK: briefing_type (String) — "AI_ML" | "WORLD"

Lambda 1 writes:
  title (String)
  url (String)
  content (String)          — story_content from NewsBlur, truncated at 8000 chars.
                              Truncation: strip at last whitespace boundary before 8000 chars,
                              append " [truncated]" so Lambda 2 knows it is working with partial content.
  feed_name (String)
  sub_bucket (String)       — research | industry | entertainment | weather | science | tech | news
  boost_tags (List)
  cluster_size (Number)
  context_block (String)    — JSON blob with fetched_at + weather + local headlines
  raindrop_id (String)
  status (String)           — "pending"
  created_at (String, ISO8601)
  ttl (Number)              — Unix timestamp, 24h from creation

Lambda 2 writes:
  status → "summarized" | "rejected"
  summary (String)          — null if rejected
  source_type (String)
  scores (Map)              — {integrity, relevance, novelty, total}
  reasoning (String)

Lambda 3 writes:
  status → "briefed"
  briefing_date (String)    — "2026-02-17-AM"
```

**Migration note**: Do not migrate `newsblur-processing-state`. Create `story_staging` as a new table. Both tables coexist during the transition window. Old table can be deleted 24 hours after the new code is deployed and verified.

### `signal_tracker` (new table)

```
PK: signal_key (String) — normalized keyword/theme e.g. "evaluation-crisis"
  mention_count (Number)
  first_seen (String, ISO8601)
  last_seen (String, ISO8601)
  example_stories (List)    — last 3 story hashes
  ttl (Number)              — Unix timestamp, NOW + 7 days, recalculated and
                              explicitly written on EVERY update (not just creation)
```

### `briefing_archive` (new table)

```
PK: briefing_date (String) — "2026-02-17-AM"
SK: briefing_type (String) — "AI_ML" | "WORLD"
  content (String)          — full markdown output
  candidate_count (Number)  — stories Lambda 1 sent to Lambda 2
  passed_count (Number)     — stories Lambda 2 passed to Lambda 3
  story_count (Number)      — stories that made the briefing
  raindrop_id (String)
  ttl (Number)              — 30 days
```

### Processing state machine

```
Lambda 1 → pending
Lambda 2 → summarized | rejected
Lambda 3 → briefed

Idempotency: Lambda 2 skips status != "pending"
             Lambda 3 skips stories where status != "summarized"
Minimum threshold: fewer than 3 PASS → Lambda 2 logs and bails, no briefing-queue message
DLQ: 3 failed attempts → dead letter queue → CloudWatch alarm
```

---

## Section 6: Infrastructure

### EventBridge (`terraform/eventbridge.tf` — new)

```hcl
# 11:00 UTC = 6AM CDT (summer) / 5AM CST (winter) — acceptable drift for a news briefing
# 23:00 UTC = 6PM CDT (summer) / 5PM CST (winter)
resource "aws_cloudwatch_event_rule" "morning_triage" {
  schedule_expression = "cron(0 11 * * ? *)"
  tags = { Project = "research-agent", Environment = "prod", ManagedBy = "terraform" }
}
resource "aws_cloudwatch_event_rule" "evening_triage" {
  schedule_expression = "cron(0 23 * * ? *)"
  tags = { Project = "research-agent", Environment = "prod", ManagedBy = "terraform" }
}
```

### SQS — DLQs added (`terraform/sqs.tf` additions)

```hcl
# briefing_dlq alarm threshold: depth > 0 (failed briefing always worth alerting)
# ai_ml_dlq and world_dlq alarm threshold: depth > 2 (avoid false alerts from transient timeouts)
# All queues: maxReceiveCount = 3 before DLQ
# DLQ retention: 7 days
```

All resources tagged: `Project = "research-agent"`, `Environment = "prod"`, `ManagedBy = "terraform"`

### CloudWatch (`terraform/cloudwatch.tf` — new)

- Cost alarm: custom metric `PersonalJournalist/Cost::estimated_api_cost` — alert if daily total > $3.00
- DLQ depth alarms (thresholds above)
- Story funnel dashboard: fetched → candidates → passed → briefed per run
- Lambda 1 duration alarm: > 55s (approaching 60s timeout)

### IAM (`terraform/iam.tf` additions)

| Lambda | Table | Permissions |
|--------|-------|-------------|
| Lambda 1 | story_staging | PutItem |
| Lambda 1 | signal_tracker | PutItem, UpdateItem |
| Lambda 1 | ai-ml-queue, world-queue | sqs:SendMessage |
| Lambda 2 | story_staging | GetItem, UpdateItem |
| Lambda 3 | story_staging | Query |
| Lambda 3 | signal_tracker | Query (specific keys — NOT Scan) |
| Lambda 3 | briefing_archive | PutItem, GetItem |

### DRY_RUN modes

`DRY_RUN=true` — no LLM calls anywhere:
- Lambda 1: full triage + routing runs, no DDB writes, no Raindrop calls, no SQS sends. Logs routing decisions.
- Lambda 2: mocks Haiku with hardcoded PASS at score 9 (`integrity:3, relevance:3, novelty:3`), logs what the prompt would have been.
- Lambda 3: full prompt built and logged, no Sonnet call, no Raindrop write.
- Cost: ~$0.00

`DRY_RUN=writes_only` — LLM calls run, no writes or external API calls:
- Lambda 2 runs real Haiku scoring, logs decisions and scores, no DDB/Raindrop updates.
- Lambda 3 calls real Sonnet, logs briefing output, no Raindrop write or briefing_archive write.
- Cost: normal Haiku + Sonnet token cost

---

## Section 7: Remaining Pieces

### `shared/dynamodb_client.py`

Unified typed DDB operations for all three handlers. Typed methods:
- `store_story(story_data)` — Lambda 1
- `update_story_status(hash, type, status, **fields)` — Lambda 2
- `get_signal(signal_key)` / `upsert_signal(signal_key, story_hash)` — Lambda 1 + 3
- `store_briefing(briefing_data)` — Lambda 3
- `get_prior_briefing(date, type)` — Lambda 3

No raw `boto3.resource` calls scattered across handlers.

### `shared/logger.py`

Emits structured JSON to stdout. CloudWatch Logs Insights can query on fields:
`routing_decision`, `story_hash`, `editorial_score`, `feed_name`, `briefing_type`, etc.

Do not simply re-export `src/utils.py::log_structured`. The new version must write JSON, not plain text.

### `scripts/dry_run.py`

Loads credentials from SSM via `seth-dev` profile (same pattern as `verify_connections.py`). Invokes triage handler directly with `DRY_RUN=true`. Prints:

```
DRY RUN — 2026-02-17 11:02 UTC
Fetched: 38 stories
Deduplicated: 6 (already seen)

Routing decisions:
  AI_ML  (18): cs.AI[3], Hacker News[4], Anthropic[2], ClaudeAI[3], WIRED[2], ...
  WORLD  (11): BBC[2], NYT[3], Space City Weather[1], ProPublica[1], ...
  SKIP   ( 3): AI/Raindrop.io[1], NewsBlur Blog[2]

Boost tags applied: boost:open-source×4, boost:user-curated×2, long-signal:rdd×1
Velocity clusters: "evaluation crisis"[3 sources] → Lead Story candidate

Editorial filter (mock, DRY_RUN=true):
  Would pass: 14/18 AI_ML candidates (threshold 9/15)
  Would pass:  8/11 WORLD candidates (threshold 8/15)
  Mock scores: all set to integrity:3, relevance:3, novelty:3 (total:9)
  Note: run DRY_RUN=writes_only to see real Haiku scoring decisions
```

### `requirements.txt` additions

```
feedparser>=6.0.10   # Space City Weather + NWS RSS parsing
                     # NOTE: feedparser 6.x has breaking API changes from 5.x
                     # Verify no feedparser 5.x pins elsewhere before adding
                     # Entry point is still feedparser.parse(url) — unchanged from 5.x.
                     # Breaking change: use feed.entries (list), NOT feed.items().
                     # Do not use the 5.x dict-style access pattern.
```

No other new runtime dependencies.

### Website integration placeholder

Location: `src/handlers/briefing_handler.py` (Approach C — handlers stay in `src/handlers/`)

```python
# FUTURE: Post briefing to recursiveintelligence-website
# Requires blog feature to be built first — see docs/plans/website-integration.md
# IMPORTANT: AI Abstract (AI_ML) only — Recursive Briefing NEVER publishes to website
# if briefing_type == "AI_ML":
#     payload = {"briefing_type": ..., "content": ..., "date": ..., "is_public": True}
#     requests.post(WEBSITE_WEBHOOK_URL, json=payload, headers={"X-Secret": WEBHOOK_SECRET})
```

---

## `docs/plans/website-integration.md` (placeholder)

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

## See also
- src/handlers/briefing_handler.py — stub location
- CLAUDE_CODE_IMPLEMENTATION_PLAN.md — original brief
```

---

## Success Criteria

Before opening the PR, verify:

- [ ] `DRY_RUN=true` runs in under 60 seconds with routing decisions logged
- [ ] `DRY_RUN=true` shows Lambda 2 mock pass/fail counts and mock scores
- [ ] Single story processes end-to-end (real APIs) in under 30 seconds
- [ ] Raindrop bookmark created at triage time (title + tags, no summary)
- [ ] Raindrop bookmark updated with summary after Lambda 2 pass
- [ ] Briefing bookmark created in correct collection after Lambda 3
- [ ] Both briefings contain source emoji indicators for every story
- [ ] Zeitgeist contains weather context; AI Abstract does not
- [ ] Three-level structure (Frontier/Enterprise/Equalizer) in AI Abstract output
- [ ] RDD Signal section omitted entirely when no `long-signal:rdd` stories present
- [ ] Entertainment stories appear as parenthetical asides in Zeitgeist, not standalone sections
- [ ] `signal_tracker` TTL explicitly recalculated on every write
- [ ] `briefing_archive` prior edition lookup uses AM/PM chain rule, not date arithmetic
- [ ] CloudWatch metrics logging story funnel counts and estimated API costs
- [ ] All tests pass: `pytest tests/ -v`
- [ ] No hardcoded credentials anywhere in the codebase
- [ ] `story_staging` table coexists with old table; old table drains on TTL

---

## Implementation Phases (for writing-plans)

1. **Foundation** — `config/`, `shared/`, `src/services/triage.py` delegates to `config/feed_rules.py`
2. **Lambda 1** — context loader, velocity scoring, boost tags, new DDB writes
3. **Lambda 2** — editorial scoring + summarizer, `source_type`, idempotency, minimum threshold
4. **Lambda 3** — dual personas, templates, signal injection, prior briefing lookup, website stub
5. **Infrastructure** — new DDB tables, EventBridge, CloudWatch, DLQs, IAM, Terraform tags
6. **Scripts + Docs** — `dry_run.py`, `website-integration.md`, `requirements.txt`, `CLAUDE.md`
7. **Integration Testing** — dry run, single story, full cycle, CloudWatch validation

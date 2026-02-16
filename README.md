# Research Agent — Phase 2b: Intelligence Pipeline + Briefing Synthesis

A serverless pipeline that fetches unread RSS stories from NewsBlur, classifies them using Claude 3.5 Haiku via Amazon Bedrock, saves high-value stories to Raindrop.io, and synthesizes a narrative briefing using Claude Sonnet 4.5. Runs twice daily at 6 AM and 6 PM US Central.

## Architecture

```
NewsBlur API  →  Lambda  →  Bedrock (Claude 3.5 Haiku)
                   ↓                    ↓
              DynamoDB           Classification results
            (dedup + state)      (importance, taxonomy,
                                  priority flag)
                   ↓
             Raindrop.io
           ┌──────┴──────┐
      Story bookmarks   Briefing bookmark
      (taxonomy tags)   (Claude Sonnet 4.5
                         narrative synthesis)
```

## Project Structure

```
research-agent/
├── src/
│   ├── lambda_handler.py        # Entry point, orchestration
│   ├── models/
│   │   ├── story.py             # Story data model
│   │   └── classification.py    # Classification result model (Phase 2b)
│   ├── clients/
│   │   ├── newsblur.py          # NewsBlur API client
│   │   ├── bedrock.py           # Bedrock/Claude 3.5 Haiku client + prompt v2
│   │   ├── bedrock_briefing.py  # Bedrock/Claude Sonnet 4.5 briefing client
│   │   └── raindrop.py          # Raindrop.io API client
│   ├── services/
│   │   ├── classifier.py        # Pipeline orchestration
│   │   └── storage.py           # DynamoDB dedup + last-run state
│   ├── config.py                # Settings (env vars / .env)
│   └── utils.py                 # Structured logging, timing
├── tests/
├── terraform/                   # IaC for Lambda, DynamoDB, IAM, EventBridge
├── verify_connections.py        # Pre-flight credential check
├── raindrop_oauth.py            # Raindrop OAuth setup
├── deploy.sh                    # Package + deploy
└── requirements.txt
```

## Prerequisites

- Python 3.12+
- AWS CLI configured with `seth-dev` profile
- Bedrock model access in us-east-1:
  - `us.anthropic.claude-3-5-haiku-20241022-v1:0` (classification)
  - `us.anthropic.claude-sonnet-4-5-20250929-v1:0` (briefing)
- SSM parameters stored under `/prod/ResearchAgent/`:
  - `NewsBlur_User`, `NewsBlur_Pass`
  - `Raindrop_Token`
  - `Raindrop_Briefing_Collection_Id`

## Setup

```bash
cd research-agent
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Verify all service connections
python verify_connections.py
```

## Running Tests

```bash
pip install pytest
pytest tests/ -v
```

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `NEWSBLUR_USERNAME` | — | NewsBlur login |
| `NEWSBLUR_PASSWORD` | — | NewsBlur password |
| `DYNAMODB_TABLE_NAME` | `newsblur-processing-state` | DynamoDB table |
| `DYNAMODB_REGION` | `us-east-1` | DynamoDB region |
| `BEDROCK_REGION` | `us-east-1` | Bedrock region |
| `BEDROCK_MODEL_ID` | `us.anthropic.claude-3-5-haiku-20241022-v1:0` | Classification model (Terraform/deployed default; local Python default is `anthropic.claude-3-5-haiku-20241022-v1:0` when unset) |
| `BEDROCK_BRIEFING_MODEL_ID` | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` | Briefing model |
| `RAINDROP_TOKEN` | — | Raindrop API token |
| `RAINDROP_BRIEFING_COLLECTION_ID` | `-1` | Raindrop collection for briefings |
| `MAX_STORIES_PER_RUN` | `200` | Story cap per invocation |
| `NEWSBLUR_MIN_SCORE` | `0` | Minimum NewsBlur intelligence score (-1, 0, 1) |
| `MARK_AS_READ` | `false` | Mark classified stories as read in NewsBlur |
| `FETCH_STRATEGY` | `hours_back` | `hours_back` or `since_last_run` |
| `HOURS_BACK_DEFAULT` | `12` | Hours to look back when using `hours_back` strategy |
| `BRIEFING_PREFILTER_DOMAIN_MIN` | `5` | Min overall score for briefing inclusion |
| `BRIEFING_PREFILTER_IMPORTANCE_MIN` | `6` | Min importance score for briefing inclusion |

_Note: Values shown in the "Default" column reflect the deployed/production configuration (set via Terraform). Python in-code fallback defaults, used when environment variables are unset, may differ; see `src/config.py` for the authoritative in-code values._

## Classification Schema (Phase 2b)

Each story receives:

- **Relevance scores** (1-10): `ai_ml`, `neuroscience`, `theory`, `content_craft`, `overall`
- **Importance score** (1-10): broader world significance beyond Seth's domain interests
- **Taxonomy tags**: `#ai-research`, `#ai-policy`, `#consciousness`, `#rdd-framework`, `#client-work`, `#neurodivergent-tech`, `#industry-news`, `#world-news`
- **Priority flag**: `⚡` (urgent), `🎯` (actionable), `🧠` (deep-think), `🔗` (connector), `📊` (data-point), `🚨` (risk-signal)
- **Concepts**: 1-7 key topics
- **Summary**: 2-3 sentence overview + why it matters

## Briefing Synthesis

Stories passing the pre-filter (`overall >= 5 OR importance >= 6`) are synthesized into a 5-section narrative briefing by Claude Sonnet 4.5:

1. **Executive Summary** — 3–5 sentences. The big-picture narrative.
2. **Must-Know Today** — 3–5 stories with full context
3. **Deep Dives** — 2–3 stories worth extended reading time
4. **Weak Signals** — emerging patterns across multiple stories
5. **Notable Omissions** — important topics absent from today's feed

The briefing is saved as a bookmark in the configured Raindrop collection, titled `"Morning Briefing — MMM D, YYYY"` or `"Evening Briefing — MMM D, YYYY"` (for example, `"Morning Briefing — Feb 16, 2026"`).

## Storage Strategy

DynamoDB is used for **minimal state tracking only**.

### Schema

```
Table: newsblur-processing-state
PK: record_type (String)    — "config" or "story"
SK: identifier (String)     — "last_run_timestamp" or story_hash

Record types:
1. config / last_run_timestamp  — ISO timestamp of last successful run
2. story / <story_hash>        — Minimal dedup record with 3-day TTL
```

## Deploying

```bash
# 1. Package Lambda zip (uses manylinux wheels for pydantic-core compatibility)
./deploy.sh

# 2. Deploy infrastructure
cd terraform
terraform init
terraform plan
terraform apply
```

## Schedule

EventBridge cron: `cron(0 11,23 * * ? *)` — 6 AM and 6 PM US Central (11:00 and 23:00 UTC).

## Pipeline Output

```json
{
  "statusCode": 200,
  "body": {
    "execution_id": "uuid",
    "timestamp": "2026-02-16T11:00:00Z",
    "high_value_count": 12,
    "raindrop_sent": 10,
    "raindrop_skipped": 2,
    "briefing_sent": 1,
    "metrics": {
      "stories_fetched": 180,
      "stories_classified": 170,
      "already_processed": 10,
      "classification_failures": 0,
      "high_value_stories": 12,
      "execution_time_seconds": 85.2,
      "top_stories": [...]
    }
  }
}
```

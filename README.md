# Research Agent — Phase 1: NewsBlur Intelligence Pipeline

A serverless pipeline that fetches unread RSS stories from NewsBlur, classifies them using Claude 3.5 Haiku via Amazon Bedrock, and returns scored results in-memory for downstream processing.

## Architecture

```
NewsBlur API  →  Lambda  →  Bedrock (Claude 3.5 Haiku)
                   ↓                    ↓
              DynamoDB            In-memory results
            (dedup only)        (classifications)
```

Each story is scored across four dimensions (ai_ml, neuroscience, theory, content_craft) plus an overall score, then tagged with content type and actionability labels. Classifications live in-memory for the duration of the Lambda invocation; DynamoDB stores only minimal dedup state.

## Project Structure

```
research-agent/
├── src/
│   ├── lambda_handler.py        # Entry point, orchestration
│   ├── models/
│   │   ├── story.py             # Story data model
│   │   └── classification.py    # Classification result model
│   ├── clients/
│   │   ├── newsblur.py          # NewsBlur API client
│   │   └── bedrock.py           # Bedrock/Claude client + prompt
│   ├── services/
│   │   ├── classifier.py        # Pipeline orchestration
│   │   └── storage.py           # DynamoDB dedup layer
│   ├── config.py                # Settings (env vars / .env)
│   └── utils.py                 # Structured logging, timing
├── tests/
│   ├── test_newsblur_client.py
│   ├── test_classifier.py
│   ├── test_storage.py
│   └── fixtures/
│       └── sample_stories.json
├── terraform/                   # IaC for Lambda, DynamoDB, IAM
├── verify_connections.py        # Pre-flight credential check
├── raindrop_oauth.py            # Raindrop OAuth setup
├── deploy.sh                    # Package + deploy
└── requirements.txt
```

## Prerequisites

- Python 3.12+
- AWS CLI configured with `seth-dev` profile
- Bedrock model access enabled for `anthropic.claude-3-5-haiku-20241022-v1:0` in us-east-1
- SSM parameters stored under `/prod/ResearchAgent/`:
  - `NewsBlur_User`, `NewsBlur_Pass`
  - `Raindrop_Token`, `Raindrop_ClientID`, `Raindrop_ClientSecret`, `Raindrop_RefreshToken`
  - `Zotero_Token`, `Zotero_User`

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

The pipeline reads settings from environment variables (Lambda) or a `.env` file (local dev):

| Variable | Default | Description |
|----------|---------|-------------|
| `NEWSBLUR_USERNAME` | — | NewsBlur login |
| `NEWSBLUR_PASSWORD` | — | NewsBlur password |
| `DYNAMODB_TABLE_NAME` | `newsblur-processing-state` | DynamoDB table |
| `DYNAMODB_REGION` | `us-east-1` | DynamoDB region |
| `BEDROCK_REGION` | `us-east-1` | Bedrock region |
| `BEDROCK_MODEL_ID` | `anthropic.claude-3-5-haiku-20241022-v1:0` | Claude model |
| `MAX_STORIES_PER_RUN` | `100` | Story cap per invocation |
| `NEWSBLUR_MIN_SCORE` | `0` | Minimum intelligence score (-1, 0, 1) |
| `MARK_AS_READ` | `false` | Mark classified stories as read |

## Storage Strategy

DynamoDB is used for **minimal state tracking only** — not as a data warehouse.

### What We Store
- **Last run timestamp** — when the pipeline last executed successfully
- **Story dedup records** — prevents reprocessing stories within a 3-day window

### What We DON'T Store
- Full classification results (processed in-memory only)
- Historical data (all story records auto-expire after 3 days via TTL)

### DynamoDB Schema

```
Table: newsblur-processing-state
PK: record_type (String)    — "config" or "story"
SK: identifier (String)     — "last_run_timestamp" or story_hash

Record types:
1. config / last_run_timestamp  — ISO timestamp of last successful run
2. story / <story_hash>        — Minimal dedup record with 3-day TTL
```

### Why This Design?
- **Cost**: ~$0/month (well under free tier with TTL cleanup)
- **Simplicity**: No cleanup jobs, TTL handles expiration automatically
- **Performance**: Batch dedup via `BatchGetItem` in chunks of 100
- **Archive**: Raindrop.io is the long-term archive (Phase 2), not DynamoDB

### Migrating from the Previous Schema

If you deployed the original `newsblur-classified-stories` table:

1. Deploy the new `newsblur-processing-state` table via Terraform
2. Update the Lambda `DYNAMODB_TABLE_NAME` env var
3. Verify the pipeline runs successfully
4. Delete the old `newsblur-classified-stories` table

## Deploying

```bash
# 1. Package Lambda zip
./deploy.sh

# 2. Deploy infrastructure
cd terraform
terraform init
terraform plan
terraform apply
```

## Classification Schema

Each story receives:
- **Relevance scores** (1-10): `ai_ml`, `neuroscience`, `theory`, `content_craft`, `overall`
- **Content type**: `breaking_news`, `research`, `thought_leadership`, `industry`, `world_news`
- **Actionability tags**: `citation_worthy`, `thought_provoking`, `time_sensitive`, `evergreen`
- **Concepts**: 3-5 key topics extracted from the article
- **Summary**: 2-3 sentence overview + one-sentence "why it matters"

## Pipeline Output

The Lambda returns an execution summary:

```json
{
  "statusCode": 200,
  "body": {
    "execution_id": "uuid",
    "timestamp": "2026-02-12T12:00:00Z",
    "high_value_count": 12,
    "metrics": {
      "stories_fetched": 73,
      "stories_classified": 68,
      "already_processed": 5,
      "classification_failures": 0,
      "high_value_stories": 12,
      "time_sensitive_stories": 2,
      "execution_time_seconds": 45.3,
      "top_stories": [...]
    }
  }
}
```

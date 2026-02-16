# NewsBlur Research Agent — Phase 3

A serverless three-Lambda pipeline that fetches RSS stories from NewsBlur, triages them by topic, summarizes each story with Claude 3.5 Haiku, and synthesizes dual daily briefings (AI/ML and World) with Claude Sonnet 4.5. Runs twice daily at 6 AM and 6 PM UTC.

## Architecture

```
EventBridge (6AM / 6PM UTC)
        |
        v
Lambda 1: Triage  (< 60s, no LLM)
- Fetch stories from NewsBlur (min_score=1)
- Rule-based triage: AI/ML | World | Skip
- Route to Raindrop (AI/ML Feed or World Digest)
- Store story content in DynamoDB (24h TTL)
- Send SQS messages to two queues
        |
        v (two SQS queues — parallel)
Lambda 2: Summarizer  (Haiku, up to 900s)
- Consume SQS messages (AI/ML and World queues)
- Summarize each story with Claude 3.5 Haiku
- Update Raindrop bookmark notes with summary
- Send qualified stories to briefing SQS queue
        |
        v
Lambda 3: Briefing  (Sonnet 4.5, up to 300s)
- Consume briefing SQS queue
- Synthesize narrative briefing per bucket (AI/ML or World)
- Post briefing bookmark to Raindrop briefing collection
```

## Project Structure

```
research-agent/
├── src/
│   ├── handlers/
│   │   ├── triage_handler.py       # Lambda 1 entry point
│   │   ├── summarizer_handler.py   # Lambda 2 entry point
│   │   └── briefing_handler.py     # Lambda 3 entry point
│   ├── models/
│   │   └── story.py                # Story data model
│   ├── clients/
│   │   ├── newsblur.py             # NewsBlur API client
│   │   ├── bedrock_summarizer.py   # Claude 3.5 Haiku summarizer
│   │   ├── bedrock_briefing.py     # Claude Sonnet 4.5 briefing
│   │   └── raindrop.py             # Raindrop.io API client
│   ├── services/
│   │   ├── triage.py               # Rule-based story categorization
│   │   └── storage.py              # DynamoDB state + story content
│   ├── config.py                   # Settings (env vars / SSM)
│   └── utils.py                    # Structured logging, timing
├── tests/
├── terraform/                      # DynamoDB, Lambda, SQS, IAM, EventBridge
├── deploy.sh                       # Package + deploy Lambda zip
├── verify_connections.py           # Pre-flight credential check
├── raindrop_oauth.py               # Raindrop OAuth helper
└── requirements.txt
```

## Raindrop Collections

| Collection | Visibility | Purpose |
|------------|-----------|---------|
| AI/ML Feed | Public | AI and ML story bookmarks with summaries |
| World Digest | Private | World news bookmarks with summaries |
| Briefings | Private | Synthesized daily briefing documents |

## Configuration

Key environment variables and SSM parameters (prefix: `/prod/ResearchAgent/`):

| Parameter | Description |
|-----------|-------------|
| `NewsBlur_User` / `NewsBlur_Pass` | NewsBlur credentials (SSM) |
| `Raindrop_Token` | Raindrop API token (SSM) |
| `RAINDROP_AIML_COLLECTION_ID` | Collection ID for AI/ML bookmarks |
| `RAINDROP_WORLD_COLLECTION_ID` | Collection ID for World Digest bookmarks |
| `RAINDROP_BRIEFING_COLLECTION_ID` | Collection ID for briefing documents |
| `DYNAMODB_TABLE_NAME` | DynamoDB table (default: `newsblur-processing-state`) |
| `BEDROCK_SUMMARIZER_MODEL_ID` | Haiku model for summarization |
| `BEDROCK_BRIEFING_MODEL_ID` | Sonnet 4.5 model for briefing synthesis |
| `NEWSBLUR_MIN_SCORE` | Min NewsBlur intelligence score (default: `1`) |
| `SQS_AIML_QUEUE_URL` | SQS queue URL for AI/ML stories |
| `SQS_WORLD_QUEUE_URL` | SQS queue URL for World stories |
| `SQS_BRIEFING_QUEUE_URL` | SQS queue URL for briefing synthesis |

## Deployment

```bash
# 1. Package Lambda zip (manylinux wheels for pydantic-core compatibility)
./deploy.sh

# 2. Deploy infrastructure
cd terraform
terraform init
terraform plan
terraform apply
```

## Development and Testing

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Verify all service connections
python verify_connections.py

# Run tests
pytest tests/ -v
```

Requires Python 3.12+, AWS CLI configured with `seth-dev` profile, and Bedrock model access in `us-east-1` for both Haiku and Sonnet 4.5.

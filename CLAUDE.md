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

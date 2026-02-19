# research-agent — Personal Journalist Engine

## What This Is
A dual-stream AI-powered briefing system for Seth. Runs twice daily (11:00/23:00 UTC)
via EventBridge.

## The Two Publications
- **The AI Abstract** — Public, industrial AI intelligence brief.
  Three-level structure: Frontier → Enterprise → Democratization.
  Published to Raindrop "AI/ML Feed" collection (public RSS) AND posted to the website.
- **The Recursive Briefing** — Private, world/culture/science dispatch.
  Narrative format, grounded in Pasadena TX weather and local news.
  Posted to website as a private owner-only page (`/briefs/<date>-pm-world?t=OWNER_ACCESS_TOKEN`)
  AND updates the fixed Raindrop bookmark in-place (private, note field). Site post is non-fatal.

## Architecture
Three Lambdas connected by SQS:
Lambda 1 (Triage, no LLM) → Lambda 2 (Haiku editorial filter) → Lambda 3 (Sonnet 4.6 briefing)

## Story Caps
- Triage passes at most `MAX_AI_ML_STORIES=40` / `MAX_WORLD_STORIES=20` candidates to scoring
- Summarizer selects top-N by score before sending to briefing queue:
  `MAX_BRIEFING_AI_ML_STORIES=10`, `MAX_BRIEFING_WORLD_STORIES=8` (in `config/scoring_weights.py`)

## Critical Rules
- DO NOT penalize consciousness/AGI/alignment content — long signal for Seth's RDD framework
- Feed routing lives in `config/feed_rules.py` — update without redeploy
- `DRY_RUN=true` for zero-cost testing | `DRY_RUN=writes_only` for real LLM, no writes
- Raindrop rate limit: `threading.Semaphore(5)` in Lambda 2, 200ms sleep in Lambda 1
- Lambda 2 bails if fewer than 3 stories pass threshold — no briefing-queue message
- Recursive Briefing posts to website as private page (category="World", token-gated) + Raindrop
- `ContextLoader.format_context_block()` must be called (not `json.dumps()`) — the Zeitgeist
  persona expects `[SYSTEM_CONTEXT_BLOCK]` marker format, not raw JSON

## Bedrock Notes
- Model: `us.anthropic.claude-sonnet-4-6` (cross-region inference profile)
- Marketplace-gated: must be unlocked by invoking once via a user with
  `aws-marketplace:ViewSubscriptions` before `invoke_model` works account-wide
- botocore default read_timeout is ~300s — always set `Config(read_timeout=580)` on the
  bedrock-runtime client (Lambda timeout is 600s)

## Website Ingest Integration
- AI/ML briefs POST to `https://recursiveintelligence.io/api/briefs/ingest`
- Auth: `Authorization: Bearer {BRIEF_API_KEY}` (Bearer token, HMAC-verified)
- Key stored in SSM: `/prod/ResearchAgent/Brief_Api_Key` (us-east-1)
- Terraform reads SSM → sets `BRIEF_API_KEY` env var on the briefing Lambda

### `_post_to_site` status handling
Accepts 200 (idempotent re-ingest) and 201 (created) as success; 409 logged as duplicate.
Source field: `feed_name` is always empty from NewsBlur river endpoint, so
`_build_items` falls back to the URL hostname (e.g. `axios.com`) via `_source_from_url`.

## Key Files
- `config/feed_rules.py` — routing logic (44 real NewsBlur feeds); add company
  names to `AI_ML_KEYWORDS` when new AI labs emerge
- `config/scoring_weights.py` — all thresholds and caps
- `config/keywords.py` — boost/penalize keyword lists
- `src/services/personas.py` — two editorial identities; all `json.dumps()` must
  use `_dumps()` helper (DynamoDB returns `Decimal`, not float)
- `src/services/editorial_scorer.py` — Haiku scoring; `SCORE_WORLD_TEMPLATE` has
  EXCLUDE clause for AI/ML content to prevent cross-stream bleed
- `src/handlers/triage_handler.py` — calls `loader.format_context_block()`, not
  `json.dumps(context_data)`, when storing the WORLD context block
- `src/handlers/summarizer_handler.py` — sorts passed stories by score desc, caps
  to top-N before sending to SQS briefing queue
- `src/handlers/briefing_handler.py` — `Config(read_timeout=580)` on Bedrock client
- `shared/dynamodb_client.py` — typed DDB operations (3 tables)
- `docs/plans/2026-02-17-personal-journalist-v2-design.md` — full design

## Cost Target
~$50/month (Anthropic Bedrock + AWS + Raindrop Pro)
Alert threshold: $3/day via CloudWatch alarm

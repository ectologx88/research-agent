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

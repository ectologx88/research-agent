# Merge, Deploy, and First Live Run Plan
## research-agent — Personal Journalist Engine v2.0
**Date**: 2026-02-18
**Branch**: `feature/personal-journalist-v2` → `main`

---

## Context: Where We Left Off

The `feature/personal-journalist-v2` branch is feature-complete. The last session completed the Sonnet 4.6 upgrade for the briefing Lambda (Lambda 3). Key discovery: Bedrock model IDs for Claude 4.6+ dropped the date suffix entirely (`us.anthropic.claude-sonnet-4-6` vs. the old `us.anthropic.claude-sonnet-4-5-20250929-v1:0`). The upgrade was applied across all four authoritative layers:

- `docs/plans/` — plan doc updated
- `src/config.py` — model ID constant updated
- `src/services/synthesizer.py` — `DEFAULT_MODEL_ID` updated
- `terraform/lambda.tf` — **production-authoritative source**

**State going in**: 184 tests passing, clean working tree.

---

## Intentional Carry-Forwards (Not Regressions)

| Item | Decision | Rationale |
|------|----------|-----------|
| `src/clients/bedrock_briefing.py` | Still references Sonnet 4.5 | Legacy v1 client — not used by v2 pipeline, explicitly excluded from upgrade scope |
| Lambda 2 (Summarizer) model | Stays on Haiku 3.5 | Haiku 4.5 is 25% more expensive with no meaningful benefit for short structured summarization. Revisit only if summary quality issues emerge in production. |

---

## Execution Sequence

### Step 1 — Open PR
Open `feature/personal-journalist-v2` → `main`.

PR description should reference:
- The implementation plan: `docs/plans/2026-02-17-personal-journalist-v2-implementation.md`
- The design doc: `docs/plans/2026-02-17-personal-journalist-v2-design.md`
- The Sonnet 4.6 upgrade doc: `docs/plans/2026-02-17-upgrade-briefing-model-sonnet-4-6.md`
- The carry-forwards above (so reviewers don't flag the legacy client as a bug)

### Step 2 — Copilot Review
Wait for GitHub Copilot to post review comments. Address any feedback before merging.

### Step 3 — Merge
Merge into `main` once the review is clean.

### Step 4 — Deploy
```bash
# From repo root — package and push all three Lambda zips
./deploy.sh

# From terraform/ — provision infrastructure
cd terraform/
terraform apply
```

**Infrastructure being applied**:
- 3 Lambdas (triage, summarizer, briefing)
- 3 SQS queues + DLQs (ai-ml-queue, world-queue, briefing-queue)
- 3 DynamoDB tables (story_staging, signal_tracker, briefing_archive)
- EventBridge rules (6AM/6PM CST crons)
- CloudWatch alarms (cost threshold: $3/day)
- IAM role expansions

### Step 5 — Smoke Test
Manually invoke the triage Lambda and tail CloudWatch logs across all three Lambdas to confirm the full pipeline runs end-to-end without errors.

```bash
# Invoke triage Lambda manually
aws lambda invoke \
  --function-name personal-journalist-triage \
  --payload '{}' \
  /tmp/triage-response.json && cat /tmp/triage-response.json

# Tail logs for all three Lambdas (separate terminals or tmux panes)
aws logs tail /aws/lambda/personal-journalist-triage --follow
aws logs tail /aws/lambda/personal-journalist-summarizer --follow
aws logs tail /aws/lambda/personal-journalist-briefing --follow
```

**What to verify**:
- Lambda 1 fetches from NewsBlur, routes stories to correct streams, writes to DynamoDB, sends SQS messages
- Lambda 2 picks up from SQS, summarizes with Haiku, updates DynamoDB and Raindrop bookmark notes
- Lambda 3 picks up from briefing queue, generates both briefings with Sonnet 4.6, posts to Raindrop

### Step 6 — Monitor First Live Run
After EventBridge triggers the first real run (6AM or 6PM CST):

- **Raindrop**: Confirm bookmarks land in "AI/ML Feed" and "Current Events and World News" collections with correct tags, summaries, and boost scores
- **Briefing quality**: Read both the AI Abstract and the Recursive Briefing outputs; verify Sonnet 4.6 output quality, three-level structure (Frontier/Enterprise/Equalizer) in the AI Abstract, and weather/local context in the Recursive Briefing
- **CloudWatch**: Check custom metrics for story counts and estimated API cost per run

---

## Out of Scope

**Website publishing** — Publishing the AI/ML briefing to the Recursive Intelligence website as an agent-authored post is an explicit Phase 4 backlog item. Not part of this delivery.

---

## Success Criteria

- [ ] PR opened and Copilot review addressed
- [ ] `terraform apply` completes without errors
- [ ] Smoke test: all three Lambdas complete without errors in CloudWatch
- [ ] First live briefings appear in correct Raindrop collections with summaries
- [ ] Sonnet 4.6 briefing output quality matches expectations
- [ ] Estimated daily cost stays under $3.00 CloudWatch threshold

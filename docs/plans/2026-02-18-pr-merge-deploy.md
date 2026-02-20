# PR, Merge, and First Live Run Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Open the `feature/personal-journalist-v2` PR, pass Copilot review, merge to main, deploy all infrastructure, and verify the first full pipeline run.

**Architecture:** Three-Lambda pipeline (triage → summarizer → briefing) connected by SQS, with DynamoDB state and EventBridge crons. Terraform is the production-authoritative source for all infrastructure.

**Tech Stack:** Python 3.12, AWS Lambda, SQS, DynamoDB, EventBridge, CloudWatch, Anthropic API (Haiku 3.5 + Sonnet 4.6), Raindrop.io, Terraform, GitHub Copilot review.

---

## Known State

- Branch: `feature/personal-journalist-v2` — local only, not yet pushed to origin
- 184 tests passing, clean working tree
- Sonnet 4.6 upgrade complete across all 4 layers
- `src/clients/bedrock_briefing.py` intentionally still on Sonnet 4.5 (legacy v1, unused by v2)
- Lambda 2 intentionally on Haiku 3.5 (cost/quality tradeoff, revisit only in production)

---

### Task 1: Push Branch to Origin

**Files:** none

**Step 1: Confirm clean state**

```bash
cd /home/r3crsvint3llgnz/01_Projects/research-agent
git status
```

Expected: `nothing to commit, working tree clean` (plus the untracked plan docs — that's fine)

**Step 2: Push branch**

```bash
git push -u origin feature/personal-journalist-v2
```

Expected: branch pushed, tracking set

---

### Task 2: Open the PR

**Files:** none (GitHub operation)

**Step 1: Create the PR**

```bash
gh pr create \
  --base main \
  --head feature/personal-journalist-v2 \
  --title "feat: Personal Journalist Engine v2.0 — dual-stream pipeline with Sonnet 4.6" \
  --body "$(cat <<'EOF'
## Summary

Refactors the research-agent from a single-stream Phase 3 pipeline into the full Personal Journalist Engine v2.0 — a dual-stream, three-Lambda system that produces two daily briefings:

- **The AI Abstract** — public AI/ML intelligence brief with Frontier/Enterprise/Equalizer structure
- **The Recursive Briefing** — private world/culture/science dispatch grounded in Pasadena TX weather and local context

## What Changed

- **Three-Lambda pipeline**: Triage (no LLM) → Summarizer (Haiku 3.5) → Briefing (Sonnet 4.6) connected by SQS
- **Dual-stream routing**: `config/feed_rules.py` and `config/keywords.py` — update without redeployment
- **Velocity scoring**: cluster detection for lead stories
- **Editorial scorer**: Haiku-based PASS/REJECT with boost/penalize tags passed to Lambda 3
- **Context loader**: Open-Meteo weather, Space City Weather RSS, NWS alerts injected as deterministic `[SYSTEM_CONTEXT_BLOCK]`
- **Shared infrastructure**: `shared/dynamodb_client.py`, `shared/logger.py`
- **Full Terraform**: 3 DynamoDB tables, 3 SQS queues + DLQs, EventBridge 6AM/6PM CST crons, CloudWatch cost alarms, IAM expansions
- **DRY_RUN mode**: Full triage logic with no LLM/API calls for feed rule tuning
- **Sonnet 4.6 upgrade**: Lambda 3 upgraded from Sonnet 4.5; Bedrock IDs for 4.6+ drop the date suffix entirely (`us.anthropic.claude-sonnet-4-6`)

## Intentional Carry-Forwards

- `src/clients/bedrock_briefing.py` still references Sonnet 4.5 — legacy v1 client, not used by the v2 pipeline, explicitly out of scope
- Lambda 2 stays on Haiku 3.5 — 25% cheaper than Haiku 4.5 with no meaningful quality difference for short structured summarization

## Design Docs

- Architecture + design: `docs/plans/2026-02-17-personal-journalist-v2-design.md`
- Full implementation spec: `docs/plans/2026-02-17-personal-journalist-v2-implementation.md`
- Sonnet 4.6 upgrade: `docs/plans/2026-02-17-upgrade-briefing-model-sonnet-4-6.md`

## Test Coverage

184 tests passing. New test files:
`test_router.py`, `test_context_loader.py`, `test_editorial_scorer.py`, `test_feed_rules.py`, `test_keywords.py`, `test_personas.py`, `test_synthesizer.py`, `test_velocity.py`, `test_dynamodb_client.py`, `test_shared_logger.py`

🤖 Generated with [Claude Code](https://claude.ai/claude-code)
EOF
)"
```

**Step 2: Confirm PR URL**

```bash
gh pr view --web
```

---

### Task 3: Wait for Copilot Review

**Step 1: Poll for Copilot comments**

```bash
gh pr checks
gh pr view --comments
```

Wait until Copilot has posted its review. This typically takes a few minutes after PR creation.

**Step 2: Read all comments carefully**

Note any comments on:
- `src/clients/bedrock_briefing.py` (legacy client — Copilot may flag the Sonnet 4.5 model ID; this is intentional, add a comment if needed)
- `shared/dynamodb_client.py` — DynamoDB batch operation patterns
- `src/services/synthesizer.py` — Sonnet 4.6 model ID format
- `terraform/lambda.tf` — new Lambda configurations
- Any test files

---

### Task 4: Address Copilot Feedback

*This task is open-ended — execute per comment.*

**For each Copilot comment:**

1. Read the comment and determine if it's valid
2. If valid: make the minimal fix, run `pytest tests/ -v` to confirm 184 tests still pass
3. If invalid / intentional carry-forward: reply on the PR thread explaining the decision (especially for `bedrock_briefing.py`)
4. Commit fixes in small, focused commits:

```bash
git add <specific files>
git commit -m "fix: address Copilot review — <one-line description>"
git push
```

**After all comments addressed:**

```bash
pytest tests/ -v
```

Expected: all 184 tests pass (or more if fixes added tests)

---

### Task 5: Merge the PR

**Step 1: Confirm checks pass**

```bash
gh pr checks
```

Expected: all checks green

**Step 2: Merge**

```bash
gh pr merge --merge --subject "feat: Personal Journalist Engine v2.0 — dual-stream pipeline with Sonnet 4.6"
```

Use `--merge` (not squash) to preserve the commit history from the feature branch.

**Step 3: Pull main**

```bash
git checkout main
git pull origin main
```

**Step 4: Verify**

```bash
pytest tests/ -v
```

Expected: all tests still pass on main

---

### Task 6: Deploy — Package Lambdas

**Files:** `deploy.sh`

**Step 1: Run deploy script**

```bash
cd /home/r3crsvint3llgnz/01_Projects/research-agent
./deploy.sh
```

Expected: three Lambda zip packages built and uploaded to S3 (or directly deployed, depending on deploy.sh implementation). Watch for any Python dependency errors — the manylinux wheels for ARM/x86 must match the Lambda runtime.

**Step 2: Verify Lambda zip uploads**

Check the deploy.sh output confirms all three packages (triage, summarizer, briefing) deployed without errors.

---

### Task 7: Deploy — Terraform Apply

**Files:** `terraform/`

**Step 1: Init (only needed if first run or provider changes)**

```bash
cd /home/r3crsvint3llgnz/01_Projects/research-agent/terraform
terraform init
```

**Step 2: Plan — review before applying**

```bash
terraform plan
```

Read the plan output carefully. Expected new resources:
- 3 Lambda functions (or updates to existing)
- 3 SQS queues (`personal-journalist-ai-ml`, `personal-journalist-world`, `personal-journalist-briefing`)
- 3 DLQs
- 3 DynamoDB tables (`story_staging`, `signal_tracker`, `briefing_archive`)
- 2 EventBridge rules (6AM CST, 6PM CST)
- CloudWatch alarms and dashboard
- IAM role updates

**Step 3: Apply**

```bash
terraform apply
```

Type `yes` when prompted.

Expected: `Apply complete! Resources: N added, N changed, 0 destroyed.`

If any resource fails, read the error carefully — do not re-run blindly. Common issues:
- IAM permission conflicts (existing role with different policy)
- SQS queue name collision (if queues existed from a previous version)
- DynamoDB table already exists with different schema

---

### Task 8: Smoke Test — Invoke Triage Lambda

**Step 1: Open four terminal panes** (tmux or separate terminals)

**Step 2: Start log tailing on all three Lambdas** (panes 2, 3, 4)

```bash
# Pane 2 — triage logs
aws logs tail /aws/lambda/personal-journalist-triage --follow --format short

# Pane 3 — summarizer logs
aws logs tail /aws/lambda/personal-journalist-summarizer --follow --format short

# Pane 4 — briefing logs
aws logs tail /aws/lambda/personal-journalist-briefing --follow --format short
```

**Step 3: Invoke triage Lambda manually** (pane 1)

```bash
aws lambda invoke \
  --function-name personal-journalist-triage \
  --payload '{}' \
  --log-type Tail \
  /tmp/triage-response.json

cat /tmp/triage-response.json
```

**Step 4: Verify Lambda 1 (Triage)**

In the triage logs, confirm:
- NewsBlur stories fetched and count logged
- Stories routed to `AI_ML` or `WORLD` or `SKIP` with reasons
- DynamoDB writes logged
- SQS messages sent to `ai-ml-queue` and `world-queue`
- Context block (weather, local headlines) logged

**Step 5: Verify Lambda 2 (Summarizer)** — triggered by SQS automatically

In the summarizer logs, confirm:
- SQS message received
- Stories fetched from DynamoDB
- Haiku summarization completed (one log line per story)
- DynamoDB status updated to `summarized`
- Raindrop bookmark notes updated
- Message sent to `briefing-queue`

**Step 6: Verify Lambda 3 (Briefing)** — triggered by SQS automatically

In the briefing logs, confirm:
- SQS message received
- Sonnet 4.6 synthesis completed for both streams
- Briefings posted to Raindrop
- DynamoDB `briefing_archive` written
- Story status updated to `briefed`
- Cost metrics logged to CloudWatch

**Step 7: Check for errors**

```bash
# Scan all three log groups for errors in the last 30 minutes
aws logs filter-log-events \
  --log-group-name /aws/lambda/personal-journalist-triage \
  --start-time $(date -d '30 minutes ago' +%s000) \
  --filter-pattern "ERROR"

aws logs filter-log-events \
  --log-group-name /aws/lambda/personal-journalist-summarizer \
  --start-time $(date -d '30 minutes ago' +%s000) \
  --filter-pattern "ERROR"

aws logs filter-log-events \
  --log-group-name /aws/lambda/personal-journalist-briefing \
  --start-time $(date -d '30 minutes ago' +%s000) \
  --filter-pattern "ERROR"
```

Expected: no ERROR entries

---

### Task 9: Monitor First Live Run

Wait for the first EventBridge-triggered run (6AM or 6PM CST). Then:

**Step 1: Check Raindrop collections**

Open Raindrop.io and verify:
- "AI/ML Feed" collection has new bookmarks with:
  - Correct tags (feed name + `ai-ml` + boost tags)
  - Summary in the note field
  - Boost score visible
- "Current Events and World News" collection has new bookmarks with:
  - Correct tags (feed name + `world:<subtype>`)
  - Summary in the note field

**Step 2: Read both briefings**

Find the briefing bookmarks posted by Lambda 3 and read both:

- **AI Abstract**: Verify three-level structure (Frontier / Enterprise Layer / Equalizer Angle) for each story, source links on every item, Open Source Watch section, Weak Signals section
- **Recursive Briefing**: Verify narrative format (not list), weather/local context woven in naturally, source credibility indicators, Notable Omissions section

**Step 3: Check CloudWatch cost metrics**

```bash
aws cloudwatch get-metric-statistics \
  --namespace PersonalJournalist \
  --metric-name estimated_api_cost \
  --start-time $(date -u -d '24 hours ago' +%Y-%m-%dT%H:%M:%S) \
  --end-time $(date -u +%Y-%m-%dT%H:%M:%S) \
  --period 86400 \
  --statistics Sum
```

Expected: well under $3.00/day threshold

**Step 4: Note any quality issues**

If Sonnet 4.6 briefing output has problems (wrong structure, missing sections, poor routing), note them for a follow-up feed rule tuning session using `scripts/dry_run.py`.

---

## Success Criteria

- [ ] PR opened and branch visible on GitHub
- [ ] Copilot review comments addressed (or replied to with reasoning)
- [ ] All checks green, PR merged to main
- [ ] `terraform apply` completes with no errors
- [ ] Smoke test: all three Lambdas complete end-to-end in CloudWatch
- [ ] First live briefings appear in correct Raindrop collections with summaries and tags
- [ ] Sonnet 4.6 briefing output has correct structure for both streams
- [ ] Estimated daily cost stays under $3.00 CloudWatch threshold

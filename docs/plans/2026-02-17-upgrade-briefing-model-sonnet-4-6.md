# Upgrade Briefing Model to Sonnet 4.6 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace every hardcoded Sonnet 4.5 model ID in the briefing pipeline (Lambda 3) with the Sonnet 4.6 Bedrock model ID, update the test assertion, and annotate all existing plan docs with a model-upgrade note.

**Architecture:** The briefing model ID appears in two forms — a cross-region inference profile (`us.anthropic.…`) used by `src/config.py` and `terraform/lambda.tf`, and a direct Bedrock model ID (`anthropic.…`) used as a fallback constant in `src/services/synthesizer.py`. Both must be updated to their 4.6 equivalents. The authoritative source at runtime is the Lambda env var (`BEDROCK_BRIEFING_MODEL_ID`) which overrides the Python default; both are kept in sync.

**Tech Stack:** Python 3.12, pydantic-settings, Terraform HCL, pytest, AWS Bedrock cross-region inference profiles

---

## Pre-flight: Look up the correct Bedrock model IDs

> ⚠️ **Do this before writing a single line of code.** Using the wrong model ID causes a silent Bedrock `ValidationException` at runtime — the Lambda will fail with no obvious error.

Sonnet 4.6 Anthropic API model ID: **`claude-sonnet-4-6`**

You need two Bedrock-specific IDs:

1. **Cross-region inference profile** (used in `src/config.py` and `terraform/lambda.tf`):
   - Pattern: `us.anthropic.{model}-{date}-v{n}:{variant}`
   - Expected: `us.anthropic.claude-sonnet-4-6-20250514-v1:0`
   - Verify in the AWS console → Bedrock → Cross-region inference → filter "sonnet-4-6"
   - Or via CLI: `aws bedrock list-inference-profiles --region us-east-1 | grep sonnet-4-6`

2. **Direct Bedrock model ID** (fallback constant in `src/services/synthesizer.py`):
   - Pattern: `anthropic.{model}-{date}-v{n}:{variant}`
   - Expected: `anthropic.claude-sonnet-4-6-20250514-v1:0`
   - Or: `aws bedrock list-foundation-models --region us-east-1 | grep sonnet-4-6`

Substitute the real IDs everywhere `INFERENCE_PROFILE_ID` and `DIRECT_MODEL_ID` appear below.

---

## Task 1: Update `src/config.py` default + test

**Files:**
- Modify: `src/config.py:42`
- Modify: `tests/test_config.py:45`

**Step 1: Run the existing test to confirm it currently passes**

```bash
pytest tests/test_config.py::test_bedrock_briefing_model_id_default -v
```
Expected: PASS (proving baseline is green before we touch anything)

**Step 2: Update the failing test first (TDD)**

In `tests/test_config.py`, change line 45:

```python
# Before
assert s.bedrock_briefing_model_id == "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

# After
assert s.bedrock_briefing_model_id == "INFERENCE_PROFILE_ID"
# e.g. "us.anthropic.claude-sonnet-4-6-20250514-v1:0"
```

**Step 3: Run to confirm it now fails**

```bash
pytest tests/test_config.py::test_bedrock_briefing_model_id_default -v
```
Expected: FAIL — `AssertionError: assert 'us.anthropic.claude-sonnet-4-5-20250929-v1:0' == 'INFERENCE_PROFILE_ID'`

**Step 4: Update `src/config.py`**

```python
# Before (line 42)
bedrock_briefing_model_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

# After
bedrock_briefing_model_id: str = "INFERENCE_PROFILE_ID"
# e.g. "us.anthropic.claude-sonnet-4-6-20250514-v1:0"
```

**Step 5: Run the test to confirm it passes**

```bash
pytest tests/test_config.py::test_bedrock_briefing_model_id_default -v
```
Expected: PASS

**Step 6: Run the full test suite to check for regressions**

```bash
pytest tests/ -q
```
Expected: All tests pass (184+)

**Step 7: Commit**

```bash
git add src/config.py tests/test_config.py
git commit -m "feat: upgrade briefing model default to Sonnet 4.6"
```

---

## Task 2: Update `src/services/synthesizer.py` fallback constant

**Files:**
- Modify: `src/services/synthesizer.py:15`

**Context:** `DEFAULT_MODEL_ID` is only used when `model_id=""` is passed to `__init__`. In production this never fires (the handler always passes `settings.bedrock_briefing_model_id`). It must still be updated to avoid confusion and to keep the fallback correct for local scripts.

Note: this uses the **direct** Bedrock model ID format (no `us.` prefix), not the inference profile.

**Step 1: Update the constant**

```python
# Before (line 15)
DEFAULT_MODEL_ID = "anthropic.claude-sonnet-4-5-20251009-v3:0"

# After
DEFAULT_MODEL_ID = "DIRECT_MODEL_ID"
# e.g. "anthropic.claude-sonnet-4-6-20250514-v1:0"
```

Also update the class and module docstrings on lines 2 and 13 from "Sonnet" (implicit 4.5) to reference 4.6:

```python
# line 2
"""Briefing synthesizer for Lambda 3. Calls Bedrock Sonnet 4.6 to generate briefings."""

# line 13 (class docstring)
"""Synthesize daily briefings via Sonnet 4.6. One instance per Lambda invocation."""
```

**Step 2: Run synthesizer tests**

```bash
pytest tests/test_synthesizer.py -v
```
Expected: All pass. The `DEFAULT_MODEL_ID` is not directly asserted in tests (it's overridden by the handler), so no test changes are required.

**Step 3: Run full suite**

```bash
pytest tests/ -q
```
Expected: All pass

**Step 4: Commit**

```bash
git add src/services/synthesizer.py
git commit -m "feat: update synthesizer DEFAULT_MODEL_ID to Sonnet 4.6"
```

---

## Task 3: Update Terraform Lambda env var

**Files:**
- Modify: `terraform/lambda.tf:154`

**Context:** This is the **production authoritative** value. It overrides the Python default at runtime. Get this right.

**Step 1: Update the env var in the `briefing` Lambda resource**

```hcl
# Before (line 154)
BEDROCK_BRIEFING_MODEL_ID    = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"

# After
BEDROCK_BRIEFING_MODEL_ID    = "INFERENCE_PROFILE_ID"
# e.g. "us.anthropic.claude-sonnet-4-6-20250514-v1:0"
```

**Step 2: Validate Terraform**

```bash
# First create the placeholder zip if dist/ doesn't exist yet:
mkdir -p dist && touch dist/lambda.zip

cd terraform && terraform validate
```
Expected: `Success! The configuration is valid.`

**Step 3: Commit**

```bash
git add terraform/lambda.tf
git commit -m "infra: upgrade briefing Lambda to Sonnet 4.6 model ID"
```

---

## Task 4: Annotate existing plan docs with model-upgrade note

**Files:**
- Modify: `docs/plans/2026-02-16-briefing-design.md`
- Modify: `docs/plans/2026-02-16-phase-3-design.md`
- Modify: `docs/plans/2026-02-17-personal-journalist-v2-design.md`

**Context:** These historical plan docs contain `claude-sonnet-4-5-20250929` references. We do NOT rewrite history — we add a callout note near each reference so future readers know the model has since been upgraded.

**Step 1: Add a deprecation callout to `2026-02-16-briefing-design.md`**

Find line 60 (contains `us.anthropic.claude-sonnet-4-5-20250929-v1:0`). Insert directly after it:

```markdown
> **Model upgrade note (2026-02-17):** Production now uses Sonnet 4.6
> (`INFERENCE_PROFILE_ID`). See `docs/plans/2026-02-17-upgrade-briefing-model-sonnet-4-6.md`.
```

**Step 2: Add same callout to `2026-02-16-phase-3-design.md`**

Find line 213 (contains `Claude Sonnet 4.5`). Insert directly after it:

```markdown
> **Model upgrade note (2026-02-17):** Production now uses Sonnet 4.6
> (`INFERENCE_PROFILE_ID`). See `docs/plans/2026-02-17-upgrade-briefing-model-sonnet-4-6.md`.
```

**Step 3: Add same callout to `2026-02-17-personal-journalist-v2-design.md`**

Find line 25 (contains `Sonnet 4.5 for Lambda 3`). Change the inline text and add note:

```markdown
# Before
**Bedrock for all LLM calls** (Haiku for Lambda 2, Sonnet 4.5 for Lambda 3)

# After
**Bedrock for all LLM calls** (Haiku for Lambda 2, Sonnet 4.6 for Lambda 3)
> **Model upgrade note (2026-02-17):** Updated from Sonnet 4.5 → 4.6.
> See `docs/plans/2026-02-17-upgrade-briefing-model-sonnet-4-6.md`.
```

**Step 4: Commit**

```bash
git add docs/plans/2026-02-16-briefing-design.md \
        docs/plans/2026-02-16-phase-3-design.md \
        docs/plans/2026-02-17-personal-journalist-v2-design.md
git commit -m "docs: annotate plan docs with Sonnet 4.6 model upgrade note"
```

---

## Task 5: Final validation

**Step 1: Run full test suite one last time**

```bash
pytest tests/ -v 2>&1 | tail -5
```
Expected: All tests pass, 0 failures

**Step 2: Confirm no stale 4-5 model ID remains in production paths**

```bash
grep -rn "sonnet-4-5" src/ config/ shared/ terraform/ \
  --include="*.py" --include="*.tf"
```
Expected: Zero matches. (Docs are excluded — they contain historical notes, not production config.)

**Step 3: Tag the upgrade**

```bash
git log --oneline -4   # review the 3 new commits
```

---

## What is NOT changing

- Lambda 2 (Haiku): `us.anthropic.claude-3-5-haiku-20241022-v1:0` — no change, Haiku 4.5 is the latest in that tier
- `src/clients/bedrock_briefing.py` — legacy client not used by the v2 pipeline; its default is stale but harmless
- Test mocks: all tests use `"test-model"` as the mock model ID — no change needed
- `tests/test_config.py::test_summarizer_model_id_has_default` — only asserts `!= ""`, not the exact string

---

## Rollback

If Sonnet 4.6 has a Bedrock availability issue in us-east-1:
1. Revert `src/config.py` to `us.anthropic.claude-sonnet-4-5-20250929-v1:0`
2. Revert `terraform/lambda.tf` env var
3. `terraform apply` to push the env var change to Lambda immediately (no redeploy needed)
4. The Terraform env var update takes effect on next Lambda cold start — no zip redeploy required

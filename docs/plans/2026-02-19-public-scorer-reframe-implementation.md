# Public Scorer Reframe + HN Velocity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Sever the AI Abstract scorer from its private industrial persona, restore the scoring threshold to 9/15, add HN social-proof velocity tags, and trigger a fresh briefing run.

**Architecture:** Four config/code changes (scorer prompt, keywords, threshold, HN check), test updates throughout (TDD — update tests before code), followed by a live Lambda invocation. All work on `main`. No deploy needed — Lambda picks up code on next deploy; for today's fresh run we invoke directly.

**Tech Stack:** Python 3.12, pytest, AWS Lambda, urllib.request (stdlib), HN Algolia API (free, no key).

---

## Task 1: Update keyword tests first (TDD — write the new expectation before breaking it)

**Files:**
- Modify: `tests/test_keywords.py`

**Step 1: Replace the industrial test, update the overlap test, add the neurodivergent test**

Open `tests/test_keywords.py`. Make these three changes:

**Remove** `test_industrial_gets_boost` and `test_overlap_produces_both_tags` entirely.

**Add** these three tests in their place:

```python
def test_industrial_keywords_not_boosted():
    # boost:industrial no longer exists — industrial AI titles get no special tag
    tags = get_boost_tags("AI for predictive maintenance in chemical plants", [])
    assert "boost:industrial" not in tags

def test_open_source_overlap_gets_only_open_source_tag():
    # open-source + industrial phrasing → only boost:open-source (industrial tag removed)
    tags = get_boost_tags("Open-source AI for manufacturing process control", [])
    assert "boost:open-source" in tags
    assert "boost:industrial" not in tags

def test_rdd_neurodivergent_gets_long_signal():
    tags = get_boost_tags("Study links autism and cognitive flexibility in problem solving", [])
    assert "long-signal:rdd" in tags
```

**Step 2: Run the keyword tests to confirm failures**

```bash
cd /home/r3crsvint3llgnz/01_Projects/research-agent
python -m pytest tests/test_keywords.py -v
```

Expected: 2 failures (`test_industrial_keywords_not_boosted` fails because `boost:industrial` IS currently added; `test_rdd_neurodivergent_gets_long_signal` fails because "autism"/"cognitive" are not yet in `RDD_KEYWORDS`). `test_open_source_overlap_gets_only_open_source_tag` may pass or fail depending on current behavior — either is fine, we'll fix it in Task 2.

---

## Task 2: Replace `config/keywords.py`

**Files:**
- Modify: `config/keywords.py` (full replacement)

**Step 1: Replace the entire file with this exact content**

```python
# config/keywords.py
"""Boost/penalize keyword lists for triage scoring."""

# Triggers boost:open-source tag -- stories about accessible, deployable AI
DEMOCRATIZATION_KEYWORDS = [
    "open source", "open-source", "self-hosted", "local llm",
    "edge deployment", "on-premise", "return on investment", "implementation guide",
    "small business", "smb", "mid-market", "accessible",
    "cost reduction", "efficiency",
]

# RDD / long-signal: slow-burn developments in cognition, consciousness, alignment
# These bypass normal scoring caps and always surface in briefings
RDD_KEYWORDS = [
    "consciousness", "emergence", "quantum", "information theory",
    "cognitive architecture", "agi", "alignment", "interpretability",
    "recursive", "distinction", "awareness", "subjective experience",
    "neural correlates", "integrated information", "global workspace",
    "autistic", "autism", "neurodivergent", "cognitive",
]

# Used by editorial scorer to penalize relevance score
AI_ML_PENALIZE = [
    "stock price", "ipo", "funding round", "valuation",
    "chatgpt wrapper", "no-code ai", "ai girlfriend",
    "productivity hack", "prompt trick",
]


def get_boost_tags(title: str, existing_tags: list[str]) -> list[str]:
    """Return boost tags based on title keywords. Preserves existing tags."""
    title_lower = (title or "").lower()
    tags = list(existing_tags)

    if any(kw in title_lower for kw in DEMOCRATIZATION_KEYWORDS):
        if "boost:open-source" not in tags:
            tags.append("boost:open-source")

    if any(kw in title_lower for kw in RDD_KEYWORDS):
        if "long-signal:rdd" not in tags:
            tags.append("long-signal:rdd")

    return tags
```

**Step 2: Run keyword tests**

```bash
python -m pytest tests/test_keywords.py -v
```

Expected: All 6 tests pass. If any fail, recheck the keyword lists.

**Step 3: Run full suite to catch any import breakage**

```bash
python -m pytest tests/ -q --tb=short
```

Expected: All tests pass **except** any test that explicitly checks for `boost:industrial` in non-keyword test files. Check the output — if anything outside `test_keywords.py` fails, grep for it:

```bash
grep -r "boost:industrial\|INDUSTRIAL_KEYWORDS" tests/ --include="*.py"
```

Fix any references found. The `test_triage_handler.py::test_boost_tags_stored_in_ddb` test uses `boost:open-source` (not industrial) — it should be fine.

**Step 4: Commit**

```bash
git add tests/test_keywords.py config/keywords.py
git commit -m "fix: remove INDUSTRIAL_KEYWORDS and boost:industrial; add neurodivergent RDD terms"
```

---

## Task 3: Restore the scoring threshold

**Files:**
- Modify: `config/scoring_weights.py`

**Step 1: Update the file**

Change line 1 (the module docstring) and line 4 (the threshold):

```python
# config/scoring_weights.py
"""Per-stream scoring thresholds and parameters.

Threshold history:
- AI_ML: started at 9, dropped to 8, then 7 as biased scorer underscored
  non-industrial content. Restored to 9 after fixing scorer prompt.
- WORLD: keeping at 7 -- world content is more variable.
"""

AI_ML_PASS_THRESHOLD = 9    # out of 15 -- restored after fixing scorer prompt bias
WORLD_PASS_THRESHOLD = 7    # out of 15 (lowered from 8)
MIN_STORIES_FOR_BRIEFING = 1  # always brief if any story passes; log thin_briefing if < 3
MAX_AI_ML_STORIES = 40      # triage cap — how many candidates to score
MAX_WORLD_STORIES = 20      # triage cap — how many candidates to score
MAX_BRIEFING_AI_ML_STORIES = 10  # top-N by score sent to briefing Lambda
MAX_BRIEFING_WORLD_STORIES = 8   # top-N by score sent to briefing Lambda
CLUSTER_SIZE_LEAD_STORY = 3  # cluster_size >= this → Lead Story
CONTENT_TRUNCATE_CHARS = 8000
```

**Step 2: Run full suite**

```bash
python -m pytest tests/ -q --tb=short
```

Expected: All tests pass. The `EditorialScorer` dry-run mock returns `total=9` (which is exactly the new threshold) — it should still count as PASS since the mock hardcodes `decision: "PASS"`. If the dry-run mock fails threshold checks, it's in the scorer logic, not the mock.

**Step 3: Commit**

```bash
git add config/scoring_weights.py
git commit -m "fix: restore AI_ML_PASS_THRESHOLD to 9/15 after fixing scorer prompt bias"
```

---

## Task 4: Reframe the AI Abstract scorer prompt

**Files:**
- Modify: `src/services/editorial_scorer.py`

**Step 1: Update the module docstring (lines 1–12)**

Change `- relevance (to Seth's context)` to `- relevance (to technically literate AI/ML readership)`:

```python
# src/services/editorial_scorer.py
"""Editorial scoring for Lambda 2. Uses Haiku to score each story.

Scoring dimensions (1-5 each, total out of 15):
- journalistic_integrity
- relevance (to technically literate AI/ML readership)
- novelty

Thresholds (from config/scoring_weights.py):
- AI_ML: pass if total >= 9
- WORLD: pass if total >= 8
"""
```

**Step 2: Replace SCORE_AI_ML_TEMPLATE (lines 20–64)**

Replace the entire `SCORE_AI_ML_TEMPLATE` string with:

```python
SCORE_AI_ML_TEMPLATE = """\
You are the editorial filter for "The AI Abstract," a public intelligence brief
covering the AI and machine learning landscape for technically literate readers:
practitioners, researchers, data scientists, founders, VCs, and informed observers
across industries.

Score this story on three dimensions (1-5 each):

JOURNALISTIC_INTEGRITY: Is this based on verifiable facts, peer-reviewed work,
or primary sources? (5 = peer-reviewed/primary source, 1 = speculation/PR copy)

RELEVANCE: Does this matter to someone seriously following AI/ML developments?
INCLUDE: model releases and capability milestones, peer-reviewed research breakthroughs
(memory architectures, reasoning advances, cognition and neuroscience studies),
open-source releases, policy and governance developments with field-wide implications,
culturally significant AI content that merits long-form analysis,
consciousness/AGI/alignment content (long-horizon signals for the field).
INCLUDE: viral or widely-discussed studies even if contested -- high engagement
signals editorial value and long-form potential (e.g. brain atrophy, cognition research).
PENALIZE: funding rounds without technical substance, product demos without novel
capability or deployment path, ChatGPT wrappers, productivity hacks, no-code AI tools,
PR-driven announcements with no research backing.

NOVELTY: Is this genuinely new information, or rehash? Does the title sound like
the tenth article on the same story this week?

Boost tags from triage are provided -- use them to inform relevance scoring:
boost:open-source   -> elevate relevance (democratization thesis)
velocity:hn-high    -> strong relevance boost; actively discussed field-wide (200+ HN points)
velocity:hn-medium  -> moderate boost; gaining traction (50-199 HN points)
long-signal:rdd     -> never penalize; slow-burn signals about AI consciousness,
                       alignment, and cognition that compound over years

Return ONLY valid JSON -- no explanation, no markdown:
{{
  "integrity": <1-5>,
  "relevance": <1-5>,
  "novelty": <1-5>,
  "total": <sum>,
  "decision": "PASS" | "REJECT",
  "source_type": "peer-reviewed" | "journalism" | "commentary" | "single-source",
  "reasoning": "<one sentence -- why it passes or fails>",
  "summary": "<two sentences if PASS: what happened + why it matters to the AI/ML field. null if REJECT>"
}}

Threshold: PASS if total >= {threshold}.

Story title: {title}
Story content: {content}
Feed: {feed_name}
Sub-bucket: {sub_bucket}
Boost tags: {boost_tags}
"""
```

**Step 3: Run full suite**

```bash
python -m pytest tests/ -q --tb=short
```

Expected: All tests pass. The scorer tests only test JSON parsing and the `_build_prompt` format method — they don't assert on template content, so this is safe.

**Step 4: Commit**

```bash
git add src/services/editorial_scorer.py
git commit -m "fix: reframe SCORE_AI_ML_TEMPLATE for public AI/ML readership; drop industrial persona"
```

---

## Task 5: Write HN velocity tests first (TDD)

**Files:**
- Modify: `tests/test_triage_handler.py`

**Step 1: Add the two new tests at the bottom of the file**

```python
@patch("src.handlers.triage_handler.ContextLoader")
@patch("src.handlers.triage_handler.boto3")
@patch("src.handlers.triage_handler.RaindropClient")
@patch("src.handlers.triage_handler.StoryStaging")
@patch("src.handlers.triage_handler.NewsBlurClient")
@patch("src.handlers.triage_handler.Settings")
def test_hn_velocity_high_adds_boost_tag(
    mock_settings_cls, mock_nb_cls, mock_staging_cls, mock_raindrop_cls,
    mock_boto3, mock_context_cls,
):
    """Stories with 200+ HN points get velocity:hn-high in stored boost_tags."""
    mock_settings_cls.return_value = _default_settings()
    story = _make_story(
        feed="cs.AI updates on arXiv.org",
        title="Major open-source LLM release",
        hash="h_hn1",
    )
    mock_nb_cls.return_value.fetch_unread_stories.return_value = [story]
    mock_staging_cls.return_value.check_duplicate.return_value = False
    mock_raindrop_cls.return_value.check_duplicate.return_value = False
    mock_raindrop_cls.return_value.create_bookmark.return_value = {"_id": 10}
    mock_context_cls.return_value.fetch_all.return_value = {}

    with patch("src.handlers.triage_handler._check_hn_velocity", return_value=250):
        handler_mod.lambda_handler({}, {})

    call_args = mock_staging_cls.return_value.store_story.call_args[0][0]
    assert "velocity:hn-high" in call_args["boost_tags"]


def test_hn_velocity_failure_does_not_raise():
    """HN API failure never propagates -- _check_hn_velocity returns 0 silently."""
    import urllib.request
    from unittest.mock import patch
    with patch("urllib.request.urlopen", side_effect=Exception("network error")):
        from src.handlers.triage_handler import _check_hn_velocity
        result = _check_hn_velocity("https://example.com/story")
    assert result == 0
```

**Step 2: Run the new tests to confirm they fail**

```bash
python -m pytest tests/test_triage_handler.py::test_hn_velocity_high_adds_boost_tag \
                 tests/test_triage_handler.py::test_hn_velocity_failure_does_not_raise -v
```

Expected: Both FAIL — `_check_hn_velocity` doesn't exist yet.

---

## Task 6: Implement `_check_hn_velocity` and wire it into `_process_stream`

**Files:**
- Modify: `src/handlers/triage_handler.py`

**Step 1: Add the function after the `_truncate_content` function (around line 29)**

```python
def _check_hn_velocity(url: str) -> int:
    """
    Query HN Algolia API for point score of this URL.
    Returns 0 on any failure -- never blocks triage.
    Free API, no key required, 2s timeout.
    """
    import urllib.request
    import urllib.parse
    import json as _json

    try:
        encoded = urllib.parse.quote(url, safe="")
        api_url = (
            f"https://hn.algolia.com/api/v1/search"
            f"?query={encoded}"
            f"&restrictSearchableAttributes=url"
            f"&hitsPerPage=1"
        )
        req = urllib.request.Request(api_url, headers={"User-Agent": "research-agent/1.0"})
        with urllib.request.urlopen(req, timeout=2) as resp:
            data = _json.loads(resp.read())
        hits = data.get("hits", [])
        if hits:
            return int(hits[0].get("points") or 0)
    except Exception:
        pass  # never raise -- HN lookup is best-effort
    return 0
```

**Step 2: Wire it into `_process_stream` — add the HN check block immediately after `boost_tags = triage.get_boost_tags(story)` (around line 181)**

Find this line in `_process_stream`:
```python
boost_tags = triage.get_boost_tags(story)
```

Insert immediately after it:
```python
# HN velocity -- best-effort, never blocks routing
if briefing_type == "AI_ML":
    hn_score = _check_hn_velocity(str(story.story_permalink))
    if hn_score >= 200:
        boost_tags.append("velocity:hn-high")
    elif hn_score >= 50:
        boost_tags.append("velocity:hn-medium")
```

**Step 3: Run the HN velocity tests**

```bash
python -m pytest tests/test_triage_handler.py::test_hn_velocity_high_adds_boost_tag \
                 tests/test_triage_handler.py::test_hn_velocity_failure_does_not_raise -v
```

Expected: Both PASS.

**Step 4: Commit**

```bash
git add src/handlers/triage_handler.py tests/test_triage_handler.py
git commit -m "feat: add HN Algolia velocity check to triage; velocity:hn-high/medium tags for AI_ML stories"
```

---

## Task 7: Run full test suite

**Step 1: Run all tests**

```bash
python -m pytest tests/ -v
```

Expected: All 191+ tests pass (189 original + 3 new keyword tests + 2 new velocity tests − 2 removed industrial tests = 192 net). The exact count depends on what was removed/added.

If anything fails:
- Industrial-related failures → grep `tests/` for `boost:industrial` or `INDUSTRIAL_KEYWORDS` and fix
- Scorer failures → check that `SCORE_AI_ML_TEMPLATE` format placeholders (`{threshold}`, `{title}`, `{content}`, `{feed_name}`, `{sub_bucket}`, `{boost_tags}`) are all present and correctly double-braced (`{{`, `}}`) for the JSON example in the template

---

## Task 8: Create `scripts/delete_todays_briefing.py`

**Files:**
- Create: `scripts/delete_todays_briefing.py`

**Step 1: Create the script**

```python
# scripts/delete_todays_briefing.py
"""One-shot: delete today's AM briefing from Raindrop briefing collection."""
import os
import requests
from datetime import date

TOKEN = os.environ["RAINDROP_TOKEN"]
COLLECTION_ID = os.environ["RAINDROP_BRIEFING_COLLECTION_ID"]
TODAY = date.today().isoformat()  # e.g. "2026-02-19"

headers = {"Authorization": f"Bearer {TOKEN}"}

# Fetch all bookmarks in briefing collection
resp = requests.get(
    f"https://api.raindrop.io/rest/v1/raindrops/{COLLECTION_ID}",
    headers=headers,
    params={"perpage": 50},
)
resp.raise_for_status()
items = resp.json().get("items", [])

# Find and delete today's AM briefing
deleted = 0
for item in items:
    title = item.get("title", "")
    if TODAY in title and ("AM" in title or "morning" in title.lower() or "abstract" in title.lower()):
        rid = item["_id"]
        del_resp = requests.delete(
            f"https://api.raindrop.io/rest/v1/raindrop/{rid}",
            headers=headers,
        )
        print(f"Deleted: {title} (id={rid}, status={del_resp.status_code})")
        deleted += 1

print(f"Done. Deleted {deleted} briefing(s).")
```

**Step 2: Commit the script**

```bash
git add scripts/delete_todays_briefing.py
git commit -m "feat: one-shot script to delete today's AM briefing from Raindrop (for re-runs)"
```

---

## Task 9: Final commit check + push

**Step 1: Verify git log looks right**

```bash
git log --oneline -7
```

Expected to see (in order, newest first):
1. `feat: one-shot script to delete today's AM briefing from Raindrop`
2. `feat: add HN Algolia velocity check to triage; velocity:hn-high/medium tags for AI_ML stories`
3. `fix: reframe SCORE_AI_ML_TEMPLATE for public AI/ML readership; drop industrial persona`
4. `fix: restore AI_ML_PASS_THRESHOLD to 9/15 after fixing scorer prompt bias`
5. `fix: remove INDUSTRIAL_KEYWORDS and boost:industrial; add neurodivergent RDD terms`
6. `docs: design doc for public scorer reframe + HN velocity (2026-02-19)` (already committed)

**Step 2: Push to main**

```bash
git push origin main
```

---

## Task 10: Live run — delete AM brief + trigger fresh pipeline

**Step 1: Confirm Lambda function name (already verified as `research-agent-triage`)**

```bash
grep "function_name" /home/r3crsvint3llgnz/01_Projects/research-agent/terraform/lambda.tf | head -3
```

Expected: `function_name = "research-agent-triage"` confirmed.

**Step 2: Fetch Raindrop credentials from SSM**

```bash
RAINDROP_TOKEN=$(aws ssm get-parameter \
  --name /prod/ResearchAgent/Raindrop_Token \
  --with-decryption \
  --query Parameter.Value \
  --output text \
  --profile seth-dev \
  --region us-east-1)

RAINDROP_BRIEFING_COLLECTION_ID=$(aws ssm get-parameter \
  --name /prod/ResearchAgent/Raindrop_Briefing_Collection_Id \
  --with-decryption \
  --query Parameter.Value \
  --output text \
  --profile seth-dev \
  --region us-east-1)

echo "Token: ${RAINDROP_TOKEN:0:8}... Collection: $RAINDROP_BRIEFING_COLLECTION_ID"
```

Expected: token prefix + numeric collection ID printed. If empty, check SSM param names in the AWS console.

**Step 3: Delete today's AM briefing from Raindrop**

```bash
cd /home/r3crsvint3llgnz/01_Projects/research-agent
RAINDROP_TOKEN=$RAINDROP_TOKEN \
RAINDROP_BRIEFING_COLLECTION_ID=$RAINDROP_BRIEFING_COLLECTION_ID \
python scripts/delete_todays_briefing.py
```

Expected: `Deleted: The AI Abstract — 2026-02-19 AM (id=..., status=200)` followed by `Done. Deleted 1 briefing(s).`

If `Deleted 0 briefings`: either the brief title format doesn't match the filter, or today's AM brief is in a different collection. Check manually in Raindrop UI and adjust the title filter in the script if needed.

**Step 4: Invoke Lambda 1 (triage) directly**

```bash
cd /home/r3crsvint3llgnz/01_Projects/research-agent
aws lambda invoke \
  --function-name research-agent-triage \
  --payload '{"source": "manual"}' \
  --cli-binary-format raw-in-base64-out \
  --profile seth-dev \
  --region us-east-1 \
  response.json && cat response.json
```

Expected response body: `{"statusCode": 200, "body": {"ai_ml_count": N, "world_count": M, ...}}`. N should be > 0 for a useful run.

Note: Lambda 1 runs the **old deployed code** — the new code changes need a deploy to take effect on Lambda. However, invoking Lambda 1 will still start the pipeline using the *existing* Lambda images, producing a fresh briefing. The scorer fix (prompt, threshold) will only be active after `./deploy.sh` is run.

**Step 5: Decide — deploy now or just run fresh with old code?**

- If you want the fixed scorer active on this run: run `./deploy.sh` first, then invoke.
- If you just want a fresh brief (old scorer still biased but new run): invoke now.

To deploy first:
```bash
./deploy.sh
```
Then wait for deployment confirmation before invoking.

**Step 6: Tail Lambda 2 (summarizer/scorer) logs**

```bash
aws logs tail /aws/lambda/research-agent-summarizer \
  --follow \
  --profile seth-dev \
  --region us-east-1
```

Watch for `editorial_scorer.scored` log lines showing `decision=PASS/REJECT` and `total=N`.

**Step 7: Tail Lambda 3 (briefing) logs**

In a second terminal:
```bash
aws logs tail /aws/lambda/research-agent-briefing \
  --follow \
  --profile seth-dev \
  --region us-east-1
```

Watch for `briefing.posted` or `site_post.success`. The brief should appear in Raindrop within ~3 minutes of Lambda 1 completing.

---

## Success Criteria

- [ ] `python -m pytest tests/ -v` → all tests pass
- [ ] `boost:industrial` appears nowhere in the codebase (except comments)
- [ ] `AI_ML_PASS_THRESHOLD = 9` confirmed in `config/scoring_weights.py`
- [ ] `_check_hn_velocity` function exists in `triage_handler.py`
- [ ] New briefing appears in Raindrop within 3 minutes of Lambda 1 invoke
- [ ] Briefing reflects new public readership framing (if deployed before run)

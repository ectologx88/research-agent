# Design: Public Scorer Reframe + HN Velocity

**Date:** 2026-02-19
**Branch:** main
**Status:** Approved

---

## Problem

The `SCORE_AI_ML_TEMPLATE` in `src/services/editorial_scorer.py` was written for a private
persona: an AI Adoption Consultant at a German chemical manufacturer managing PhD-level engineers.
This private framing leaked into scoring behavior:

- `boost:industrial` explicitly elevated relevance for manufacturing/chemical AI content
- `DEMOCRATIZATION_KEYWORDS` included "chemical", "supply chain", "predictive maintenance"
- Non-industrial AI/ML research was systematically under-scored
- Threshold was walked down 9 → 7 to compensate for bias — admitting more noise

The AI Abstract is a **public** brief for technically literate readers (practitioners,
researchers, founders, VCs). The scorer should reflect that readership, not a private context.

---

## Root Cause Chain

```
Private persona in SCORE_AI_ML_TEMPLATE
  → industrial stories over-scored
  → non-industrial AI research under-scored
  → threshold lowered 9→7 to compensate
  → more noise passes
  → brief quality degrades
```

Fix: sever the private context, restore the threshold.

---

## Changes

### 1. `src/services/editorial_scorer.py` — SCORE_AI_ML_TEMPLATE

Full replacement (lines 20–64). Key changes:

- **Persona:** "editorial filter for The AI Abstract, a public intelligence brief covering the
  AI and machine learning landscape for technically literate readers: practitioners, researchers,
  data scientists, founders, VCs, and informed observers across industries."
- **RELEVANCE INCLUDE:** model releases, peer-reviewed breakthroughs, open-source, policy/governance,
  consciousness/AGI/alignment. **New:** viral/widely-discussed studies even if contested — high
  engagement signals editorial value independently of source quality (e.g. brain atrophy research).
- **Boost tag glossary:** drops `boost:industrial`; adds `velocity:hn-high` and `velocity:hn-medium`
  (pre-registers HN velocity tags before they are implemented in triage).
- **summary field:** "why it matters for enterprise AI" → "why it matters to the AI/ML field"
- **Docstring:** `relevance (to Seth's context)` → `relevance (to technically literate AI/ML readership)`

### 2. `config/keywords.py` — full replacement

- `DEMOCRATIZATION_KEYWORDS`: removes "manufacturing", "industrial", "chemical", "supply chain",
  "predictive maintenance" — these were private-context additions
- `INDUSTRIAL_KEYWORDS`: **deleted entirely** — `boost:industrial` tag no longer exists
- `RDD_KEYWORDS`: adds "autistic", "autism", "neurodivergent", "cognitive" — captures
  neurodivergence research as long-signal, aligns with consciousness/cognition research thread
  and Wake series context
- `get_boost_tags()`: drops `boost:industrial` branch

### 3. `config/scoring_weights.py`

- `AI_ML_PASS_THRESHOLD`: 7 → **9** (restored after fixing scorer prompt bias)
- Updated docstring records threshold history for future maintainers

### 4. `src/handlers/triage_handler.py` — HN Velocity Check

Add `_check_hn_velocity(url: str) -> int` as a module-level standalone function:

- Queries HN Algolia API (`hn.algolia.com/api/v1/search?query=<url>`)
- 2s timeout, stdlib only (`urllib.request`, `urllib.parse`)
- Returns 0 on any failure — never raises, never blocks routing

Insert into `_process_stream()` immediately after `boost_tags = triage.get_boost_tags(story)`,
guarded by `briefing_type == "AI_ML"` (WORLD stories are not HN-calibrated):

```python
if briefing_type == "AI_ML":
    hn_score = _check_hn_velocity(str(story.story_permalink))
    if hn_score >= 200:
        boost_tags.append("velocity:hn-high")
    elif hn_score >= 50:
        boost_tags.append("velocity:hn-medium")
```

**Performance:** sequential, up to 40 calls × 2s timeout = 80s worst case. Real-world typical
< 200ms per call = ~8-15s added to Lambda 1 runtime. Acceptable given Lambda 1's time budget.

### 5. Test Updates

**`tests/test_keywords.py`:**
- `test_industrial_gets_boost` → replace with `test_industrial_keywords_not_boosted` asserting
  `boost:industrial` is NOT produced by any industrial-adjacent title
- `test_overlap_produces_both_tags` → update: only `boost:open-source` expected (not `boost:industrial`)
- Add `test_rdd_neurodivergent_gets_long_signal` — neurodivergent/autism/cognitive titles get
  `long-signal:rdd`

**`tests/test_triage_handler.py`:**
- `test_hn_velocity_high_adds_boost_tag`: patches `_check_hn_velocity` → 250, verifies
  `velocity:hn-high` in stored `boost_tags`
- `test_hn_velocity_failure_does_not_raise`: patches `urllib.request.urlopen` to raise Exception,
  verifies `_check_hn_velocity` returns 0

### 6. Live Run (Task 6)

After all tests pass:
1. Fetch Raindrop credentials from SSM
2. Run `scripts/delete_todays_briefing.py` (one-shot utility, placed in `scripts/` not `deploy.sh`)
3. Check `terraform/lambda.tf` for exact Lambda 1 function name
4. Invoke Lambda 1 directly; tail Lambda 2 + 3 logs
5. New briefing should appear in Raindrop within ~3 minutes

---

## What Does NOT Change

- `SCORE_WORLD_TEMPLATE` — world brief persona and scoring are correct
- `config/feed_rules.py` — routing is correct
- `src/services/personas.py` — briefing synthesis prompts already corrected
- `src/services/velocity.py` — topic clustering is separate from HN social proof velocity

---

## Files Modified

```
src/services/editorial_scorer.py    # SCORE_AI_ML_TEMPLATE + docstring
config/keywords.py                  # remove industrial, add neurodivergent RDD terms
config/scoring_weights.py           # AI_ML threshold 7→9, updated docstring
src/handlers/triage_handler.py      # _check_hn_velocity() + inline call
tests/test_keywords.py              # update industrial tests, add neurodivergent test
tests/test_triage_handler.py        # add HN velocity tests
scripts/delete_todays_briefing.py   # one-shot Raindrop cleanup utility (new file)
```

---

## Success Criteria

1. All tests green (189+ passing)
2. Fresh Lambda run produces AI Abstract with 9/15 threshold applied
3. HN velocity tags appear in DDB boost_tags for any AI_ML story with 50+ HN points
4. Industrial content no longer gets artificial relevance boost from scorer

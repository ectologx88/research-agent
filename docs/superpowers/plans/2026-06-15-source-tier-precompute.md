# Source Tier Precompute Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic `source_tier` field (`"arxiv"` | `"secondary"`) to each scored story, computed by regex from the story's URL and content, and instruct both personas to render a `[no arXiv artifact]` marker plus attribution framing for `"secondary"`-tier stories.

**Architecture:** A new pure module-level helper `_compute_source_tier(url, content) -> str` in `src/handlers/summarizer_handler.py` searches `url` and `content` separately for an arXiv ID (URL form or bare `arXiv:YYMM.NNNNN` citation) using a compiled regex `_ARXIV_ID_PATTERN`. `_score_story()` calls it and adds `"source_tier"` to its return dict, which flows unchanged through SQS to the briefing Lambda and into `_dumps(stories)` in `src/services/personas.py`. Both `_EQUALIZER_SYSTEM` and `_ZEITGEIST_SYSTEM` get an additive instruction block (verbatim, identical text) telling the persona how to render `secondary`-tier stories.

**Tech Stack:** Python 3.12, pytest, unittest.mock, `re` (stdlib) — no new dependencies.

---

### Task 1: Add `_compute_source_tier()` helper with tests

**Files:**
- Modify: `src/handlers/summarizer_handler.py:1-2` (imports), and add new function + regex constant after imports, before `def lambda_handler(event, context):` (currently line 21)
- Test: `tests/test_summarizer_handler.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_summarizer_handler.py`, after the existing imports (after line 6, before `_sqs_event`):

```python
def test_compute_source_tier_arxiv_abs_url():
    assert handler_mod._compute_source_tier(
        "https://arxiv.org/abs/2606.09894", ""
    ) == "arxiv"


def test_compute_source_tier_arxiv_pdf_url_with_version():
    assert handler_mod._compute_source_tier(
        "https://export.arxiv.org/pdf/2606.09894v2", ""
    ) == "arxiv"


def test_compute_source_tier_press_writeup_citing_preprint():
    assert handler_mod._compute_source_tier(
        "https://arstechnica.com/science/some-article/",
        "...researchers say... arXiv:2606.09894 describes the method...",
    ) == "arxiv"


def test_compute_source_tier_erdos_case_no_arxiv_id():
    assert handler_mod._compute_source_tier(
        "https://arstechnica.com/science/some-article/",
        "...OpenAI disproved the Erdős unit distance conjecture, Gowers said...",
    ) == "secondary"


def test_compute_source_tier_empty_inputs():
    assert handler_mod._compute_source_tier("", "") == "secondary"


def test_compute_source_tier_missing_keys_via_get_defaults():
    item = {}
    assert handler_mod._compute_source_tier(
        item.get("url", ""), item.get("content", "")
    ) == "secondary"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_summarizer_handler.py -k compute_source_tier -v`
Expected: FAIL with `AttributeError: module 'src.handlers.summarizer_handler' has no attribute '_compute_source_tier'`

- [ ] **Step 3: Add the `re` import**

In `src/handlers/summarizer_handler.py`, the current imports are:

```python
"""Lambda 2: Editorial scoring, Raindrop note updates, forward to briefing queue."""
import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
```

Change to:

```python
"""Lambda 2: Editorial scoring, Raindrop note updates, forward to briefing queue."""
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
```

- [ ] **Step 4: Implement `_compute_source_tier()` and `_ARXIV_ID_PATTERN`**

Add this after the imports/module-level constants block, immediately before `def lambda_handler(event, context):` (currently line 21):

```python
_ARXIV_ID_PATTERN = re.compile(
    r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})|arxiv:\s*(\d{4}\.\d{4,5})",
    re.IGNORECASE,
)


def _compute_source_tier(url: str, content: str) -> str:
    """Classify a story as "arxiv" or "secondary" based on a citable arXiv artifact.

    Searches both the story's URL and its content for an arXiv URL
    (arxiv.org/abs/... or arxiv.org/pdf/..., any subdomain, with or without
    a version suffix) or a bare "arXiv:YYMM.NNNNN" citation in body text.
    A match anywhere means a citable preprint exists, even if the story's
    own URL points to a press writeup. No match degrades to "secondary",
    the more conservative tier.
    """
    if _ARXIV_ID_PATTERN.search(f"{url}\n{content}"):
        return "arxiv"
    return "secondary"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_summarizer_handler.py -k compute_source_tier -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add src/handlers/summarizer_handler.py tests/test_summarizer_handler.py
git commit -m "Add _compute_source_tier helper for arXiv-artifact detection"
```

---

### Task 2: Wire `source_tier` into `_score_story`'s return dict

**Files:**
- Modify: `src/handlers/summarizer_handler.py:115` (inside `_score_story`'s return dict)
- Test: `tests/test_summarizer_handler.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_summarizer_handler.py`, after `test_passes_stories_sent_to_briefing_queue` (after line 96):

```python
@patch("src.handlers.summarizer_handler.NewsBlurClient")
@patch("src.handlers.summarizer_handler.RaindropClient")
@patch("src.handlers.summarizer_handler.EditorialScorer")
@patch("src.handlers.summarizer_handler.StoryStaging")
@patch("src.handlers.summarizer_handler.boto3")
@patch("src.handlers.summarizer_handler.Settings")
def test_source_tier_included_in_briefing_payload(
    mock_settings_cls, mock_boto3, mock_staging_cls, mock_scorer_cls,
    mock_raindrop_cls, mock_nb_cls,
):
    mock_settings_cls.return_value = _default_settings()
    items = [_make_item(f"h{i}") for i in range(5)]
    items[0]["url"] = "https://arxiv.org/abs/2606.09894"
    items[1]["url"] = "https://arstechnica.com/science/some-article/"
    items[1]["content"] = "OpenAI disproved the Erdős unit distance conjecture, Gowers said."
    mock_staging_cls.return_value.batch_get_stories.return_value = items
    mock_scorer_cls.return_value.score.return_value = _pass_result()
    mock_raindrop_cls.return_value.update_bookmark.return_value = {}

    handler_mod.lambda_handler(_sqs_event(hashes=[f"h{i}" for i in range(5)]), {})

    sqs_mock = mock_boto3.client.return_value
    body = json.loads(sqs_mock.send_message.call_args[1]["MessageBody"])
    stories_by_hash = {s["story_hash"]: s for s in body["stories"]}
    assert stories_by_hash["h0"]["source_tier"] == "arxiv"
    assert stories_by_hash["h1"]["source_tier"] == "secondary"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_summarizer_handler.py -k source_tier_included -v`
Expected: FAIL — `KeyError: 'source_tier'`

- [ ] **Step 3: Wire `_compute_source_tier` into the return dict**

In `src/handlers/summarizer_handler.py`, the return dict in `_score_story` is (around line 112-132):

```python
        return ({
            "story_hash": story_hash,
            "title": item["title"],
            "url": item.get("url", ""),
            "summary": result.summary,
            "source_type": result.source_type,
```

Change the `"url"` line and the line immediately after it to:

```python
        return ({
            "story_hash": story_hash,
            "title": item["title"],
            "url": item.get("url", ""),
            "source_tier": _compute_source_tier(item.get("url", ""), item.get("content", "")),
            "summary": result.summary,
            "source_type": result.source_type,
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_summarizer_handler.py -k source_tier_included -v`
Expected: PASS

- [ ] **Step 5: Run the full summarizer handler test suite to confirm no regressions**

Run: `pytest tests/test_summarizer_handler.py -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/handlers/summarizer_handler.py tests/test_summarizer_handler.py
git commit -m "Wire source_tier into briefing queue story payload"
```

---

### Task 3: Add `source_tier` rendering instructions to both personas

**Files:**
- Modify: `src/services/personas.py:139` (Equalizer `RENDERING RULES`) and `:198-201` (Zeitgeist `<journalistic_standards>` DEPTH paragraph)
- Test: `tests/test_personas.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_personas.py`, in `TestEqualizerJournalisticStandards` (after `test_depth_guidance_present`, after line 128):

```python
    def test_source_tier_secondary_instruction_present(self):
        prompt = build_equalizer_prompt(stories=[], signals=[], prior_briefing=None)
        assert "[no arXiv artifact]" in prompt
        assert 'source_tier == "secondary"' in prompt
```

Add to `TestZeitgeistPrompt` (after `test_journalistic_standards_present`, after line 101):

```python
    def test_source_tier_secondary_instruction_present(self):
        prompt = build_zeitgeist_prompt(
            stories=[], signals=[], prior_briefing=None, context_block=""
        )
        assert "[no arXiv artifact]" in prompt
        assert 'source_tier == "secondary"' in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_personas.py -k source_tier_secondary -v`
Expected: FAIL — `assert "[no arXiv artifact]" in prompt` (instruction text not yet present)

- [ ] **Step 3: Define the shared instruction text constant**

In `src/services/personas.py`, immediately after the `SOURCE_EMOJI` dict (after line 26, before `_EQUALIZER_SYSTEM = """\`), add:

```python
_SOURCE_TIER_INSTRUCTION = (
    '`source_tier == "secondary"`: this story has no arXiv-citable artifact. '
    "When linking this story inline on first mention, append the marker "
    "`[no arXiv artifact]` immediately after the link — this is part of the "
    "mandatory inline-link rendering, not optional decoration. Additionally, "
    "attribute extraordinary, quantitative, or surprising claims explicitly to "
    'the reporting outlet (e.g., "according to [Outlet], not yet corroborated '
    'by a published paper") rather than stating them as established fact — '
    "regardless of `integrity` score. Both the marker and the attribution "
    "framing are independent of and additional to the `integrity <= 2` flag "
    "and `SOURCE_EMOJI`."
)
```

- [ ] **Step 4: Insert the instruction into `_EQUALIZER_SYSTEM`'s RENDERING RULES**

In `src/services/personas.py`, find (around line 136-141):

```python
RENDERING RULES
- Inline links: when a source is referenced in the body, link it on first mention as
  [emoji][Title](url). Do not re-link the same URL. Emoji key: {emoji_table}
- integrity <= 2: add explicit ⚠️ single-source/unverified flag in body near the story
- cluster_size >= 3: this is the lead story — open with it, give it the most space
- NEVER invent sources or include stories not in the payload
```

Change the `integrity <= 2` line and the line after it to:

```python
RENDERING RULES
- Inline links: when a source is referenced in the body, link it on first mention as
  [emoji][Title](url). Do not re-link the same URL. Emoji key: {emoji_table}
- integrity <= 2: add explicit ⚠️ single-source/unverified flag in body near the story
- {source_tier_instruction}
- cluster_size >= 3: this is the lead story — open with it, give it the most space
- NEVER invent sources or include stories not in the payload
```

Then update the `.format(...)` call at the bottom of `_EQUALIZER_SYSTEM` (currently around line 143-145):

```python
""".format(
    emoji_table="\n".join(f"  {k} → {v}" for k, v in SOURCE_EMOJI.items())
)
```

Change to:

```python
""".format(
    emoji_table="\n".join(f"  {k} → {v}" for k, v in SOURCE_EMOJI.items()),
    source_tier_instruction=_SOURCE_TIER_INSTRUCTION,
)
```

Note: the existing `{emoji_table}` placeholder and the new `{source_tier_instruction}` placeholder are both inside a triple-quoted string that uses `.format()`. Since the string contains literal `{` characters only in these two format placeholders (no other braces appear in `_EQUALIZER_SYSTEM`), no escaping changes are needed beyond adding the new placeholder and format argument.

- [ ] **Step 5: Insert the instruction into `_ZEITGEIST_SYSTEM`'s `<journalistic_standards>` block**

In `src/services/personas.py`, find (around line 198-201):

```python
DEPTH: Stories with clear primary-source backing (integrity >= 4) earn more space.
A geopolitical development with a peer-reviewed or direct-reporting source should
not receive the same treatment as an aggregated wire summary.
</journalistic_standards>
```

Change to:

```python
DEPTH: Stories with clear primary-source backing (integrity >= 4) earn more space.
A geopolitical development with a peer-reviewed or direct-reporting source should
not receive the same treatment as an aggregated wire summary.

{source_tier_instruction}
</journalistic_standards>
```

Then update the `.format(...)` call at the bottom of `_ZEITGEIST_SYSTEM` (currently around line 202-204):

```python
""".format(
    emoji_table=", ".join(f"{k}={v}" for k, v in SOURCE_EMOJI.items())
)
```

Change to:

```python
""".format(
    emoji_table=", ".join(f"{k}={v}" for k, v in SOURCE_EMOJI.items()),
    source_tier_instruction=_SOURCE_TIER_INSTRUCTION,
)
```

Note: `_SOURCE_TIER_INSTRUCTION` itself contains literal `{` / `}`-free text (no curly braces in its content), so embedding it via `.format()` substitution is safe and does not require doubling any braces.

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_personas.py -k source_tier_secondary -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Run the full personas test suite to confirm no regressions**

Run: `pytest tests/test_personas.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/services/personas.py tests/test_personas.py
git commit -m "Instruct personas to render [no arXiv artifact] marker for secondary-tier stories"
```

---

### Task 4: Full test suite, lint, and manual spot-check note

**Files:** None (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `pytest`
Expected: All tests PASS

- [ ] **Step 2: Run lint**

Run: `ruff check .`
Expected: No errors (warnings acceptable per project convention)

- [ ] **Step 3: Final commit if any lint fixes were needed**

If `ruff check .` reported issues, fix with `ruff check --fix .` and commit:

```bash
git add src/handlers/summarizer_handler.py src/services/personas.py tests/test_summarizer_handler.py tests/test_personas.py
git commit -m "Lint fixes for source_tier precompute changes"
```

If no issues, no commit needed — this task is verification-only.

- [ ] **Step 4: Record the manual spot-check as a follow-up (not automated)**

This plan's automated tests verify (a) `_compute_source_tier` classifies correctly, and (b) both prompts contain the `[no arXiv artifact]` / `source_tier == "secondary"` instruction text. They cannot verify that Sonnet actually applies the marker and attribution framing in generated output.

After this branch is deployed, run a manual one-time spot-check:

```bash
DRY_RUN=writes_only <invoke briefing Lambda with a payload containing at least one secondary-tier story with a striking/extraordinary claim>
```

Confirm the generated brief contains the `[no arXiv artifact]` marker on that story's inline link, and that any extraordinary claim is attributed to the reporting outlet rather than stated as fact. This is noted here so it is not silently skipped — it is not part of the automated test suite and does not block merging this branch.

---

## Summary of changes

- `src/handlers/summarizer_handler.py`: new `_ARXIV_ID_PATTERN` regex + `_compute_source_tier()` helper, `import re` added, `_score_story` return dict gains `"source_tier"` key
- `src/services/personas.py`: new `_SOURCE_TIER_INSTRUCTION` constant, inserted into both `_EQUALIZER_SYSTEM` (RENDERING RULES) and `_ZEITGEIST_SYSTEM` (`<journalistic_standards>`) via `.format()`
- `tests/test_summarizer_handler.py`: 6 new unit tests for `_compute_source_tier`, 1 new integration test for `source_tier` in the SQS payload
- `tests/test_personas.py`: 2 new tests asserting the `[no arXiv artifact]` instruction is present in both prompts
- No DB schema changes, no new dependencies, no changes to `SignalTracker`, `velocity.py`, `editorial_scorer.py`, or `SOURCE_EMOJI`
- One manual post-deploy spot-check documented (not automated)

# Signal-Age Framing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate inconsistent LLM-invented timeframe framing ("since February" vs "over the past month") for weak-signal data by pre-computing a `coverage_phrase` string server-side and instructing the LLM to use it verbatim.

**Architecture:** A new pure helper function `_annotate_signal_age()` in `src/handlers/briefing_handler.py` runs immediately after signals are fetched from `SignalTracker`, attaching a `coverage_phrase` field to each signal dict based on `mention_count` and `first_seen`. The prompt builders in `src/services/personas.py` are updated to instruct the LLM to use `coverage_phrase` verbatim instead of computing its own timeframe.

**Tech Stack:** Python 3.14, pytest, unittest.mock — no new dependencies.

---

### Task 1: Add `_annotate_signal_age()` helper with tests

**Files:**
- Modify: `src/handlers/briefing_handler.py:1-16` (imports), and add new function near top of file (after imports, before `_briefing_date_to_iso`)
- Test: `tests/test_briefing_handler.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_briefing_handler.py`, near the top (after existing imports, before the first test function — these are plain unit tests with no mocking needed):

```python
from datetime import datetime, timedelta, timezone


def test_annotate_signal_age_multiple_mentions():
    now = datetime.now(timezone.utc)
    first_seen = (now - timedelta(days=12)).isoformat()
    signals = [{"signal_key": "eval-crisis", "mention_count": 5, "first_seen": first_seen}]

    result = handler_mod._annotate_signal_age(signals)

    assert result[0]["coverage_phrase"] == "mentioned 5 times over the past 12 days"


def test_annotate_signal_age_single_mention():
    now = datetime.now(timezone.utc)
    first_seen = (now - timedelta(days=3)).isoformat()
    signals = [{"signal_key": "open-source", "mention_count": 1, "first_seen": first_seen}]

    result = handler_mod._annotate_signal_age(signals)

    assert result[0]["coverage_phrase"] == "mentioned once, 3 days ago"


def test_annotate_signal_age_first_seen_today():
    now = datetime.now(timezone.utc)
    signals = [{"signal_key": "new-topic", "mention_count": 1, "first_seen": now.isoformat()}]

    result = handler_mod._annotate_signal_age(signals)

    assert result[0]["coverage_phrase"] == "first appeared today"


def test_annotate_signal_age_missing_first_seen():
    signals = [{"signal_key": "no-timestamp", "mention_count": 3}]

    result = handler_mod._annotate_signal_age(signals)

    assert result[0]["coverage_phrase"] == "first appeared today"


def test_annotate_signal_age_malformed_first_seen():
    signals = [{"signal_key": "bad-timestamp", "mention_count": 3, "first_seen": "not-a-date"}]

    result = handler_mod._annotate_signal_age(signals)

    assert result[0]["coverage_phrase"] == "first appeared today"


def test_annotate_signal_age_empty_list():
    assert handler_mod._annotate_signal_age([]) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_briefing_handler.py -k annotate_signal_age -v`
Expected: FAIL with `AttributeError: module 'src.handlers.briefing_handler' has no attribute '_annotate_signal_age'`

- [ ] **Step 3: Add the `datetime` import**

In `src/handlers/briefing_handler.py`, the current imports are:

```python
"""Lambda 3: Synthesize narrative briefing and publish."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request

import boto3
from botocore.config import Config
```

Add `from datetime import datetime, timezone` after `import urllib.request`:

```python
"""Lambda 3: Synthesize narrative briefing and publish."""
import json
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import boto3
from botocore.config import Config
```

- [ ] **Step 4: Implement `_annotate_signal_age()`**

Add this function after the imports/module-level constants, before `_briefing_date_to_iso` (around line 18):

```python
def _annotate_signal_age(signals: list[dict]) -> list[dict]:
    """Attach a precomputed `coverage_phrase` to each signal dict.

    Computes the phrase from `mention_count` and `first_seen` so the LLM
    never has to do date arithmetic or invent a timeframe unit. Missing or
    unparseable `first_seen` degrades to "first appeared today" — signal
    tracking is best-effort, this must never raise.
    """
    now_utc = datetime.now(timezone.utc)

    for signal in signals:
        mention_count = signal.get("mention_count", 0)
        first_seen_raw = signal.get("first_seen")

        days_tracked = 0
        if first_seen_raw:
            try:
                first_seen_dt = datetime.fromisoformat(first_seen_raw)
                days_tracked = max((now_utc - first_seen_dt).days, 0)
            except ValueError:
                days_tracked = 0

        if days_tracked == 0:
            coverage_phrase = "first appeared today"
        elif mention_count == 1:
            coverage_phrase = f"mentioned once, {days_tracked} days ago"
        else:
            coverage_phrase = f"mentioned {mention_count} times over the past {days_tracked} days"

        signal["coverage_phrase"] = coverage_phrase

    return signals
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_briefing_handler.py -k annotate_signal_age -v`
Expected: PASS (6 tests)

- [ ] **Step 6: Commit**

```bash
git add src/handlers/briefing_handler.py tests/test_briefing_handler.py
git commit -m "Add _annotate_signal_age helper for consistent coverage phrasing"
```

---

### Task 2: Wire `_annotate_signal_age()` into the signal-fetch flow

**Files:**
- Modify: `src/handlers/briefing_handler.py` (around line 240, where `signals = signal_tracker.get_signals(cluster_keys)` is called)
- Test: `tests/test_briefing_handler.py` (extend `test_signals_fetched_from_cluster_keys`)

- [ ] **Step 1: Write the failing test**

Modify the existing `test_signals_fetched_from_cluster_keys` test in `tests/test_briefing_handler.py` (around line 154-176). The mocked `get_signals` return value currently has no `first_seen`, which is fine — `_annotate_signal_age` handles that. Add an assertion that the synthesizer receives signals with `coverage_phrase` attached. First, find how `signals` reaches the synthesizer — check what `mock_synth_cls.return_value.synthesize` is called with:

```python
def test_signals_annotated_before_synthesis(
    mock_settings_cls, mock_boto3, mock_post_to_site, mock_synth_cls,
    mock_signal_cls, mock_archive_cls,
):
    mock_settings_cls.return_value = _default_settings()
    stories = [_make_story("h1", cluster_key="eval-crisis")]
    mock_synth_cls.return_value.synthesize.return_value = "Briefing."
    mock_synth_cls.return_value._prior_briefing_key.return_value = ("2026-02-16-PM", "AI_ML")
    mock_archive_cls.return_value.get_prior.return_value = None
    mock_signal_cls.return_value.get_signals.return_value = [
        {"signal_key": "eval-crisis", "mention_count": 5}
    ]

    handler_mod.lambda_handler(_sqs_event(stories=stories), {})

    _, kwargs = mock_synth_cls.return_value.synthesize.call_args
    signals_arg = kwargs.get("signals") if "signals" in kwargs else mock_synth_cls.return_value.synthesize.call_args[0][1]
    assert signals_arg[0]["coverage_phrase"] == "first appeared today"
```

Place this new test directly after `test_signals_fetched_from_cluster_keys` (after line 176), reusing the same `@patch` decorator stack — copy the exact decorator stack from `test_signals_fetched_from_cluster_keys` (lines preceding it) onto this new function.

Note: before writing this test, run `grep -n "synthesize(" src/handlers/briefing_handler.py` to confirm the exact call signature (positional vs keyword `signals=`) so the assertion extracts the right argument. Adjust `signals_arg` extraction to match what you find — the goal is simply to confirm the `signals` list passed to `synthesize()` has `coverage_phrase` set.

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_briefing_handler.py -k signals_annotated -v`
Expected: FAIL — `KeyError: 'coverage_phrase'` (the field doesn't exist yet because `_annotate_signal_age` isn't called)

- [ ] **Step 3: Wire the helper into the handler**

In `src/handlers/briefing_handler.py`, find the line:

```python
    signals = signal_tracker.get_signals(cluster_keys) if cluster_keys else []
```

Change it to:

```python
    signals = signal_tracker.get_signals(cluster_keys) if cluster_keys else []
    signals = _annotate_signal_age(signals)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_briefing_handler.py -k signals_annotated -v`
Expected: PASS

- [ ] **Step 5: Run the full briefing handler test suite to confirm no regressions**

Run: `pytest tests/test_briefing_handler.py -v`
Expected: All tests PASS, including `test_signals_fetched_from_cluster_keys` (unaffected — it doesn't inspect `coverage_phrase`)

- [ ] **Step 6: Commit**

```bash
git add src/handlers/briefing_handler.py tests/test_briefing_handler.py
git commit -m "Annotate signals with coverage_phrase before synthesis"
```

---

### Task 3: Update prompt instructions in personas.py

**Files:**
- Modify: `src/services/personas.py:219` (Equalizer) and `:247` (Zeitgeist)
- Test: `tests/test_personas.py`

- [ ] **Step 1: Check existing test patterns for prompt-content assertions**

Run: `grep -n "WEAK SIGNALS\|def test_.*signal" tests/test_personas.py`

This shows whether there's an existing test asserting on the WEAK SIGNALS section content, so the new test follows the same style (likely asserting a substring is present in the built prompt string).

- [ ] **Step 2: Write the failing tests**

Add to `tests/test_personas.py` (use the same story/signal fixture patterns as neighboring tests in that file — check `build_equalizer_prompt` and `build_zeitgeist_prompt` test setups for the minimal `stories` argument shape required):

```python
def test_equalizer_prompt_instructs_coverage_phrase_usage():
    signals = [{"signal_key": "eval-crisis", "mention_count": 5, "coverage_phrase": "mentioned 5 times over the past 12 days"}]

    prompt = build_equalizer_prompt(stories=[], signals=signals, prior_briefing=None)

    assert "coverage_phrase" in prompt
    assert "mentioned 5 times over the past 12 days" in prompt


def test_zeitgeist_prompt_instructs_coverage_phrase_usage():
    signals = [{"signal_key": "eval-crisis", "mention_count": 5, "coverage_phrase": "mentioned 5 times over the past 12 days"}]

    prompt = build_zeitgeist_prompt(stories=[], signals=signals, prior_briefing=None, context_block="")

    assert "coverage_phrase" in prompt
    assert "mentioned 5 times over the past 12 days" in prompt
```

If `build_equalizer_prompt` or `build_zeitgeist_prompt` require non-empty `stories` (check by running the test first — if it errors on empty list before your assertion, e.g. `IndexError`, use a minimal single-story dict matching the shape used in other tests in this file, found via `grep -n "stories = \[" tests/test_personas.py`).

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_personas.py -k coverage_phrase -v`
Expected: FAIL — `assert "coverage_phrase" in prompt` fails because the instruction text doesn't mention it yet (the `_dumps(signals)` dump will contain the *data* field `coverage_phrase`, but that's only true once Task 2's annotation is present in the dict you pass — since this test passes its own dict with `coverage_phrase` already set, `_dumps(signals)` WILL contain it. So this assertion alone may pass even before Step 4. The real failing assertion is the *instruction text* — adjust the test to assert on the instruction wording instead)

Revise the tests from Step 2 to assert on the instruction text specifically:

```python
def test_equalizer_prompt_instructs_coverage_phrase_usage():
    signals = [{"signal_key": "eval-crisis", "mention_count": 5, "coverage_phrase": "mentioned 5 times over the past 12 days"}]

    prompt = build_equalizer_prompt(stories=[], signals=signals, prior_briefing=None)

    assert "coverage_phrase" in prompt
    assert "Do not compute or estimate a timeframe" in prompt


def test_zeitgeist_prompt_instructs_coverage_phrase_usage():
    signals = [{"signal_key": "eval-crisis", "mention_count": 5, "coverage_phrase": "mentioned 5 times over the past 12 days"}]

    prompt = build_zeitgeist_prompt(stories=[], signals=signals, prior_briefing=None, context_block="")

    assert "coverage_phrase" in prompt
    assert "Do not compute or estimate a timeframe" in prompt
```

Run: `pytest tests/test_personas.py -k coverage_phrase -v`
Expected: FAIL — `assert "Do not compute or estimate a timeframe" in prompt` (instruction text not yet added)

- [ ] **Step 4: Update the Equalizer prompt instruction**

In `src/services/personas.py`, find (around line 218-220):

```python
    if signals:
        parts.append("\n\n## WEAK SIGNALS (from signal_tracker — use exactly this data)\n")
        parts.append(_dumps(signals))
```

Replace with:

```python
    if signals:
        parts.append("\n\n## WEAK SIGNALS (from signal_tracker — use exactly this data)\n")
        parts.append(_dumps(signals))
        parts.append(
            "\n\nFor each signal, use its `coverage_phrase` field verbatim (or "
            "lightly adapted to fit the sentence grammatically) to describe how "
            "long this topic has been recurring. Do not compute or estimate a "
            "timeframe from `first_seen`/`last_seen` yourself, and do not state "
            "a different mention count or time unit than what `coverage_phrase` "
            "provides.\n"
        )
```

- [ ] **Step 5: Update the Zeitgeist prompt instruction**

In `src/services/personas.py`, find (around line 246-248):

```python
    if signals:
        parts.append("\n\n## WEAK SIGNALS\n")
        parts.append(_dumps(signals))
```

Replace with:

```python
    if signals:
        parts.append("\n\n## WEAK SIGNALS\n")
        parts.append(_dumps(signals))
        parts.append(
            "\n\nFor each signal, use its `coverage_phrase` field verbatim (or "
            "lightly adapted to fit the sentence grammatically) to describe how "
            "long this topic has been recurring. Do not compute or estimate a "
            "timeframe from `first_seen`/`last_seen` yourself, and do not state "
            "a different mention count or time unit than what `coverage_phrase` "
            "provides.\n"
        )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `pytest tests/test_personas.py -k coverage_phrase -v`
Expected: PASS (2 tests)

- [ ] **Step 7: Run the full personas test suite to confirm no regressions**

Run: `pytest tests/test_personas.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/services/personas.py tests/test_personas.py
git commit -m "Instruct prompts to use precomputed coverage_phrase for signal timeframes"
```

---

### Task 4: Full test suite and lint

**Files:** None (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `pytest`
Expected: All tests PASS

- [ ] **Step 2: Run lint**

Run: `ruff check .`
Expected: No errors (warnings acceptable per project convention)

- [ ] **Step 3: Final commit if any lint fixes were needed**

If `ruff check .` reported and auto-fixed issues (`ruff check --fix .`), commit:

```bash
git add -A
git commit -m "Lint fixes for signal-age framing changes"
```

If no issues, no commit needed — this task is verification-only.

---

## Summary of changes

- `src/handlers/briefing_handler.py`: new `_annotate_signal_age()` helper + one call site wired in after `get_signals()`
- `src/services/personas.py`: two prompt-instruction additions (Equalizer + Zeitgeist WEAK SIGNALS sections)
- `tests/test_briefing_handler.py`: 7 new/modified tests
- `tests/test_personas.py`: 2 new tests
- No DB schema changes, no new dependencies

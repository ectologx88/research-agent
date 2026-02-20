# Briefing Display Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix three display bugs in the AI Abstract pipeline and website detail page.

**Architecture:** Two repos (`research-agent` Lambda 3 + `recursiveintelligence-website` Next.js page). Changes are surgical — no schema migrations, no new env vars.

**Tech Stack:** Python (Lambda 3 handler + personas), TypeScript/Next.js (brief detail page)

---

## Bug Summary

| # | Bug | Root cause | Fix |
|---|-----|-----------|-----|
| 1 | Title renders as `AI Abstract — 2026-02-19-AM` | Passes raw `briefing_date` slug to `_post_to_site` | Map `time_of_day` → `Morning Edition` / `Evening Edition` |
| 2 | Tagline `**Making the Future Evenly Distributed.**` appears twice — once as raw markdown in card/detail summary, once inside rendered body | `_EQUALIZER_SYSTEM` tells Sonnet to emit it as first body line; `_extract_summary()` naively grabs first non-heading line (the tagline) | Remove tagline from LLM output; add DESCRIPTION sentinel; strip it in handler |
| 3 | `summary` card field is the tagline (raw markdown) instead of clean editorial copy | Same root cause as #2 | DESCRIPTION sentinel extracted as summary; tagline added as static design element in page.tsx only for AI/ML |

**Critical constraint:** The sentinel line `DESCRIPTION: <text>` must be stripped from the body BEFORE it is passed to `_post_to_site`. The body stored in DynamoDB and rendered on the site must be clean.

---

## Task 1: Remove tagline from LLM prompt, add DESCRIPTION sentinel

**Files:**
- Modify: `src/services/personas.py:38-39`

**Step 1: Write failing test**

In `tests/test_briefing_handler.py`, at the top of the file add:

```python
def test_equalizer_system_has_description_sentinel():
    """EQUALIZER prompt must instruct the model to output DESCRIPTION: sentinel."""
    from src.services.personas import _EQUALIZER_SYSTEM
    assert "DESCRIPTION:" in _EQUALIZER_SYSTEM
    assert "Making the Future Evenly Distributed" not in _EQUALIZER_SYSTEM
```

**Step 2: Run test to verify it fails**

```bash
cd /home/r3crsvint3llgnz/01_Projects/research-agent
python -m pytest tests/test_briefing_handler.py::test_equalizer_system_has_description_sentinel -v
```

Expected: FAIL (`Making the Future Evenly Distributed` is present, `DESCRIPTION:` is absent)

**Step 3: Implement — edit `_EQUALIZER_SYSTEM` in `src/services/personas.py`**

Replace lines 36–39 (from `STRUCTURE (produce exactly this order...` through the tagline):

```python
_EQUALIZER_SYSTEM = """\
You are the editorial AI for "The AI Abstract" — a public intelligence brief covering the
AI and machine learning landscape for technically literate readers: practitioners,
researchers, founders, and informed observers across industries.

Your editorial identity: The Equalizer. Voice is authoritative practitioner — write from
inside the field, not "experts say." The thesis: AI is the great equalizer.

DESCRIPTION: Before the briefing body, output exactly one line:
DESCRIPTION: <one sentence — what the AI/ML field moved on today, plain text, no markdown>
This line will be extracted as the brief summary for the website card. Strip all markdown.

STRUCTURE (produce exactly this order, omit sections with no content):

# ⚖️ The AI Abstract

**Editorial: State of Play** (150 words — the dominant shift in the last 12h)
```

The rest of `_EQUALIZER_SYSTEM` (from `**The Level Playing Field Report**` to the end) stays unchanged.

**Step 4: Run test to verify it passes**

```bash
python -m pytest tests/test_briefing_handler.py::test_equalizer_system_has_description_sentinel -v
```

Expected: PASS

**Step 5: Run full suite**

```bash
python -m pytest tests/ -v --tb=short
```

All tests must stay green.

**Step 6: Commit**

```bash
cd /home/r3crsvint3llgnz/01_Projects/research-agent
git add src/services/personas.py tests/test_briefing_handler.py
git commit -m "fix: remove tagline from LLM output, add DESCRIPTION sentinel to Equalizer prompt"
```

---

## Task 2: Extract DESCRIPTION sentinel and fix title in briefing_handler.py

**Files:**
- Modify: `src/handlers/briefing_handler.py:24-30` (`_extract_summary` → `_extract_description`)
- Modify: `src/handlers/briefing_handler.py:58-94` (`_post_to_site` signature + body)
- Modify: `src/handlers/briefing_handler.py:159-163` (title construction + sentinel strip call)

**Step 1: Write failing tests**

Add these tests to `tests/test_briefing_handler.py`:

```python
def test_extract_description_returns_sentinel_line():
    """DESCRIPTION: sentinel line is extracted as description."""
    text = "DESCRIPTION: The field moved fast today.\n\n# ⚖️ The AI Abstract\n\nBody here."
    desc, body = handler_mod._extract_description(text)
    assert desc == "The field moved fast today."
    assert "DESCRIPTION:" not in body
    assert "# ⚖️ The AI Abstract" in body


def test_extract_description_falls_back_to_first_non_heading_line():
    """If no DESCRIPTION: sentinel, falls back to first non-empty non-heading line."""
    text = "# Heading\n\nFallback summary sentence."
    desc, body = handler_mod._extract_description(text)
    assert desc == "Fallback summary sentence."
    assert body == text  # body unchanged when no sentinel found


def test_post_to_site_uses_clean_body():
    """_post_to_site sends body WITHOUT the DESCRIPTION: sentinel line."""
    import urllib.request
    from unittest.mock import patch, MagicMock
    from src.config import Settings

    settings = MagicMock(spec=Settings)
    settings.site_url = "https://example.com"
    settings.brief_api_key = "key"

    raw_text = "DESCRIPTION: Clean sentence.\n\n# ⚖️ The AI Abstract\n\nBody here."
    captured = {}

    def fake_urlopen(req, *args, **kwargs):
        import json as _json
        captured["payload"] = _json.loads(req.data)
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.status = 201
        return mock_resp

    with patch("urllib.request.urlopen", fake_urlopen):
        handler_mod._post_to_site(
            settings, "2026-02-19-AM", [],
            raw_text,
            category="AI/ML",
            title="The AI Abstract — Morning Edition",
        )

    assert captured["payload"]["summary"] == "Clean sentence."
    assert "DESCRIPTION:" not in captured["payload"]["body"]
    assert "# ⚖️ The AI Abstract" in captured["payload"]["body"]


def test_aiml_title_morning_edition():
    """AM AI_ML briefings get title 'The AI Abstract — Morning Edition'."""
    # We inspect the call args to _post_to_site in the integration test
    from unittest.mock import patch, MagicMock, call
    import json

    with patch("src.handlers.briefing_handler.Settings") as mock_settings_cls, \
         patch("src.handlers.briefing_handler.boto3"), \
         patch("src.handlers.briefing_handler._post_to_site") as mock_post, \
         patch("src.handlers.briefing_handler.BriefingSynthesizer") as mock_synth_cls, \
         patch("src.handlers.briefing_handler.SignalTracker"), \
         patch("src.handlers.briefing_handler.BriefingArchive"):

        mock_settings_cls.return_value = _default_settings()
        mock_synth_cls.return_value.synthesize.return_value = (
            "DESCRIPTION: AI moved fast.\n\n# ⚖️ The AI Abstract\n\nBody."
        )
        mock_synth_cls.return_value._prior_briefing_key.return_value = ("2026-02-18", "AI_ML")

        event = _sqs_event(briefing_type="AI_ML", briefing_date="2026-02-19-AM",
                           stories=[_make_story()])
        handler_mod.lambda_handler(event, {})

    _, kwargs = mock_post.call_args
    assert kwargs["title"] == "The AI Abstract — Morning Edition"


def test_aiml_title_evening_edition():
    """PM AI_ML briefings get title 'The AI Abstract — Evening Edition'."""
    from unittest.mock import patch

    with patch("src.handlers.briefing_handler.Settings") as mock_settings_cls, \
         patch("src.handlers.briefing_handler.boto3"), \
         patch("src.handlers.briefing_handler._post_to_site") as mock_post, \
         patch("src.handlers.briefing_handler.BriefingSynthesizer") as mock_synth_cls, \
         patch("src.handlers.briefing_handler.SignalTracker"), \
         patch("src.handlers.briefing_handler.BriefingArchive"):

        mock_settings_cls.return_value = _default_settings()
        mock_synth_cls.return_value.synthesize.return_value = (
            "DESCRIPTION: Evening summary.\n\n# Body."
        )
        mock_synth_cls.return_value._prior_briefing_key.return_value = ("2026-02-18", "AI_ML")

        event = _sqs_event(briefing_type="AI_ML", briefing_date="2026-02-19-PM",
                           stories=[_make_story()])
        handler_mod.lambda_handler(event, {})

    _, kwargs = mock_post.call_args
    assert kwargs["title"] == "The AI Abstract — Evening Edition"
```

**Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_briefing_handler.py::test_extract_description_returns_sentinel_line tests/test_briefing_handler.py::test_extract_description_falls_back_to_first_non_heading_line -v
```

Expected: `AttributeError: module has no attribute '_extract_description'`

**Step 3: Implement**

In `src/handlers/briefing_handler.py`:

**3a.** Replace `_extract_summary` (lines 24–30) with `_extract_description`:

```python
def _extract_description(briefing_text: str) -> tuple[str, str]:
    """Extract DESCRIPTION: sentinel line as the clean summary.

    Returns (description, clean_body) where clean_body has the sentinel line removed.
    Falls back to first non-heading line if no sentinel found (e.g. WORLD briefings).
    """
    lines = briefing_text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith("DESCRIPTION:"):
            description = line[len("DESCRIPTION:"):].strip()
            # Remove the sentinel line and any immediately following blank line
            remaining = lines[i + 1:]
            if remaining and remaining[0].strip() == "":
                remaining = remaining[1:]
            clean_body = "\n".join(remaining)
            return description, clean_body
    # Fallback: no sentinel found — grab first non-empty non-heading line
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped, briefing_text
    return briefing_text[:500], briefing_text
```

**3b.** Update `_post_to_site` signature and body (lines 58–94). Add `description` param, use it directly:

```python
def _post_to_site(settings: Settings, briefing_date: str, stories: list,
                  briefing_text: str, *, category: str, title: str,
                  description: str) -> None:
    """POST briefing to the website ingest endpoint.

    briefing_text must already have the DESCRIPTION: sentinel stripped.
    Treats 200/201 as success and 409 as idempotent success (already ingested).
    Raises RuntimeError on any other status so the Lambda retries via DLQ.
    """
    payload = json.dumps({
        "title": title,
        "date": _briefing_date_to_iso(briefing_date),
        "category": category,
        "summary": description,
        "body": briefing_text,
        "items": _build_items(stories),
    }).encode()

    req = urllib.request.Request(
        url=f"{settings.site_url}/api/briefs/ingest",
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {settings.brief_api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code

    if status in (200, 201):
        log("INFO", "briefing.site_ingest_ok", briefing_date=briefing_date)
    elif status == 409:
        log("INFO", "briefing.site_ingest_duplicate", briefing_date=briefing_date)
    else:
        raise RuntimeError(f"Site ingest returned unexpected status {status}")
```

**3c.** Update the `lambda_handler` publish block (around lines 155–170). Replace the AI_ML publish section:

```python
    if do_writes:
        if briefing_type == "AI_ML":
            edition = "Morning Edition" if time_of_day == "AM" else "Evening Edition"
            description, clean_body = _extract_description(briefing_text)
            _post_to_site(settings, briefing_date, stories, clean_body,
                          category="AI/ML",
                          title=f"The AI Abstract — {edition}",
                          description=description)
            published = True
        else:  # WORLD
            description, clean_body = _extract_description(briefing_text)
            try:
                _post_to_site(settings, briefing_date, stories, clean_body,
                              category="World",
                              title=f"The Recursive Briefing — {briefing_date}",
                              description=description)
            except RuntimeError as exc:
                log("WARNING", "briefing.world_site_ingest_failed", error=str(exc))
```

Note: WORLD briefings don't have a DESCRIPTION sentinel in the Zeitgeist prompt — `_extract_description` will fall back gracefully to first non-heading line, which is fine for the private WORLD brief.

**Step 4: Run failing tests to verify they pass**

```bash
python -m pytest tests/test_briefing_handler.py::test_extract_description_returns_sentinel_line \
  tests/test_briefing_handler.py::test_extract_description_falls_back_to_first_non_heading_line \
  tests/test_briefing_handler.py::test_post_to_site_uses_clean_body \
  tests/test_briefing_handler.py::test_aiml_title_morning_edition \
  tests/test_briefing_handler.py::test_aiml_title_evening_edition -v
```

Expected: All 5 PASS

**Step 5: Fix broken existing tests**

The existing test `test_extract_summary_skips_headings` and `test_extract_summary_returns_first_non_blank_line` now reference `_extract_summary` which no longer exists. Update them to use `_extract_description`:

```python
def test_extract_description_skips_headings():
    text = "# Heading\n\nThis is the summary paragraph."
    desc, body = handler_mod._extract_description(text)
    assert desc == "This is the summary paragraph."
    assert body == text  # no sentinel, body unchanged


def test_extract_description_returns_first_non_blank_line():
    text = "\n\nFirst real line."
    desc, body = handler_mod._extract_description(text)
    assert desc == "First real line."
    assert body == text  # no sentinel, body unchanged
```

**Step 6: Run full suite**

```bash
python -m pytest tests/ -v --tb=short
```

All tests must be green.

**Step 7: Commit**

```bash
cd /home/r3crsvint3llgnz/01_Projects/research-agent
git add src/handlers/briefing_handler.py tests/test_briefing_handler.py
git commit -m "fix: strip DESCRIPTION sentinel, fix title to Morning/Evening Edition

- _extract_description() replaces _extract_summary(); strips DESCRIPTION: sentinel
  and returns (description, clean_body) — body passed to site is always sentinel-free
- Title: 'The AI Abstract — Morning Edition' / 'Evening Edition' (was raw slug)
- WORLD briefing fallback: _extract_description gracefully falls back when no sentinel"
```

---

## Task 3: Add tagline as design element in brief detail page (AI/ML only)

**Files:**
- Modify: `recursiveintelligence-website/src/app/briefs/[id]/page.tsx:73-100`

**Step 1: No automated test needed** — this is a pure JSX rendering change. Verify manually.

**Step 2: Implement**

In `page.tsx`, after the closing `</div>` of the header block (line 96) and before the `<p>` summary paragraph (line 98), add a conditional tagline:

```tsx
      </div>

      {brief.category === 'AI/ML' && (
        <p className="text-[color:var(--ri-muted)] text-sm font-medium tracking-wide mb-8 italic">
          Making the Future Evenly Distributed.
        </p>
      )}

      <p className="text-[color:var(--ri-fg)] text-base leading-relaxed mb-10 max-w-2xl">
        {brief.summary}
      </p>
```

The exact insertion point is between line 96 (`</div>`) and line 98 (`<p className="text-[color:var(--ri-fg)]...`).

**Step 3: Verify build passes**

```bash
cd /home/r3crsvint3llgnz/01_Projects/recursiveintelligence-website
npm run build 2>&1 | tail -20
```

Expected: Build succeeds (exit 0). No TypeScript errors.

**Step 4: Commit**

```bash
cd /home/r3crsvint3llgnz/01_Projects/recursiveintelligence-website
git add src/app/briefs/[id]/page.tsx
git commit -m "feat: add tagline as static design element for AI/ML briefs only

Tagline 'Making the Future Evenly Distributed.' renders as styled italic
below the h1, keyed on brief.category === 'AI/ML'. Not shown for WORLD
(The Recursive Briefing) which has its own editorial identity."
```

---

## Verification Checklist

After all tasks complete:

- [ ] `python -m pytest tests/ -v` — all green in research-agent
- [ ] `npm run build` — succeeds in recursiveintelligence-website
- [ ] `_EQUALIZER_SYSTEM` does NOT contain `Making the Future Evenly Distributed`
- [ ] `_EQUALIZER_SYSTEM` DOES contain `DESCRIPTION:` sentinel instruction
- [ ] `briefing_handler._extract_description` exists (not `_extract_summary`)
- [ ] `_post_to_site` accepts `description` kwarg
- [ ] Title in AI_ML path uses `Morning Edition` / `Evening Edition`, not raw slug
- [ ] Tagline rendered only on `brief.category === 'AI/ML'` pages

---

## What Does NOT Change

- `_ZEITGEIST_SYSTEM` in `personas.py` — Recursive Briefing has no DESCRIPTION sentinel; handler fallback handles gracefully
- `config/feed_rules.py`, `config/keywords.py`, `config/scoring_weights.py` — already fixed earlier
- DynamoDB schema — `summary` field already exists; we just populate it correctly
- Website ingest API — no changes to `route.ts`
- `BriefBody` component — already renders markdown correctly; body just needs to be sentinel-free

# `source_tier` precompute — design

## Problem

The 2026-06-12 adversarial review flagged the highest-severity finding in the
corpus (section 1.4 of the knowledge-graph PRD,
`docs/superpowers/specs/2026-06-15-knowledge-graph-claim-tracking-prd.md`): the
2026-06-01 AI Abstract stated OpenAI "disproved the Erdős unit distance
conjecture," validated by Tim Gowers, sourced to Ars Technica with **no arXiv
ID** — and presented it with the same declarative confidence as cited
preprints. This is exactly the "AI + math breakthrough + famous mathematician"
pattern an LLM fabricates by completion, and the only claim in the reviewed set
with no falsifiable artifact.

The pipeline already has a source-quality signal: `editorial_scorer.py` (Haiku)
assigns `source_type` (`peer-reviewed` / `journalism` / `commentary` /
`single-source`) and an `integrity` score (1-5), and `personas.py` already
instructs `integrity <= 2` stories to get an explicit ⚠️ hedge. But this is a
**reporting-quality** signal, not a **primary-artifact** signal. The Erdős
story was reported by an established outlet (Ars Technica) with a named expert
(Gowers) — it plausibly scored `journalism` / `integrity 3-4`, well above the
existing hedge threshold, despite citing a claim with no citable paper behind
it.

## Fix

Add a second, independent, deterministic axis: `source_tier` ∈
`{"arxiv", "secondary"}`. `"arxiv"` means an arXiv paper ID was found
somewhere in the story's URL or content — i.e., a citable preprint exists,
even if the story's own `url` points to a press-writeup rather than the
paper itself. `"secondary"` means no arXiv ID was found anywhere — no
citable artifact, regardless of how the story is framed. Computed by regex,
no LLM involved (same "precompute + instruct verbatim" pattern as PR #20's
`coverage_phrase`).

Two reinforcing changes to `personas.py`:

1. **Structural marker** (addresses the adversarial-review finding that
   prose-only conditional rules — like the existing `integrity <= 2` ⚠️
   flag — already failed to catch this exact case): when `source_tier ==
   "secondary"`, the persona must append a fixed marker, `[no arXiv
   artifact]`, immediately after the inline link on first mention. This
   piggybacks on the existing *mandatory* inline-link rendering rule
   (`SOURCING`/`RENDERING RULES`), which the persona already executes
   consistently — it is not a new freestanding rule competing for attention.
2. **Prose framing instruction** (additive): `secondary`-tier stories must
   attribute extraordinary/quantitative/surprising claims to the reporting
   outlet rather than stating them as established fact — **regardless of
   `integrity` score**.

Neither change replaces or modifies the existing `integrity <= 2` hedge or
`SOURCE_EMOJI`; `source_tier`, `source_type`/`integrity`, and `SOURCE_EMOJI`
remain independent signals that all apply.

## Data flow

```
summarizer_handler.py::_score_story()
    -> story dict built (url, content, source_type, integrity, ...)
    -> _compute_source_tier(url: str, content: str) -> "arxiv" | "secondary"   [NEW, pure]
    -> story["source_tier"] = ...
    -> dict sent to briefing SQS queue (unchanged shape, +1 field)
    -> briefing_handler -> personas.py build_*_prompt()
    -> _dumps(stories) includes source_tier
    -> persona instructed: secondary-tier stories get [no arXiv artifact]
       marker on their inline link + attribution/hedge framing for
       extraordinary claims
```

## Components

### `_compute_source_tier(url: str, content: str) -> str`

New pure helper in `src/handlers/summarizer_handler.py`, placed near
`_score_story`.

- Search `f"{url}\n{content}"` with a single compiled regex:
  ```python
  _ARXIV_ID_PATTERN = re.compile(
      r"arxiv\.org/(?:abs|pdf)/(\d{4}\.\d{4,5})|arxiv:\s*(\d{4}\.\d{4,5})",
      re.IGNORECASE,
  )
  ```
  This matches both an arXiv URL (`arxiv.org/abs/2606.09894`,
  `export.arxiv.org/pdf/2606.09894`, with or without scheme/`www.`/trailing
  version suffix like `v2` — the pattern doesn't anchor on hostname, so any
  `arxiv.org/abs/...` or `arxiv.org/pdf/...` substring matches regardless of
  subdomain) and a bare citation (`arXiv:2606.09894` in body text, the
  conventional citation format used by press writeups that reference a
  specific preprint).
- Match found anywhere in `url` or `content` → `"arxiv"`. No match → `"secondary"`.
- Must never raise — pure regex search on strings, with `.get(..., "")`
  defaults for missing `url`/`content`. Missing/malformed input degrades to
  `"secondary"`, the more-conservative (more-hedged) tier — consistent with
  `_annotate_signal_age`'s (PR #20) precedent of degrading to the more
  conservative `"first appeared today"` on missing data.

**Known limitation (accepted):** a story whose content mentions an arXiv ID
*belonging to an unrelated paper* (e.g., citing prior work for context) would
be tagged `"arxiv"` even though the story's own central claim has no artifact.
This is a false negative for hedging, not a false positive for fabrication —
the regex is a cheap proxy, not a claim-level fact-checker (that's
section-4/full-graph territory, out of scope here). Tightening this further
would require LLM-based claim-to-citation linking, which this phase
explicitly avoids.

### Wiring into `_score_story`

In the return dict built by `_score_story` (`src/handlers/summarizer_handler.py`,
around line 115, alongside the existing `"url": item.get("url", "")`), add:

```python
"source_tier": _compute_source_tier(item.get("url", ""), item.get("content", "")),
```

No change to the dict's other fields, no change to SQS message shape beyond
the one new key.

### Prompt changes (`src/services/personas.py`)

Add two instruction additions to **both** `_EQUALIZER_SYSTEM` and
`_ZEITGEIST_SYSTEM`. Placement:

- Equalizer: in `RENDERING RULES`, immediately after the existing
  `- integrity <= 2: add explicit ⚠️ single-source/unverified flag in body near the story`
  line.
- Zeitgeist: in `<journalistic_standards>`, immediately after the existing
  `DEPTH` paragraph.

Instruction text (used verbatim in both):

> `source_tier == "secondary"`: this story has no arXiv-citable artifact.
> When linking this story inline on first mention, append the marker `[no
> arXiv artifact]` immediately after the link — this is part of the mandatory
> inline-link rendering, not optional decoration. Additionally, attribute
> extraordinary, quantitative, or surprising claims explicitly to the
> reporting outlet (e.g., "according to [Outlet], not yet corroborated by a
> published paper") rather than stating them as established fact — regardless
> of `integrity` score. Both the marker and the attribution framing are
> independent of and additional to the `integrity <= 2` flag and
> `SOURCE_EMOJI`.

No changes to `SOURCE_EMOJI`, `build_equalizer_prompt`, or
`build_zeitgeist_prompt` signatures — `source_tier` rides along inside each
story dict in `_dumps(stories)`, which both functions already emit.

## Error handling

`_compute_source_tier` is pure regex matching on already-fetched data — no
external calls, no new failure path. `re.search` does not raise on the inputs
here (plain strings via `.get(..., "")` defaults); no match is the normal
`"secondary"` path. This mirrors `_annotate_signal_age`'s existing
non-fatal-degradation precedent and requires no new error-boundary code in
`summarizer_handler.py`.

## Testing

`tests/test_summarizer_handler.py` — unit tests for `_compute_source_tier`:
- `url="https://arxiv.org/abs/2606.09894"`, `content=""` → `"arxiv"`
- `url="https://export.arxiv.org/pdf/2606.09894v2"`, `content=""` → `"arxiv"`
- `url="https://arstechnica.com/science/..."`, `content="...researchers say... arXiv:2606.09894..."`
  → `"arxiv"` (press writeup citing a real preprint)
- `url="https://arstechnica.com/science/..."`, `content="...OpenAI disproved the Erdős unit distance conjecture, Gowers said..."`
  (no arXiv ID anywhere) → `"secondary"` — this is the Erdős-case regression test
- `url=""`, `content=""` → `"secondary"`
- Missing `url`/`content` keys (via `_score_story`'s `.get(..., "")` defaults)
  → `"secondary"`

`tests/test_personas.py` — extend existing prompt-content tests:
- `build_equalizer_prompt` output contains the `[no arXiv artifact]` marker
  instruction and the `source_tier == "secondary"` attribution instruction
- `build_zeitgeist_prompt` output contains the same

**Acknowledged gap:** these tests verify the prompt *contains* the
instructions and that `_compute_source_tier` classifies correctly — they
cannot verify Sonnet actually applies the marker/framing in generated output.
That requires a manual spot-check: after deploying, run `DRY_RUN=writes_only`
on a payload containing at least one `secondary`-tier story with a striking
claim, and confirm the `[no arXiv artifact]` marker and attribution framing
appear in the generated brief. This is a one-time manual verification step,
not an automated test — noted here so it isn't silently skipped.

## Scope

Two-file code change (`summarizer_handler.py`, `personas.py`) + unit tests +
one manual post-deploy spot-check. No DB schema change, no new dependencies,
no changes to `SignalTracker`, `velocity.py`, `editorial_scorer.py`, or
`SOURCE_EMOJI`. Addresses PRD Phase 1
(`docs/superpowers/specs/2026-06-15-knowledge-graph-claim-tracking-prd.md`,
section 2). Independent of Phase 2 (which remains NEEDS RE-SCOPING).

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
`{"arxiv", "secondary"}`, computed from the story's URL alone (no LLM
involved — same "precompute + instruct verbatim" pattern as PR #20's
`coverage_phrase`). Persona prompts get an additional, additive instruction:
`secondary`-tier stories must attribute extraordinary/quantitative/surprising
claims to the reporting outlet rather than stating them as established fact —
**regardless of `integrity` score**. This does not replace or modify the
existing `integrity <= 2` hedge; the two signals are independent and both
apply.

## Data flow

```
summarizer_handler.py::_score_story()
    -> story dict built (url, source_type, integrity, ...)
    -> _compute_source_tier(url: str) -> "arxiv" | "secondary"   [NEW, pure]
    -> story["source_tier"] = ...
    -> dict sent to briefing SQS queue (unchanged shape, +1 field)
    -> briefing_handler -> personas.py build_*_prompt()
    -> _dumps(stories) includes source_tier
    -> persona instructed: secondary-tier claims get attribution/hedge framing
```

## Components

### `_compute_source_tier(url: str) -> str`

New pure helper in `src/handlers/summarizer_handler.py`, placed near
`_score_story`.

- Parse `url` with `urllib.parse.urlparse`, lowercase the hostname.
- `hostname == "arxiv.org"` → `"arxiv"`.
- Everything else — non-arxiv hostname, empty string, missing value, or a
  malformed URL that `urlparse` cannot extract a hostname from — → `"secondary"`.
- Must never raise. Missing/malformed input degrades to `"secondary"`, the
  more-conservative (more-hedged) tier — consistent with the precedent set by
  `_annotate_signal_age` (PR #20), where missing `first_seen` degrades to the
  more-conservative `"first appeared today"`.

### Wiring into `_score_story`

In the return dict built by `_score_story` (`src/handlers/summarizer_handler.py`,
around line 115, alongside the existing `"url": item.get("url", "")`), add:

```python
"source_tier": _compute_source_tier(item.get("url", "")),
```

No change to the dict's other fields, no change to SQS message shape beyond
the one new key.

### Prompt changes (`src/services/personas.py`)

Add one new instruction block to **both** `_EQUALIZER_SYSTEM` and
`_ZEITGEIST_SYSTEM`. Placement:

- Equalizer: in `RENDERING RULES`, immediately after the existing
  `- integrity <= 2: add explicit ⚠️ single-source/unverified flag in body near the story`
  line.
- Zeitgeist: in `<journalistic_standards>`, immediately after the existing
  `DEPTH` paragraph.

Instruction text (used verbatim in both):

> `source_tier == "secondary"`: this story has no arXiv-citable artifact.
> Attribute extraordinary, quantitative, or surprising claims explicitly to the
> reporting outlet (e.g., "according to [Outlet], not yet corroborated by a
> published paper") rather than stating them as established fact — regardless
> of `integrity` score. This is independent of and additional to the
> `integrity <= 2` flag.

No changes to `SOURCE_EMOJI`, `build_equalizer_prompt`, or
`build_zeitgeist_prompt` signatures — `source_tier` rides along inside each
story dict in `_dumps(stories)`, which both functions already emit.

## Error handling

`_compute_source_tier` is pure string/URL parsing on already-fetched data —
no external calls, no new failure path. `urlparse` does not raise on malformed
input; a missing hostname attribute is treated as "not arxiv.org" →
`"secondary"`. This mirrors `_annotate_signal_age`'s existing
non-fatal-degradation precedent and requires no new error-boundary code in
`summarizer_handler.py`.

## Testing

`tests/test_summarizer_handler.py` — unit tests for `_compute_source_tier`:
- `"https://arxiv.org/abs/2606.09894"` → `"arxiv"`
- `"https://arstechnica.com/science/..."` → `"secondary"`
- `""` (empty string) → `"secondary"`
- Missing `url` key (via `_score_story`'s `item.get("url", "")` default) →
  `"secondary"`
- Malformed string (e.g. `"not a url"`) → `"secondary"`, no exception

`tests/test_personas.py` — extend existing prompt-content tests:
- `build_equalizer_prompt` output contains the new `source_tier == "secondary"`
  instruction text
- `build_zeitgeist_prompt` output contains the same instruction text

## Scope

Two-file code change (`summarizer_handler.py`, `personas.py`) + unit tests. No
DB schema change, no new dependencies, no changes to `SignalTracker`,
`velocity.py`, `editorial_scorer.py`, or `SOURCE_EMOJI`. Addresses PRD Phase 1
(`docs/superpowers/specs/2026-06-15-knowledge-graph-claim-tracking-prd.md`,
section 2). Independent of Phase 2 (which remains NEEDS RE-SCOPING).

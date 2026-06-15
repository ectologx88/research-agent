# Signal-age framing — design

## Problem

The `signal_tracker` table stores real, persistent data per `signal_key`:
`mention_count`, `first_seen`, `last_seen`, `example_stories`, with a 7-day
rolling TTL reset on every update. Each briefing run, `briefing_handler.py`
fetches signals for the cluster_keys present in that day's batch and passes
the raw dicts straight into the prompt under `## WEAK SIGNALS (from
signal_tracker — use exactly this data)`.

The underlying counts are real — `mention_count` is not fabricated. But the
prompt only constrains the *data*, not the *phrasing*. The LLM free-texts the
coverage window from raw ISO timestamps (`first_seen`/`last_seen`), producing
inconsistent framings across briefs — e.g. "appeared 305 times since
February" on one day vs "14 stories over the past month" on another, with no
shared unit or methodology. This reads as fabricated analytics even though
the source numbers are real.

## Fix

Compute the full coverage *phrase* server-side, where date arithmetic and
pluralization are deterministic, and pass it to the LLM as a ready-to-use
string rather than raw numbers. This is a stopgap: a future topic/knowledge
graph (separate project) will likely replace `signal_tracker` entirely with
persistent topic provenance. This fix is scoped to be small and low-risk in
the meantime, not to be the final answer.

### `_annotate_signal_age(signals: list[dict]) -> list[dict]`

New private helper in `src/handlers/briefing_handler.py`, called immediately
after `signals = signal_tracker.get_signals(cluster_keys)`:

- For each signal dict, parse `first_seen` (ISO 8601 UTC string) with
  `datetime.fromisoformat`. `now_utc = datetime.now(timezone.utc)` (both
  values timezone-aware, since `_now_iso()` produces a `+00:00` offset).
- `days_tracked = max((now_utc - first_seen_dt).days, 0)`.
- `mention_count = signal.get("mention_count", 0)`.
- Build `coverage_phrase` covering the cases:
  - `days_tracked == 0`: `"first appeared today"`
  - `mention_count == 1`: `"mentioned once, N days ago"` (N = days_tracked)
  - otherwise: `"mentioned {mention_count} times over the past {days_tracked} days"`
- Set `signal["coverage_phrase"] = coverage_phrase`.
- If `first_seen` is missing or unparseable, treat as `days_tracked = 0`
  (→ `"first appeared today"`) and leave the rest of the signal dict
  unchanged — signal tracking is already documented as best-effort; this must
  not raise or block the briefing.

`first_seen` is the chosen anchor: it's the only persistent timestamp in the
schema, and it directly answers the question the brief is trying to convey
("how long has this topic been showing up").

**Known limitation (accepted):** the `signal_tracker` TTL is a 7-day rolling
window reset on every update. If a signal_key goes unmentioned for >7 days,
the item expires and the next mention recreates it with `first_seen = now`
and `mention_count = 1` — producing `"first appeared today"` for a topic that
has actually recurred over a longer span. This is a pre-existing property of
`signal_tracker`'s data model, not introduced by this fix. It's accepted as
correct-enough for this stopgap (a topic that's been quiet for a week
plausibly *should* read as newly resurgent) and is exactly the kind of
limitation the future topic graph would address with real persistent
provenance.

### Prompt change (`src/services/personas.py`)

Under `## WEAK SIGNALS`, in both `build_equalizer_prompt` and
`build_zeitgeist_prompt`, add an instruction:

> For each signal, use the precomputed `coverage_phrase` field verbatim (or
> lightly adapted to fit the sentence grammatically) to describe how long
> this topic has been recurring. Do not compute or estimate a timeframe from
> `first_seen`/`last_seen` yourself, and do not state a different mention
> count or time unit than what `coverage_phrase` provides.

## Data flow

```
SignalTracker.get_signals(cluster_keys)
    -> raw dicts (signal_key, mention_count, first_seen, last_seen, example_stories, ttl)
    -> _annotate_signal_age(signals)   [NEW]
    -> dicts + coverage_phrase
    -> _dumps(signals) into prompt (## WEAK SIGNALS)
    -> LLM instructed to use coverage_phrase verbatim/lightly-adapted
```

## Error handling

No external calls. Pure datetime parsing and string formatting on
already-fetched data. Malformed or missing `first_seen` degrades to
`"first appeared today"` — not fabricated, just conservative. No new failure
path; existing non-fatal handling for signal-tracker data is preserved.

## Testing

Unit tests for `_annotate_signal_age` in `tests/test_briefing_handler.py`:
- Normal case, `mention_count > 1`: `first_seen` N days ago →
  `coverage_phrase == "mentioned {mention_count} times over the past N days"`
- `mention_count == 1`, `days_tracked > 0` → "mentioned once, N days ago"
- `days_tracked == 0` (first_seen today) → "first appeared today"
- Missing `first_seen` → "first appeared today"
- Malformed `first_seen` string → "first appeared today"
- Empty `signals` list → returns `[]`

## Scope

Single-file code change (`briefing_handler.py`) + prompt-text change
(`personas.py`) + unit tests. No DB schema change, no new dependencies, no
changes to `SignalTracker` or `velocity.py`. Explicitly a stopgap pending the
topic/knowledge-graph project.

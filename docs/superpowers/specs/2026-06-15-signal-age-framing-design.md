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

Compute the coverage window server-side, where date arithmetic is
deterministic, and constrain the prompt to use that pre-computed value
verbatim alongside `mention_count`.

### `_annotate_signal_age(signals: list[dict]) -> list[dict]`

New private helper in `src/handlers/briefing_handler.py`, called immediately
after `signals = signal_tracker.get_signals(cluster_keys)`:

- For each signal dict, parse `first_seen` (ISO 8601 UTC string) with
  `datetime.fromisoformat`.
- `days_tracked = max((now_utc - first_seen_dt).days, 0)`.
- Set `signal["days_tracked"] = days_tracked`.
- If `first_seen` is missing or unparseable, set `days_tracked = 0` and leave
  the rest of the signal dict unchanged — signal tracking is already
  documented as best-effort; this must not raise or block the briefing.

`first_seen` is the chosen anchor: it's the only persistent timestamp in the
schema, and it directly answers the question the brief is trying to convey
("how long has this topic been showing up"). No new state is introduced.

### Prompt change (`src/services/personas.py`)

Under `## WEAK SIGNALS`, in both `build_equalizer_prompt` and
`build_zeitgeist_prompt`, add an instruction:

> For each signal, report coverage as "mentioned in {mention_count} stories
> over {days_tracked} days" (or a natural variation) — use exactly
> `mention_count` and `days_tracked` from the data. Do not estimate the
> timeframe from `first_seen`/`last_seen` yourself, and do not use other
> units (e.g. "since [month]").

## Data flow

```
SignalTracker.get_signals(cluster_keys)
    -> raw dicts (signal_key, mention_count, first_seen, last_seen, example_stories, ttl)
    -> _annotate_signal_age(signals)   [NEW]
    -> dicts + days_tracked
    -> _dumps(signals) into prompt (## WEAK SIGNALS)
    -> LLM instructed to phrase coverage using mention_count + days_tracked verbatim
```

## Error handling

No external calls. Pure datetime parsing on already-fetched data. Malformed
or missing `first_seen` degrades to `days_tracked = 0` (renders as "over 0
days" — odd but not fabricated, self-corrects once `first_seen` is populated
on next upsert). No new failure path; existing non-fatal handling for
signal-tracker data is preserved.

## Testing

Unit tests for `_annotate_signal_age` in `tests/test_briefing_handler.py`:
- Normal case: `first_seen` N days ago → `days_tracked == N`
- Missing `first_seen` → `days_tracked == 0`
- Malformed `first_seen` string → `days_tracked == 0`
- Empty `signals` list → returns `[]`

## Scope

Single-file code change (`briefing_handler.py`) + prompt-text change
(`personas.py`) + unit tests. No DB schema change, no new dependencies, no
changes to `SignalTracker` or `velocity.py`.

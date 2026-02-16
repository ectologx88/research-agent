# Fetch Window Design

**Date:** 2026-02-16
**Status:** Approved

## Overview

Switch the pipeline from `since_last_run` to a fixed 12-hour lookback window, aligning with the 12-hour EventBridge schedule.

## Change

Two environment variable updates in `terraform/lambda.tf`:

| Variable | Old | New |
|---|---|---|
| `FETCH_STRATEGY` | (not set, defaults to `since_last_run`) | `hours_back` |
| `HOURS_BACK_DEFAULT` | `36` | `12` |

No application code changes. The `hours_back` branch already exists in `classifier.py`.

## Behavior

- Every run fetches stories published in the last 12 hours
- Missed runs do not catch up — next run still only looks back 12 hours
- Stories that score ≥ 8 overall are bookmarked to Raindrop (no change)
- No hard cap on Raindrop sends per run — threshold-only selection

## Out of Scope

- Summary/digest delivery (Phase 2b, delivery mechanism TBD)
- Fetch strategy simplification (YAGNI — `since_last_run` stays dormant)

# config/scoring_weights.py
"""Per-stream scoring thresholds and parameters.

Threshold history:
- AI_ML: started at 9, dropped to 8 (2026-03-01) to compensate for thin PM candidate
  pools. Restored to 9 (2026-04-11) after switching to single daily run with 26h fetch
  window — PM compensation no longer needed.
- WORLD: stream disabled (2026-04-11).
"""

AI_ML_PASS_THRESHOLD = 9    # out of 15
WORLD_PASS_THRESHOLD = 7    # out of 15 — kept for reference; WORLD stream disabled
MIN_STORIES_FOR_BRIEFING = 5  # suppress edition entirely if below this threshold
MAX_AI_ML_STORIES = 40      # triage cap — how many candidates to score
MAX_WORLD_STORIES = 20      # triage cap — WORLD stream disabled; kept for reference
MAX_BRIEFING_AI_ML_STORIES = 10  # top-N by score sent to briefing Lambda
MAX_BRIEFING_WORLD_STORIES = 8   # WORLD stream disabled; kept for reference
CLUSTER_SIZE_LEAD_STORY = 3  # cluster_size >= this → Lead Story
CONTENT_TRUNCATE_CHARS = 8000

# config/scoring_weights.py
"""Per-stream scoring thresholds and parameters."""

AI_ML_PASS_THRESHOLD = 7    # out of 15 (lowered from 9; avg 2.33/5 per dimension)
WORLD_PASS_THRESHOLD = 7    # out of 15 (lowered from 8)
MIN_STORIES_FOR_BRIEFING = 1  # always brief if any story passes; log thin_briefing if < 3
MAX_AI_ML_STORIES = 40      # triage cap — how many candidates to score
MAX_WORLD_STORIES = 20      # triage cap — how many candidates to score
MAX_BRIEFING_AI_ML_STORIES = 12  # top-N by score sent to briefing Lambda
MAX_BRIEFING_WORLD_STORIES = 8   # top-N by score sent to briefing Lambda
CLUSTER_SIZE_LEAD_STORY = 3  # cluster_size >= this → Lead Story
CONTENT_TRUNCATE_CHARS = 8000

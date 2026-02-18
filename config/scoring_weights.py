# config/scoring_weights.py
"""Per-stream scoring thresholds and parameters."""

AI_ML_PASS_THRESHOLD = 9    # out of 15
WORLD_PASS_THRESHOLD = 8    # out of 15
MIN_STORIES_FOR_BRIEFING = 3  # bail if fewer pass Lambda 2
MAX_AI_ML_STORIES = 15      # Lambda 3 cap
MAX_WORLD_STORIES = 10      # Lambda 3 cap
CLUSTER_SIZE_LEAD_STORY = 3  # cluster_size >= this → Lead Story
CONTENT_TRUNCATE_CHARS = 8000

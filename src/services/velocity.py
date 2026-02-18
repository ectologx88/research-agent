# src/services/velocity.py
"""Velocity clustering: detect stories covering the same topic.

Pure Python, no ML. Uses token-set intersection to identify story clusters.
cluster_size >= 3 → Lead Story candidate in Lambda 3.
"""
import re
from collections import Counter
from typing import Any

STOPWORDS = {
    "the", "and", "for", "that", "this", "with", "from", "have", "will",
    "are", "was", "been", "has", "its", "into", "over", "says", "said",
    "new", "can", "may", "also", "more", "than", "but", "not", "how",
    "what", "when", "why", "who", "all", "about", "after", "first",
    "being", "which", "their", "here", "would", "could", "make",
}


def _tokenize(title: str) -> set[str]:
    """Lowercase, strip non-alphanumeric, drop stopwords and short tokens.

    Applies naive suffix-stripping (trailing 's') so that 'benchmarks'
    and 'benchmark' are treated as the same token.
    """
    tokens = re.sub(r"[^a-z0-9 ]", " ", title.lower()).split()
    result = set()
    for t in tokens:
        if len(t) < 4 or t in STOPWORDS:
            continue
        # Naive plural normalisation: strip trailing 's' when result >= 4 chars
        if t.endswith("s") and len(t) > 4:
            t = t[:-1]
        result.add(t)
    return result


def compute_clusters(stories: list[Any]) -> dict[str, tuple[int, str]]:
    """
    Compute cluster_size and cluster_key for each story.

    Returns:
        {story_hash: (cluster_size, cluster_key)}
        cluster_size = number of other stories sharing >= 2 tokens
        cluster_key = most frequent shared token across the cluster
                      (empty string if cluster_size == 0)
    """
    if not stories:
        return {}

    token_sets = {s.story_hash: _tokenize(s.story_title) for s in stories}
    results = {}

    for story in stories:
        my_tokens = token_sets[story.story_hash]
        shared_counter: Counter = Counter()
        cluster_size = 0

        for other_hash, other_tokens in token_sets.items():
            if other_hash == story.story_hash:
                continue
            shared = my_tokens & other_tokens
            if len(shared) >= 2:
                cluster_size += 1
                shared_counter.update(shared)

        cluster_key = shared_counter.most_common(1)[0][0] if shared_counter else ""
        results[story.story_hash] = (cluster_size, cluster_key)

    return results

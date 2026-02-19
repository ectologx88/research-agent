from unittest.mock import MagicMock
from src.services.velocity import compute_clusters


def _story(hash_id, title):
    s = MagicMock()
    s.story_hash = hash_id
    s.story_title = title
    return s


class TestComputeClusters:
    def test_single_story_has_cluster_size_zero(self):
        stories = [_story("a1", "Evaluation crisis analysis")]
        result = compute_clusters(stories)
        assert result["a1"][0] == 0
        assert result["a1"][1] == ""  # cluster_key empty when no cluster

    def test_three_matching_stories_form_cluster(self):
        # All three share exact tokens: "evaluation", "crisis", "analysis"
        stories = [
            _story("a1", "Evaluation crisis analysis benchmark"),
            _story("a2", "Evaluation benchmark systematic analysis"),
            _story("a3", "Evaluation crisis systematic analysis"),
        ]
        result = compute_clusters(stories)
        # a1 shares {evaluation, analysis} with a2 AND {evaluation, crisis, analysis} with a3
        # a2 shares {evaluation, analysis} with a1 AND {evaluation, systematic, analysis} with a3
        # a3 shares {evaluation, crisis, analysis} with a1 AND {evaluation, systematic, analysis} with a2
        assert result["a1"][0] >= 2
        assert result["a2"][0] >= 2
        assert result["a3"][0] >= 2

    def test_cluster_key_is_most_common_shared_token(self):
        # "evaluation" appears in all three pairs — most frequent shared token
        stories = [
            _story("a1", "Evaluation crisis benchmark analysis"),
            _story("a2", "Evaluation benchmark systematic review"),
            _story("a3", "Evaluation crisis systematic analysis"),
        ]
        result = compute_clusters(stories)
        # For a1: shares {evaluation, benchmark} with a2, {evaluation, crisis, analysis} with a3
        # shared_counter: {evaluation: 2, benchmark: 1, crisis: 1, analysis: 1}
        assert result["a1"][1] == "evaluation"

    def test_unrelated_stories_no_cluster(self):
        stories = [
            _story("a1", "Apple releases iPhone update"),
            _story("a2", "Houston weather forecast shows rain"),
            _story("a3", "Stock market closes higher"),
        ]
        result = compute_clusters(stories)
        # No story shares 2+ meaningful tokens with another
        for h, (size, _) in result.items():
            assert size == 0

    def test_stopwords_not_counted(self):
        # "with", "from", "that" are stopwords — should not form a cluster
        stories = [
            _story("a1", "News from the latest update"),
            _story("a2", "Update from that source"),
        ]
        result = compute_clusters(stories)
        # "update" is shared but only 1 token — not enough for cluster
        assert result["a1"][0] == 0

    def test_empty_list(self):
        assert compute_clusters([]) == {}

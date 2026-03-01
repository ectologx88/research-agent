"""Tests for TriageService boost tag extraction."""
from unittest.mock import MagicMock

from src.services.triage import Bucket, TriageService


def _story(feed_title, story_title="Some title"):
    s = MagicMock()
    s.story_feed_title = feed_title
    s.story_title = story_title
    return s


class TestBoostTags:
    def test_open_source_boost(self):
        svc = TriageService()
        tags = svc.get_boost_tags(_story(
            "cs.AI updates on arXiv.org",
            "Open-source Llama variant outperforms proprietary models",
        ))
        assert "boost:open-source" in tags

    def test_user_curated_boost_for_gbninjaturtle(self):
        svc = TriageService()
        tags = svc.get_boost_tags(_story("saved by gbninjaturtle", "anything"))
        assert "boost:user-curated" in tags

    def test_rdd_long_signal(self):
        svc = TriageService()
        tags = svc.get_boost_tags(_story(
            "NeuroLogica Blog",
            "New research on consciousness and emergence",
        ))
        assert "long-signal:rdd" in tags

    def test_non_gbninjaturtle_feed_no_user_curated(self):
        svc = TriageService()
        tags = svc.get_boost_tags(_story("ClaudeAI", "anything"))
        assert "boost:user-curated" not in tags

"""Tests for TriageService. Feed names match actual NewsBlur subscriptions
defined in config/feed_rules.py — do not use invented names here."""
from unittest.mock import MagicMock

from src.services.triage import Bucket, TriageService


def _story(feed_title, story_title="Some title"):
    s = MagicMock()
    s.story_feed_title = feed_title
    s.story_title = story_title
    return s


class TestFeedNameRules:
    def test_arxiv_ai_routes_to_ai_ml(self):
        svc = TriageService()
        assert svc.categorize(_story("cs.AI updates on arXiv.org")) == Bucket.AI_ML

    def test_bbc_routes_to_world(self):
        svc = TriageService()
        assert svc.categorize(_story("BBC News")) == Bucket.WORLD

    def test_newsblur_blog_routes_to_skip(self):
        svc = TriageService()
        assert svc.categorize(_story("The NewsBlur Blog")) == Bucket.SKIP

    def test_raindrop_feed_routes_to_skip(self):
        svc = TriageService()
        assert svc.categorize(_story("AI / Raindrop.io")) == Bucket.SKIP

    def test_space_city_weather_routes_to_world(self):
        svc = TriageService()
        bucket, sub = svc.categorize_with_sub(_story("Space City Weather"))
        assert bucket == Bucket.WORLD
        assert sub == "news"

    def test_neurologica_routes_to_science(self):
        svc = TriageService()
        bucket, sub = svc.categorize_with_sub(_story("NeuroLogica Blog"))
        assert bucket == Bucket.WORLD
        assert sub == "science"

    def test_ghostbusters_routes_to_entertainment(self):
        svc = TriageService()
        bucket, sub = svc.categorize_with_sub(_story("Ghostbusters News"))
        assert bucket == Bucket.WORLD
        assert sub == "entertainment"

    def test_apple_newsroom_routes_to_tech_not_entertainment(self):
        svc = TriageService()
        bucket, sub = svc.categorize_with_sub(_story("Apple Newsroom"))
        assert bucket == Bucket.WORLD
        assert sub == "tech"


class TestKeywordFallback:
    def test_hacker_news_llm_keyword_routes_to_ai_ml(self):
        svc = TriageService()
        assert svc.categorize(_story("Hacker News", "New LLM beats GPT-4")) == Bucket.AI_ML

    def test_hacker_news_no_keyword_routes_to_world(self):
        svc = TriageService()
        assert svc.categorize(_story("Hacker News", "Best coffee grinder Ask HN")) == Bucket.WORLD

    def test_unknown_feed_defaults_to_world(self):
        svc = TriageService()
        assert svc.categorize(_story("Some Random Blog", "Weekend plans")) == Bucket.WORLD

    def test_feed_name_takes_priority_over_keyword(self):
        # ALWAYS_SKIP beats AI/ML keywords
        svc = TriageService()
        assert svc.categorize(_story("The NewsBlur Blog", "new LLM released")) == Bucket.SKIP


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

    def test_non_gbninjaturtle_reddit_feed_no_user_curated(self):
        svc = TriageService()
        tags = svc.get_boost_tags(_story("ClaudeAI", "anything"))
        assert "boost:user-curated" not in tags


class TestBatchCategorize:
    def test_returns_dict_of_bucket_to_stories(self):
        svc = TriageService()
        stories = [
            _story("cs.AI updates on arXiv.org"),
            _story("BBC News"),
            _story("The NewsBlur Blog"),
        ]
        result = svc.batch_categorize(stories)
        assert len(result[Bucket.AI_ML]) == 1
        assert len(result[Bucket.WORLD]) == 1
        assert len(result[Bucket.SKIP]) == 1

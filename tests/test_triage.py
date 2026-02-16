from src.services.triage import TriageService, Bucket

class TestFeedNameRules:
    def _story(self, feed_title, story_title="Some title"):
        from unittest.mock import MagicMock
        s = MagicMock()
        s.story_feed_title = feed_title
        s.story_title = story_title
        return s

    def test_arxiv_feed_routes_to_ai_ml(self):
        svc = TriageService()
        assert svc.categorize(self._story("arXiv AI")) == Bucket.AI_ML

    def test_bbc_feed_routes_to_world(self):
        svc = TriageService()
        assert svc.categorize(self._story("BBC News")) == Bucket.WORLD

    def test_espn_routes_to_skip(self):
        svc = TriageService()
        assert svc.categorize(self._story("ESPN")) == Bucket.SKIP

    def test_weather_feed_routes_to_world_with_weather_sub(self):
        svc = TriageService()
        bucket, sub = svc.categorize_with_sub(self._story("Weather Underground"))
        assert bucket == Bucket.WORLD
        assert sub == "weather"

class TestKeywordFallback:
    def _story(self, title, feed="Unknown Feed"):
        from unittest.mock import MagicMock
        s = MagicMock()
        s.story_feed_title = feed
        s.story_title = title
        return s

    def test_llm_keyword_routes_to_ai_ml(self):
        svc = TriageService()
        assert svc.categorize(self._story("New LLM beats GPT-4 on benchmarks")) == Bucket.AI_ML

    def test_iphone_keyword_routes_to_world(self):
        svc = TriageService()
        bucket, sub = svc.categorize_with_sub(self._story("iPhone 17 announced"))
        assert bucket == Bucket.WORLD
        assert sub == "tech"

    def test_unrecognized_routes_to_world_news(self):
        svc = TriageService()
        bucket, sub = svc.categorize_with_sub(self._story("Local election results"))
        assert bucket == Bucket.WORLD
        assert sub == "news"

    def test_feed_name_takes_priority_over_keyword(self):
        # Even if title has AI keywords, a skip feed wins
        svc = TriageService()
        assert svc.categorize(self._story("LLM beats everything", feed="ESPN")) == Bucket.SKIP

class TestBatchCategorize:
    def test_returns_dict_of_bucket_to_stories(self):
        from unittest.mock import MagicMock
        svc = TriageService()
        stories = []
        for feed, title in [
            ("arXiv AI", "Neural networks"),
            ("BBC News", "Election results"),
            ("ESPN", "Game recap"),
        ]:
            s = MagicMock()
            s.story_feed_title = feed
            s.story_title = title
            stories.append(s)
        result = svc.batch_categorize(stories)
        assert len(result[Bucket.AI_ML]) == 1
        assert len(result[Bucket.WORLD]) == 1
        assert len(result[Bucket.SKIP]) == 1

# tests/test_feed_rules.py
from config.feed_rules import (
    ALWAYS_AI_ML, ALWAYS_WORLD, ALWAYS_SCIENCE,
    REDDIT_FEEDS, AMBIGUOUS_FEEDS, ALWAYS_SKIP,
    get_route, Route
)

class TestAlwaysAiMl:
    def test_arxiv_ai_routes(self):
        route, sub = get_route("cs.AI updates on arXiv.org", "")
        assert route == Route.AI_ML
        assert sub == "research"

    def test_anthropic_news_routes(self):
        route, sub = get_route("Anthropic News", "")
        assert route == Route.AI_ML

class TestAlwaysWorld:
    def test_bbc_routes(self):
        route, sub = get_route("BBC News", "")
        assert route == Route.WORLD
        assert sub == "news"

    def test_reuters_substring_match(self):
        # Exact NewsBlur title may vary — verify on first run
        route, sub = get_route("Reuters", "")
        assert route == Route.WORLD

class TestAlwaysScience:
    def test_nature_routes_to_science(self):
        route, sub = get_route("Nature - Issue - nature.com science feeds", "")
        assert route == Route.WORLD
        assert sub == "science"

    def test_neurologica_routes_to_science(self):
        route, sub = get_route("NeuroLogica Blog", "")
        assert route == Route.WORLD
        assert sub == "science"

class TestAlwaysEntertainment:
    def test_ghostbusters_routes_to_entertainment(self):
        route, sub = get_route("Ghostbusters News", "")
        assert route == Route.WORLD
        assert sub == "entertainment"

    def test_apple_newsroom_routes_to_tech(self):
        route, sub = get_route("Apple Newsroom", "")
        assert route == Route.WORLD
        assert sub == "tech"

    def test_macrumors_routes_to_tech(self):
        route, sub = get_route("MacRumors: Mac News and Rumors - All Stories", "")
        assert route == Route.WORLD
        assert sub == "tech"

class TestAlwaysSkip:
    def test_raindrop_feed_skipped(self):
        route, _ = get_route("AI / Raindrop.io", "")
        assert route == Route.SKIP

    def test_newsblur_blog_skipped(self):
        route, _ = get_route("The NewsBlur Blog", "")
        assert route == Route.SKIP

class TestRedditFeeds:
    def test_claudeai_routes_to_ai_ml(self):
        route, sub = get_route("ClaudeAI", "Claude 3.5 new release")
        assert route == Route.AI_ML
        assert sub == "research"

    def test_neuroscience_reddit_routes_to_science(self):
        route, sub = get_route("top scoring links : neuroscience", "brain plasticity")
        assert route == Route.WORLD
        assert sub == "science"

    def test_apple_reddit_routes_to_tech(self):
        route, sub = get_route("top scoring links : apple", "iPhone 17 review")
        assert route == Route.WORLD
        assert sub == "tech"

class TestAmbiguousFeeds:
    def test_hacker_news_ai_keyword_routes_to_ai_ml(self):
        route, sub = get_route("Hacker News", "New LLM benchmark shows GPT-5 advantage")
        assert route == Route.AI_ML
        assert sub == "research"

    def test_hacker_news_no_keyword_defaults_to_world_tech(self):
        route, sub = get_route("Hacker News", "Ask HN: Best coffee grinder")
        assert route == Route.WORLD
        assert sub == "tech"

class TestPrecedence:
    def test_skip_beats_keyword(self):
        # Even if title has AI keywords, SKIP feeds are always skipped
        route, _ = get_route("The NewsBlur Blog", "new LLM model released")
        assert route == Route.SKIP

class TestUnknownFeedFallback:
    def test_unknown_feed_ai_keyword_routes_to_ai_ml(self):
        route, sub = get_route("Some Random Blog", "New LLM released today")
        assert route == Route.AI_ML
        assert sub == "research"

    def test_unknown_feed_no_keyword_routes_to_world_news(self):
        route, sub = get_route("Some Random Blog", "Local election results")
        assert route == Route.WORLD
        assert sub == "news"

    def test_none_feed_name_routes_to_world_news(self):
        route, sub = get_route(None, "Local election results")
        assert route == Route.WORLD
        assert sub == "news"

    def test_empty_feed_name_routes_to_world_news(self):
        route, sub = get_route("", "Local election results")
        assert route == Route.WORLD
        assert sub == "news"

    def test_none_story_title_is_handled_safely(self):
        route, sub = get_route("Some Random Blog", None)
        assert route == Route.WORLD
        assert sub == "news"

# tests/test_feed_rules.py
from config.feed_rules import (
    FOLDER_ROUTE_MAP,
    UNFOLDERD_ROUTE_MAP,
    ALWAYS_SKIP_NAMES,
    AI_ML_KEYWORDS,
    Route,
    _has_ai_ml_keyword,
)


class TestFolderRouteMap:
    def test_ai_ml_research_routes_to_ai_ml(self):
        route, sub = FOLDER_ROUTE_MAP["AI-ML-Research"]
        assert route == Route.AI_ML
        assert sub == "research"

    def test_ai_ml_community_routes_to_ai_ml(self):
        route, sub = FOLDER_ROUTE_MAP["AI-ML-Community"]
        assert route == Route.AI_ML
        assert sub == "community"

    def test_current_events_routes_to_world_news(self):
        route, sub = FOLDER_ROUTE_MAP["Current Events & World"]
        assert route == Route.WORLD
        assert sub == "news"

    def test_weather_routes_to_world_news(self):
        route, sub = FOLDER_ROUTE_MAP["Weather"]
        assert route == Route.WORLD
        assert sub == "news"

    def test_world_science_routes_to_world_science(self):
        route, sub = FOLDER_ROUTE_MAP["World-Science"]
        assert route == Route.WORLD
        assert sub == "science"

    def test_world_tech_routes_to_world_tech(self):
        route, sub = FOLDER_ROUTE_MAP["World-Tech"]
        assert route == Route.WORLD
        assert sub == "tech"

    def test_general_tech_absent_from_folder_map(self):
        # General-Tech uses keyword routing — not in FOLDER_ROUTE_MAP
        assert "General-Tech" not in FOLDER_ROUTE_MAP


class TestUnfolderdRouteMap:
    def test_ghostbusters_routes_to_entertainment(self):
        route, sub = UNFOLDERD_ROUTE_MAP["Ghostbusters News"]
        assert route == Route.WORLD
        assert sub == "entertainment"


class TestAlwaysSkipNames:
    def test_raindrop_feed_in_skip(self):
        assert "AI / Raindrop.io" in ALWAYS_SKIP_NAMES

    def test_newsblur_blog_in_skip(self):
        assert "The NewsBlur Blog" in ALWAYS_SKIP_NAMES


class TestKeywordRouting:
    def test_llm_keyword_matches(self):
        assert _has_ai_ml_keyword("New LLM benchmark shows GPT-5 advantage")

    def test_claude_keyword_matches(self):
        assert _has_ai_ml_keyword("Claude 3.5 new release")

    def test_non_ai_title_does_not_match(self):
        assert not _has_ai_ml_keyword("Ask HN: Best coffee grinder")

    def test_election_title_does_not_match(self):
        assert not _has_ai_ml_keyword("Local election results")

    def test_none_title_is_safe(self):
        assert not _has_ai_ml_keyword(None)

    def test_empty_title_is_safe(self):
        assert not _has_ai_ml_keyword("")

    def test_anthropic_keyword_matches(self):
        assert _has_ai_ml_keyword("Anthropic releases new model weights")

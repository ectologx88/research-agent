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

    def test_general_tech_absent_from_folder_map(self):
        assert "General-Tech" not in FOLDER_ROUTE_MAP

    def test_world_folders_absent(self):
        for name in ("Current Events & World", "Weather", "World-Science", "World-Tech"):
            assert name not in FOLDER_ROUTE_MAP, f"{name!r} should not be in FOLDER_ROUTE_MAP"


class TestUnfolderdRouteMap:
    def test_unfolderd_map_is_empty(self):
        assert UNFOLDERD_ROUTE_MAP == {}, "UNFOLDERD_ROUTE_MAP should be empty (WORLD stream disabled)"


class TestAIMLPrimaryFolder:
    def test_ai_ml_primary_routes_to_research(self):
        route, sub = FOLDER_ROUTE_MAP["AI-ML-Primary"]
        assert route == Route.AI_ML
        assert sub == "research"


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

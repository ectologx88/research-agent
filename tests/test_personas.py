# tests/test_personas.py
from src.services.personas import (
    build_equalizer_prompt,
    build_zeitgeist_prompt,
    SOURCE_EMOJI,
)
from src.services.editorial_scorer import EditorialScorer


class TestSourceEmoji:
    def test_peer_reviewed_gets_microscope(self):
        assert SOURCE_EMOJI["peer-reviewed"] == "🔬"

    def test_single_source_gets_warning(self):
        assert SOURCE_EMOJI["single-source"] == "⚠️"


class TestEqualizerPrompt:
    def test_includes_editorial_identity(self):
        prompt = build_equalizer_prompt(stories=[], signals=[], prior_briefing=None)
        assert "AI Abstract" in prompt
        assert "Equalizer" in prompt or "equalizer" in prompt

    def test_does_not_include_context_block(self):
        prompt = build_equalizer_prompt(stories=[], signals=[], prior_briefing=None)
        assert "SYSTEM_CONTEXT_BLOCK" not in prompt

    def test_includes_stories_json(self):
        stories = [{"title": "Test story", "summary": "Summary.", "source_type": "journalism",
                    "boost_tags": [], "cluster_size": 1, "sub_bucket": "research",
                    "scores": {"total": 10}, "url": "https://example.com",
                    "feed_name": "cs.AI updates on arXiv.org", "reasoning": "Good."}]
        prompt = build_equalizer_prompt(stories=stories, signals=[], prior_briefing=None)
        assert "Test story" in prompt

    def test_signal_data_included(self):
        signals = [{"signal_key": "eval-crisis", "mention_count": 3,
                    "last_seen": "2026-02-17", "example_stories": []}]
        prompt = build_equalizer_prompt(stories=[], signals=signals, prior_briefing=None)
        assert "eval-crisis" in prompt

    def test_prior_briefing_included_when_present(self):
        prompt = build_equalizer_prompt(
            stories=[], signals=[],
            prior_briefing={"content": "Yesterday's briefing summary."}
        )
        assert "Yesterday's briefing" in prompt


class TestZeitgeistPrompt:
    def test_includes_editorial_identity(self):
        prompt = build_zeitgeist_prompt(
            stories=[], signals=[], prior_briefing=None, context_block=""
        )
        assert "Recursive Briefing" in prompt or "Zeitgeist" in prompt

    def test_includes_context_block(self):
        block = "[SYSTEM_CONTEXT_BLOCK — Deterministic Data]..."
        prompt = build_zeitgeist_prompt(
            stories=[], signals=[], prior_briefing=None, context_block=block
        )
        assert "SYSTEM_CONTEXT_BLOCK" in prompt

    def test_entertainment_aside_instruction_present(self):
        prompt = build_zeitgeist_prompt(
            stories=[], signals=[], prior_briefing=None, context_block=""
        )
        assert "aside" in prompt.lower() or "parenthetical" in prompt.lower()

    def test_lede_grounding_rule_present(self):
        prompt = build_zeitgeist_prompt(
            stories=[], signals=[], prior_briefing=None, context_block=""
        )
        assert "specific story" in prompt.lower() or "anchor" in prompt.lower()

    def test_no_third_person_correspondent_instruction(self):
        prompt = build_zeitgeist_prompt(
            stories=[], signals=[], prior_briefing=None, context_block=""
        )
        assert "third person" in prompt.lower() or "third-person" in prompt.lower()

    def test_journalistic_standards_present(self):
        prompt = build_zeitgeist_prompt(
            stories=[], signals=[], prior_briefing=None, context_block=""
        )
        assert "journalistic_standards" in prompt
        assert "framing" in prompt.lower()

    def test_link_requirement_present(self):
        prompt = build_zeitgeist_prompt(
            stories=[], signals=[], prior_briefing=None, context_block=""
        )
        assert "evidence trail" in prompt.lower() or "links are" in prompt.lower()


class TestEqualizerJournalisticStandards:
    def test_meta_transition_banned(self):
        prompt = build_equalizer_prompt(stories=[], signals=[], prior_briefing=None)
        assert "This is the right place to note" in prompt

    def test_self_referential_commentary_banned(self):
        prompt = build_equalizer_prompt(stories=[], signals=[], prior_briefing=None)
        assert "slow news day" in prompt or "thin payload" in prompt

    def test_journalistic_standards_block_present(self):
        prompt = build_equalizer_prompt(stories=[], signals=[], prior_briefing=None)
        assert "journalistic_standards" in prompt

    def test_depth_guidance_present(self):
        prompt = build_equalizer_prompt(stories=[], signals=[], prior_briefing=None)
        assert "cluster_size" in prompt
        assert "integrity" in prompt


class TestScorerHardGates:
    def test_ai_ml_prompt_contains_reddit_hard_gate(self):
        scorer = EditorialScorer()
        prompt = scorer._build_prompt("AI_ML", "title", "content", "reddit.com", "research", [])
        assert "hard_gate" in prompt
        assert "REDDIT" in prompt or "Reddit" in prompt

    def test_world_prompt_contains_sourcing_hard_gate(self):
        scorer = EditorialScorer()
        prompt = scorer._build_prompt("WORLD", "title", "content", "reddit.com", "science", [])
        assert "hard_gate" in prompt

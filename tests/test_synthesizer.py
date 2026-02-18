# tests/test_synthesizer.py
from unittest.mock import MagicMock, patch
from src.services.synthesizer import BriefingSynthesizer


class TestPriorBriefingLookup:
    def test_am_run_queries_yesterday_pm(self):
        """AM run → query yesterday's PM briefing."""
        synth = BriefingSynthesizer.__new__(BriefingSynthesizer)
        key = synth._prior_briefing_key("2026-02-17", "AM")
        assert key == ("2026-02-16-PM", "AI_ML")

    def test_pm_run_queries_today_am(self):
        """PM run → query today's AM briefing."""
        synth = BriefingSynthesizer.__new__(BriefingSynthesizer)
        key = synth._prior_briefing_key("2026-02-17", "PM")
        assert key == ("2026-02-17-AM", "AI_ML")


class TestBriefingTypeBranching:
    def test_equalizer_gets_no_context_block(self):
        synth = MagicMock(spec=BriefingSynthesizer)
        synth._prior_briefing_key = BriefingSynthesizer._prior_briefing_key.__get__(synth)
        # Verify build_prompt_for_type routes AI_ML to equalizer path
        pass

    def test_zeitgeist_gets_context_block(self):
        pass

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
    @patch("src.services.synthesizer.build_zeitgeist_prompt")
    @patch("src.services.synthesizer.build_equalizer_prompt")
    def test_equalizer_gets_no_context_block(self, mock_eq, mock_zg):
        """AI_ML briefing_type routes to build_equalizer_prompt, not Zeitgeist."""
        mock_eq.return_value = "eq_prompt"
        synth = BriefingSynthesizer(dry_run=True)
        synth.synthesize(
            stories=[], run_date="2026-02-17", time_of_day="AM",
            briefing_type="AI_ML", context_block="ctx",
            signals=[], prior_briefing=None,
        )
        mock_eq.assert_called_once()
        mock_zg.assert_not_called()

    @patch("src.services.synthesizer.build_zeitgeist_prompt")
    @patch("src.services.synthesizer.build_equalizer_prompt")
    def test_zeitgeist_gets_context_block(self, mock_eq, mock_zg):
        """WORLD briefing_type routes to build_zeitgeist_prompt with context_block."""
        mock_zg.return_value = "zg_prompt"
        synth = BriefingSynthesizer(dry_run=True)
        synth.synthesize(
            stories=[], run_date="2026-02-17", time_of_day="AM",
            briefing_type="WORLD", context_block="SYSTEM_CONTEXT_BLOCK test",
            signals=[], prior_briefing=None,
        )
        mock_zg.assert_called_once()
        mock_eq.assert_not_called()
        # context_block is passed to build_zeitgeist_prompt
        _, kwargs = mock_zg.call_args
        assert kwargs.get("context_block") == "SYSTEM_CONTEXT_BLOCK test"

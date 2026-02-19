"""Tests for the v2 briefing handler."""
import json
from unittest.mock import MagicMock, patch

import src.handlers.briefing_handler as handler_mod



def test_equalizer_system_has_description_sentinel():
    """EQUALIZER prompt must instruct the model to output DESCRIPTION: sentinel."""
    from src.services.personas import _EQUALIZER_SYSTEM
    assert "DESCRIPTION:" in _EQUALIZER_SYSTEM
    assert "Making the Future Evenly Distributed" not in _EQUALIZER_SYSTEM


def _sqs_event(briefing_type="AI_ML", stories=None, briefing_date="2026-02-17-AM"):
    body = json.dumps({
        "briefing_type": briefing_type,
        "briefing_date": briefing_date,
        "candidate_count": 5,
        "stories": stories or [],
    })
    return {"Records": [{"body": body}]}


def _make_story(hash_id="h1", cluster_key="eval-crisis", context_block="{}"):
    return {
        "story_hash": hash_id,
        "title": f"Story {hash_id}",
        "url": f"https://example.com/{hash_id}",
        "summary": "Summary sentence. Why it matters.",
        "source_type": "journalism",
        "sub_bucket": "research",
        "boost_tags": [],
        "cluster_size": 1,
        "cluster_key": cluster_key,
        "context_block": context_block,
        "feed_name": "cs.AI updates on arXiv.org",
        "scores": {"integrity": 4, "relevance": 4, "novelty": 4, "total": 12},
        "raindrop_id": 100,
    }


def _default_settings():
    s = MagicMock()
    s.dry_run = "false"
    s.dynamodb_region = "us-east-1"
    s.dynamodb_signal_table = "signal-tracker"
    s.dynamodb_briefing_table = "briefing-archive"
    s.bedrock_region = "us-east-1"
    s.bedrock_briefing_model_id = "test-model"
    s.raindrop_token = "tok"
    s.raindrop_personal_brief_id = 42
    s.site_url = "https://recursiveintelligence.io"
    s.brief_api_key = "testkey"
    return s


# ── Unit tests for helper functions ───────────────────────────────────────

def test_briefing_date_to_iso_am():
    assert handler_mod._briefing_date_to_iso("2026-02-17-AM") == "2026-02-17T06:00:00Z"


def test_briefing_date_to_iso_pm():
    assert handler_mod._briefing_date_to_iso("2026-02-17-PM") == "2026-02-17T18:00:00Z"


def test_extract_summary_skips_headings():
    text = "# Heading\n\nThis is the summary paragraph."
    assert handler_mod._extract_summary(text) == "This is the summary paragraph."


def test_extract_summary_returns_first_non_blank_line():
    text = "\n\nFirst real line."
    assert handler_mod._extract_summary(text) == "First real line."


def test_build_items_filters_stories_missing_url_or_summary():
    stories = [
        {"title": "A", "url": "https://a.com", "summary": "Sum A", "feed_name": "Feed A"},
        {"title": "B", "url": "", "summary": "Sum B", "feed_name": "Feed B"},      # empty url
        {"title": "C", "url": "https://c.com", "summary": "", "feed_name": "Feed C"},  # empty summary
    ]
    items = handler_mod._build_items(stories)
    assert len(items) == 1
    assert items[0] == {
        "title": "A", "url": "https://a.com", "source": "Feed A", "snippet": "Sum A"
    }


# ── Integration tests for lambda_handler ──────────────────────────────────

@patch("src.handlers.briefing_handler.BriefingArchive")
@patch("src.handlers.briefing_handler.SignalTracker")
@patch("src.handlers.briefing_handler.BriefingSynthesizer")
@patch("src.handlers.briefing_handler._post_to_site")
@patch("src.handlers.briefing_handler.boto3")
@patch("src.handlers.briefing_handler.Settings")
def test_aiml_briefing_posts_to_site(
    mock_settings_cls, mock_boto3, mock_post_to_site, mock_synth_cls,
    mock_signal_cls, mock_archive_cls,
):
    mock_settings_cls.return_value = _default_settings()
    stories = [_make_story(f"h{i}", cluster_key="eval-crisis") for i in range(3)]
    mock_synth_cls.return_value.synthesize.return_value = "Full briefing text."
    mock_synth_cls.return_value._prior_briefing_key.return_value = ("2026-02-16-PM", "AI_ML")
    mock_archive_cls.return_value.get_prior.return_value = None
    mock_signal_cls.return_value.get_signals.return_value = []

    resp = handler_mod.lambda_handler(_sqs_event(stories=stories), {})

    assert resp["statusCode"] == 200
    assert resp["body"]["briefing_sent"] == 1
    mock_post_to_site.assert_called_once()


@patch("src.handlers.briefing_handler.BriefingArchive")
@patch("src.handlers.briefing_handler.SignalTracker")
@patch("src.handlers.briefing_handler.BriefingSynthesizer")
@patch("src.handlers.briefing_handler.RaindropClient")
@patch("src.handlers.briefing_handler.boto3")
@patch("src.handlers.briefing_handler.Settings")
def test_world_briefing_updates_raindrop(
    mock_settings_cls, mock_boto3, mock_raindrop_cls, mock_synth_cls,
    mock_signal_cls, mock_archive_cls,
):
    mock_settings_cls.return_value = _default_settings()
    stories = [_make_story()]
    mock_synth_cls.return_value.synthesize.return_value = "World briefing text."
    mock_synth_cls.return_value._prior_briefing_key.return_value = ("2026-02-16-PM", "WORLD")
    mock_archive_cls.return_value.get_prior.return_value = None
    mock_signal_cls.return_value.get_signals.return_value = []

    resp = handler_mod.lambda_handler(_sqs_event(briefing_type="WORLD", stories=stories), {})

    assert resp["statusCode"] == 200
    assert resp["body"]["briefing_sent"] == 1
    mock_raindrop_cls.return_value.update_bookmark.assert_called_once_with(
        raindrop_id=42, note="World briefing text."
    )


@patch("src.handlers.briefing_handler.BriefingArchive")
@patch("src.handlers.briefing_handler.SignalTracker")
@patch("src.handlers.briefing_handler.BriefingSynthesizer")
@patch("src.handlers.briefing_handler._post_to_site")
@patch("src.handlers.briefing_handler.boto3")
@patch("src.handlers.briefing_handler.Settings")
def test_signals_fetched_from_cluster_keys(
    mock_settings_cls, mock_boto3, mock_post_to_site, mock_synth_cls,
    mock_signal_cls, mock_archive_cls,
):
    mock_settings_cls.return_value = _default_settings()
    stories = [
        _make_story("h1", cluster_key="eval-crisis"),
        _make_story("h2", cluster_key="open-source"),
        _make_story("h3", cluster_key="eval-crisis"),  # duplicate key
    ]
    mock_synth_cls.return_value.synthesize.return_value = "Briefing."
    mock_synth_cls.return_value._prior_briefing_key.return_value = ("2026-02-16-PM", "AI_ML")
    mock_archive_cls.return_value.get_prior.return_value = None
    mock_signal_cls.return_value.get_signals.return_value = [
        {"signal_key": "eval-crisis", "mention_count": 5}
    ]

    handler_mod.lambda_handler(_sqs_event(stories=stories), {})

    # get_signals called with deduplicated cluster_keys (2 unique keys)
    call_args = mock_signal_cls.return_value.get_signals.call_args[0][0]
    assert set(call_args) == {"eval-crisis", "open-source"}


@patch("src.handlers.briefing_handler.BriefingArchive")
@patch("src.handlers.briefing_handler.SignalTracker")
@patch("src.handlers.briefing_handler.BriefingSynthesizer")
@patch("src.handlers.briefing_handler._post_to_site")
@patch("src.handlers.briefing_handler.boto3")
@patch("src.handlers.briefing_handler.Settings")
def test_archive_written_after_publish(
    mock_settings_cls, mock_boto3, mock_post_to_site, mock_synth_cls,
    mock_signal_cls, mock_archive_cls,
):
    mock_settings_cls.return_value = _default_settings()
    stories = [_make_story()]
    mock_synth_cls.return_value.synthesize.return_value = "Briefing text."
    mock_synth_cls.return_value._prior_briefing_key.return_value = ("2026-02-16-PM", "AI_ML")
    mock_archive_cls.return_value.get_prior.return_value = None
    mock_signal_cls.return_value.get_signals.return_value = []

    handler_mod.lambda_handler(_sqs_event(stories=stories), {})

    mock_archive_cls.return_value.store_briefing.assert_called_once()
    store_kwargs = mock_archive_cls.return_value.store_briefing.call_args[1]
    assert store_kwargs["briefing_date"] == "2026-02-17-AM"
    assert store_kwargs["briefing_type"] == "AI_ML"
    assert store_kwargs["content"] == "Briefing text."
    assert store_kwargs["raindrop_id"] is None   # AI_ML no longer uses Raindrop
    assert store_kwargs["candidate_count"] == 5
    assert store_kwargs["story_count"] == 1


@patch("src.handlers.briefing_handler.BriefingArchive")
@patch("src.handlers.briefing_handler.SignalTracker")
@patch("src.handlers.briefing_handler.BriefingSynthesizer")
@patch("src.handlers.briefing_handler._post_to_site")
@patch("src.handlers.briefing_handler.boto3")
@patch("src.handlers.briefing_handler.Settings")
def test_dry_run_true_no_writes(
    mock_settings_cls, mock_boto3, mock_post_to_site, mock_synth_cls,
    mock_signal_cls, mock_archive_cls,
):
    settings = _default_settings()
    settings.dry_run = "true"
    mock_settings_cls.return_value = settings
    mock_synth_cls.return_value.synthesize.return_value = "[DRY_RUN] placeholder"
    mock_synth_cls.return_value._prior_briefing_key.return_value = ("2026-02-16-PM", "AI_ML")
    mock_archive_cls.return_value.get_prior.return_value = None
    mock_signal_cls.return_value.get_signals.return_value = []

    resp = handler_mod.lambda_handler(_sqs_event(stories=[_make_story()]), {})

    assert resp["body"]["dry_run"] == "true"
    # Site ingest not called in dry_run
    mock_post_to_site.assert_not_called()
    # Archive not written in dry_run
    mock_archive_cls.return_value.store_briefing.assert_not_called()

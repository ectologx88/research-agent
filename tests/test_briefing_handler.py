"""Tests for the v2 briefing handler."""
import json
from unittest.mock import MagicMock, patch

import src.handlers.briefing_handler as handler_mod


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
    s.raindrop_aiml_collection_id = 11
    s.raindrop_world_collection_id = 22
    return s


@patch("src.handlers.briefing_handler.BriefingArchive")
@patch("src.handlers.briefing_handler.SignalTracker")
@patch("src.handlers.briefing_handler.BriefingSynthesizer")
@patch("src.handlers.briefing_handler.RaindropClient")
@patch("src.handlers.briefing_handler.boto3")
@patch("src.handlers.briefing_handler.Settings")
def test_creates_briefing_and_posts_to_raindrop(
    mock_settings_cls, mock_boto3, mock_raindrop_cls, mock_synth_cls,
    mock_signal_cls, mock_archive_cls,
):
    mock_settings_cls.return_value = _default_settings()
    stories = [_make_story(f"h{i}", cluster_key="eval-crisis") for i in range(3)]
    mock_raindrop_cls.return_value.check_duplicate.return_value = False
    mock_raindrop_cls.return_value.create_bookmark.return_value = {"_id": 999}
    mock_synth_cls.return_value.synthesize.return_value = "Full briefing text."
    mock_synth_cls.return_value._prior_briefing_key.return_value = ("2026-02-16-PM", "AI_ML")
    mock_archive_cls.return_value.get_prior.return_value = None
    mock_signal_cls.return_value.get_signals.return_value = []

    resp = handler_mod.lambda_handler(_sqs_event(stories=stories), {})

    assert resp["statusCode"] == 200
    assert resp["body"]["briefing_sent"] == 1
    mock_raindrop_cls.return_value.create_bookmark.assert_called_once()


@patch("src.handlers.briefing_handler.BriefingArchive")
@patch("src.handlers.briefing_handler.SignalTracker")
@patch("src.handlers.briefing_handler.BriefingSynthesizer")
@patch("src.handlers.briefing_handler.RaindropClient")
@patch("src.handlers.briefing_handler.boto3")
@patch("src.handlers.briefing_handler.Settings")
def test_duplicate_briefing_skipped(
    mock_settings_cls, mock_boto3, mock_raindrop_cls, mock_synth_cls,
    mock_signal_cls, mock_archive_cls,
):
    mock_settings_cls.return_value = _default_settings()
    mock_raindrop_cls.return_value.check_duplicate.return_value = True  # duplicate

    resp = handler_mod.lambda_handler(_sqs_event(), {})

    assert resp["body"]["briefing_sent"] == 0
    assert resp["body"].get("reason") == "duplicate"
    mock_synth_cls.return_value.synthesize.assert_not_called()


@patch("src.handlers.briefing_handler.BriefingArchive")
@patch("src.handlers.briefing_handler.SignalTracker")
@patch("src.handlers.briefing_handler.BriefingSynthesizer")
@patch("src.handlers.briefing_handler.RaindropClient")
@patch("src.handlers.briefing_handler.boto3")
@patch("src.handlers.briefing_handler.Settings")
def test_signals_fetched_from_cluster_keys(
    mock_settings_cls, mock_boto3, mock_raindrop_cls, mock_synth_cls,
    mock_signal_cls, mock_archive_cls,
):
    mock_settings_cls.return_value = _default_settings()
    stories = [
        _make_story("h1", cluster_key="eval-crisis"),
        _make_story("h2", cluster_key="open-source"),
        _make_story("h3", cluster_key="eval-crisis"),  # duplicate key
    ]
    mock_raindrop_cls.return_value.check_duplicate.return_value = False
    mock_raindrop_cls.return_value.create_bookmark.return_value = {"_id": 1}
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
@patch("src.handlers.briefing_handler.RaindropClient")
@patch("src.handlers.briefing_handler.boto3")
@patch("src.handlers.briefing_handler.Settings")
def test_archive_written_after_raindrop(
    mock_settings_cls, mock_boto3, mock_raindrop_cls, mock_synth_cls,
    mock_signal_cls, mock_archive_cls,
):
    mock_settings_cls.return_value = _default_settings()
    stories = [_make_story()]
    mock_raindrop_cls.return_value.check_duplicate.return_value = False
    mock_raindrop_cls.return_value.create_bookmark.return_value = {"_id": 42}
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
    assert store_kwargs["raindrop_id"] == "42"   # must be str, not int
    assert store_kwargs["candidate_count"] == 5
    assert store_kwargs["story_count"] == 1


@patch("src.handlers.briefing_handler.BriefingArchive")
@patch("src.handlers.briefing_handler.SignalTracker")
@patch("src.handlers.briefing_handler.BriefingSynthesizer")
@patch("src.handlers.briefing_handler.RaindropClient")
@patch("src.handlers.briefing_handler.boto3")
@patch("src.handlers.briefing_handler.Settings")
def test_dry_run_true_no_writes(
    mock_settings_cls, mock_boto3, mock_raindrop_cls, mock_synth_cls,
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
    # Raindrop not created in dry_run
    mock_raindrop_cls.assert_not_called()
    # Archive not written in dry_run
    mock_archive_cls.return_value.store_briefing.assert_not_called()

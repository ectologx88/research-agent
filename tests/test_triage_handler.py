"""Tests for the v2 triage handler."""
import json
from unittest.mock import MagicMock, patch, call

import src.handlers.triage_handler as handler_mod


def _make_story(feed="cs.AI updates on arXiv.org", title="Neural nets",
                url="https://arxiv.org/1", hash="h1", content="Article body"):
    s = MagicMock()
    s.story_feed_title = feed
    s.story_title = title
    s.story_permalink = url
    s.story_hash = hash
    s.story_content = content
    s.newsblur_score = 1
    return s


def _default_settings():
    s = MagicMock()
    s.newsblur_username = "user"
    s.newsblur_password = "pass"
    s.newsblur_min_score = 1
    s.newsblur_hours_back = 12
    s.max_stories_per_run = 150
    s.dynamodb_region = "us-east-1"
    s.dynamodb_story_staging_table = "story-staging"
    s.dynamodb_signal_table = "signal-tracker"
    s.raindrop_token = "tok"
    s.raindrop_aiml_collection_id = 11
    s.sqs_aiml_queue_url = "https://sqs/aiml"
    s.dry_run = "false"
    # Per-folder caps
    s.ai_ml_research_max_stories = 40
    s.ai_ml_community_max_stories = 25
    s.general_tech_max_stories = 40
    s.ai_ml_research_min_score = 0
    return s


def _ai_ml_folder_map():
    """Folder map that routes stories through AI-ML-Research only."""
    return {"AI-ML-Research": [12345], "": []}


def _unfolderd_folder_map():
    """Folder map that routes stories through unfolderd feeds only."""
    return {"": [99999]}


@patch("src.handlers.triage_handler.ContextLoader")
@patch("src.handlers.triage_handler.boto3")
@patch("src.handlers.triage_handler.RaindropClient")
@patch("src.handlers.triage_handler.StoryStaging")
@patch("src.handlers.triage_handler.NewsBlurClient")
@patch("src.handlers.triage_handler.Settings")
def test_routes_aiml_story_to_aiml_collection(
    mock_settings_cls, mock_nb_cls, mock_staging_cls, mock_raindrop_cls,
    mock_boto3, mock_context_cls,
):
    mock_settings_cls.return_value = _default_settings()
    story = _make_story(feed="cs.AI updates on arXiv.org", hash="h1")
    mock_nb_cls.return_value.get_feeds_by_folder.return_value = _ai_ml_folder_map()
    mock_nb_cls.return_value.fetch_unread_stories.return_value = [story]
    mock_staging_cls.return_value.check_duplicate.return_value = False
    mock_raindrop_cls.return_value.check_duplicate.return_value = False
    mock_raindrop_cls.return_value.create_bookmark.return_value = {"_id": 999}
    mock_context_cls.return_value.fetch_all.return_value = {}

    resp = handler_mod.lambda_handler({}, {})

    assert resp["statusCode"] == 200
    assert resp["body"]["ai_ml_count"] == 1
    assert "world_count" not in resp["body"]
    mock_staging_cls.return_value.store_story.assert_called_once()


@patch("src.handlers.triage_handler.ContextLoader")
@patch("src.handlers.triage_handler.boto3")
@patch("src.handlers.triage_handler.RaindropClient")
@patch("src.handlers.triage_handler.StoryStaging")
@patch("src.handlers.triage_handler.NewsBlurClient")
@patch("src.handlers.triage_handler.Settings")
def test_skip_stories_not_saved(
    mock_settings_cls, mock_nb_cls, mock_staging_cls, mock_raindrop_cls,
    mock_boto3, mock_context_cls,
):
    mock_settings_cls.return_value = _default_settings()
    story = _make_story(feed="AI / Raindrop.io", title="Meta story", hash="h2")
    mock_nb_cls.return_value.get_feeds_by_folder.return_value = _unfolderd_folder_map()
    mock_nb_cls.return_value.fetch_unread_stories.return_value = [story]
    mock_staging_cls.return_value.check_duplicate.return_value = False
    mock_context_cls.return_value.fetch_all.return_value = {}

    resp = handler_mod.lambda_handler({}, {})

    assert resp["body"]["skipped_count"] == 1
    mock_staging_cls.return_value.store_story.assert_not_called()


@patch("src.handlers.triage_handler.ContextLoader")
@patch("src.handlers.triage_handler.boto3")
@patch("src.handlers.triage_handler.RaindropClient")
@patch("src.handlers.triage_handler.StoryStaging")
@patch("src.handlers.triage_handler.NewsBlurClient")
@patch("src.handlers.triage_handler.Settings")
def test_dry_run_skips_writes_and_sqs(
    mock_settings_cls, mock_nb_cls, mock_staging_cls, mock_raindrop_cls,
    mock_boto3, mock_context_cls,
):
    settings = _default_settings()
    settings.dry_run = "true"
    mock_settings_cls.return_value = settings
    story = _make_story(feed="cs.AI updates on arXiv.org", hash="h3")
    mock_nb_cls.return_value.get_feeds_by_folder.return_value = _ai_ml_folder_map()
    mock_nb_cls.return_value.fetch_unread_stories.return_value = [story]
    mock_context_cls.return_value.fetch_all.return_value = {}

    resp = handler_mod.lambda_handler({}, {})

    assert resp["body"]["dry_run"] is True
    # Counts still reported in dry-run (just not written)
    assert resp["body"]["ai_ml_count"] == 1
    # DDB writes skipped
    mock_staging_cls.return_value.store_story.assert_not_called()
    # SQS sends skipped
    mock_boto3.client.return_value.send_message.assert_not_called()
    # Raindrop not created in dry_run
    mock_raindrop_cls.assert_not_called()


@patch("src.handlers.triage_handler.ContextLoader")
@patch("src.handlers.triage_handler.boto3")
@patch("src.handlers.triage_handler.RaindropClient")
@patch("src.handlers.triage_handler.StoryStaging")
@patch("src.handlers.triage_handler.NewsBlurClient")
@patch("src.handlers.triage_handler.Settings")
def test_boost_tags_stored_in_ddb(
    mock_settings_cls, mock_nb_cls, mock_staging_cls, mock_raindrop_cls,
    mock_boto3, mock_context_cls,
):
    mock_settings_cls.return_value = _default_settings()
    # Story with "open-source" in title -> should get boost:open-source
    story = _make_story(
        feed="cs.AI updates on arXiv.org",
        title="Open-source LLM beats GPT-4",
        hash="h4",
    )
    mock_nb_cls.return_value.get_feeds_by_folder.return_value = _ai_ml_folder_map()
    mock_nb_cls.return_value.fetch_unread_stories.return_value = [story]
    mock_staging_cls.return_value.check_duplicate.return_value = False
    mock_raindrop_cls.return_value.check_duplicate.return_value = False
    mock_raindrop_cls.return_value.create_bookmark.return_value = {"_id": 1}
    mock_context_cls.return_value.fetch_all.return_value = {}

    handler_mod.lambda_handler({}, {})

    call_args = mock_staging_cls.return_value.store_story.call_args[0][0]
    assert "boost:open-source" in call_args["boost_tags"]


@patch("src.handlers.triage_handler.ContextLoader")
@patch("src.handlers.triage_handler.boto3")
@patch("src.handlers.triage_handler.RaindropClient")
@patch("src.handlers.triage_handler.StoryStaging")
@patch("src.handlers.triage_handler.NewsBlurClient")
@patch("src.handlers.triage_handler.Settings")
def test_context_block_stored_with_stories(
    mock_settings_cls, mock_nb_cls, mock_staging_cls, mock_raindrop_cls,
    mock_boto3, mock_context_cls,
):
    mock_settings_cls.return_value = _default_settings()
    story = _make_story(hash="h5")
    mock_nb_cls.return_value.get_feeds_by_folder.return_value = _ai_ml_folder_map()
    mock_nb_cls.return_value.fetch_unread_stories.return_value = [story]
    mock_staging_cls.return_value.check_duplicate.return_value = False
    mock_raindrop_cls.return_value.check_duplicate.return_value = False
    mock_raindrop_cls.return_value.create_bookmark.return_value = {"_id": 2}
    mock_context_cls.return_value.fetch_all.return_value = {"weather": {"temp_f": 72.0}}
    mock_context_cls.return_value.format_context_block.return_value = "WEATHER:\nCurrent: 72.0°F"

    handler_mod.lambda_handler({}, {})

    call_args = mock_staging_cls.return_value.store_story.call_args[0][0]
    assert "72.0" in call_args["context_block"]


@patch("src.handlers.triage_handler.ContextLoader")
@patch("src.handlers.triage_handler.boto3")
@patch("src.handlers.triage_handler.RaindropClient")
@patch("src.handlers.triage_handler.StoryStaging")
@patch("src.handlers.triage_handler.NewsBlurClient")
@patch("src.handlers.triage_handler.Settings")
def test_candidate_count_in_sqs_message(
    mock_settings_cls, mock_nb_cls, mock_staging_cls, mock_raindrop_cls,
    mock_boto3, mock_context_cls,
):
    mock_settings_cls.return_value = _default_settings()
    story = _make_story(hash="h6")
    mock_nb_cls.return_value.get_feeds_by_folder.return_value = _ai_ml_folder_map()
    mock_nb_cls.return_value.fetch_unread_stories.return_value = [story]
    mock_staging_cls.return_value.check_duplicate.return_value = False
    mock_raindrop_cls.return_value.check_duplicate.return_value = False
    mock_raindrop_cls.return_value.create_bookmark.return_value = {"_id": 3}
    mock_context_cls.return_value.fetch_all.return_value = {}

    handler_mod.lambda_handler({}, {})

    sqs_mock = mock_boto3.client.return_value
    assert sqs_mock.send_message.called
    body = json.loads(sqs_mock.send_message.call_args[1]["MessageBody"])
    assert "candidate_count" in body
    assert "briefing_date" in body


@patch("src.handlers.triage_handler.ContextLoader")
@patch("src.handlers.triage_handler.boto3")
@patch("src.handlers.triage_handler.RaindropClient")
@patch("src.handlers.triage_handler.StoryStaging")
@patch("src.handlers.triage_handler.NewsBlurClient")
@patch("src.handlers.triage_handler.Settings")
def test_hn_velocity_high_adds_boost_tag(
    mock_settings_cls, mock_nb_cls, mock_staging_cls, mock_raindrop_cls,
    mock_boto3, mock_context_cls,
):
    """Stories with 200+ HN points get velocity:hn-high in stored boost_tags."""
    mock_settings_cls.return_value = _default_settings()
    story = _make_story(
        feed="cs.AI updates on arXiv.org",
        title="Major open-source LLM release",
        hash="h_hn1",
    )
    mock_nb_cls.return_value.get_feeds_by_folder.return_value = _ai_ml_folder_map()
    mock_nb_cls.return_value.fetch_unread_stories.return_value = [story]
    mock_staging_cls.return_value.check_duplicate.return_value = False
    mock_raindrop_cls.return_value.check_duplicate.return_value = False
    mock_raindrop_cls.return_value.create_bookmark.return_value = {"_id": 10}
    mock_context_cls.return_value.fetch_all.return_value = {}

    with patch("src.handlers.triage_handler._check_hn_velocity", return_value=250):
        handler_mod.lambda_handler({}, {})

    call_args = mock_staging_cls.return_value.store_story.call_args[0][0]
    assert "velocity:hn-high" in call_args["boost_tags"]


def test_hn_velocity_failure_does_not_raise():
    """HN API failure never propagates -- _check_hn_velocity returns 0 silently."""
    import urllib.request
    from unittest.mock import patch
    with patch("urllib.request.urlopen", side_effect=Exception("network error")):
        from src.handlers.triage_handler import _check_hn_velocity
        result = _check_hn_velocity("https://example.com/story")
    assert result == 0


@patch("src.handlers.triage_handler.ContextLoader")
@patch("src.handlers.triage_handler.boto3")
@patch("src.handlers.triage_handler.RaindropClient")
@patch("src.handlers.triage_handler.StoryStaging")
@patch("src.handlers.triage_handler.SignalTracker")
@patch("src.handlers.triage_handler.Settings")
@patch("src.handlers.triage_handler.NewsBlurClient")
def test_response_has_no_world_count(mock_nb_cls, mock_settings_cls, mock_signal,
                                      mock_staging, mock_raindrop, mock_boto3, mock_ctx):
    settings = _default_settings()
    mock_settings_cls.return_value = settings
    nb = MagicMock()
    nb.get_feeds_by_folder.return_value = {"AI-ML-Research": [123], "": []}
    nb.fetch_unread_stories.return_value = []
    mock_nb_cls.return_value = nb
    mock_ctx.return_value.fetch_all.return_value = {}
    mock_ctx.return_value.format_context_block.return_value = "{}"
    mock_staging.return_value.check_duplicate.return_value = False

    from src.handlers.triage_handler import lambda_handler
    result = lambda_handler({}, None)

    assert "world_count" not in result["body"]


@patch("src.handlers.triage_handler.utcnow")
@patch("src.handlers.triage_handler.ContextLoader")
@patch("src.handlers.triage_handler.boto3")
@patch("src.handlers.triage_handler.RaindropClient")
@patch("src.handlers.triage_handler.StoryStaging")
@patch("src.handlers.triage_handler.SignalTracker")
@patch("src.handlers.triage_handler.Settings")
@patch("src.handlers.triage_handler.NewsBlurClient")
def test_monday_fetch_uses_74_hours_back(mock_nb_cls, mock_settings_cls, mock_signal,
                                          mock_staging, mock_raindrop, mock_boto3,
                                          mock_ctx, mock_utcnow):
    from datetime import datetime, timezone
    # 2026-04-13 is a Monday
    mock_utcnow.return_value = datetime(2026, 4, 13, 13, 0, 0, tzinfo=timezone.utc)

    settings = _default_settings()
    settings.newsblur_hours_back = 26
    mock_settings_cls.return_value = settings

    nb = MagicMock()
    nb.get_feeds_by_folder.return_value = {"AI-ML-Research": [123], "": []}
    nb.fetch_unread_stories.return_value = []
    mock_nb_cls.return_value = nb
    mock_ctx.return_value.fetch_all.return_value = {}
    mock_ctx.return_value.format_context_block.return_value = "{}"
    mock_staging.return_value.check_duplicate.return_value = False

    from src.handlers.triage_handler import lambda_handler
    lambda_handler({}, None)

    # All fetch_unread_stories calls should use hours_back=74 on Monday
    for call in nb.fetch_unread_stories.call_args_list:
        assert call.kwargs.get("hours_back") == 74, \
            f"Expected hours_back=74 on Monday, got {call.kwargs.get('hours_back')}"


@patch("src.handlers.triage_handler.utcnow")
@patch("src.handlers.triage_handler.ContextLoader")
@patch("src.handlers.triage_handler.boto3")
@patch("src.handlers.triage_handler.RaindropClient")
@patch("src.handlers.triage_handler.StoryStaging")
@patch("src.handlers.triage_handler.SignalTracker")
@patch("src.handlers.triage_handler.Settings")
@patch("src.handlers.triage_handler.NewsBlurClient")
def test_tuesday_fetch_uses_default_hours_back(mock_nb_cls, mock_settings_cls, mock_signal,
                                                mock_staging, mock_raindrop, mock_boto3,
                                                mock_ctx, mock_utcnow):
    from datetime import datetime, timezone
    # 2026-04-14 is a Tuesday
    mock_utcnow.return_value = datetime(2026, 4, 14, 13, 0, 0, tzinfo=timezone.utc)

    settings = _default_settings()
    settings.newsblur_hours_back = 26
    mock_settings_cls.return_value = settings

    nb = MagicMock()
    nb.get_feeds_by_folder.return_value = {"AI-ML-Research": [123], "": []}
    nb.fetch_unread_stories.return_value = []
    mock_nb_cls.return_value = nb
    mock_ctx.return_value.fetch_all.return_value = {}
    mock_ctx.return_value.format_context_block.return_value = "{}"
    mock_staging.return_value.check_duplicate.return_value = False

    from src.handlers.triage_handler import lambda_handler
    lambda_handler({}, None)

    for call in nb.fetch_unread_stories.call_args_list:
        assert call.kwargs.get("hours_back") == 26, \
            f"Expected hours_back=26 on Tuesday, got {call.kwargs.get('hours_back')}"

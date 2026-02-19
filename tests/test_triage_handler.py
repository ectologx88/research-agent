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
    s.max_stories_per_run = 150
    s.dynamodb_region = "us-east-1"
    s.dynamodb_story_staging_table = "story-staging"
    s.dynamodb_signal_table = "signal-tracker"
    s.raindrop_token = "tok"
    s.raindrop_aiml_collection_id = 11
    s.raindrop_world_collection_id = 22
    s.sqs_aiml_queue_url = "https://sqs/aiml"
    s.sqs_world_queue_url = "https://sqs/world"
    s.dry_run = "false"
    return s


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
    mock_nb_cls.return_value.fetch_unread_stories.return_value = [story]
    mock_staging_cls.return_value.check_duplicate.return_value = False
    mock_raindrop_cls.return_value.check_duplicate.return_value = False
    mock_raindrop_cls.return_value.create_bookmark.return_value = {"_id": 999}
    mock_context_cls.return_value.fetch_all.return_value = {}

    resp = handler_mod.lambda_handler({}, {})

    assert resp["statusCode"] == 200
    assert resp["body"]["ai_ml_count"] == 1
    assert resp["body"]["world_count"] == 0
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

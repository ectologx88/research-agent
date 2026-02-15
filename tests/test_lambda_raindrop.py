"""Integration tests for Raindrop wiring in lambda_handler."""
from unittest.mock import MagicMock, patch, call
import pytest


def _make_story(url="https://example.com/story"):
    s = MagicMock()
    s.story_permalink = url
    s.story_title = "Test Story"
    return s


def _make_classification(overall=9, concepts=["ai"], why="It matters."):
    c = MagicMock()
    c.scores.overall = overall
    c.concepts = concepts
    c.why_matters = why
    return c


def _make_result(pairs):
    r = MagicMock()
    r.classified = pairs
    r.metrics = MagicMock()
    r.metrics.__dict__ = {}
    import dataclasses
    with patch("dataclasses.asdict", return_value={}):
        pass
    return r


@patch("src.lambda_handler.RaindropClient")
@patch("src.lambda_handler.ClassificationService")
@patch("src.lambda_handler.ProcessingStateStorage")
@patch("src.lambda_handler.BedrockClassifier")
@patch("src.lambda_handler.NewsBlurClient")
@patch("src.lambda_handler.Settings")
def test_high_value_stories_sent_to_raindrop(
    mock_settings_cls, mock_nb_cls, mock_bedrock_cls,
    mock_storage_cls, mock_svc_cls, mock_raindrop_cls
):
    import dataclasses

    settings = MagicMock()
    settings.newsblur_username = "u"
    settings.newsblur_password = "p"
    settings.bedrock_region = "us-east-1"
    settings.bedrock_model_id = "model"
    settings.dynamodb_table_name = "table"
    settings.dynamodb_region = "us-east-1"
    settings.threshold_overall = 8
    settings.raindrop_token = "tok"
    settings.raindrop_collection_id = -1
    mock_settings_cls.return_value = settings

    story = _make_story()
    classification = _make_classification(overall=9)
    result = MagicMock()
    result.classified = [(story, classification)]
    result.metrics = MagicMock()
    mock_svc_cls.return_value.run.return_value = result

    raindrop_instance = MagicMock()
    raindrop_instance.check_duplicate.return_value = False
    mock_raindrop_cls.return_value = raindrop_instance

    with patch("dataclasses.asdict", return_value={}):
        from src import lambda_handler
        response = lambda_handler.lambda_handler({}, {})

    raindrop_instance.check_duplicate.assert_called_once_with(story.story_permalink)
    raindrop_instance.create_bookmark.assert_called_once_with(
        url=story.story_permalink,
        title=story.story_title,
        tags=classification.concepts,
        note=classification.why_matters,
    )
    assert response["body"]["raindrop_sent"] == 1
    assert response["body"]["raindrop_skipped"] == 0


@patch("src.lambda_handler.RaindropClient")
@patch("src.lambda_handler.ClassificationService")
@patch("src.lambda_handler.ProcessingStateStorage")
@patch("src.lambda_handler.BedrockClassifier")
@patch("src.lambda_handler.NewsBlurClient")
@patch("src.lambda_handler.Settings")
def test_duplicate_stories_skipped(
    mock_settings_cls, mock_nb_cls, mock_bedrock_cls,
    mock_storage_cls, mock_svc_cls, mock_raindrop_cls
):
    settings = MagicMock()
    settings.threshold_overall = 8
    settings.raindrop_token = "tok"
    settings.raindrop_collection_id = -1
    mock_settings_cls.return_value = settings

    story = _make_story()
    classification = _make_classification(overall=9)
    result = MagicMock()
    result.classified = [(story, classification)]
    result.metrics = MagicMock()
    mock_svc_cls.return_value.run.return_value = result

    raindrop_instance = MagicMock()
    raindrop_instance.check_duplicate.return_value = True  # already in Raindrop
    mock_raindrop_cls.return_value = raindrop_instance

    with patch("dataclasses.asdict", return_value={}):
        from src import lambda_handler
        response = lambda_handler.lambda_handler({}, {})

    raindrop_instance.create_bookmark.assert_not_called()
    assert response["body"]["raindrop_skipped"] == 1


@patch("src.lambda_handler.RaindropClient")
@patch("src.lambda_handler.ClassificationService")
@patch("src.lambda_handler.ProcessingStateStorage")
@patch("src.lambda_handler.BedrockClassifier")
@patch("src.lambda_handler.NewsBlurClient")
@patch("src.lambda_handler.Settings")
def test_auth_failure_stops_remaining_stories(
    mock_settings_cls, mock_nb_cls, mock_bedrock_cls,
    mock_storage_cls, mock_svc_cls, mock_raindrop_cls
):
    settings = MagicMock()
    settings.threshold_overall = 8
    settings.raindrop_token = "tok"
    settings.raindrop_collection_id = -1
    mock_settings_cls.return_value = settings

    story1 = _make_story(url="https://example.com/1")
    story2 = _make_story(url="https://example.com/2")
    c1 = _make_classification(overall=9)
    c2 = _make_classification(overall=9)
    result = MagicMock()
    result.classified = [(story1, c1), (story2, c2)]
    result.metrics = MagicMock()
    mock_svc_cls.return_value.run.return_value = result

    from src.clients.raindrop import RaindropAuthError
    raindrop_instance = MagicMock()
    raindrop_instance.check_duplicate.side_effect = RaindropAuthError("token expired")
    mock_raindrop_cls.return_value = raindrop_instance

    with patch("dataclasses.asdict", return_value={}):
        from src import lambda_handler
        response = lambda_handler.lambda_handler({}, {})

    # Only one check_duplicate call made (auth_failed stops the loop)
    assert raindrop_instance.check_duplicate.call_count == 1
    assert raindrop_instance.create_bookmark.call_count == 0
    assert response["body"]["raindrop_sent"] == 0
    assert response["body"]["raindrop_skipped"] == 2  # both stories skipped


@patch("src.lambda_handler.RaindropClient")
@patch("src.lambda_handler.ClassificationService")
@patch("src.lambda_handler.ProcessingStateStorage")
@patch("src.lambda_handler.BedrockClassifier")
@patch("src.lambda_handler.NewsBlurClient")
@patch("src.lambda_handler.Settings")
def test_no_raindrop_token_skips_entirely(
    mock_settings_cls, mock_nb_cls, mock_bedrock_cls,
    mock_storage_cls, mock_svc_cls, mock_raindrop_cls
):
    settings = MagicMock()
    settings.threshold_overall = 8
    settings.raindrop_token = ""  # no token
    settings.raindrop_collection_id = -1
    mock_settings_cls.return_value = settings

    story = _make_story()
    classification = _make_classification(overall=9)
    result = MagicMock()
    result.classified = [(story, classification)]
    result.metrics = MagicMock()
    mock_svc_cls.return_value.run.return_value = result

    with patch("dataclasses.asdict", return_value={}):
        from src import lambda_handler
        response = lambda_handler.lambda_handler({}, {})

    mock_raindrop_cls.assert_not_called()
    assert response["body"]["raindrop_sent"] == 0
    assert response["body"]["raindrop_skipped"] == 0

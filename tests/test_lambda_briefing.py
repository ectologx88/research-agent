"""Tests for Phase 2b briefing wiring in lambda_handler."""
from unittest.mock import MagicMock, patch

import pytest


def _make_mock_result(stories_and_classifications):
    """Build a mock PipelineResult."""
    mock_result = MagicMock()
    mock_result.classified = stories_and_classifications
    mock_result.metrics = MagicMock()
    mock_result.metrics.stories_fetched = len(stories_and_classifications)
    mock_result.metrics.already_processed = 0
    mock_result.metrics.stories_classified = len(stories_and_classifications)
    mock_result.metrics.classification_failures = 0
    mock_result.metrics.dedup_write_failures = 0
    mock_result.metrics.high_value_stories = 0
    mock_result.metrics.time_sensitive_stories = 0
    mock_result.metrics.execution_time_seconds = 1.0
    mock_result.metrics.top_stories = []
    return mock_result


def _make_story(url="https://example.com/1", title="Story"):
    s = MagicMock()
    s.story_permalink = url
    s.story_title = title
    s.story_hash = "hash1"
    return s


def _make_classification(overall=9, importance=7):
    c = MagicMock()
    c.scores.overall = overall
    c.scores.importance = importance
    c.taxonomy_tags = []
    c.priority_flag = None
    c.concepts = ["concept1"]
    c.why_matters = "Why it matters."
    return c


def _make_settings(raindrop_token="tok", briefing_collection_id=42):
    settings = MagicMock()
    settings.newsblur_username = "u"
    settings.newsblur_password = "p"
    settings.bedrock_region = "us-east-1"
    settings.bedrock_model_id = "model"
    settings.bedrock_briefing_model_id = "briefing-model"
    settings.dynamodb_table_name = "table"
    settings.dynamodb_region = "us-east-1"
    settings.threshold_overall = 8
    settings.raindrop_token = raindrop_token
    settings.raindrop_collection_id = -1
    settings.raindrop_briefing_collection_id = briefing_collection_id
    settings.briefing_prefilter_domain_min = 5
    settings.briefing_prefilter_importance_min = 6
    return settings


@patch("src.lambda_handler.RaindropClient")
@patch("src.lambda_handler.BedrockBriefingClient")
@patch("src.lambda_handler.ClassificationService")
@patch("src.lambda_handler.ProcessingStateStorage")
@patch("src.lambda_handler.BedrockClassifier")
@patch("src.lambda_handler.NewsBlurClient")
@patch("src.lambda_handler.Settings")
def test_briefing_sent_when_token_set(
    mock_settings_cls, mock_nb_cls, mock_bedrock_cls,
    mock_storage_cls, mock_svc_cls, mock_briefing_cls, mock_raindrop_cls
):
    """If raindrop_token is set and stories pass pre-filter, briefing bookmark is created."""
    mock_settings_cls.return_value = _make_settings(raindrop_token="tok", briefing_collection_id=42)

    story = _make_story()
    clf = _make_classification(overall=9, importance=7)
    mock_result = _make_mock_result([(story, clf)])
    mock_svc_cls.return_value.run.return_value = mock_result

    mock_briefing_cls.return_value.synthesize.return_value = "Briefing text here."
    mock_raindrop_cls.return_value.check_duplicate.return_value = False

    with patch("dataclasses.asdict", return_value={}):
        from src import lambda_handler
        resp = lambda_handler.lambda_handler({}, {})

    assert resp["statusCode"] == 200
    assert resp["body"]["briefing_sent"] == 1


@patch("src.lambda_handler.RaindropClient")
@patch("src.lambda_handler.BedrockBriefingClient")
@patch("src.lambda_handler.ClassificationService")
@patch("src.lambda_handler.ProcessingStateStorage")
@patch("src.lambda_handler.BedrockClassifier")
@patch("src.lambda_handler.NewsBlurClient")
@patch("src.lambda_handler.Settings")
def test_briefing_skipped_when_no_token(
    mock_settings_cls, mock_nb_cls, mock_bedrock_cls,
    mock_storage_cls, mock_svc_cls, mock_briefing_cls, mock_raindrop_cls
):
    mock_settings_cls.return_value = _make_settings(raindrop_token="")

    mock_result = _make_mock_result([])
    mock_svc_cls.return_value.run.return_value = mock_result

    with patch("dataclasses.asdict", return_value={}):
        from src import lambda_handler
        resp = lambda_handler.lambda_handler({}, {})

    assert resp["body"]["briefing_sent"] == 0
    mock_briefing_cls.return_value.synthesize.assert_not_called()


@patch("src.lambda_handler.RaindropClient")
@patch("src.lambda_handler.BedrockBriefingClient")
@patch("src.lambda_handler.ClassificationService")
@patch("src.lambda_handler.ProcessingStateStorage")
@patch("src.lambda_handler.BedrockClassifier")
@patch("src.lambda_handler.NewsBlurClient")
@patch("src.lambda_handler.Settings")
def test_prefilter_excludes_low_scores(
    mock_settings_cls, mock_nb_cls, mock_bedrock_cls,
    mock_storage_cls, mock_svc_cls, mock_briefing_cls, mock_raindrop_cls
):
    """Stories with overall < 5 AND importance < 6 should not go to briefing."""
    mock_settings_cls.return_value = _make_settings(raindrop_token="tok")

    story = _make_story()
    clf = _make_classification(overall=4, importance=5)  # Both below threshold
    mock_result = _make_mock_result([(story, clf)])
    mock_svc_cls.return_value.run.return_value = mock_result

    with patch("dataclasses.asdict", return_value={}):
        from src import lambda_handler
        lambda_handler.lambda_handler({}, {})

    mock_briefing_cls.return_value.synthesize.assert_not_called()


@patch("src.lambda_handler.RaindropClient")
@patch("src.lambda_handler.BedrockBriefingClient")
@patch("src.lambda_handler.ClassificationService")
@patch("src.lambda_handler.ProcessingStateStorage")
@patch("src.lambda_handler.BedrockClassifier")
@patch("src.lambda_handler.NewsBlurClient")
@patch("src.lambda_handler.Settings")
def test_stories_use_taxonomy_tags_for_raindrop(
    mock_settings_cls, mock_nb_cls, mock_bedrock_cls,
    mock_storage_cls, mock_svc_cls, mock_briefing_cls, mock_raindrop_cls
):
    """Story bookmarks should pass taxonomy tag values (not concepts) to create_bookmark."""
    mock_settings_cls.return_value = _make_settings(raindrop_token="tok")

    from src.models.classification import TaxonomyTag
    story = _make_story()
    clf = _make_classification(overall=9, importance=7)
    clf.taxonomy_tags = [TaxonomyTag.AI_RESEARCH, TaxonomyTag.AI_POLICY]

    mock_result = _make_mock_result([(story, clf)])
    mock_svc_cls.return_value.run.return_value = mock_result

    mock_briefing_cls.return_value.synthesize.return_value = "Briefing."
    mock_raindrop_cls.return_value.check_duplicate.return_value = False

    with patch("dataclasses.asdict", return_value={}):
        from src import lambda_handler
        lambda_handler.lambda_handler({}, {})

    # call_args_list[0] is the story bookmark; call_args_list[1] would be the briefing bookmark
    call_kwargs = mock_raindrop_cls.return_value.create_bookmark.call_args_list[0]
    # First call is for the story bookmark; check tags argument
    tags_used = call_kwargs.kwargs.get("tags") or call_kwargs.args[2]
    assert "#ai-research" in tags_used or TaxonomyTag.AI_RESEARCH.value in tags_used

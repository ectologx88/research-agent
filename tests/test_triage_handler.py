from unittest.mock import MagicMock, patch


def _make_story(feed="arXiv AI", title="Neural nets", url="https://arxiv.org/1", hash="h1"):
    s = MagicMock()
    s.story_feed_title = feed
    s.story_title = title
    s.story_permalink = url
    s.story_hash = hash
    s.story_content = "Article body"
    s.story_authors = "Author"
    s.newsblur_score = 1
    return s


@patch("src.handlers.triage_handler.boto3")
@patch("src.handlers.triage_handler.RaindropClient")
@patch("src.handlers.triage_handler.ProcessingStateStorage")
@patch("src.handlers.triage_handler.NewsBlurClient")
@patch("src.handlers.triage_handler.Settings")
def test_routes_aiml_story_to_aiml_collection(
    mock_settings_cls, mock_nb_cls, mock_storage_cls, mock_raindrop_cls, mock_boto3
):
    settings = MagicMock()
    settings.raindrop_token = "tok"
    settings.raindrop_aiml_collection_id = 11
    settings.raindrop_world_collection_id = 22
    settings.sqs_aiml_queue_url = "https://sqs/aiml"
    settings.sqs_world_queue_url = "https://sqs/world"
    settings.newsblur_min_score = 1
    settings.max_stories_per_run = 150
    settings.mark_as_read = False
    settings.fetch_strategy = "hours_back"
    settings.hours_back_default = 12
    settings.dynamodb_table_name = "table"
    settings.dynamodb_region = "us-east-1"
    mock_settings_cls.return_value = settings

    story = _make_story(feed="arXiv AI", hash="h1")
    mock_nb_cls.return_value.fetch_unread_stories.return_value = [story]
    mock_storage_cls.return_value.batch_check_processed.return_value = set()
    mock_storage_cls.return_value.store_story_content.return_value = True
    mock_raindrop_cls.return_value.check_duplicate.return_value = False
    mock_raindrop_cls.return_value.create_bookmark.return_value = {"_id": 999}

    from src.handlers.triage_handler import lambda_handler
    resp = lambda_handler({}, {})

    assert resp["statusCode"] == 200
    assert resp["body"]["ai_ml_count"] == 1
    assert resp["body"]["world_count"] == 0

    raindrop_instance = mock_raindrop_cls.return_value
    assert raindrop_instance.create_bookmark.called


@patch("src.handlers.triage_handler.boto3")
@patch("src.handlers.triage_handler.RaindropClient")
@patch("src.handlers.triage_handler.ProcessingStateStorage")
@patch("src.handlers.triage_handler.NewsBlurClient")
@patch("src.handlers.triage_handler.Settings")
def test_skip_stories_are_not_saved(
    mock_settings_cls, mock_nb_cls, mock_storage_cls, mock_raindrop_cls, mock_boto3
):
    settings = MagicMock()
    settings.raindrop_token = "tok"
    settings.sqs_aiml_queue_url = "https://sqs/aiml"
    settings.sqs_world_queue_url = "https://sqs/world"
    settings.newsblur_min_score = 1
    settings.max_stories_per_run = 150
    settings.mark_as_read = False
    settings.dynamodb_table_name = "table"
    settings.dynamodb_region = "us-east-1"
    mock_settings_cls.return_value = settings

    story = _make_story(feed="ESPN", title="Game recap")
    mock_nb_cls.return_value.fetch_unread_stories.return_value = [story]
    mock_storage_cls.return_value.batch_check_processed.return_value = set()

    from src.handlers.triage_handler import lambda_handler
    resp = lambda_handler({}, {})

    assert resp["body"]["skipped_count"] == 1
    mock_raindrop_cls.return_value.create_bookmark.assert_not_called()

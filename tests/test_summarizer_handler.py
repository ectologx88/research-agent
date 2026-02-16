import json
from unittest.mock import MagicMock, patch


def _sqs_event(briefing_type="ai-ml", hashes=("h1",)):
    body = json.dumps({
        "briefing_type": briefing_type,
        "run_date": "2026-02-16",
        "time_of_day": "morning",
        "story_hashes": list(hashes),
    })
    return {"Records": [{"body": body}]}


@patch("src.handlers.summarizer_handler.boto3")
@patch("src.handlers.summarizer_handler.RaindropClient")
@patch("src.handlers.summarizer_handler.BedrockSummarizerClient")
@patch("src.handlers.summarizer_handler.ProcessingStateStorage")
@patch("src.handlers.summarizer_handler.Settings")
def test_summarizes_stories_and_sends_to_briefing_queue(
    mock_settings_cls, mock_storage_cls, mock_summarizer_cls, mock_raindrop_cls, mock_boto3
):
    settings = MagicMock()
    settings.raindrop_token = "tok"
    settings.sqs_briefing_queue_url = "https://sqs/briefing"
    settings.summarizer_aiml_min_score = 6
    settings.summarizer_world_min_score = 5
    settings.dynamodb_table_name = "table"
    settings.dynamodb_region = "us-east-1"
    settings.bedrock_region = "us-east-1"
    settings.bedrock_summarizer_model_id = "test-model"
    mock_settings_cls.return_value = settings

    mock_storage_cls.return_value.get_stories_content.return_value = {
        "h1": {
            "title": "LLM paper", "url": "https://arxiv.org/1",
            "content": "body", "bucket": "ai-ml", "sub_bucket": "research",
            "raindrop_id": 123, "feed_title": "arXiv"
        },
        "h2": {
            "title": "Another paper", "url": "https://arxiv.org/2",
            "content": "body", "bucket": "ai-ml", "sub_bucket": "research",
            "raindrop_id": 124, "feed_title": "arXiv"
        },
        "h3": {
            "title": "Third paper", "url": "https://arxiv.org/3",
            "content": "body", "bucket": "ai-ml", "sub_bucket": "research",
            "raindrop_id": 125, "feed_title": "arXiv"
        },
    }
    mock_summarizer_cls.return_value.summarize.return_value = MagicMock(
        summary="A great paper.", why_matters="Important.", score=8
    )

    from src.handlers.summarizer_handler import lambda_handler
    resp = lambda_handler(_sqs_event(hashes=["h1", "h2", "h3"]), {})

    assert resp["statusCode"] == 200
    assert resp["body"]["summarized"] == 3
    assert resp["body"]["sent_to_briefing"] == 3
    # Raindrop note should be updated
    assert mock_raindrop_cls.return_value.update_bookmark.call_count == 3


@patch("src.handlers.summarizer_handler.boto3")
@patch("src.handlers.summarizer_handler.RaindropClient")
@patch("src.handlers.summarizer_handler.BedrockSummarizerClient")
@patch("src.handlers.summarizer_handler.ProcessingStateStorage")
@patch("src.handlers.summarizer_handler.Settings")
def test_low_score_stories_not_sent_to_briefing(
    mock_settings_cls, mock_storage_cls, mock_summarizer_cls, mock_raindrop_cls, mock_boto3
):
    settings = MagicMock()
    settings.raindrop_token = "tok"
    settings.sqs_briefing_queue_url = "https://sqs/briefing"
    settings.summarizer_aiml_min_score = 6
    settings.dynamodb_table_name = "table"
    settings.dynamodb_region = "us-east-1"
    settings.bedrock_region = "us-east-1"
    settings.bedrock_summarizer_model_id = "test-model"
    mock_settings_cls.return_value = settings

    mock_storage_cls.return_value.get_stories_content.return_value = {
        "h1": {
            "title": "Minor update", "url": "https://example.com",
            "content": "body", "bucket": "ai-ml", "raindrop_id": 123, "feed_title": "Blog"
        },
    }
    mock_summarizer_cls.return_value.summarize.return_value = MagicMock(
        summary="Minor.", why_matters="Not much.", score=3
    )

    from src.handlers.summarizer_handler import lambda_handler
    resp = lambda_handler(_sqs_event(hashes=["h1"]), {})

    assert resp["body"]["sent_to_briefing"] == 0
    # Should NOT send SQS since < 3 stories passed threshold
    mock_boto3.client.return_value.send_message.assert_not_called()

import json
from unittest.mock import MagicMock, patch


def _sqs_event(briefing_type="ai-ml", stories=None):
    if stories is None:
        stories = [
            {"title": f"Story {i}", "url": f"https://example.com/{i}",
             "summary": "Summary.", "why_matters": "Important.", "score": 8,
             "sub_bucket": "research", "feed_title": "arXiv"}
            for i in range(5)
        ]
    body = json.dumps({
        "briefing_type": briefing_type,
        "run_date": "2026-02-16",
        "time_of_day": "morning",
        "stories": stories,
    })
    return {"Records": [{"body": body}]}


@patch("src.handlers.briefing_handler.RaindropClient")
@patch("src.handlers.briefing_handler.BedrockBriefingClient")
@patch("src.handlers.briefing_handler.Settings")
def test_creates_briefing_bookmark(mock_settings_cls, mock_briefing_cls, mock_raindrop_cls):
    settings = MagicMock()
    settings.raindrop_token = "tok"
    settings.raindrop_briefing_collection_id = 42
    settings.bedrock_region = "us-east-1"
    settings.bedrock_briefing_model_id = "model"
    mock_settings_cls.return_value = settings

    mock_briefing_cls.return_value.synthesize.return_value = "Full briefing text."
    mock_raindrop_cls.return_value.check_duplicate.return_value = False

    from src.handlers.briefing_handler import lambda_handler
    resp = lambda_handler(_sqs_event(), {})

    assert resp["statusCode"] == 200
    assert resp["body"]["briefing_sent"] == 1
    mock_raindrop_cls.return_value.create_bookmark.assert_called_once()

    call_kwargs = mock_raindrop_cls.return_value.create_bookmark.call_args
    # URL should contain newsblur.com/briefing/ and the briefing type
    url = call_kwargs.kwargs.get("url") or (call_kwargs.args[0] if call_kwargs.args else "")
    assert "newsblur.com/briefing/" in url
    assert "ai-ml" in url


@patch("src.handlers.briefing_handler.RaindropClient")
@patch("src.handlers.briefing_handler.BedrockBriefingClient")
@patch("src.handlers.briefing_handler.Settings")
def test_skips_duplicate_briefing(mock_settings_cls, mock_briefing_cls, mock_raindrop_cls):
    settings = MagicMock()
    settings.raindrop_token = "tok"
    settings.raindrop_briefing_collection_id = 42
    settings.bedrock_region = "us-east-1"
    settings.bedrock_briefing_model_id = "model"
    mock_settings_cls.return_value = settings

    mock_raindrop_cls.return_value.check_duplicate.return_value = True  # already exists

    from src.handlers.briefing_handler import lambda_handler
    resp = lambda_handler(_sqs_event(), {})

    assert resp["body"]["briefing_sent"] == 0
    mock_briefing_cls.return_value.synthesize.assert_not_called()

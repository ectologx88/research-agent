"""Tests for the v2 summarizer handler."""
import json
from unittest.mock import MagicMock, patch, call

import src.handlers.summarizer_handler as handler_mod
from src.services.editorial_scorer import ScoringResult


def _sqs_event(briefing_type="AI_ML", hashes=("h1",), briefing_date="2026-02-17-AM"):
    body = json.dumps({
        "briefing_type": briefing_type,
        "briefing_date": briefing_date,
        "story_hashes": list(hashes),
        "candidate_count": len(hashes),
    })
    return {"Records": [{"body": body}]}


def _default_settings():
    s = MagicMock()
    s.dry_run = "false"
    s.dynamodb_region = "us-east-1"
    s.dynamodb_story_staging_table = "story-staging"
    s.bedrock_region = "us-east-1"
    s.bedrock_summarizer_model_id = "test-model"
    s.raindrop_token = "tok"
    s.raindrop_aiml_collection_id = 11
    s.raindrop_world_collection_id = 22
    s.sqs_briefing_queue_url = "https://sqs/briefing"
    s.newsblur_username = "user"
    s.newsblur_password = "pass"
    return s


def _make_item(hash_id, status="pending", raindrop_id=100):
    return {
        "story_hash": hash_id,
        "briefing_type": "AI_ML",
        "title": f"Story {hash_id}",
        "url": f"https://example.com/{hash_id}",
        "content": "Story content.",
        "feed_name": "cs.AI updates on arXiv.org",
        "sub_bucket": "research",
        "boost_tags": [],
        "cluster_size": 0,
        "cluster_key": "",
        "context_block": "{}",
        "status": status,
        "raindrop_id": raindrop_id,
    }


def _pass_result():
    return ScoringResult(
        integrity=4, relevance=4, novelty=4, total=12,
        decision="PASS", source_type="journalism",
        reasoning="Good story.", summary="Summary sentence. Why it matters."
    )


def _reject_result():
    return ScoringResult(
        integrity=2, relevance=2, novelty=2, total=6,
        decision="REJECT", source_type="commentary",
        reasoning="Not relevant.", summary=None
    )


@patch("src.handlers.summarizer_handler.NewsBlurClient")
@patch("src.handlers.summarizer_handler.RaindropClient")
@patch("src.handlers.summarizer_handler.EditorialScorer")
@patch("src.handlers.summarizer_handler.StoryStaging")
@patch("src.handlers.summarizer_handler.boto3")
@patch("src.handlers.summarizer_handler.Settings")
def test_passes_stories_sent_to_briefing_queue(
    mock_settings_cls, mock_boto3, mock_staging_cls, mock_scorer_cls,
    mock_raindrop_cls, mock_nb_cls,
):
    mock_settings_cls.return_value = _default_settings()
    items = [_make_item(f"h{i}") for i in range(3)]
    mock_staging_cls.return_value.batch_get_stories.return_value = items
    mock_scorer_cls.return_value.score.return_value = _pass_result()
    mock_raindrop_cls.return_value.update_bookmark.return_value = {}

    resp = handler_mod.lambda_handler(_sqs_event(hashes=["h0", "h1", "h2"]), {})

    assert resp["statusCode"] == 200
    assert resp["body"]["passed"] == 3
    assert resp["body"]["sent_to_briefing"] == 3
    sqs_mock = mock_boto3.client.return_value
    assert sqs_mock.send_message.called
    body = json.loads(sqs_mock.send_message.call_args[1]["MessageBody"])
    assert body["briefing_type"] == "AI_ML"
    assert body["briefing_date"] == "2026-02-17-AM"
    assert "stories" in body
    assert "candidate_count" in body


@patch("src.handlers.summarizer_handler.NewsBlurClient")
@patch("src.handlers.summarizer_handler.RaindropClient")
@patch("src.handlers.summarizer_handler.EditorialScorer")
@patch("src.handlers.summarizer_handler.StoryStaging")
@patch("src.handlers.summarizer_handler.boto3")
@patch("src.handlers.summarizer_handler.Settings")
def test_fewer_than_3_pass_sends_thin_briefing(
    mock_settings_cls, mock_boto3, mock_staging_cls, mock_scorer_cls,
    mock_raindrop_cls, mock_nb_cls,
):
    """Fewer than 3 passing stories should still produce a briefing (thin_briefing path)."""
    mock_settings_cls.return_value = _default_settings()
    # 5 stories, only h0 and h2 pass (2 total — thin briefing)
    items = [_make_item(f"h{i}") for i in range(5)]
    mock_staging_cls.return_value.batch_get_stories.return_value = items

    def _score(**kwargs):
        return _pass_result() if kwargs["title"] in ("Story h0", "Story h2") else _reject_result()

    mock_scorer_cls.return_value.score.side_effect = _score

    resp = handler_mod.lambda_handler(_sqs_event(hashes=[f"h{i}" for i in range(5)]), {})

    assert resp["body"]["passed"] == 2
    assert resp["body"]["sent_to_briefing"] == 2  # always send if any pass
    mock_boto3.client.return_value.send_message.assert_called_once()


@patch("src.handlers.summarizer_handler.NewsBlurClient")
@patch("src.handlers.summarizer_handler.RaindropClient")
@patch("src.handlers.summarizer_handler.EditorialScorer")
@patch("src.handlers.summarizer_handler.StoryStaging")
@patch("src.handlers.summarizer_handler.boto3")
@patch("src.handlers.summarizer_handler.Settings")
def test_idempotency_skips_already_summarized(
    mock_settings_cls, mock_boto3, mock_staging_cls, mock_scorer_cls,
    mock_raindrop_cls, mock_nb_cls,
):
    mock_settings_cls.return_value = _default_settings()
    items = [
        _make_item("h1", status="summarized"),
        _make_item("h2", status="pending"),
    ]
    mock_staging_cls.return_value.batch_get_stories.return_value = items
    mock_scorer_cls.return_value.score.return_value = _pass_result()
    mock_raindrop_cls.return_value.update_bookmark.return_value = {}

    handler_mod.lambda_handler(_sqs_event(hashes=["h1", "h2"]), {})

    # scorer.score called once (only h2 is pending)
    assert mock_scorer_cls.return_value.score.call_count == 1


@patch("src.handlers.summarizer_handler.NewsBlurClient")
@patch("src.handlers.summarizer_handler.RaindropClient")
@patch("src.handlers.summarizer_handler.EditorialScorer")
@patch("src.handlers.summarizer_handler.StoryStaging")
@patch("src.handlers.summarizer_handler.boto3")
@patch("src.handlers.summarizer_handler.Settings")
def test_dry_run_true_uses_mock_scorer_no_writes(
    mock_settings_cls, mock_boto3, mock_staging_cls, mock_scorer_cls,
    mock_raindrop_cls, mock_nb_cls,
):
    settings = _default_settings()
    settings.dry_run = "true"
    mock_settings_cls.return_value = settings
    items = [_make_item("h1")]
    mock_staging_cls.return_value.batch_get_stories.return_value = items
    mock_scorer_cls.return_value.score.return_value = _pass_result()

    resp = handler_mod.lambda_handler(_sqs_event(hashes=["h1"]), {})

    assert resp["body"]["dry_run"] == "true"
    # EditorialScorer constructed with dry_run=True
    init_kwargs = mock_scorer_cls.call_args[1]
    assert init_kwargs.get("dry_run") is True
    # No DDB writes
    mock_staging_cls.return_value.update_status.assert_not_called()
    # No SQS
    mock_boto3.client.return_value.send_message.assert_not_called()
    # Raindrop not created
    mock_raindrop_cls.assert_not_called()
    # NewsBlur not called in dry_run
    mock_nb_cls.assert_not_called()


@patch("src.handlers.summarizer_handler.NewsBlurClient")
@patch("src.handlers.summarizer_handler.RaindropClient")
@patch("src.handlers.summarizer_handler.EditorialScorer")
@patch("src.handlers.summarizer_handler.StoryStaging")
@patch("src.handlers.summarizer_handler.boto3")
@patch("src.handlers.summarizer_handler.Settings")
def test_raindrop_update_called_for_passing_stories(
    mock_settings_cls, mock_boto3, mock_staging_cls, mock_scorer_cls,
    mock_raindrop_cls, mock_nb_cls,
):
    mock_settings_cls.return_value = _default_settings()
    items = [_make_item(f"h{i}", raindrop_id=100 + i) for i in range(3)]
    mock_staging_cls.return_value.batch_get_stories.return_value = items
    mock_scorer_cls.return_value.score.return_value = _pass_result()
    mock_raindrop_cls.return_value.update_bookmark.return_value = {}

    handler_mod.lambda_handler(_sqs_event(hashes=["h0", "h1", "h2"]), {})

    assert mock_raindrop_cls.return_value.update_bookmark.call_count == 3

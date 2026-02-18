from unittest.mock import MagicMock
import pytest
from shared.dynamodb_client import StoryStaging, SignalTracker, BriefingArchive


class TestStoryStaging:
    def _client(self):
        table = MagicMock()
        return StoryStaging(table), table

    def test_store_story_puts_item(self):
        client, table = self._client()
        client.store_story({
            "story_hash": "abc123",
            "briefing_type": "AI_ML",
            "title": "Test",
            "url": "https://example.com",
            "content": "body",
            "feed_name": "cs.AI updates on arXiv.org",
            "sub_bucket": "research",
            "boost_tags": [],
            "cluster_size": 0,
            "cluster_key": "",
            "context_block": "{}",
            "raindrop_id": None,
        })
        table.put_item.assert_called_once()
        item = table.put_item.call_args[1]["Item"]
        assert item["story_hash"] == "abc123"
        assert item["status"] == "pending"
        assert "ttl" in item  # 24h TTL set

    def test_update_status_summarized(self):
        client, table = self._client()
        client.update_status(
            "abc123", "AI_ML", "summarized",
            summary="Two sentences.", source_type="journalism",
            scores={"integrity": 4, "relevance": 4, "novelty": 3, "total": 11},
            reasoning="Strong primary source reporting.",
        )
        table.update_item.assert_called_once()

    def test_get_story_returns_item(self):
        client, table = self._client()
        table.get_item.return_value = {"Item": {"story_hash": "abc123", "status": "pending"}}
        result = client.get_story("abc123", "AI_ML")
        assert result["story_hash"] == "abc123"

    def test_get_story_returns_none_when_missing(self):
        client, table = self._client()
        table.get_item.return_value = {}
        result = client.get_story("missing", "AI_ML")
        assert result is None

    def test_check_duplicate_true(self):
        client, table = self._client()
        table.get_item.return_value = {"Item": {"story_hash": "abc", "status": "pending"}}
        assert client.check_duplicate("abc", "AI_ML") is True

    def test_check_duplicate_false(self):
        client, table = self._client()
        table.get_item.return_value = {}
        assert client.check_duplicate("missing", "AI_ML") is False

    def test_batch_get_stories_skips_missing(self):
        client, table = self._client()
        def get_item_side_effect(Key):
            if Key["story_hash"] == "found":
                return {"Item": {"story_hash": "found"}}
            return {}
        table.get_item.side_effect = get_item_side_effect
        result = client.batch_get_stories(["found", "missing"], "AI_ML")
        assert len(result) == 1
        assert result[0]["story_hash"] == "found"

    def test_update_status_expression_content(self):
        client, table = self._client()
        client.update_status("h1", "AI_ML", "summarized", summary="text")
        call_kwargs = table.update_item.call_args[1]
        assert "summary" in call_kwargs["UpdateExpression"]
        assert ":f_summary" in call_kwargs["ExpressionAttributeValues"]
        assert call_kwargs["ExpressionAttributeValues"][":status"] == "summarized"

    def test_update_status_rejects_invalid_field_names(self):
        client, table = self._client()
        with pytest.raises(ValueError, match="valid DynamoDB"):
            client.update_status("h1", "AI_ML", "summarized", **{"bad-field": "value"})


class TestSignalTracker:
    def _client(self):
        table = MagicMock()
        return SignalTracker(table), table

    def test_upsert_increments_count(self):
        client, table = self._client()
        table.get_item.return_value = {
            "Item": {
                "signal_key": "evaluation-crisis",
                "mention_count": 2,
                "first_seen": "2026-02-16T11:00:00+00:00",
                "last_seen": "2026-02-16T23:00:00+00:00",
                "example_stories": ["h1", "h2"],
            }
        }
        client.upsert("evaluation-crisis", "newstory123")
        # With the atomic update_item approach, put_item is no longer called
        table.put_item.assert_not_called()
        # update_item should be called (at least once for the atomic count increment)
        assert table.update_item.call_count >= 1

    def test_upsert_creates_new_signal(self):
        client, table = self._client()
        table.get_item.return_value = {}
        client.upsert("new-signal", "story456")
        # With atomic approach: update_item for count, then update_item for example_stories
        assert table.update_item.call_count >= 1
        table.put_item.assert_not_called()

    def test_get_signals_queries_specific_keys(self):
        client, table = self._client()
        table.get_item.return_value = {"Item": {"signal_key": "k1", "mention_count": 3}}
        result = client.get_signals(["k1"])
        assert len(result) == 1
        # Must NOT use scan
        table.scan.assert_not_called()

    def test_upsert_deduplicates_story_hash(self):
        client, table = self._client()
        # Signal already has story_hash in example_stories
        table.get_item.return_value = {
            "Item": {
                "signal_key": "test-signal",
                "mention_count": 1,
                "first_seen": "2026-02-16T11:00:00+00:00",
                "last_seen": "2026-02-16T11:00:00+00:00",
                "example_stories": ["existing-hash"],
                "ttl": 9999999,
            }
        }
        client.upsert("test-signal", "existing-hash")
        # update_item should be called for the count (atomic) + check if stories need updating
        # but story list update should NOT add duplicate
        # Find the stories update call if any
        calls = [c for c in table.update_item.call_args_list
                  if "example_stories" in str(c)]
        # No stories update needed — hash already present
        assert all(":stories" not in str(c) for c in calls)


class TestBriefingArchive:
    def _client(self):
        table = MagicMock()
        return BriefingArchive(table), table

    def test_store_briefing(self):
        client, table = self._client()
        client.store_briefing(
            briefing_date="2026-02-17-AM",
            briefing_type="AI_ML",
            content="# The AI Abstract\n...",
            candidate_count=18,
            passed_count=12,
            story_count=8,
            raindrop_id="rd123",
        )
        item = table.put_item.call_args[1]["Item"]
        assert item["briefing_date"] == "2026-02-17-AM"
        assert item["candidate_count"] == 18
        assert "ttl" in item  # 30-day TTL

    def test_get_prior_returns_none_when_missing(self):
        client, table = self._client()
        table.get_item.return_value = {}
        result = client.get_prior("2026-02-17-AM", "AI_ML")
        assert result is None

    def test_get_prior_returns_item_when_exists(self):
        client, table = self._client()
        table.get_item.return_value = {
            "Item": {"briefing_date": "2026-02-16-PM", "briefing_type": "AI_ML", "content": "..."}
        }
        result = client.get_prior("2026-02-16-PM", "AI_ML")
        assert result is not None
        assert result["briefing_date"] == "2026-02-16-PM"

"""Tests for the ProcessingStateStorage deduplication layer."""

import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.services.storage import ProcessingStateStorage, TTL_DAYS


@pytest.fixture
def mock_table():
    return MagicMock()


@pytest.fixture
def mock_dynamo(mock_table):
    dynamo = MagicMock()
    dynamo.Table.return_value = mock_table
    return dynamo


@pytest.fixture
def storage(mock_dynamo, mock_table):
    with patch("src.services.storage.boto3") as mock_boto:
        mock_boto.resource.return_value = mock_dynamo
        s = ProcessingStateStorage("test-table", region="us-east-1")
    # Point internal refs at our mocks
    s._dynamo = mock_dynamo
    s._table = mock_table
    # Mock the client for batch_get_item
    mock_client = MagicMock()
    mock_dynamo.meta.client = mock_client
    return s


class TestLastRunTimestamp:
    def test_returns_none_when_no_config(self, storage, mock_table):
        mock_table.get_item.return_value = {}
        assert storage.get_last_run_timestamp() is None

    def test_returns_none_when_missing_value(self, storage, mock_table):
        mock_table.get_item.return_value = {"Item": {"record_type": "config"}}
        assert storage.get_last_run_timestamp() is None

    def test_returns_datetime_when_present(self, storage, mock_table):
        ts = "2026-02-12T10:30:00+00:00"
        mock_table.get_item.return_value = {"Item": {"value": ts}}
        result = storage.get_last_run_timestamp()
        assert result is not None
        assert result.year == 2026
        assert result.month == 2

    def test_update_stores_iso_string(self, storage, mock_table):
        ts = datetime(2026, 2, 12, 10, 0, tzinfo=timezone.utc)
        assert storage.update_last_run_timestamp(ts) is True
        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args[1]["Item"]
        assert item["record_type"] == "config"
        assert item["identifier"] == "last_run_timestamp"
        assert item["value"] == ts.isoformat()

    def test_update_returns_false_on_error(self, storage, mock_table):
        mock_table.put_item.side_effect = Exception("DynamoDB down")
        assert storage.update_last_run_timestamp(datetime.now(timezone.utc)) is False


class TestAlreadyProcessed:
    def test_returns_true_when_item_exists(self, storage, mock_table):
        mock_table.get_item.return_value = {"Item": {"identifier": "hash1"}}
        assert storage.already_processed("hash1") is True

    def test_returns_false_when_missing(self, storage, mock_table):
        mock_table.get_item.return_value = {}
        assert storage.already_processed("hash1") is False


class TestBatchCheckProcessed:
    def test_returns_matching_hashes(self, storage, mock_dynamo):
        mock_client = mock_dynamo.meta.client
        mock_client.batch_get_item.return_value = {
            "Responses": {
                "test-table": [
                    {"identifier": {"S": "hash1"}},
                    {"identifier": {"S": "hash3"}},
                ]
            }
        }
        result = storage.batch_check_processed(["hash1", "hash2", "hash3"])
        assert result == {"hash1", "hash3"}

    def test_returns_empty_set_for_empty_input(self, storage):
        assert storage.batch_check_processed([]) == set()

    def test_chunks_large_batches(self, storage, mock_dynamo):
        mock_client = mock_dynamo.meta.client
        mock_client.batch_get_item.return_value = {"Responses": {"test-table": []}}
        hashes = [f"hash{i}" for i in range(250)]
        storage.batch_check_processed(hashes)
        # 250 hashes / 100 per chunk = 3 calls
        assert mock_client.batch_get_item.call_count == 3

    def test_handles_unprocessed_keys_with_backoff(self, storage, mock_dynamo):
        mock_client = mock_dynamo.meta.client
        # First call returns one item and unprocessed keys, second call completes
        with patch("src.services.storage.time.sleep") as mock_sleep:
            mock_client.batch_get_item.side_effect = [
                {
                    "Responses": {
                        "test-table": [{"identifier": {"S": "hash1"}}]
                    },
                    "UnprocessedKeys": {
                        "test-table": {
                            "Keys": [{"record_type": {"S": "story"}, "identifier": {"S": "hash2"}}]
                        }
                    }
                },
                {
                    "Responses": {
                        "test-table": [{"identifier": {"S": "hash2"}}]
                    }
                }
            ]
            result = storage.batch_check_processed(["hash1", "hash2"])
            assert result == {"hash1", "hash2"}
            assert mock_client.batch_get_item.call_count == 2
            # Verify sleep was called with initial backoff of 0.1s
            mock_sleep.assert_called_once_with(0.1)

    def test_stops_after_max_retries(self, storage, mock_dynamo):
        mock_client = mock_dynamo.meta.client
        # Always return unprocessed keys to trigger max retry limit
        with patch("src.services.storage.time.sleep"):
            mock_client.batch_get_item.return_value = {
                "Responses": {"test-table": []},
                "UnprocessedKeys": {
                    "test-table": {
                        "Keys": [{"record_type": {"S": "story"}, "identifier": {"S": "hash1"}}]
                    }
                }
            }
            result = storage.batch_check_processed(["hash1"])
            # Should return empty set after max retries (11 total calls: 1 initial + 10 retries)
            assert result == set()
            assert mock_client.batch_get_item.call_count == 11


class TestMarkProcessed:
    def test_stores_minimal_record_with_ttl(self, storage, mock_table):
        # Freeze time to avoid flakiness
        fixed_time = 1000000000
        with patch("src.services.storage.time.time", return_value=fixed_time):
            assert storage.mark_processed("hash1", 9) is True

        mock_table.put_item.assert_called_once()
        item = mock_table.put_item.call_args[1]["Item"]

        assert item["record_type"] == "story"
        assert item["identifier"] == "hash1"
        assert item["overall_score"] == 9
        assert "processed_at" in item

        # TTL should be exactly 3 days from frozen time
        expected_ttl = fixed_time + (TTL_DAYS * 86400)
        assert item["ttl"] == expected_ttl

    def test_returns_false_on_error(self, storage, mock_table):
        mock_table.put_item.side_effect = Exception("write failed")
        assert storage.mark_processed("hash1", 5) is False

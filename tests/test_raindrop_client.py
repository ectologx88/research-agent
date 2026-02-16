"""Tests for the Raindrop API client."""
from unittest.mock import MagicMock, patch

import pytest
import requests

from src.clients.raindrop import RaindropClient, RaindropAuthError


class TestCheckDuplicate:
    def _client(self):
        return RaindropClient(token="tok", collection_id=-1)

    def test_returns_true_when_url_found(self):
        client = self._client()
        with patch.object(client, "_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"result": True, "count": 1, "items": [{"link": "https://example.com/story"}]}
            mock_resp.raise_for_status = MagicMock()
            mock_session.get.return_value = mock_resp

            assert client.check_duplicate("https://example.com/story") is True

    def test_returns_false_when_url_not_found(self):
        client = self._client()
        with patch.object(client, "_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"result": True, "count": 0, "items": []}
            mock_resp.raise_for_status = MagicMock()
            mock_session.get.return_value = mock_resp

            assert client.check_duplicate("https://example.com/new") is False

    def test_returns_false_on_empty_url(self):
        client = self._client()
        assert client.check_duplicate("") is False

    def test_raises_auth_error_on_401(self):
        client = self._client()
        with patch.object(client, "_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
                response=mock_resp
            )
            mock_session.get.return_value = mock_resp

            with pytest.raises(RaindropAuthError):
                client.check_duplicate("https://example.com/story")


class TestCreateBookmark:
    def _client(self):
        return RaindropClient(token="tok", collection_id=99)

    def test_sends_correct_payload(self):
        client = self._client()
        with patch.object(client, "_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_resp.json.return_value = {"result": True, "item": {"_id": 123}}
            mock_resp.raise_for_status = MagicMock()
            mock_session.post.return_value = mock_resp

            result = client.create_bookmark(
                url="https://example.com/story",
                title="Test Story",
                tags=["ai", "research"],
                note="This matters because of X.",
            )

            call_kwargs = mock_session.post.call_args
            payload = call_kwargs[1]["json"]
            assert payload["link"] == "https://example.com/story"
            assert payload["title"] == "Test Story"
            assert payload["tags"] == ["ai", "research"]
            assert payload["note"] == "This matters because of X."
            assert payload["collection"]["$id"] == 99
            assert result["_id"] == 123

    def test_raises_auth_error_on_401(self):
        client = self._client()
        with patch.object(client, "_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
                response=mock_resp
            )
            mock_session.post.return_value = mock_resp

            with pytest.raises(RaindropAuthError):
                client.create_bookmark("https://x.com", "T", [], "note")

    def test_retries_on_5xx_then_succeeds(self):
        client = self._client()
        with patch.object(client, "_session") as mock_session:
            fail_resp = MagicMock()
            fail_resp.status_code = 503
            fail_resp.raise_for_status.side_effect = requests.exceptions.HTTPError(
                response=fail_resp
            )
            ok_resp = MagicMock()
            ok_resp.status_code = 200
            ok_resp.json.return_value = {"result": True, "item": {"_id": 42}}
            ok_resp.raise_for_status = MagicMock()
            mock_session.post.side_effect = [fail_resp, ok_resp]

            with patch("tenacity.nap.time") as mock_time:
                mock_time.sleep = MagicMock()
                result = client.create_bookmark("https://x.com", "T", [], "note")

            assert mock_session.post.call_count == 2
            assert result["_id"] == 42

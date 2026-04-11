"""Tests for the NewsBlur API client."""

import json
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.clients.newsblur import NewsBlurClient, NewsBlurAuthError


class TestAuthentication:
    def test_successful_login(self):
        client = NewsBlurClient("user", "pass")
        with patch.object(client, "_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {"authenticated": True, "code": 1}
            mock_session.post.return_value = mock_resp

            assert client.authenticate() is True
            mock_session.post.assert_called_once()

    def test_failed_login_raises(self):
        client = NewsBlurClient("user", "wrong")
        with patch.object(client, "_session") as mock_session:
            mock_resp = MagicMock()
            mock_resp.json.return_value = {
                "authenticated": False,
                "code": -1,
                "errors": ["Invalid password"],
            }
            mock_session.post.return_value = mock_resp

            with pytest.raises(NewsBlurAuthError, match="Login failed"):
                client.authenticate()


class TestScoreComputation:
    @pytest.mark.parametrize(
        "intel,expected",
        [
            ({"feed": 1, "title": 0, "author": 0, "tags": 0}, 1),
            ({"feed": 0, "title": 0, "author": 0, "tags": 0}, 0),
            ({"feed": -1, "title": 0, "author": 0, "tags": 0}, -1),
            ({"feed": 1, "title": -1, "author": 0, "tags": 0}, 1),  # positive wins
            ({}, 0),
        ],
    )
    def test_compute_score(self, intel, expected):
        assert NewsBlurClient._compute_score(intel) == expected


class TestDateParsing:
    @pytest.mark.parametrize(
        "raw,expected_year",
        [
            ("2026-02-12 09:30:00", 2026),
            ("2026-02-12T09:30:00", 2026),
            ("2026-02-12T09:30:00Z", 2026),
        ],
    )
    def test_valid_formats(self, raw, expected_year):
        dt = NewsBlurClient._parse_date(raw)
        assert dt is not None
        assert dt.year == expected_year
        assert dt.tzinfo == timezone.utc

    def test_invalid_format_returns_none(self):
        assert NewsBlurClient._parse_date("not-a-date") is None


class TestFetchStories:
    def test_parses_stories_from_api_response(self, sample_stories_raw):
        client = NewsBlurClient("user", "pass")
        client._authenticated = True

        with patch.object(client, "_get") as mock_get:
            # First page: all stories. Second page: empty (stops pagination).
            mock_get.side_effect = [
                {"stories": sample_stories_raw},
                {"stories": []},
            ]

            stories = client.fetch_unread_stories(hours_back=2400, max_results=50)
            assert len(stories) == len(sample_stories_raw)
            assert stories[0].story_hash == "abc123:feed1"
            assert stories[0].newsblur_score == 1

    def test_respects_max_results(self, sample_stories_raw):
        client = NewsBlurClient("user", "pass")
        client._authenticated = True

        with patch.object(client, "_get") as mock_get:
            mock_get.return_value = {"stories": sample_stories_raw}
            stories = client.fetch_unread_stories(hours_back=2400, max_results=2)
            assert len(stories) == 2

    def test_filters_by_min_score(self, sample_stories_raw):
        client = NewsBlurClient("user", "pass")
        client._authenticated = True

        with patch.object(client, "_get") as mock_get:
            mock_get.side_effect = [
                {"stories": sample_stories_raw},
                {"stories": []},
            ]
            # min_score=1 should exclude the neutral story (ghi789)
            stories = client.fetch_unread_stories(
                hours_back=2400, min_score=1, max_results=50
            )
            hashes = {s.story_hash for s in stories}
            assert "ghi789:feed3" not in hashes

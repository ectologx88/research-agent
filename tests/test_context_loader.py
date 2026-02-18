from unittest.mock import patch, MagicMock
from src.services.context_loader import ContextLoader


class TestGetWeather:
    def test_returns_weather_dict_on_success(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "current": {
                "temperature_2m": 72.5,
                "weather_code": 1,
                "wind_speed_10m": 8.2,
            },
            "daily": {
                "temperature_2m_max": [81.0],
                "temperature_2m_min": [65.0],
                "precipitation_sum": [0.0],
            }
        }
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.get", return_value=mock_resp):
            loader = ContextLoader()
            result = loader.get_weather()
        assert result["temp_f"] == 72.5
        assert result["high_f"] == 81.0
        assert result["low_f"] == 65.0
        assert result["wind_mph"] == 8.2
        assert result["precip_in"] == 0.0

    def test_returns_none_on_timeout(self):
        import requests
        with patch("requests.get", side_effect=requests.exceptions.Timeout):
            loader = ContextLoader()
            result = loader.get_weather()
        assert result is None


class TestGetSpaceCityHeadlines:
    def test_returns_top_two_headlines(self):
        mock_feed = MagicMock()
        mock_feed.entries = [
            MagicMock(title="Tropical storm forms in Gulf"),
            MagicMock(title="Houston temps drop this weekend"),
            MagicMock(title="Third story should be ignored"),
        ]
        with patch("feedparser.parse", return_value=mock_feed):
            loader = ContextLoader()
            result = loader.get_space_city_headlines()
        assert len(result) == 2
        assert result[0] == "Tropical storm forms in Gulf"

    def test_returns_empty_on_parse_failure(self):
        with patch("feedparser.parse", side_effect=Exception("network error")):
            loader = ContextLoader()
            result = loader.get_space_city_headlines()
        assert result == []


class TestGetNwsAlerts:
    def test_returns_alert_headlines(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "features": [
                {"properties": {"headline": "Tornado Warning issued for Harris County"}},
                {"properties": {"headline": "Flash Flood Watch in effect"}},
            ]
        }
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.get", return_value=mock_resp):
            loader = ContextLoader()
            result = loader.get_nws_alerts()
        assert len(result) == 2
        assert "Tornado Warning" in result[0]

    def test_missing_features_key_returns_empty(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"type": "FeatureCollection"}  # no "features"
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.get", return_value=mock_resp):
            loader = ContextLoader()
            result = loader.get_nws_alerts()
        assert result == []

    def test_non_list_features_returns_empty(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"features": "malformed"}
        mock_resp.raise_for_status = MagicMock()
        with patch("requests.get", return_value=mock_resp):
            loader = ContextLoader()
            result = loader.get_nws_alerts()
        assert result == []

    def test_returns_empty_on_http_error(self):
        import requests
        with patch("requests.get", side_effect=requests.exceptions.RequestException):
            loader = ContextLoader()
            result = loader.get_nws_alerts()
        assert result == []


class TestFetchAll:
    def test_returns_full_context_block(self):
        loader = ContextLoader()
        with patch.object(loader, "get_weather", return_value={"temp_f": 72.0, "high_f": 80.0,
                          "low_f": 65.0, "wind_mph": 5.0, "precip_in": 0.0}), \
             patch.object(loader, "get_space_city_headlines", return_value=["Storm watch"]), \
             patch.object(loader, "get_nws_alerts", return_value=[]):
            result = loader.fetch_all()
        assert "fetched_at" in result
        assert result["weather"]["temp_f"] == 72.0
        assert result["nws_alerts"] == []

    def test_partial_failure_still_returns(self):
        loader = ContextLoader()
        with patch.object(loader, "get_weather", return_value=None), \
             patch.object(loader, "get_space_city_headlines", return_value=[]), \
             patch.object(loader, "get_nws_alerts", return_value=[]):
            result = loader.fetch_all()
        assert result["weather"] is None


class TestFormatContextBlock:
    def test_formats_with_no_alerts(self):
        loader = ContextLoader()
        data = {
            "fetched_at": "2026-02-17T11:00:00+00:00",
            "weather": {"temp_f": 72.0, "condition": "Partly cloudy",
                        "high_f": 80.0, "low_f": 65.0, "wind_mph": 5.0, "precip_in": 0.1},
            "local_headlines": ["Storm watch issued for Houston"],
            "nws_alerts": [],
        }
        block = loader.format_context_block(data)
        assert "[SYSTEM_CONTEXT_BLOCK" in block
        assert "72.0°F" in block
        assert "ACTIVE ALERTS" not in block
        assert "0.1 in. expected" in block

    def test_formats_with_alerts(self):
        loader = ContextLoader()
        data = {
            "fetched_at": "2026-02-17T11:00:00+00:00",
            "weather": {"temp_f": 68.0, "condition": "Stormy",
                        "high_f": 70.0, "low_f": 60.0, "wind_mph": 35.0, "precip_in": 2.0},
            "local_headlines": [],
            "nws_alerts": ["Tornado Warning for Harris County"],
        }
        block = loader.format_context_block(data)
        assert "⚠️ ACTIVE ALERTS" in block
        assert "Tornado Warning" in block

    def test_alerts_shown_when_weather_none(self):
        loader = ContextLoader()
        data = {
            "fetched_at": "2026-02-17T11:00:00+00:00",
            "weather": None,
            "local_headlines": [],
            "nws_alerts": ["Tornado Warning for Harris County"],
        }
        block = loader.format_context_block(data)
        assert "⚠️ ACTIVE ALERTS" in block
        assert "Tornado Warning" in block

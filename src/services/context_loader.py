# src/services/context_loader.py
"""Weather + local news context fetcher for the Zeitgeist briefing.

All data is fetched deterministically (no LLM). The result is stored in
story_staging DDB by Lambda 1 at triage time. Lambda 3 reads it — the
fetched_at timestamp reflects Lambda 1's fetch time, never Lambda 3's.

This module is best-effort: any single source failure is logged and skipped.
Lambda 1 does not fail because weather is down.
"""
from datetime import datetime, timezone
from typing import Any, Optional

import feedparser
import requests

from shared.logger import log

PASADENA_LAT = 29.6911
PASADENA_LON = -95.2091
SPACE_CITY_WEATHER_RSS = "https://spacecityweather.com/feed/"
NWS_ALERTS_URL = "https://api.weather.gov/alerts/active?zone=TXZ163"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


class ContextLoader:
    """Fetches weather + local news context for the Zeitgeist briefing."""

    def get_weather(self) -> Optional[dict[str, Any]]:
        """Fetch current conditions from Open-Meteo (free, no API key)."""
        params = {
            "latitude": PASADENA_LAT,
            "longitude": PASADENA_LON,
            "current": "temperature_2m,weather_code,wind_speed_10m",
            "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum",
            "temperature_unit": "fahrenheit",
            "wind_speed_unit": "mph",
            "timezone": "America/Chicago",
            "forecast_days": 1,
        }
        try:
            resp = requests.get(OPEN_METEO_URL, params=params, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            current = data["current"]
            daily = data["daily"]
            return {
                "temp_f": current["temperature_2m"],
                "condition": _weather_code_to_str(current["weather_code"]),
                "high_f": daily["temperature_2m_max"][0],
                "low_f": daily["temperature_2m_min"][0],
                "wind_mph": current["wind_speed_10m"],
                "precip_in": daily["precipitation_sum"][0],
            }
        except Exception as exc:
            log("WARNING", "context_loader.get_weather failed", error=str(exc))
            return None

    def get_space_city_headlines(self) -> list[str]:
        """Parse Space City Weather RSS for top 1-2 headlines.

        NOTE: feedparser 6.x API — use feed.entries (list), not feed.items().
        """
        try:
            feed = feedparser.parse(SPACE_CITY_WEATHER_RSS)
            return [e.title for e in feed.entries[:2]]
        except Exception as exc:
            log("WARNING", "context_loader.space_city_weather failed", error=str(exc))
            return []

    def get_nws_alerts(self) -> list[str]:
        """Fetch active NWS alerts for Harris County (TXZ163).

        Guards against malformed response: if 'features' key missing or not a list,
        returns empty and logs WARNING — does not raise.
        """
        try:
            resp = requests.get(NWS_ALERTS_URL, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features")
            if not isinstance(features, list):
                log("WARNING", "context_loader.nws_alerts unexpected schema",
                    features_type=type(features).__name__)
                return []
            return [
                f["properties"]["headline"]
                for f in features
                if f.get("properties", {}).get("headline")
            ]
        except Exception as exc:
            log("WARNING", "context_loader.get_nws_alerts failed", error=str(exc))
            return []

    def fetch_all(self) -> dict[str, Any]:
        """Fetch all context sources. Returns partial result on failure."""
        return {
            "weather": self.get_weather(),
            "local_headlines": self.get_space_city_headlines(),
            "nws_alerts": self.get_nws_alerts(),
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }

    def format_context_block(self, data: dict[str, Any]) -> str:
        """Format context data for injection into the Zeitgeist prompt."""
        w = data.get("weather") or {}
        alerts = data.get("nws_alerts") or []
        headlines = data.get("local_headlines") or []

        weather_block = ""
        if w:
            weather_block = (
                f"WEATHER:\n"
                f"Current: {w.get('temp_f')}°F, {w.get('condition')}\n"
                f"Today: High {w.get('high_f')}°F / Low {w.get('low_f')}°F"
                f" | Wind: {w.get('wind_mph')} mph\n"
                f"Precipitation: {w.get('precip_in')} in. expected"
            )

        local_block = ""
        if headlines:
            local_block = "LOCAL:\n" + "\n".join(f"- {h}" for h in headlines)

        alert_section = ""
        if alerts:
            alert_section = f"\n⚠️ ACTIVE ALERTS: {', '.join(alerts)}"

        return (
            f"[SYSTEM_CONTEXT_BLOCK — Deterministic Data, Do Not Contradict]\n"
            f"Location: Pasadena, TX (Houston metro) | {data.get('fetched_at')} UTC\n\n"
            f"{weather_block}\n\n"
            f"{local_block}"
            f"{alert_section}\n"
            f"[END SYSTEM_CONTEXT_BLOCK]"
        )


# WMO weather code → human-readable string (subset)
_WMO_CODES = {
    0: "Clear sky", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast",
    45: "Foggy", 48: "Icy fog",
    51: "Light drizzle", 53: "Moderate drizzle", 55: "Dense drizzle",
    61: "Slight rain", 63: "Moderate rain", 65: "Heavy rain",
    71: "Slight snow", 73: "Moderate snow", 75: "Heavy snow",
    80: "Slight showers", 81: "Moderate showers", 82: "Violent showers",
    95: "Thunderstorm", 96: "Thunderstorm with hail", 99: "Heavy thunderstorm with hail",
}


def _weather_code_to_str(code: int) -> str:
    return _WMO_CODES.get(code, f"Code {code}")

"""Raindrop.io API client with bookmark creation and duplicate detection."""

from typing import List

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.utils import log_structured


class RaindropError(Exception):
    """Base exception for Raindrop client errors."""


class RaindropAuthError(RaindropError):
    """Authentication failed (401)."""


class RaindropClient:
    """Client for the Raindrop.io REST API v1."""

    BASE_URL = "https://api.raindrop.io/rest/v1"

    def __init__(self, token: str, collection_id: int = -1, base_url: str | None = None):
        self._collection_id = collection_id
        self._base = (base_url or self.BASE_URL).rstrip("/")
        self._session = requests.Session()
        self._session.headers.update({"Authorization": f"Bearer {token}"})

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type(requests.exceptions.RequestException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,
    )
    def check_duplicate(self, url: str) -> bool:
        """Return True if *url* already exists in the target collection."""
        if not url:
            return False
        resp = self._session.get(
            f"{self._base}/raindrops/{self._collection_id}",
            params={"search": f"link:{url}", "perpage": 1},
            timeout=15,
        )
        if resp.status_code == 401:
            raise RaindropAuthError("Raindrop token invalid or expired (401)")
        resp.raise_for_status()
        data = resp.json()
        return data.get("count", 0) > 0

    # ------------------------------------------------------------------
    # Bookmark creation
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type(requests.exceptions.RequestException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,
    )
    def create_bookmark(
        self,
        url: str,
        title: str,
        tags: List[str],
        note: str,
    ) -> dict:
        """Create a bookmark in Raindrop. Returns the created item dict.

        Raises:
            RaindropAuthError: On 401 (credentials invalid — do not retry).
            RaindropError: On persistent failure after retries.
        """
        url = str(url)
        payload = {
            "link": url,
            "title": title,
            "tags": tags,
            "note": note,
            "collection": {"$id": self._collection_id},
        }
        resp = self._session.post(
            f"{self._base}/raindrop",
            json=payload,
            timeout=15,
        )
        if resp.status_code == 401:
            raise RaindropAuthError("Raindrop token invalid or expired (401)")
        resp.raise_for_status()
        data = resp.json()
        log_structured("INFO", "Raindrop bookmark created", url=url, title=title)
        return data["item"]

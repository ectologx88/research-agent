"""NewsBlur API client with session management and retry logic."""

from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict

import requests
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.models.story import Story
from src.utils import log_structured, utcnow


class NewsBlurError(Exception):
    """Base exception for NewsBlur client errors."""


class NewsBlurAuthError(NewsBlurError):
    """Authentication failed."""


class NewsBlurClient:
    """Authenticated client for the NewsBlur REST API."""

    BASE_URL = "https://newsblur.com"

    def __init__(self, username: str, password: str, base_url: str | None = None):
        self._username = username
        self._password = password
        self._base = (base_url or self.BASE_URL).rstrip("/")
        self._session = requests.Session()
        self._authenticated = False

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        resp = self._session.post(
            f"{self._base}/api/login",
            data={"username": self._username, "password": self._password},
            timeout=15,
        )
        body = resp.json()
        self._authenticated = body.get("authenticated", False)
        if not self._authenticated:
            raise NewsBlurAuthError(
                f"Login failed: code={body.get('code')} errors={body.get('errors')}"
            )
        log_structured("INFO", "NewsBlur authenticated", user=self._username)
        return True

    # ------------------------------------------------------------------
    # Story fetching
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type(requests.exceptions.RequestException),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _get(self, path: str, params: dict | None = None) -> dict:
        """Authenticated GET with retry."""
        if not self._authenticated:
            self.authenticate()
        resp = self._session.get(
            f"{self._base}{path}", params=params or {}, timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    def get_feeds_by_folder(self) -> Dict[str, List[int]]:
        """Return a mapping of folder name → list of feed IDs.

        The special key "" holds unfolderd (top-level) feed IDs.
        Calls /reader/feeds which returns the full feed list and folder structure.
        """
        data = self._get("/reader/feeds")
        result: Dict[str, List[int]] = {"": []}

        for entry in data.get("folders", []):
            if isinstance(entry, int):
                result[""].append(entry)
            elif isinstance(entry, dict):
                for folder_name, id_list in entry.items():
                    result[folder_name] = [i for i in id_list if isinstance(i, int)]

        total_feeds = sum(len(v) for v in result.values())
        log_structured(
            "INFO",
            "triage.feed_map_loaded",
            total_folders=len(result) - 1,
            total_feed_ids=total_feeds,
        )
        return result

    def fetch_unread_stories(
        self,
        since_timestamp: Optional[datetime] = None,
        hours_back: int = 36,
        min_score: int = 0,
        max_results: int = 100,
        feed_ids: Optional[List[int]] = None,
    ) -> List[Story]:
        """Fetch unread stories, newest first, with optional filters.

        Args:
            since_timestamp: Only return stories after this time.
            hours_back: Fallback window when *since_timestamp* is None.
            min_score: Minimum NewsBlur intelligence score (-1, 0, or 1).
            max_results: Hard cap on returned stories.
            feed_ids: If set, restrict fetch to these feed IDs (river_stories feeds[] param).
        """
        cutoff = since_timestamp or (utcnow() - timedelta(hours=hours_back))
        stories: List[Story] = []
        page = 1
        now = utcnow()

        while len(stories) < max_results:
            params: dict = {
                "page": page,
                "order": "newest",
                "read_filter": "unread",
                "include_story_content": "true",
            }
            if feed_ids:
                params["feeds[]"] = feed_ids
            data = self._get(
                "/reader/river_stories",
                params=params,
            )

            raw_stories = data.get("stories", [])
            if not raw_stories:
                break

            for s in raw_stories:
                story_dt = self._parse_date(s.get("story_date", ""))
                if story_dt and story_dt < cutoff:
                    # Reached stories older than our window — stop paging
                    log_structured(
                        "INFO",
                        "Reached cutoff date, stopping pagination",
                        page=page,
                        cutoff=cutoff.isoformat(),
                    )
                    return stories[:max_results]

                score = self._compute_score(s.get("intelligence", {}))
                if score < min_score:
                    continue

                try:
                    story = Story(
                        story_hash=s["story_hash"],
                        story_title=s.get("story_title", "(no title)"),
                        story_permalink=s.get("story_permalink", ""),
                        story_content=s.get("story_content", ""),
                        story_date=story_dt or now,
                        story_feed_title=s.get("story_feed_title", ""),
                        story_authors=s.get("story_authors") or None,
                        newsblur_score=score,
                        fetched_at=now,
                    )
                    stories.append(story)
                except Exception as exc:
                    log_structured(
                        "WARNING",
                        "Skipped malformed story",
                        hash=s.get("story_hash"),
                        error=str(exc),
                    )

            page += 1

        log_structured(
            "INFO",
            "Fetched stories",
            count=len(stories),
            pages=page - 1,
        )
        return stories[:max_results]

    # ------------------------------------------------------------------
    # Mark-as-read
    # ------------------------------------------------------------------

    def mark_stories_as_read(self, story_hashes: List[str]) -> bool:
        if not story_hashes:
            return True
        resp = self._session.post(
            f"{self._base}/reader/mark_story_hashes_as_read",
            data={"story_hash": story_hashes},
            timeout=15,
        )
        return resp.json().get("result") == "ok"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_date(raw: str) -> Optional[datetime]:
        """Parse NewsBlur's date format into a timezone-aware datetime."""
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
        ):
            try:
                return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
            except ValueError:
                continue
        return None

    @staticmethod
    def _compute_score(intelligence: dict) -> int:
        """Collapse NewsBlur's per-dimension intelligence into a single score.

        Logic mirrors the web UI:
        - Any positive dimension → 1  (focus)
        - Any negative (none positive) → -1  (hidden)
        - All zero → 0  (neutral)
        """
        values = [
            intelligence.get("feed", 0),
            intelligence.get("title", 0),
            intelligence.get("author", 0),
            intelligence.get("tags", 0),
        ]
        if any(v > 0 for v in values):
            return 1
        if any(v < 0 for v in values):
            return -1
        return 0

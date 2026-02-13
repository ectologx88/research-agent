"""Raw story model ingested from NewsBlur."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, HttpUrl


class Story(BaseModel):
    """A single story fetched from NewsBlur."""

    story_hash: str
    story_title: str
    story_permalink: HttpUrl
    story_content: str
    story_date: datetime
    story_feed_title: str
    story_authors: Optional[str] = None
    newsblur_score: int  # -1 (hidden), 0 (neutral), 1 (focus)
    fetched_at: datetime

    @property
    def content_truncated(self) -> str:
        """Return content capped at 4000 chars for classification."""
        if len(self.story_content) <= 4000:
            return self.story_content
        return self.story_content[:4000] + "\n[...truncated]"

# shared/dynamodb_client.py
"""Typed DynamoDB clients for the three pipeline tables.

Usage:
    import boto3
    from shared.dynamodb_client import StoryStaging, SignalTracker, BriefingArchive

    dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
    stories = StoryStaging(dynamodb.Table("story-staging"))
    signals = SignalTracker(dynamodb.Table("signal-tracker"))
    archive = BriefingArchive(dynamodb.Table("briefing-archive"))
"""
import re
import time
from datetime import datetime, timezone
from typing import Any, Optional

from shared.logger import log


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ttl(seconds: int) -> int:
    return int(time.time()) + seconds


class StoryStaging:
    """Operations on the story_staging table (PK: story_hash, SK: briefing_type)."""

    def __init__(self, table):
        self._table = table

    def store_story(self, data: dict[str, Any]) -> None:
        """Write a new story at status='pending'. Called by Lambda 1."""
        item = {
            **data,
            "status": "pending",
            "created_at": _now_iso(),
            "ttl": _ttl(36 * 3600),  # 36h: survives one suppressed day into the next run
        }
        self._table.put_item(Item=item)

    def update_status(
        self,
        story_hash: str,
        briefing_type: str,
        status: str,
        **fields: Any,
    ) -> None:
        """Update story status and arbitrary fields. Called by Lambda 2 and 3."""
        # Validate field names: must be valid identifiers (alphanumeric + underscore)
        for k in fields:
            if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', k):
                raise ValueError(f"Field name {k!r} is not a valid DynamoDB attribute name")

        update_expr_parts = ["#st = :status"]
        expr_names = {"#st": "status"}
        expr_values: dict[str, Any] = {":status": status}

        for k, v in fields.items():
            placeholder = f":f_{k}"
            update_expr_parts.append(f"#{k} = {placeholder}")
            expr_names[f"#{k}"] = k
            expr_values[placeholder] = v

        self._table.update_item(
            Key={"story_hash": story_hash, "briefing_type": briefing_type},
            UpdateExpression="SET " + ", ".join(update_expr_parts),
            ExpressionAttributeNames=expr_names,
            ExpressionAttributeValues=expr_values,
        )

    def get_story(self, story_hash: str, briefing_type: str) -> Optional[dict]:
        """Fetch a single story by primary key."""
        resp = self._table.get_item(
            Key={"story_hash": story_hash, "briefing_type": briefing_type}
        )
        return resp.get("Item")

    def batch_get_stories(
        self, story_hashes: list[str], briefing_type: str
    ) -> list[dict]:
        """Fetch multiple stories using BatchGetItem. Returns only items found."""
        if not story_hashes:
            return []

        table_name = self._table.name
        client = self._table.meta.client

        keys = [
            {"story_hash": h, "briefing_type": briefing_type}
            for h in story_hashes
        ]

        results: list[dict] = []

        # DynamoDB BatchGetItem supports up to 100 keys per table per request.
        for i in range(0, len(keys), 100):
            batch_keys = keys[i : i + 100]
            request_items = {table_name: {"Keys": batch_keys}}

            while request_items:
                response = client.batch_get_item(RequestItems=request_items)
                items = response.get("Responses", {}).get(table_name, [])
                results.extend(items)

                unprocessed = response.get("UnprocessedKeys", {})
                request_items = unprocessed if unprocessed and unprocessed.get(table_name, {}).get("Keys") else {}

        return results

    def check_duplicate(self, story_hash: str, briefing_type: str) -> bool:
        """Return True if story already exists in story_staging."""
        return self.get_story(story_hash, briefing_type) is not None


class SignalTracker:
    """Operations on signal_tracker table (PK: signal_key, 7-day rolling TTL)."""

    def __init__(self, table):
        self._table = table

    def upsert(self, signal_key: str, story_hash: str) -> None:
        """Increment mention count atomically, keep last 3 example stories.
        TTL is reset to now + 7 days on every update (rolling).
        example_stories list is best-effort (not atomic) — acceptable for signal tracking.
        """
        now = _now_iso()
        new_ttl = _ttl(7 * 24 * 3600)

        # Atomic count increment + set timestamps + rolling TTL
        self._table.update_item(
            Key={"signal_key": signal_key},
            UpdateExpression=(
                "SET mention_count = if_not_exists(mention_count, :zero) + :one, "
                "last_seen = :now, #ttl = :ttl, "
                "first_seen = if_not_exists(first_seen, :now)"
            ),
            ExpressionAttributeNames={"#ttl": "ttl"},
            ExpressionAttributeValues={
                ":zero": 0,
                ":one": 1,
                ":now": now,
                ":ttl": new_ttl,
            },
        )

        # Best-effort: append story_hash to example list (cap at 3)
        existing = self.get_signals([signal_key])
        if existing:
            item = existing[0]
            stories = item.get("example_stories", [])
            if story_hash not in stories:
                stories = (stories + [story_hash])[-3:]
                self._table.update_item(
                    Key={"signal_key": signal_key},
                    UpdateExpression="SET example_stories = :stories",
                    ExpressionAttributeValues={":stories": stories},
                )
        else:
            # New item: set initial example_stories
            self._table.update_item(
                Key={"signal_key": signal_key},
                UpdateExpression="SET example_stories = :stories",
                ExpressionAttributeValues={":stories": [story_hash]},
            )

    def get_signals(self, signal_keys: list[str]) -> list[dict]:
        """Fetch specific signal keys. Uses GetItem per key — NOT Scan."""
        results = []
        for key in signal_keys:
            resp = self._table.get_item(Key={"signal_key": key})
            if "Item" in resp:
                results.append(resp["Item"])
        return results


class BriefingArchive:
    """Operations on briefing_archive table (PK: briefing_date, SK: briefing_type)."""

    def __init__(self, table):
        self._table = table

    def store_briefing(
        self,
        briefing_date: str,
        briefing_type: str,
        content: str,
        candidate_count: int,
        passed_count: int,
        story_count: int,
        raindrop_id: Optional[str],
    ) -> None:
        """Store completed briefing with 30-day TTL."""
        self._table.put_item(Item={
            "briefing_date": briefing_date,
            "briefing_type": briefing_type,
            "content": content,
            "candidate_count": candidate_count,
            "passed_count": passed_count,
            "story_count": story_count,
            "raindrop_id": raindrop_id,
            "created_at": _now_iso(),
            "ttl": _ttl(30 * 24 * 3600),
        })

    def get_prior(self, briefing_date: str, briefing_type: str) -> Optional[dict]:
        """
        Fetch the immediately preceding briefing edition.
        AM run -> yesterday's PM: pass briefing_date="2026-02-16-PM"
        PM run -> today's AM: pass briefing_date="2026-02-17-AM"
        Caller is responsible for computing the correct date key.
        """
        resp = self._table.get_item(
            Key={"briefing_date": briefing_date, "briefing_type": briefing_type}
        )
        return resp.get("Item")

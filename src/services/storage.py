"""DynamoDB storage layer for classified stories."""

import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

import boto3
from boto3.dynamodb.conditions import Key

from src.models.classification import Classification
from src.models.story import Story
from src.utils import log_structured

CONFIG_PK = "__PIPELINE_CONFIG__"
LAST_RUN_SK = 0
TTL_DAYS = 90


class ClassificationStorage:
    """Read/write classified stories and pipeline state in DynamoDB."""

    def __init__(self, table_name: str, region: str = "us-east-1"):
        dynamo = boto3.resource("dynamodb", region_name=region)
        self._table = dynamo.Table(table_name)
        self._table_name = table_name

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    def store_classification(
        self, story: Story, classification: Classification
    ) -> bool:
        """Persist a classified story. Idempotent on story_hash."""
        ttl = int(time.time()) + (TTL_DAYS * 86400)
        date_str = story.story_date.strftime("%Y-%m-%d")

        item = {
            "story_hash": classification.story_hash,
            "classified_at": int(classification.classified_at.timestamp()),
            "story_title": story.story_title,
            "story_url": str(story.story_permalink),
            "story_date": story.story_date.isoformat(),
            "feed_title": story.story_feed_title,
            "classification": classification.model_dump(mode="json"),
            "date": date_str,
            "overall_score": classification.scores.overall,
            "ttl": ttl,
        }

        try:
            self._table.put_item(Item=item)
            return True
        except Exception as exc:
            log_structured(
                "ERROR",
                "Failed to store classification",
                hash=classification.story_hash,
                error=str(exc),
            )
            return False

    # ------------------------------------------------------------------
    # Read / dedup
    # ------------------------------------------------------------------

    def story_already_classified(self, story_hash: str) -> bool:
        resp = self._table.query(
            KeyConditionExpression=Key("story_hash").eq(story_hash),
            Limit=1,
            Select="COUNT",
        )
        return resp["Count"] > 0

    # ------------------------------------------------------------------
    # Pipeline state
    # ------------------------------------------------------------------

    def get_last_run_timestamp(self) -> Optional[datetime]:
        resp = self._table.get_item(
            Key={"story_hash": CONFIG_PK, "classified_at": LAST_RUN_SK}
        )
        item = resp.get("Item")
        if not item or "last_run" not in item:
            return None
        return datetime.fromisoformat(item["last_run"])

    def update_last_run_timestamp(self, ts: datetime) -> bool:
        try:
            self._table.put_item(
                Item={
                    "story_hash": CONFIG_PK,
                    "classified_at": LAST_RUN_SK,
                    "last_run": ts.isoformat(),
                }
            )
            return True
        except Exception as exc:
            log_structured(
                "ERROR", "Failed to update last-run timestamp", error=str(exc)
            )
            return False

    # ------------------------------------------------------------------
    # Query (for downstream / Phase 2)
    # ------------------------------------------------------------------

    def get_classifications_by_date(
        self, date: str, min_score: int = 8
    ) -> List[Dict]:
        """Query the GSI for high-value stories on a given date."""
        resp = self._table.query(
            IndexName="classification-by-date",
            KeyConditionExpression=(
                Key("date").eq(date) & Key("overall_score").gte(min_score)
            ),
        )
        return resp.get("Items", [])

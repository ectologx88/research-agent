"""Minimal DynamoDB storage for deduplication and pipeline state only.

Classifications are processed in-memory — DynamoDB only tracks which
stories have been seen (with a 3-day TTL) and the last-run timestamp.
"""

import time
from datetime import datetime, timezone
from typing import List, Optional, Set

import boto3

from src.utils import log_structured

TTL_DAYS = 3


class ProcessingStateStorage:
    """Deduplication and state tracking via DynamoDB."""

    def __init__(self, table_name: str, region: str = "us-east-1"):
        self._dynamo = boto3.resource("dynamodb", region_name=region)
        self._table = self._dynamo.Table(table_name)
        self._table_name = table_name

    # ------------------------------------------------------------------
    # Pipeline state
    # ------------------------------------------------------------------

    def get_last_run_timestamp(self) -> Optional[datetime]:
        resp = self._table.get_item(
            Key={"record_type": "config", "identifier": "last_run_timestamp"}
        )
        item = resp.get("Item")
        if not item or "value" not in item:
            return None
        return datetime.fromisoformat(item["value"])

    def update_last_run_timestamp(self, ts: datetime) -> bool:
        try:
            self._table.put_item(
                Item={
                    "record_type": "config",
                    "identifier": "last_run_timestamp",
                    "value": ts.isoformat(),
                }
            )
            return True
        except Exception as exc:
            log_structured(
                "ERROR", "Failed to update last-run timestamp", error=str(exc)
            )
            return False

    # ------------------------------------------------------------------
    # Deduplication
    # ------------------------------------------------------------------

    def already_processed(self, story_hash: str) -> bool:
        resp = self._table.get_item(
            Key={"record_type": "story", "identifier": story_hash},
            ProjectionExpression="identifier",
        )
        return "Item" in resp

    def batch_check_processed(self, story_hashes: List[str]) -> Set[str]:
        """Return the subset of *story_hashes* that already exist in the table.

        Processes in chunks of 100 (DynamoDB BatchGetItem limit).
        Handles UnprocessedKeys with exponential backoff.
        """
        processed: Set[str] = set()
        if not story_hashes:
            return processed

        for offset in range(0, len(story_hashes), 100):
            chunk = story_hashes[offset : offset + 100]
            request_items = {
                self._table_name: {
                    "Keys": [
                        {"record_type": "story", "identifier": h} for h in chunk
                    ],
                    "ProjectionExpression": "identifier",
                }
            }

            # Handle UnprocessedKeys with exponential backoff (max 10 retries)
            backoff_seconds = 0.1
            max_retries = 10
            retry_count = 0
            while request_items:
                resp = self._dynamo.batch_get_item(RequestItems=request_items)

                # Process returned items
                for item in resp.get("Responses", {}).get(self._table_name, []):
                    processed.add(item["identifier"])

                # Check for unprocessed keys
                unprocessed = resp.get("UnprocessedKeys")
                if unprocessed and unprocessed.get(self._table_name):
                    retry_count += 1
                    if retry_count > max_retries:
                        log_structured(
                            "ERROR",
                            "Max retries exceeded for unprocessed keys",
                            unprocessed_count=len(unprocessed[self._table_name]["Keys"]),
                            max_retries=max_retries,
                        )
                        break
                    request_items = unprocessed
                    log_structured(
                        "WARNING",
                        "Retrying unprocessed keys",
                        count=len(unprocessed[self._table_name]["Keys"]),
                        backoff=backoff_seconds,
                        retry_attempt=retry_count,
                    )
                    time.sleep(backoff_seconds)
                    backoff_seconds = min(backoff_seconds * 2, 5.0)
                else:
                    request_items = None

        return processed

    def mark_processed(self, story_hash: str, overall_score: int) -> bool:
        """Store a minimal dedup record with 3-day TTL."""
        ttl = int(time.time()) + (TTL_DAYS * 86400)
        try:
            self._table.put_item(
                Item={
                    "record_type": "story",
                    "identifier": story_hash,
                    "processed_at": datetime.now(timezone.utc).isoformat(),
                    "overall_score": overall_score,
                    "ttl": ttl,
                }
            )
            return True
        except Exception as exc:
            log_structured(
                "ERROR",
                "Failed to mark story processed",
                hash=story_hash,
                error=str(exc),
            )
            return False

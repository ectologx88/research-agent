# scripts/delete_todays_briefing.py
"""One-shot: delete today's AM briefing from Raindrop briefing collection."""
import os
import requests
from datetime import date

TOKEN = os.environ["RAINDROP_TOKEN"]
COLLECTION_ID = os.environ["RAINDROP_BRIEFING_COLLECTION_ID"]
TODAY = date.today().isoformat()  # e.g. "2026-02-19"

headers = {"Authorization": f"Bearer {TOKEN}"}

# Fetch all bookmarks in briefing collection
resp = requests.get(
    f"https://api.raindrop.io/rest/v1/raindrops/{COLLECTION_ID}",
    headers=headers,
    params={"perpage": 50},
)
resp.raise_for_status()
items = resp.json().get("items", [])

# Find and delete today's AM briefing
deleted = 0
for item in items:
    title = item.get("title", "")
    if TODAY in title and ("AM" in title or "morning" in title.lower() or "abstract" in title.lower()):
        rid = item["_id"]
        del_resp = requests.delete(
            f"https://api.raindrop.io/rest/v1/raindrop/{rid}",
            headers=headers,
        )
        print(f"Deleted: {title} (id={rid}, status={del_resp.status_code})")
        deleted += 1

print(f"Done. Deleted {deleted} briefing(s).")

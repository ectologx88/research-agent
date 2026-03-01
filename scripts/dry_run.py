#!/usr/bin/env python3
"""Dry run the full triage pipeline locally. Zero LLM cost, zero writes.

Usage:
    DRY_RUN=true python scripts/dry_run.py

Loads credentials from AWS SSM (seth-dev profile), invokes triage handler
with DRY_RUN=true, prints routing report and Lambda 2 mock scoring summary.
"""
import os
import sys
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ.setdefault("DRY_RUN", "true")

import boto3
from src.clients.newsblur import NewsBlurClient
from src.services.triage import TriageService
from src.services.velocity import compute_clusters
from config.feed_rules import FOLDER_ROUTE_MAP, UNFOLDERD_ROUTE_MAP, ALWAYS_SKIP_NAMES, _has_ai_ml_keyword, Route
from config.scoring_weights import (
    AI_ML_PASS_THRESHOLD, WORLD_PASS_THRESHOLD, MIN_STORIES_FOR_BRIEFING
)
from collections import Counter, defaultdict


AWS_PROFILE = "seth-dev"
SSM_PREFIX = "/prod/ResearchAgent/"


def fetch_credentials():
    session = boto3.Session(profile_name=AWS_PROFILE, region_name="us-east-1")
    ssm = session.client("ssm")
    user = ssm.get_parameter(Name=f"{SSM_PREFIX}NewsBlur_User", WithDecryption=True)["Parameter"]["Value"]
    passwd = ssm.get_parameter(Name=f"{SSM_PREFIX}NewsBlur_Pass", WithDecryption=True)["Parameter"]["Value"]
    return user, passwd


def main():
    from datetime import datetime, timezone
    print(f"\nDRY RUN — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M')} UTC")
    print("=" * 60)

    user, passwd = fetch_credentials()
    nb = NewsBlurClient(user, passwd)
    nb.authenticate()

    # Per-folder fetch
    folder_map = nb.get_feeds_by_folder()
    print(f"Folders found: {[k for k in folder_map if k]}")

    ai_ml: list[tuple] = []
    world: list[tuple] = []
    seen_hashes: set[str] = set()

    folders_to_fetch = list(FOLDER_ROUTE_MAP.items()) + [("General-Tech", None)]

    for folder_name, route_info in folders_to_fetch:
        feed_ids = folder_map.get(folder_name, [])
        if not feed_ids:
            print(f"  [{folder_name}] no feeds found, skipping")
            continue

        is_keyword_routed = route_info is None
        min_score = 0 if folder_name == "AI-ML-Research" else 1
        max_results = {"AI-ML-Research": 40, "AI-ML-Community": 25, "General-Tech": 40}.get(
            folder_name,
            50 if "World" in folder_name or folder_name == "Current Events & World" or folder_name == "Weather" else 30
        )

        stories = nb.fetch_unread_stories(
            feed_ids=feed_ids, min_score=min_score, max_results=max_results, hours_back=12
        )
        print(f"  [{folder_name}] {len(stories)} stories")

        for story in stories:
            if story.story_hash in seen_hashes:
                continue
            seen_hashes.add(story.story_hash)

            if is_keyword_routed:
                if _has_ai_ml_keyword(story.story_title or ""):
                    ai_ml.append((story, "research"))
                else:
                    world.append((story, "tech"))
            else:
                route, sub_bucket = route_info
                if route == Route.AI_ML:
                    ai_ml.append((story, sub_bucket))
                else:
                    world.append((story, sub_bucket))

    # Unfolderd feeds
    unfolderd_ids = folder_map.get("", [])
    if unfolderd_ids:
        unfolderd_stories = nb.fetch_unread_stories(
            feed_ids=unfolderd_ids, min_score=1, max_results=20, hours_back=12
        )
        print(f"  [(unfolderd)] {len(unfolderd_stories)} stories")
        for story in unfolderd_stories:
            if story.story_hash in seen_hashes:
                continue
            seen_hashes.add(story.story_hash)
            feed = story.story_feed_title or ""
            if feed in ALWAYS_SKIP_NAMES:
                continue
            entry = UNFOLDERD_ROUTE_MAP.get(feed)
            if entry:
                world.append((story, entry[1]))

    skip_count = 0  # skipped at source by ALWAYS_SKIP_NAMES check

    # Count by feed
    def feed_counts(items):
        counts = defaultdict(int)
        for story, _ in items:
            counts[story.story_feed_title] += 1
        return dict(sorted(counts.items(), key=lambda x: -x[1]))

    print(f"\nRouting decisions:")
    print(f"  AI_ML  ({len(ai_ml)}): {feed_counts(ai_ml)}")
    print(f"  WORLD  ({len(world)}): {feed_counts(world)}")
    print(f"  SKIP   ({skip_count}): filtered at source")

    # Boost tags
    svc = TriageService()
    all_boost = []
    for story, _ in ai_ml + world:
        tags = svc.get_boost_tags(story)
        all_boost.extend(tags)
    boost_counts = Counter(all_boost)
    if boost_counts:
        print(f"\nBoost tags applied: {', '.join(f'{t}x{c}' for t, c in boost_counts.items())}")

    # Velocity clusters
    all_stories = [s for s, _ in ai_ml + world]
    clusters = compute_clusters(all_stories)
    lead_candidates = [(h, key) for h, (size, key) in clusters.items() if size >= 3]
    if lead_candidates:
        cluster_keys = Counter(key for _, key in lead_candidates)
        print(f"\nVelocity clusters:")
        for key, count in cluster_keys.most_common(5):
            print(f'  "{key}" [{count} stories] -> Lead Story candidate')
    else:
        print("\nVelocity clusters: none (no topic covered by 3+ sources)")

    # Lambda 2 mock summary
    print(f"\nEditorial filter (mock, DRY_RUN=true):")
    ai_ml_total = len(ai_ml)
    world_total = len(world)
    print(f"  Would pass: {ai_ml_total}/{ai_ml_total} AI_ML candidates (threshold {AI_ML_PASS_THRESHOLD}/15)")
    print(f"  Would pass: {world_total}/{world_total} WORLD candidates (threshold {WORLD_PASS_THRESHOLD}/15)")
    print(f"  Mock scores: all set to integrity:3, relevance:3, novelty:3 (total:9)")
    print(f"  Note: run DRY_RUN=writes_only to see real Haiku scoring decisions")

    print()


if __name__ == "__main__":
    main()

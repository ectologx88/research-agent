# Phase 2b: Briefing Design

**Date:** 2026-02-16
**Status:** Approved

## Overview

Extend the pipeline to produce a narrative intelligence briefing twice daily (6 AM / 6 PM US Central), delivered as a Raindrop bookmark. Adds an `importance` score, replaces generic tags with Seth's taxonomy, and synthesizes filtered stories into a structured briefing using Claude Sonnet 4.5.

---

## Section 1: Classification Changes

### New Score: Importance (1–10)

A 6th classification dimension alongside the existing five (domain_relevance, technical_depth, actionability, novelty, credibility). Measures strategic significance independent of domain relevance — captures world-shaking AI/policy events that matter even if tangential to Seth's day-to-day work.

Bedrock prompt updated to return `importance` as an integer 1–10 with a one-sentence rationale.

### Tags: Seth's Taxonomy

Replace the current generic `actionability_tags` list with two fields:

**Category tags** (zero or more from fixed list):
- `#ai-research` — papers, benchmarks, capabilities advances
- `#ai-policy` — regulation, governance, safety policy
- `#consciousness` — philosophy of mind, sentience, phenomenology
- `#rdd-framework` — Recursive Developmental Design methodology
- `#client-work` — practical AI adoption, enterprise deployment
- `#neurodivergent-tech` — ADHD/autism/accessibility tooling
- `#industry-news` — market moves, funding, launches, acquisitions
- `#world-news` — geopolitical/economic events with AI implications

**Priority flags** (zero or one):
- `⚡` — breaking, time-sensitive
- `🎯` — directly actionable for Seth's work
- `🧠` — deep conceptual value
- `🔗` — connects multiple threads in Seth's thinking
- `📊` — data/evidence-driven
- `🚨` — risk/threat signal

Bedrock prompt updated accordingly. Tags stored on story objects and used for both Raindrop bookmarks and briefing synthesis.

---

## Section 2: Pre-filter and Briefing Synthesis

### Pre-filter

Before sending to the briefing synthesizer, stories must pass:

```
domain_relevance >= 5  OR  importance >= 6
```

This gates compute cost and focuses the briefing on material Seth actually cares about. Stories below threshold are still processed and bookmarked normally if overall ≥ 8.

### Briefing Synthesis

Model: `us.anthropic.claude-sonnet-4-5-20250929-v1:0` (Sonnet 4.5 inference profile)

System prompt: Seth's full reader profile (AI adoption consultant, RDD framework developer, autism/ADHD context, journalistic integrity standards, communication preferences).

The briefing prompt passes filtered stories (title, source, scores, tags, summary, key concepts) and requests a **5-section narrative briefing**:

1. **Executive Summary** — 3–5 sentence big-picture synthesis of what today's coverage means
2. **Must-Know Today** — 3–5 stories with the most immediate relevance; why each matters to Seth specifically
3. **Deep Dives** — 2–3 stories worth extended reading; conceptual hooks and connections to Seth's frameworks
4. **Weak Signals** — emerging patterns or under-covered themes that may become significant
5. **Notable Omissions** — what the coverage is conspicuously missing or underselling

Output is plain text (Markdown acceptable). No JSON wrapper.

---

## Section 3: Raindrop Delivery

### Story Bookmarks (updated)

Existing high-value story bookmarks (overall ≥ 8) updated to use Seth's taxonomy tags instead of generic actionability tags. Note field remains "why it matters" from classification.

### Briefing Bookmark

One bookmark per run:

| Field | Value |
|---|---|
| Title | `Morning Briefing — Feb 16, 2026` or `Evening Briefing — …` |
| URL | First story's URL (Raindrop requires a URL; briefing text lives in the note) |
| Note | Full briefing text |
| Tags | `briefing`, `ai-generated`, `morning` or `evening` |
| Collection | `RAINDROP_BRIEFING_COLLECTION_ID` (SSM-stored, defaults to `-1` unsorted inbox) |

Morning/Evening determined by UTC hour at invocation time: hour < 18 → Morning, hour ≥ 18 → Evening (aligns with 11:00 and 23:00 UTC schedule).

No duplicate-check for briefing bookmarks — each run always produces one.

---

## Section 4: Operational Changes

### Schedule

Change EventBridge from `rate(12 hours)` to `cron(0 11,23 * * ? *)`:
- `11:00 UTC` → 6:00 AM CST / 5:00 AM CDT
- `23:00 UTC` → 6:00 PM CST / 5:00 PM CDT

### Volume

Increase `MAX_STORIES_PER_RUN` from `100` to `200`. Pre-filter reduces stories reaching the synthesizer; higher fetch cap ensures adequate raw material.

### New Environment Variable

`RAINDROP_BRIEFING_COLLECTION_ID` — Raindrop collection ID for briefing bookmarks. Stored in SSM at `/prod/ResearchAgent/Raindrop_Briefing_Collection_Id`. Defaults to `-1` (unsorted inbox) if not set.

---

## Out of Scope

- Email/SMS/push delivery of briefing text (delivery mechanism TBD for Phase 2c)
- Per-tag collection routing in Raindrop
- Retroactive re-classification of previously processed stories

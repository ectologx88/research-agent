# Research Agent — Feed Configuration Reference

Current as of 2026-03-01. Use this to brainstorm changes to folder structure,
per-folder caps, scoring thresholds, and new feed additions.

---

## How Routing Works (Post Per-Folder Refactor)

The triage Lambda now fetches each NewsBlur folder independently in parallel,
then routes all stories to one of two briefing streams:

- **AI_ML** → The AI Abstract (public, posted to site + Raindrop)
- **WORLD** → The Recursive Briefing (private, owner-only page + Raindrop)

Routing is determined by folder identity, not individual feed name matching.
The only exception is **General-Tech**, which uses per-story keyword routing.

```
NewsBlur Folder → get_feeds_by_folder() → parallel river fetches
                                               ↓
                                    FOLDER_ROUTE_MAP lookup
                                    (or keyword scan for General-Tech)
                                               ↓
                              ai_ml_stories | world_stories
                                               ↓
                                  Haiku editorial scoring
                                               ↓
                             Sonnet 4.6 briefing synthesis
```

---

## Current Folder Configuration

Defined in `config/feed_rules.py` (FOLDER_ROUTE_MAP) and `src/config.py` (caps).

| Folder | Stream | Sub-bucket | Max Stories | min_score | Rationale |
|--------|--------|-----------|-------------|-----------|-----------|
| AI-ML-Research | AI_ML | research | 40 | **0** | arXiv has no trained intelligence rules; score=0 is normal |
| AI-ML-Community | AI_ML | community | 25 | 1 | Reddit pre-filtered by upvotes; NB scoring reliable |
| Current Events & World | WORLD | news | 50 | 1 | High-volume; NB scoring reliable |
| Weather | WORLD | news | 50 | 1 | Shared cap with news (combined fetch with Current Events is a future option) |
| World-Science | WORLD | science | 30 | **0** | Science feeds vary; let Haiku filter |
| World-Tech | WORLD | tech | 25 | 1 | Consumer tech; lower volume |
| General-Tech | AI_ML or WORLD | research or tech | 40 | **0** | Per-story keyword routing; HN/WIRED/Ars Technica |
| (unfolderd) | varies | varies | 20 | 1 | Small batch; routed by UNFOLDERD_ROUTE_MAP |

**Total candidate ceiling per run:** ~210 stories
**Typical actual yield (2026-03-01 dry run):** 65 stories (28 AI_ML, 37 WORLD)

---

## Current Feed Membership (as reorganized 2026-03-01)

### AI-ML-Research
- cs.AI updates on arXiv.org
- cs.CL updates on arXiv.org
- Anthropic News / Anthropic Engineering Blog / Anthropic Research
- Google DeepMind News
- The Machine Herald

### AI-ML-Community
- ClaudeAI (r/ClaudeAI)
- top scoring links : MachineLearning (r/MachineLearning)
- top scoring links : artificial (r/artificial)

### Current Events & World
- Axios
- BBC News
- NPR Topics: News
- NYT > Top Stories
- Houston Public Media
- ProPublica

### Weather
- Space City Weather

### World-Science
- ScienceDaily
- Nature - Issue - nature.com science feeds
- Recent Articles in Phys. Rev. Lett.
- NeuroLogica Blog
- top scoring links : neuroscience
- top scoring links : science
- cognitive science

### World-Tech
- 9to5Mac
- Apple Newsroom
- MacRumors: Mac News and Rumors - All Stories
- Google Workspace Updates
- The Keyword (Google)

### General-Tech (keyword-routed per story)
- Hacker News
- WIRED
- Ars Technica - All content
- Marco.org
- The Next Web
- Uncrunched

### Unfolderd (top-level, no folder)
- Ghostbusters News → WORLD/entertainment
- AI / Raindrop.io → **SKIP** (circular — Seth's own RSS export)
- The NewsBlur Blog → **SKIP** (meta)

---

## Scoring Pipeline Caps

These are downstream limits applied *after* triage — they cap how many candidates
Haiku scores and how many reach the final Sonnet synthesis.

Defined in `config/scoring_weights.py`:

| Stage | AI_ML Cap | WORLD Cap |
|-------|-----------|-----------|
| Triage → Haiku (scoring candidates) | 40 | 20 |
| Haiku → Sonnet (briefing candidates) | 10 | 8 |

**Haiku pass thresholds** (scores out of 15):
- AI_ML: 9/15
- WORLD: 7/15

---

## NewsBlur Intelligence Score Reference

NewsBlur scores each story -1, 0, or 1 per dimension (feed, title, author, tags).
The client collapses these to a single score:

| Score | Meaning | When set |
|-------|---------|----------|
| 1 | Focus | Any dimension positive (trained intelligence rule matches) |
| 0 | Neutral | All dimensions zero (no rules trained, or rules don't fire) |
| -1 | Hidden | Any dimension negative (blocked) |

**Key insight:** arXiv feeds have no trained intelligence rules in NewsBlur,
so all arXiv papers score 0. Using `min_score=1` silently drops them all.
`AI-ML-Research` and `World-Science` both use `min_score=0` to prevent this.

---

## Global Defaults

Defined in `src/config.py`:

| Setting | Value | Description |
|---------|-------|-------------|
| `newsblur_min_score` | 1 | Default min score; per-folder overrides take precedence |
| `newsblur_hours_back` | 12 | Fetch window; stories older than 12h are not fetched |
| `max_stories_per_run` | 150 | Global cap used only in fallback mode |
| `mark_as_read` | false | Stories are never marked read in NewsBlur |

---

## Adding a New Feed or Folder

### To add a feed to an existing folder
Just subscribe to it in NewsBlur and put it in the right folder. No code change needed.
`get_feeds_by_folder()` picks up the updated membership automatically.

### To add a new folder with a fixed route
1. Create the folder in NewsBlur, subscribe feeds to it
2. Add entry to `FOLDER_ROUTE_MAP` in `config/feed_rules.py`:
   ```python
   "My-New-Folder": (Route.AI_ML, "research"),
   ```
3. Add a max cap field to `Settings` in `src/config.py`:
   ```python
   my_new_folder_max_stories: int = 30
   ```
4. Wire it up in `_build_folder_configs()` in `triage_handler.py`
5. Add the env var to `terraform/lambda.tf` and `terraform apply`

### To add a new folder with keyword routing
Same as above but set `keyword_route=True` in the `FolderConfig`. The handler
then calls `_has_ai_ml_keyword(title)` per story, defaulting to WORLD/tech if no match.

### To add an unfolderd (top-level) feed with a specific route
Add to `UNFOLDERD_ROUTE_MAP` in `config/feed_rules.py`:
```python
"My Feed Title": (Route.WORLD, "entertainment"),
```
Leave the feed unfolderd in NewsBlur. No cap or score override — unfolderd batch uses
`max_results=20` and `min_score=newsblur_min_score`.

### To skip a feed regardless of where it is
Add its exact NewsBlur title to `ALWAYS_SKIP_NAMES` in `config/feed_rules.py`.
Currently used for circular/meta feeds only.

---

## Cost Sensitivity

More candidates to Haiku = higher Haiku cost. Current estimate per run:

| Scenario | Candidates | Est. Haiku cost |
|----------|-----------|-----------------|
| Before per-folder (2026-03-01) | ~23 | ~$0.01 |
| After per-folder (typical) | ~65 | ~$0.04–0.06 |
| At ceiling (all folders full) | ~210 | ~$0.12–0.15 |

Sonnet synthesis cost is fixed at 2 calls/run regardless of candidate count.
Monthly estimate at typical yield: ~$2–4 Haiku + ~$8–12 Sonnet ≈ $10–16/month.

CloudWatch cost alert threshold: $3/day (set in Amplify + `src/config.py`).

---

## Known Constraints and Trade-offs

- **`story_feed_title` is always empty** from `/reader/river_stories`. This is a
  NewsBlur API limitation. Routing uses folder identity; `feed_name` stored in
  DynamoDB will be blank for all stories. `briefing_handler.py` falls back to
  URL hostname for the source display.

- **hours_back=12 caps the arXiv backlog** naturally. The 247+122 unread arXiv
  papers that accumulated before this change are outside the 12h window and will
  not be fetched. Only new papers (last 12h) reach triage going forward.

- **Weather folder shares a cap** with Current Events & World (both use
  `world_news_max_stories=50`). In practice Space City Weather produces 1–3
  stories/run. Could be separated if weather volume grows.

- **General-Tech keyword routing is coarse** — story title is the only signal.
  A HN story about coffee grinders with no AI/ML keywords goes to WORLD/tech
  regardless of comment content or points. Acceptable for now.

- **Unfolderd cap is fixed at 20** (not a config setting). Currently produces 0
  stories (Ghostbusters News is quiet). Could be promoted to a proper folder
  if new misc feeds are added.

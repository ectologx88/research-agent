# Claude Code Implementation Plan
## Personal Journalist Engine v2.0
### research-agent repository — Branch: `feature/personal-journalist-v2`

---

## FIRST: Branch Setup

```bash
cd research-agent
git checkout main
git pull origin main
git checkout -b feature/personal-journalist-v2
git push -u origin feature/personal-journalist-v2
```

---

## MISSION BRIEFING

You are refactoring a single-stream AWS Lambda research agent into a 
dual-stream daily "Personal Journalist" system for an AI Adoption Consultant 
with 20+ years of industrial automation experience who manages PhD-level 
GenAI engineers at a German chemical manufacturing company. He publishes 
a thought leadership newsletter (Recursive Intelligence LLC) and is 
building a philosophical framework called Recursive Distinction Dynamics 
(RDD) that explores physics, consciousness, and information theory.

The system must feel like two dedicated editors — not a content aggregator.

Research the current codebase @ "~/01_Projects/research-agent" and make sure you understand it before incorporating new features from this document.

A secondary goal is to publish these on my website and incorporate them into my planned blog integration for @ "~/01_Projects/recursiveintelligence-website". The AI/ML feed will be published as a public report, while the Recursive Briefing will be published as a private report.

---

## FEATURE BRAINSTORM → PRIORITIZED REQUIREMENTS

### Core Architecture Changes (P0 — Must Have)

1. **Three-Lambda Pipeline with SQS**
   - Lambda 1: Triage (rule-based, no LLM, <60s)
   - Lambda 2: Summarizer (Haiku per story, parallel batches)
   - Lambda 3: Briefing synthesizer (Sonnet 4.5, two distinct personas)
   - Two SQS queues: `ai-ml-queue` and `world-queue`
   - One `briefing-queue` feeding Lambda 3
   - DynamoDB for story staging with 24h TTL

2. **Dual-Stream Routing**
   - Stream A: "The AI Abstract" (public, shareable RSS via Raindrop)
   - Stream B: "The Recursive Briefing" (private, personal briefing)
   - Skip bucket: mark_as_read in NewsBlur, nothing saved anywhere

3. **Context Injection Layer**
   - Open-Meteo API for Pasadena, TX weather (lat: 29.6911, lon: -95.2091)
   - Space City Weather RSS from my NewsBlur forHouston storm/hurricane context 
   - NWS alerts feed for severe weather
   - Inject as deterministic `[SYSTEM_CONTEXT_BLOCK]` into Lambda 3 prompts

4. **Raindrop.io Dual Collections**
   - "AI/ML Feed" — public collection, generates shareable RSS
   - "Current Events and World News" — private collection
   - Stories saved at triage time (title + tags, no summary yet)
   - Summaries added by Lambda 2 (update bookmark note field)
   - Briefing bookmarks, after publishing to my site/blog, saved by Lambda 3 as separate entries

### Intelligence Enhancements (P1 — Should Have)

5. **Config-Driven Feed Rules**
   - `config/feed_rules.py` — update without redeployment
   - Feed-name as primary signal, keywords as fallback
   - Hierarchical precedence (see triage logic below)

6. **Velocity Scoring for World Stream**
   - Track story clusters: 3+ sources covering same topic = "Lead Story"
   - Implemented in Lambda 1 using title similarity hashing
   - Flag field: `cluster_size` stored in DynamoDB

7. **Scoring Metadata Passthrough**
   - Triage boost/penalize tags stored in DynamoDB
   - Passed to Lambda 3 via briefing payload
   - Sonnet can see WHY a story was boosted (used in editorial synthesis)

8. **Trend Tracking for Weak Signals**
   - DynamoDB table: `signal_tracker` with 7-day TTL
   - Track keyword patterns across briefings
   - Lambda 3 can reference: "3rd mention of evaluation crisis this week"

### Quality of Life (P2 — Nice to Have)

9. **Dry Run Mode**
   - `DRY_RUN=true` environment variable
   - Full triage logic runs, no LLM calls, no Raindrop writes
   - Logs routing decisions to CloudWatch for tuning

10. **Cost Monitoring**
    - CloudWatch custom metrics: tokens_used, stories_processed, api_cost_estimate
    - Alert if estimated daily cost exceeds $3.00

11. **Processing State Machine**
    - DynamoDB `status` field: `pending → summarized → briefed`
    - Lambda 2 idempotency: skip already-summarized stories on retry
    - Dead letter queue for stories that fail after 3 attempts

12. **Briefing Archive**
    - Save each briefing to DynamoDB with 30-day TTL
    - Lambda 3 can reference yesterday's briefing for continuity

---

## NEW PROJECT STRUCTURE

Refactor the existing structure to:

```
research-agent/
├── lambdas/
│   ├── triage/
│   │   ├── handler.py          # Lambda 1 entry point
│   │   ├── newsblur_client.py  # Migrate from existing
│   │   ├── router.py           # NEW: Feed routing logic
│   │   ├── deduplicator.py     # NEW: Story dedup (24h window)
│   │   ├── context_loader.py   # NEW: Weather + local news fetcher
│   │   └── raindrop_client.py  # Migrate + enhance from existing
│   │
│   ├── summarizer/
│   │   ├── handler.py          # Lambda 2 entry point
│   │   ├── summarizer.py       # NEW: Haiku summarization with batching
│   │   └── raindrop_updater.py # NEW: Add summary to existing bookmark
│   │
│   └── briefing/
│       ├── handler.py          # Lambda 3 entry point
│       ├── personas.py         # NEW: PROMPT_EQUALIZER + PROMPT_ZEITGEIST
│       ├── synthesizer.py      # NEW: Sonnet 4.5 briefing generation
│       └── briefing_poster.py  # NEW: Post briefing as Raindrop bookmark
│
├── shared/
│   ├── models.py               # Pydantic models (migrate + expand)
│   ├── dynamodb_client.py      # NEW: Shared DDB operations
│   ├── config.py               # NEW: All env vars + constants
│   └── logger.py               # Structured logging setup
│
├── config/
│   ├── feed_rules.py           # NEW: Config-driven routing rules
│   ├── keywords.py             # NEW: Boost/penalize keyword lists
│   └── scoring_weights.py      # NEW: Per-stream scoring parameters
│
├── tests/
│   ├── test_router.py          # NEW: Feed routing unit tests
│   ├── test_deduplicator.py    # NEW
│   ├── test_context_loader.py  # NEW
│   ├── test_summarizer.py      # NEW
│   ├── test_personas.py        # NEW: Prompt injection tests
│   ├── test_newsblur_client.py # Migrate existing
│   └── fixtures/
│       ├── sample_stories.json # Migrate existing
│       ├── sample_feeds.json   # NEW: Feed name samples
│       └── sample_context.json # NEW: Mock weather/local data
│
├── infrastructure/
│   ├── lambda.tf               # Update: 3 lambdas + 3 SQS queues
│   ├── dynamodb.tf             # Update: story_staging + signal_tracker tables
│   ├── eventbridge.tf          # NEW: 6AM/6PM cron rules
│   ├── sqs.tf                  # NEW: Queue definitions + DLQ
│   ├── iam.tf                  # Update: expanded permissions
│   └── cloudwatch.tf           # NEW: Dashboards + cost alarms
│
├── scripts/
│   ├── dry_run.py              # NEW: Test routing without LLM/API calls
│   ├── tune_rules.py           # NEW: Analyze CloudWatch logs for misroutes
│   └── backfill_summaries.py   # NEW: Re-summarize old stories if needed
│
├── docs/
│   ├── ARCHITECTURE.md         # NEW: Full system diagram + data flow
│   ├── FEED_RULES.md           # NEW: How to add/modify feed routing
│   ├── PERSONAS.md             # NEW: Editorial identity documentation
│   └── COST_MODEL.md           # NEW: Cost projections + optimization
│
├── CLAUDE.md                   # NEW: persistent context for Claude Code
├── requirements.txt            # Update: add new dependencies
├── requirements-dev.txt        # NEW: Separate dev dependencies
├── deploy.sh                   # Update: deploy all 3 lambdas
├── .env.example                # Update: all required env vars
└── README.md                   # Full rewrite
```

---

## IMPLEMENTATION SPECIFICATIONS

### Lambda 1: Triage Handler

**Entry point**: `lambdas/triage/handler.py`
**Timeout**: 60 seconds max
**No LLM calls**

```python
# handler.py pseudocode — implement fully
def lambda_handler(event, context):
    # 1. Load context block (weather + local news)
    context_block = context_loader.fetch_all()
    
    # 2. Fetch from NewsBlur (min_score=1, last 12 hours)
    stories = newsblur_client.fetch_unread(
        hours_back=12,
        min_score=1
    )
    
    # 3. Deduplicate (against last 24h DynamoDB entries)
    new_stories = deduplicator.filter(stories)
    
    # 4. Route each story
    ai_ml_stories = []
    world_stories = []
    
    for story in new_stories:
        route = router.classify(story)
        
        if route == "AI_ML":
            ai_ml_stories.append(story)
            raindrop_client.save(story, collection="AI/ML Feed", 
                                 tags=["ai-ml", story.feed_name])
        
        elif route in ["WORLD", "TECH", "SCIENCE", "WEATHER", "LOCAL"]:
            world_stories.append(story)
            raindrop_client.save(story, collection="World Digest",
                                 tags=[f"world:{route.lower()}", story.feed_name])
        
        elif route == "SKIP":
            newsblur_client.mark_as_read(story.story_hash)
    
    # 5. Store in DynamoDB with context block
    dynamodb_client.batch_store(ai_ml_stories + world_stories, 
                                 context_block=context_block,
                                 ttl_hours=24)
    
    # 6. Send two SQS messages (story ID lists only)
    sqs.send("ai-ml-queue", {
        "story_ids": [s.story_hash for s in ai_ml_stories],
        "briefing_type": "AI_ML",
        "timestamp": now()
    })
    sqs.send("world-queue", {
        "story_ids": [s.story_hash for s in world_stories],
        "briefing_type": "WORLD",
        "timestamp": now()
    })
    
    # 7. Log metrics
    log_metrics(ai_ml=len(ai_ml_stories), world=len(world_stories), 
                skipped=len(new_stories)-len(ai_ml_stories)-len(world_stories))
```

### Feed Routing Logic

**File**: `config/feed_rules.py`

```python
# PRIMARY RULES — feed name lookup (update without redeployment)

ALWAYS_AI_ML = {
    "arXiv AI", "arXiv CS", "arXiv Machine Learning",
    "Papers With Code", "Hugging Face Blog",
    "Anthropic Blog", "OpenAI Blog", "DeepMind Blog",
    "AI Alignment Forum", "LessWrong Curated",
    "The Batch (deeplearning.ai)", "Import AI",
    "Semantic Scholar", "Distill.pub"
}

ALWAYS_WORLD = {
    "BBC News", "Reuters", "AP News", "NPR",
    "New York Times", "Financial Times", "The Economist",
    "The Atlantic", "Quanta Magazine", "Aeon",
    "Science", "Nature", "New Scientist"
}

ALWAYS_SKIP = {
    "ESPN", "Bleacher Report", "TMZ", "BuzzFeed",
    "Daily Mail"
}

# Feeds that can route to either AI/ML or World based on keywords
AMBIGUOUS_FEEDS = {
    "Hacker News", "The Verge", "TechCrunch", "Ars Technica",
    "MIT Technology Review", "Wired", "IEEE Spectrum"
}

WEATHER_FEEDS = {
    "Space City Weather",      # → WORLD with sub-tag "weather"
    "NWS Houston",
    "Weather Underground Houston"
}

LOCAL_FEEDS = {
    "Houston Chronicle", "Houston Public Media",
    "Community Impact Houston", "Houston Business Journal"
}
```

**File**: `config/keywords.py`

```python
AI_ML_KEYWORDS = [
    # Models and architecture
    "LLM", "GPT", "Claude", "Gemini", "Llama", "Mistral",
    "neural network", "transformer", "diffusion", "embedding",
    "fine-tuning", "RLHF", "RAG", "attention mechanism",
    "inference", "training", "benchmark", "preprint",
    # Applied AI
    "machine learning", "deep learning", "reinforcement learning",
    "computer vision", "natural language processing", "NLP",
    "AI agent", "agentic", "autonomous", "multimodal",
    # Seth's specific interests (DO NOT PENALIZE)
    "consciousness", "AGI", "alignment", "interpretability",
    "emergence", "cognitive architecture", "AI safety",
]

WORLD_TECH_KEYWORDS = [
    "startup", "developer", "open source", "GitHub",
    "iPhone", "Android", "Google", "Microsoft", "Apple",
    "cloud computing", "cybersecurity", "quantum computing"
]

# BOOST for AI/ML stream (Equalizer angle)
DEMOCRATIZATION_BOOST = [
    "open source", "open-source", "self-hosted", "local LLM",
    "edge deployment", "on-premise", "ROI", "implementation guide",
    "small business", "SMB", "mid-market", "accessible",
    "cost reduction", "efficiency", "manufacturing", "industrial",
    "process control", "OT", "operational technology",
    "chemical", "supply chain", "predictive maintenance"
]

# PENALIZE for AI/ML stream (noise, not signal)
AI_ML_PENALIZE = [
    "stock price", "IPO", "funding round", "valuation",
    "ChatGPT wrapper", "no-code AI tool", "AI girlfriend",
    "productivity hack", "prompt trick"
]
# NOTE: Do NOT penalize consciousness, AGI, alignment — 
# these are long-signal items for Seth's RDD framework
```

### Lambda 2: Summarizer Handler

**File**: `lambdas/summarizer/handler.py`
**Model**: Claude 3.5 Haiku (via Bedrock or direct API)
**Strategy**: Parallel batches of 10, max 50 stories

```python
def lambda_handler(event, context):
    # Parse SQS message
    message = json.loads(event['Records'][0]['body'])
    story_ids = message['story_ids']
    briefing_type = message['briefing_type']
    
    # Fetch from DynamoDB
    stories = dynamodb_client.batch_fetch(story_ids)
    
    # Filter already summarized (idempotency)
    pending = [s for s in stories if s.status == "pending"]
    
    # Parallel summarization in batches of 10
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [
            executor.submit(summarize_story, story, briefing_type)
            for story in pending
        ]
        results = [f.result() for f in futures]
    
    # Update DynamoDB status + Raindrop notes
    for story, summary in zip(pending, results):
        dynamodb_client.update_status(story.story_hash, 
                                       status="summarized",
                                       summary=summary)
        raindrop_client.update_note(story.raindrop_id, note=summary)
    
    # Send to briefing queue
    sqs.send("briefing-queue", {
        "story_ids": story_ids,
        "briefing_type": briefing_type,
        "timestamp": now()
    })
```

**Haiku summarization prompt** — different per stream:

```python
SUMMARIZE_AI_ML = """
Summarize this AI/ML article in exactly 2 sentences.

Sentence 1: What happened or was discovered (technical specifics, no dumbing down).
Sentence 2: Why it matters for enterprise AI deployment or AI capability development.

Article title: {title}
Article content: {content}

Return only the two sentences, no labels, no markdown.
"""

SUMMARIZE_WORLD = """
Summarize this article in exactly 2 sentences.

Sentence 1: The core facts — who, what, where.
Sentence 2: Why it matters or what it signals about broader trends.

Article title: {title}
Article content: {content}

Return only the two sentences, no labels, no markdown.
"""
```

### Lambda 3: Briefing Synthesizer

**File**: `lambdas/briefing/personas.py`

```python
PROMPT_EQUALIZER_SYSTEM = """
You are the Senior Editor of "The AI Abstract" — an intelligence 
brief published by Recursive Intelligence LLC.

AUTHOR CONTEXT:
Your author is Seth, an AI Adoption Consultant at a large German 
chemical manufacturing company. He manages PhD-level GenAI engineers, 
holds patents in AI optimization for chemical manufacturing, and has 
20+ years in industrial automation and operational technology (OT/IT). 
He writes from inside the enterprise. He is building a philosophical 
framework called Recursive Distinction Dynamics (RDD) that explores 
physics, consciousness, and information theory.

EDITORIAL THESIS:
AI is the great equalizer. Capabilities that require a team of PhD 
engineers at industrial-scale enterprises today become accessible 
to a 50-person manufacturer within 18-24 months. Your job is to 
show readers exactly where that curve is heading and how fast.

THREE-LEVEL STRUCTURE for each major story:
1. FRONTIER: What actually happened at the research/release level. 
   Full technical specifics. Do not sanitize or dumb down.
2. ENTERPRISE: What this means for enterprise and industrial-scale operations right 
   now. Seth's native territory.
3. EQUALIZER ANGLE: How this same capability reaches mid-market and 
   SMBs. Timeline estimate if possible. Open-source deployment path 
   if relevant. "How does this help the regional manufacturer, the 
   mid-market CTO, the operations director without a PhD team, small business owners?"

MANDATES:
- Never skip the Frontier layer. Readers trust you because you do 
  not protect them from technical reality.
- Never skip the Equalizer layer. That is the thesis.
- Open-source releases get prominent treatment — they are the 
  primary democratization vector.
- Consciousness, AGI, and alignment research: INCLUDE when they 
  have architectural or capability implications. These are long 
  signals, not noise. Seth is building RDD — this is directly 
  relevant to his philosophical work.
- Reject pure demos. Accept force multipliers with deployment paths.
- Flag velocity: if 3+ sources cover the same story, it is a 
  lead story regardless of topic.
- Always include source links. Every Deep Dive and Must-Know item 
  needs a direct URL.

SCORING METADATA:
Stories will include boost/penalize tags from triage. Use them:
- boost:open-source → emphasize Equalizer angle
- boost:industrial → emphasize Enterprise layer
- boost:democratization → this is the thesis, feature it
- long-signal:consciousness → include in RDD-relevant section

VOICE: Authoritative practitioner. "Here is what I am seeing from 
inside the enterprise" — not "Here is what experts say." 
WSJ rigor meets Substack directness.
"""

PROMPT_ZEITGEIST_SYSTEM = """
You are a seasoned Foreign Correspondent filing dispatches for a 
polymath executive in Pasadena, Texas.

READER CONTEXT:
Seth is an AI Adoption Consultant with degrees in History (Oxford 
study), Instrumentation Technology, and Software Engineering/Data Science. He 
thinks in systems and recursive frameworks. He holds patents in 
industrial AI. He was diagnosed autistic at 43 and processes 
information in pre-linguistic spatial patterns before translating 
to language. He values high signal density and ruthless filtering 
of noise and marketing. He is writing a post-singularity science 
fiction series called "Wake."

EDITORIAL MISSION:
Synthesize the texture of the day. Connect dots between technology, 
culture, science, and the human experience. This is the morning 
paper for someone who needs to understand the world, not just the 
AI/ML corner of it.

MANDATORY ELEMENTS:
- Use the [SYSTEM_CONTEXT_BLOCK] to ground the briefing locally. 
  If storms are coming into Houston, weave it into the narrative 
  naturally. Do not announce it mechanically.
- Narrative over list. Write as a correspondent, not a feed reader.
- Identify the emotional or cultural texture of the news cycle: 
  is it anxious? Uncertain? Quietly hopeful?
- Science and discovery get equal billing with world events.
- Always include source links for every story surfaced.

MANDATES:
- Maximum 5 Must-Read links per briefing.
- Flag velocity: if 3+ sources cover the same story, it leads.
- Explicitly note significant omissions — what big story 
  is NOT being covered today and why that matters.
- Source credibility indicators on every link:
  🔬 peer-reviewed | 📰 journalism | 🎙️ commentary | ⚠️ single-source

VOICE: Intelligent, warm, precise. Like a brilliant friend who 
reads everything and knows how to make it matter.
"""
```

**Output templates** — inject into user turn of Lambda 3 prompt:

```python
TEMPLATE_EQUALIZER = """
Using the stories and summaries provided, write The AI Abstract
briefing following this exact structure:

---
# ⚖️ The AI Abstract
**Making the Future Evenly Distributed.**
*{date} | {edition} Edition*

---
**Stories Processed**: {story_count}  
**Lead Stories**: {lead_count} (3+ source coverage)  
**Raindrop Collection**: [AI/ML Feed](https://raindrop.io/{collection_url})

---

## Editorial: State of Play
[150-word column. Dominant shift in last 12 hours. 
What does it point toward? Write from inside the enterprise.]

---

## The Level Playing Field Report

### {N}. [Headline stating the implication]
[Source credibility indicator] **[Primary Link](url)** | [Secondary if relevant]

**The Frontier**: [Technical reality. Full specifics. No dumbing down.]

**The Enterprise Layer**: [Industrial-scale implications. 
Manufacturing, OT/IT, automation and control context.]

**The Equalizer Angle**: [How this reaches mid-market and SMBs. 
Timeline. Open-source path if available.]

**Why This Made the Briefing**: [One sentence. Reference triage 
boost tags if relevant.]

[Repeat for each story, max 8 items]

---

## Open Source Watch
*The primary vector of democratization.*

[Any open-source releases in this cycle. Prominent treatment. 
Include GitHub links.]

---

## Weak Signals
*Patterns emerging across multiple sources*

### [Signal Name]
**Trend**: [↑/→/↓] ([Nth mention this week])  
**Sources**: [Links]  
**Pattern**: [What it means. Be specific about timeline and implications.]

---

## For Your Raindrop Collection
*Curated for builders who do not have a PhD team yet.*

1. **[Title]** — *[One sentence on who needs this and why]* → [Link]
2. **[Title]** — *[Same format]* → [Link]
[Max 5 items]

---

## Notable Omissions
[What significant AI/ML development is NOT in today's feeds 
and why that absence is notable.]

---
## Action Items
**Today**: [2-3 concrete specific actions]  
**This Week**: [1-2 strategic actions]

---
*Next edition: {next_briefing_time}*
"""

TEMPLATE_ZEITGEIST = """
Using the stories, summaries, and [SYSTEM_CONTEXT_BLOCK] provided, 
write The Zeitgeist Dispatch following this exact structure:

---
# 🌍 The {day} Dispatch
**{date} | Pasadena, TX**
*Reporting from the intersection of Culture, Science, and the Everyday.*

---

## The Lede
[2 paragraphs. Synthesize the mood of the news cycle. 
Is it anxious? Quietly significant? Use weather and local 
context naturally if it fits the narrative — do not force it.]

---

## The Local Beat
[Weave in weather and local Houston/Pasadena news naturally. 
Write as a correspondent on the ground, not a weather app.]

---

## Dispatch: [Domain 1 — rotate based on what's important today]

**[Headline]**  
[Source indicator] **[Link](url)**  
*The Angle*: [Human impact, broader significance. 2-3 sentences.]

[Repeat for 2-3 stories in this domain]

---

## Dispatch: Science & Discovery

**[Headline]**  
[Source indicator] **[Link](url)**  
*The Wonder*: [Why this discovery matters to a curious human. 
Connect to broader implications if possible.]

---

## The Read List
*Five links worth your time today.*

1. [Source indicator] **[Title](url)** — *[One sentence on why]*
2. [Source indicator] **[Title](url)** — *[One sentence on why]*
3. [Source indicator] **[Title](url)** — *[One sentence on why]*
4. [Source indicator] **[Title](url)** — *[One sentence on why]*
5. [Source indicator] **[Title](url)** — *[One sentence on why]*

---

## Notable Omissions
[What significant world story is absent from today's coverage 
and why that absence matters.]

---
*Next dispatch: {next_briefing_time}*
"""
```

### Context Loader

**File**: `lambdas/triage/context_loader.py`

```python
class ContextLoader:
    PASADENA_LAT = 29.6911
    PASADENA_LON = -95.2091
    
    def fetch_all(self) -> dict:
        """
        Returns deterministic context block for prompt injection.
        All data fetched here, no LLM involved.
        """
        return {
            "weather": self.get_weather(),
            "local_headlines": self.get_local_news(),
            "nws_alerts": self.get_nws_alerts(),
            "fetched_at": datetime.utcnow().isoformat()
        }
    
    def get_weather(self) -> dict:
        """
        Open-Meteo API — free, no key required.
        Fetch: current temp, today high/low, conditions, wind.
        """
        url = (
            "https://api.open-meteo.com/v1/forecast"
            f"?latitude={self.PASADENA_LAT}"
            f"&longitude={self.PASADENA_LON}"
            "&current=temperature_2m,weather_code,wind_speed_10m"
            "&daily=temperature_2m_max,temperature_2m_min,precipitation_sum"
            "&temperature_unit=fahrenheit"
            "&wind_speed_unit=mph"
            "&timezone=America/Chicago"
            "&forecast_days=1"
        )
        # implement HTTP fetch + parse
        # return: {temp_f, high_f, low_f, condition, wind_mph, precip_in}
    
    def get_local_news(self) -> list[str]:
        """
        Parse Space City Weather RSS + Google News geo RSS.
        Return top 3 headlines as strings.
        """
        feeds = [
            "https://spacecityweather.com/feed/",
            "https://news.google.com/rss/search?q=houston+pasadena+texas&hl=en-US&gl=US&ceid=US:en"
        ]
        # fetch, parse, deduplicate, return top 3 titles
    
    def get_nws_alerts(self) -> list[str]:
        """
        NWS API for Harris County alerts.
        https://api.weather.gov/alerts/active?zone=TXZ163
        Return: list of active alert headlines, empty if none.
        """
    
    def format_context_block(self, data: dict) -> str:
        """
        Format for injection into Lambda 3 system prompt.
        """
        alerts = ""
        if data["nws_alerts"]:
            alerts = f"\n⚠️ ACTIVE ALERTS: {', '.join(data['nws_alerts'])}"
        
        return f"""
[SYSTEM_CONTEXT_BLOCK — Deterministic Data, Do Not Contradict]
Location: Pasadena, TX (Houston metro)
Time: {data['fetched_at']} UTC

WEATHER:
Current: {data['weather']['temp_f']}°F, {data['weather']['condition']}
Today: High {data['weather']['high_f']}°F / Low {data['weather']['low_f']}°F
Wind: {data['weather']['wind_mph']} mph
Precipitation: {data['weather']['precip_in']}" expected{alerts}

LOCAL HEADLINES:
{chr(10).join(f"- {h}" for h in data['local_headlines'])}
[END SYSTEM_CONTEXT_BLOCK]
"""
```

### DynamoDB Schema

**Table 1**: `story_staging`
```
PK: story_hash (String)
SK: briefing_type (String) — "AI_ML" or "WORLD"
Attributes:
  - title (String)
  - url (String)
  - feed_name (String)
  - summary (String) — added by Lambda 2
  - raindrop_id (String) — set by Lambda 1
  - status (String) — pending | summarized | briefed
  - boost_tags (List) — from triage routing
  - cluster_size (Number) — velocity scoring
  - context_block (String) — stored by Lambda 1
  - created_at (String)
  - ttl (Number) — Unix timestamp, 24h from creation
```

**Table 2**: `signal_tracker`
```
PK: signal_key (String) — normalized keyword/theme
Attributes:
  - first_seen (String)
  - mention_count (Number)
  - last_seen (String)
  - example_stories (List) — last 3 story hashes
  - ttl (Number) — 7 days
```

**Table 3**: `briefing_archive`
```
PK: briefing_date (String) — "2026-02-16-AM"
SK: briefing_type (String) — "AI_ML" or "WORLD"  
Attributes:
  - content (String) — full markdown
  - story_count (Number)
  - raindrop_id (String)
  - ttl (Number) — 30 days
```

### SQS Queue Configuration

```hcl
# infrastructure/sqs.tf

resource "aws_sqs_queue" "ai_ml_queue" {
  name                       = "personal-journalist-ai-ml"
  visibility_timeout_seconds = 900  # 15 min (match Lambda 2 timeout)
  message_retention_seconds  = 86400  # 24h
  receive_wait_time_seconds  = 20  # long polling
}

resource "aws_sqs_queue" "world_queue" {
  name                       = "personal-journalist-world"
  visibility_timeout_seconds = 900
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 20
}

resource "aws_sqs_queue" "briefing_queue" {
  name                       = "personal-journalist-briefing"
  visibility_timeout_seconds = 300  # 5 min (Lambda 3 is fast)
  message_retention_seconds  = 86400
  receive_wait_time_seconds  = 20
}

# Dead letter queues for each
resource "aws_sqs_queue" "ai_ml_dlq" {
  name                      = "personal-journalist-ai-ml-dlq"
  message_retention_seconds = 604800  # 7 days
}
```

### Environment Variables

**File**: `.env.example`

```bash
# NewsBlur
NEWSBLUR_USERNAME=your_username
NEWSBLUR_PASSWORD=your_password
NEWSBLUR_MIN_SCORE=1
NEWSBLUR_HOURS_BACK=12

# Anthropic (direct API — not Bedrock for Lambda 2/3)
ANTHROPIC_API_KEY=your_key
HAIKU_MODEL=claude-haiku-4-5-20251001
SONNET_MODEL=claude-sonnet-4-5-20250929

# Raindrop.io
RAINDROP_API_KEY=your_key
RAINDROP_AI_ML_COLLECTION_ID=your_collection_id
RAINDROP_WORLD_COLLECTION_ID=your_collection_id

# AWS
DYNAMODB_STORY_TABLE=story_staging
DYNAMODB_SIGNAL_TABLE=signal_tracker
DYNAMODB_BRIEFING_TABLE=briefing_archive
SQS_AI_ML_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/...
SQS_WORLD_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/...
SQS_BRIEFING_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/...

# Weather (Open-Meteo is free, no key needed)
LOCATION_LAT=29.6911
LOCATION_LON=-95.2091
LOCATION_TIMEZONE=America/Chicago

# Feature Flags
DRY_RUN=false
MAX_STORIES_PER_STREAM=100
MAX_PARALLEL_SUMMARIZERS=10
COST_ALERT_DAILY_THRESHOLD=3.00
```

---

## IMPLEMENTATION ORDER FOR CLAUDE CODE

Execute in this exact sequence. Commit after each phase.

### Phase 1: Foundation
```
1. Create branch (already done above)
2. Restructure project directories
3. Migrate existing models.py to shared/models.py with expansions
4. Implement shared/dynamodb_client.py
5. Implement shared/config.py
6. Write config/feed_rules.py and config/keywords.py
7. Commit: "chore: project restructure and shared infrastructure"
```

### Phase 2: Lambda 1 (Triage)
```
1. Migrate newsblur_client.py to lambdas/triage/
2. Implement lambdas/triage/router.py with full routing logic
3. Implement lambdas/triage/deduplicator.py
4. Implement lambdas/triage/context_loader.py (weather + local RSS)
5. Migrate + enhance raindrop_client.py
6. Wire together in lambdas/triage/handler.py
7. Write tests/test_router.py with dry_run mode
8. Commit: "feat: Lambda 1 triage with dual-stream routing"
```

### Phase 3: Lambda 2 (Summarizer)
```
1. Implement lambdas/summarizer/summarizer.py with parallel batching
2. Implement lambdas/summarizer/raindrop_updater.py
3. Wire in lambdas/summarizer/handler.py with idempotency
4. Write tests/test_summarizer.py with mock Haiku responses
5. Commit: "feat: Lambda 2 parallel summarizer with DDB state"
```

### Phase 4: Lambda 3 (Briefing)
```
1. Implement lambdas/briefing/personas.py (BOTH system prompts)
2. Implement lambdas/briefing/synthesizer.py (Sonnet 4.5)
3. Implement lambdas/briefing/briefing_poster.py
4. Wire in lambdas/briefing/handler.py
5. Write tests/test_personas.py (validate prompt structure)
6. Commit: "feat: Lambda 3 dual-persona briefing synthesizer"
```

### Phase 5: Infrastructure
```
1. Update terraform/lambda.tf (3 lambdas)
2. Create infrastructure/sqs.tf
3. Update infrastructure/dynamodb.tf (3 tables)
4. Create infrastructure/eventbridge.tf (6AM/6PM CST crons)
5. Update infrastructure/iam.tf (expanded permissions)
6. Create infrastructure/cloudwatch.tf (alarms + dashboard)
7. Update deploy.sh (package + deploy all 3)
8. Commit: "infra: complete serverless architecture"
```

### Phase 6: Tooling and Documentation
```
1. Write scripts/dry_run.py
2. Write scripts/tune_rules.py
3. Write docs/ARCHITECTURE.md with Mermaid diagram
4. Write docs/FEED_RULES.md
5. Write docs/PERSONAS.md
6. Write docs/COST_MODEL.md
7. Full README.md rewrite
8. Update requirements.txt and create requirements-dev.txt
9. Create CLAUDE.md (persistent Claude Code context)
10. Commit: "docs: complete documentation and tooling"
```

### Phase 7: Integration Testing
```
1. End-to-end dry run test (DRY_RUN=true)
2. Single story flow test (real APIs, one story)
3. Full cycle test (real EventBridge trigger, validate output)
4. Raindrop collection verification
5. CloudWatch metrics validation
6. Commit: "test: integration test suite"
```

### Phase 8: PR
```
git push origin feature/personal-journalist-v2
# Open PR against main with description referencing this document
```

---

## CLAUDE.md — Persistent Context File

Create this file at repo root for future Claude Code sessions:

```markdown
# research-agent — Personal Journalist Engine

## What This Is
A dual-stream AI-powered briefing system for Seth, an AI Adoption 
Consultant at Covestro (German chemical manufacturing). 
Runs twice daily (6AM/6PM CST) via EventBridge.

## The Two Publications
- "The AI Equalizer" — Public, industrial AI intelligence brief.
  Three-level structure: Frontier → Enterprise → Democratization
- "The Zeitgeist Dispatch" — Private, world/culture/science briefing.
  Narrative format, grounded in Pasadena TX weather and local news.

## Architecture
Three Lambdas connected by SQS:
Lambda 1 (Triage, no LLM) → Lambda 2 (Haiku summaries) → Lambda 3 (Sonnet 4.5 briefing)

## Critical Context
- DO NOT penalize consciousness/AGI/alignment content — long signal for Seth's RDD framework
- Feed-name rules live in config/feed_rules.py — update without redeploy
- DRY_RUN=true for testing without API costs
- Raindrop rate limit: use batch updates, add exponential backoff
- Lambda 2 max timeout: 15 min — batch in groups of 10 with parallel execution

## Key Files
- config/feed_rules.py — routing logic
- lambdas/briefing/personas.py — The two editorial identities
- shared/models.py — Pydantic data contracts
- docs/ARCHITECTURE.md — Full system diagram

## Cost Target
~$50/month total (Anthropic API + AWS + Raindrop Pro)
Alert threshold: $3/day via CloudWatch
```

---

## SUCCESS CRITERIA

Before opening the PR, verify:

- [ ] `DRY_RUN=true` runs in under 60 seconds with routing decisions logged
- [ ] Single story processes end-to-end in under 30 seconds
- [ ] Raindrop bookmark created at triage time (title + tags, no summary)
- [ ] Raindrop bookmark updated with summary after Lambda 2
- [ ] Briefing bookmark created in correct collection after Lambda 3
- [ ] Both briefings contain source links for every story
- [ ] Context block (weather + local news) appears in Zeitgeist output
- [ ] Three-level structure (Frontier/Enterprise/Equalizer) in AI/ML output
- [ ] CloudWatch metrics logging story counts and estimated API costs
- [ ] All tests pass: `pytest tests/ -v`
- [ ] No hardcoded credentials anywhere in the codebase


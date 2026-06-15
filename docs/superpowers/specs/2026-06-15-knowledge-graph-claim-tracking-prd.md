# Knowledge Graph / Claim-Tracking — PRD

## Status

Pre-brainstorming. This PRD captures the full scope discussed so far so it can be
decomposed into GitHub issues with explicit blocker/dependency relationships and
brainstormed/built incrementally, sub-project by sub-project. Tracking issue: #21.

---

## 1. Origin: adversarial review findings (2026-06-12, "The AI Abstract")

Before any knowledge-graph discussion, four adversarial-review personas were
dispatched against 18 days of published AI/ML briefs (2026-05-14 → 2026-06-12).
Their findings motivate this whole effort — not as a UX problem, but as a
**trust/precision problem in the underlying pipeline** that a knowledge graph is
positioned to address structurally.

### 1.1 Potential customer (SMB owner, Google-search entry point)

- Lands on a brief expecting "should I hire this person for AI work," gets a
  grad-seminar-level mechanistic deep dive (negation neglect, persona-model
  collapse, gradient signal mechanics).
- **Zero translation layer** between "the smart stuff he knows" and "the stuff
  I'd pay him for." No bio, no "why this matters for your business" framing, no
  visible services/CTA.
- Net effect: research depth reads as *credibility* but also as *mismatch* —
  "this person's head is in arXiv, not in my unglamorous CRM integration."
- **Not subscribing** as-is; would need a separate, lower-frequency,
  jargon-free "practical AI for business owners" product.

### 1.2 Marketing/SEO review (all 18 entries, representative sample of 10)

- **Biggest issue:** "research aggregator wearing a consulting-firm's
  homepage." Strong differentiated synthesis product, wrong audience framing.
- **SEO:** titles 100% identical across all 18 posts ("The AI Abstract —
  Morning Edition") — zero keyword differentiation, self-inflicted and
  trivially fixable. Summaries are framed as *findings*, not as *searches* —
  one inferential layer away from what someone would actually type.
- **Audience-market fit:** assumes reader already knows GRPO, RASP, SAEs,
  KV-cache compression, RLHF. Real audience is ML engineers / technical
  due-diligence people, not the stated SMB/founder audience.
- **Conversion path:** effectively absent — no CTA, no "this is the failure
  mode I help teams catch before deployment" bridge from finding →
  practitioner implication for buyers.
- **Differentiation (genuinely strong, underexploited):** cross-paper
  synthesis and **"signal cluster" tracking** ("language cluster, 385 mentions
  since February") is a real moat nobody else does publicly — but it's silent,
  not surfaced as a differentiator.
- **Brand risk:** tone is good (appropriately skeptical of hype, explicit
  "treat this carefully" caveats on contested claims) — but volume/density
  risks reading as "100% reading papers, 0% building things," backwards for a
  consulting pitch.
- Fix order proposed: (1) differentiate titles, (2) one bridging sentence per
  post (finding → builder/deployer implication), (3) consider a parallel
  zero-jargon "translated" weekly digest from the same pipeline.

### 1.3 Research-agent customer — biotech/regulatory-affairs persona

This persona is the one most directly relevant to the knowledge-graph
discussion below, because it independently arrives at "narrative lineage" and
"trust calibration" as the two load-bearing requirements.

- **Translatability — keep this:** mechanism-first framing ("here's *why* this
  matters, not just what happened") and **cross-day cluster-tracking**
  ("third time CDER has touched biosimilar interchangeability standards this
  month") are exactly the pattern-detection a regulatory-intelligence team
  needs versus raw FDA.gov RSS noise.
- **What doesn't transfer:** the 🔬/📰 source-tiering emoji scheme assumes a
  two-tier arXiv-preprint/secondary-reporting world. Regulatory affairs' source
  diet (Federal Register, FDA guidance drafts, EMA reflection papers, warning
  letters, advisory-committee transcripts, competitor SEC filings,
  ClinicalTrials.gov, PMDA) has no arXiv-equivalent steady-cadence firehose —
  would need a different ingestion layer emphasizing **change detection
  (diffing guidance documents)** over "summarize the new thing." (Out of scope
  for this PRD — noted for completeness.)
- **Trust calibration — "biggest worry":** several suspiciously precise
  numbers (98.42% repeated-position rate, 0.150 vs 0.908 correlation, 94%
  brain-signal recovery) presented with total confidence. In AI/ML discourse a
  hallucinated number is low-cost. In a regulatory-strategy memo or FDA
  correspondence, a fabricated/mis-extracted figure is "not an embarrassment,
  that's a credibility and potentially legal exposure problem."
- **Value proposition:** infrastructure, not output — an internal triage
  digest analysts use before reading primary sources, not publishable
  thought leadership, for a regulated industry.
- **Dealbreaker:** no visible verification/correction layer. Publishes daily
  with no fact-check step, and a parallel review already found questionable
  numbers. Needs citation-verification or confidence-flagging *before* trust
  in the underlying engineering — "otherwise I'm commissioning someone to
  automate a liability generator."
- **The pitch this persona wants:** show the failure-handling architecture
  first — how low-confidence extractions are flagged, how sources are cited
  with verifiable links/page numbers, what human review happens before an
  analyst sees it.

### 1.4 AI research analyst — claim-level fact audit

Spot-checked specific numeric/factual claims across the 18-brief corpus.

- **Highest-priority check:** 2026-06-01 brief states OpenAI "disproved the
  Erdős unit distance conjecture," validated by Tim Gowers (sourced to Ars
  Technica, no arXiv ID). Flagged as "the single most dangerous sentence in the
  corpus" — exactly the "AI + math breakthrough + famous mathematician" pattern
  an LLM fabricates by completion, and the *only* claim in the set with no
  falsifiable artifact (no paper ID). **If this is hallucinated, it indicates
  the pipeline fabricates whole findings when the source is non-arXiv — a
  systemic risk, not a one-off.**
- 2026-06-10 "Navigable Manifold of Hypothesized Consciousness-Spectrum
  States" (arXiv 2606.09894) — brief itself hedges appropriately, but flagged
  to verify the paper exists and whether "consciousness-spectrum" is the
  authors' framing or the summarizer's.
- Two near-identical "tells" for invented decimal precision: "98.42%
  repetition" and an accompanying "16.63%" in the same 2026-05-26 brief — real
  numbers often come pre-rounded; two-decimal precision on derived ratios is a
  fingerprint of either faithful-but-odd source reporting or LLM-invented
  rigor.
- 2026-05-25 "recovered 94% of peak brain encoding performance" — round number
  + over-tidy causal framing ("that's the critical number") smells like LLM
  synthesis imposing a thesis the source may not have stated so cleanly.
- 2026-06-11 "F1 of 0.337... random chance floors around 0.1 to 0.2" — the F1
  figure is plausible, but "random chance floors around 0.1-0.2" reads as an
  unsourced comparator invented to make the number land emotionally.
- **arXiv ID sanity check:** IDs are internally consistent with publication
  dates (YYMM.NNNNN), but several briefs cite much older papers (2503, 2507,
  2510-2512, 2601-2604) as "today's payload" peers with no vintage
  distinction — **temporal flattening**. Not fabrication, but a reader would
  assume everything cited is new.
- **Source-tier consistency:** largely flat — the Erdős claim (secondhand tech
  press) gets the same declarative confidence as arXiv preprints with
  methodology sections, even though the pipeline demonstrably *can* hedge well
  (it does so for the consciousness-manifold paper). Calibration capability
  exists, application is inconsistent.
- **"Cluster signal" mechanism — internally inconsistent:** 2026-05-19 "language
  cluster appeared 305 times since February" (~2.9/day, oddly high for a daily
  single-topic brief) vs 2026-05-15 "model cluster, 14 stories over the past
  month" — wildly different scales with no shared units or methodology read as
  a per-brief stylistic flourish rather than a queried metric. **Open
  question the analyst posed directly: is there an actual counter being
  queried, or is this number generated by the LLM each run?** If the latter,
  it's fabricated analytics dressed as a real signal.
- **Bottom-line estimate:** ~60-70% of numeric claims are "faithful-ish"
  (directionally correct, possibly rounded/reframed); failure mode concentrates
  at the edges — secondhand/non-arXiv claims with extraordinary framing,
  unsourced invented comparators, and any analytics-flavored number not tied to
  a cited/queryable source.

### 1.5 What these four reviews establish together

1. The **cluster/signal-tracking mechanism is real differentiated value**
   (1.2, 1.3) but its outputs are **partially or wholly LLM-generated rather
   than queried** (1.4's open question) — i.e., the exact failure mode PR #20
   already fixed for *timeframe phrasing* likely recurs for *cluster counts and
   narrative continuity claims* generally.
2. **Narrative lineage/callback** ("third time CDER has touched this," "since
   February") is independently identified by both the regulatory-affairs
   persona (1.3, as a *strength to keep*) and the research analyst (1.4, as a
   *risk if ungrounded*) — it's valuable precisely because it's the kind of
   claim that's expensive to get wrong.
3. The Erdős/Gowers claim (1.4) is the sharpest illustration of why **claim
   provenance matters**: a claim sourced to secondhand tech press, presented
   with the same confidence as a cited arXiv preprint, with no mechanism to
   later confirm/refute/retract it if it turns out to be wrong.

PR #20 (`coverage_phrase`, merged) already fixed the narrowest instance of
problem #1 — LLM-invented *timeframe phrasing* for `signal_tracker` data. It
was explicitly scoped as a stopgap (see
`docs/superpowers/specs/2026-06-15-signal-age-framing-design.md`). This PRD is
about the general case: **replacing `signal_tracker`'s mention-counter with a
knowledge graph that gives the briefing pipeline real, queryable provenance for
topics, clusters, and claims** — so that "X times since Y," "this is the Nth
time," and "this contradicts/confirms what we said before" are all grounded
facts the LLM is instructed to use verbatim, not text it generates.

---

## 2. Vision: claim tracking with resolution status

A seasoned journalist in this space knows what's already been written. New
coverage of a topic calls back to the original: what was claimed, what's
changed, what's panned out. `signal_tracker`'s mention-counter cannot do this —
it has no concept of:

- **Entity-level dedup across reframing** — recognizing two differently-worded
  stories are about the same underlying topic/entity/paper, beyond same-day
  token-overlap clustering (`velocity.py`).
- **Narrative lineage** — "we covered this on [date], here's what's changed
  since."
- **Claim tracking with resolution status** — a story claims "X will happen by
  Y"; a later story confirms/refutes/updates that claim. Requires claim
  extraction (LLM-assisted), entity linking, and a resolution-status field
  surfaced to the briefing LLM the same way `coverage_phrase` surfaces timing
  today (precomputed, verbatim-use instruction — same pattern as PR #20).

---

## 3. Technology decision

**Recommendation: DynamoDB adjacency-list pattern.**

| Option | Verdict |
|---|---|
| Amazon Neptune (Serverless) | Ruled out — doesn't scale to zero, exceeds ~$50/month budget. |
| Neo4j AuraDB (free tier) | Viable but introduces a new external managed service (auth, latency, Lambda cold-start considerations). |
| **DynamoDB adjacency-list** | **Recommended.** No new infrastructure — direct evolution of `SignalTracker`'s existing table/access patterns. Handles 1-2 hop lookups well (topic → related claims, claim → resolution status). Multi-hop traversal requires multiple round-trips. No native vector/similarity search — would need in-process embedding cosine-sim or a separate vector store for claim-similarity matching. |
| Kuzu (embedded "DuckDB for graphs") | Single-file embedded DB (`data.kz`) persisted to S3, loaded into Lambda `/tmp`. Native Cypher + vector indices in one engine — relevant for claim-similarity matching. **Untested:** whether the `kuzu` Python wheel runs in the Lambda Python runtime without a custom layer (~30-45 min spike against `public.ecr.aws/lambda/python:3.13`). |

Decision: proceed with the DynamoDB adjacency-list as the working assumption.
The Kuzu spike remains an open item under #21 if multi-hop/similarity needs
outgrow DynamoDB later — not a blocker for starting.

---

## 4. Scope decomposition

The full vision is too large for a single spec/plan cycle. It decomposes into
four sequential sub-projects, each independently buildable and testable:

### 4.1 Sub-project 1 — Graph storage layer (recommended starting point)

Replace/extend `SignalTracker`'s DynamoDB table with an adjacency-list schema
capable of representing entities, topics, and edges between them (e.g.
`topic --mentioned_in--> story`, `claim --about--> entity`). Provides the
read/write primitives (`get_node`, `get_edges`, `upsert_node`, `upsert_edge`)
that all later sub-projects build on. No claim extraction or LLM involvement
yet — this is the data-layer foundation, directly analogous to today's
`shared/dynamodb_client.py`.

**Blocks:** 4.2, 4.3, 4.4 (all require the storage layer to exist).

### 4.2 Sub-project 2 — Claim extraction

LLM-assisted extraction of discrete, checkable claims from story content
(e.g. "X predicts Y by Z," "Model A achieves N% on benchmark B"). Writes
extracted claims as nodes into the graph from 4.1, each tagged with source
story, extraction confidence, and a resolution-status field initialized to
`open`.

**Blocked by:** 4.1. **Blocks:** 4.3, 4.4.

### 4.3 Sub-project 3 — Entity linking / claim matching

Given a newly extracted claim (4.2), determine whether it relates to an
existing entity/claim already in the graph (entity-level dedup across
reframing — same underlying topic, different wording). Establishes the
narrative-lineage edges ("this story is a follow-up to claim X from
[date]").

**Blocked by:** 4.1, 4.2. **Blocks:** 4.4.

### 4.4 Sub-project 4 — Resolution-status lifecycle + briefing integration

Resolution-status transitions (open → confirmed / refuted / evolved) based on
linked follow-up claims (4.3), and surfacing this to the briefing LLM via a
precomputed field — same pattern as `coverage_phrase` from PR #20: the LLM is
instructed to use the precomputed status/lineage phrase verbatim rather than
inferring its own narrative continuity.

**Blocked by:** 4.1, 4.2, 4.3.

---

## 5. Relationship to existing work

- PR #20 (merged, `feature/signal-age-framing`) fixed the narrowest instance of
  the "LLM invents framing instead of using real data" failure mode, for
  `signal_tracker`'s timeframe phrasing only. Pattern (precompute → instruct
  verbatim use) is the template for 4.4.
- Issue #21 ("Knowledge graph for topic/claim provenance (replace
  signal_tracker)") is the original tracking issue for this whole effort; this
  PRD supersedes its scope description and should be referenced from the
  decomposed issues created from section 4.
- `signal_tracker` (`shared/dynamodb_client.py`'s `SignalTracker`) remains in
  place and unchanged until 4.1 is built and proven; no "rip and replace"
  before then.

---

## 6. Out of scope (noted, not pursued here)

- A separate ingestion layer for non-arXiv source types (regulatory filings,
  Federal Register, etc.) — raised by the biotech persona (1.3) as a
  *different pipeline*, not part of this knowledge-graph effort.
- A parallel zero-jargon "translated" digest product — raised by the
  marketing/SEO review (1.2) as a content/positioning fix, independent of the
  knowledge-graph/claim-tracking data layer.
- General citation-verification/confidence-flagging UI surfaced to readers
  (1.3's "dealbreaker") — the claim-tracking graph in section 4 is a
  *prerequisite* for this (it gives claims a verifiable identity/lineage to
  attach a confidence/verification flag to), but building the
  reader-facing flagging UI itself is separate follow-on work.

---

## 7. Next steps

1. User review of this PRD.
2. Decompose section 4 into GitHub issues (one per sub-project), with explicit
   `blocked by` / `blocks` links matching the dependency chain in 4.1 → 4.2 →
   4.3 → 4.4, and cross-reference #21.
3. `superpowers:brainstorming` for sub-project 4.1 (graph storage layer) as the
   first buildable unit, producing its own spec under
   `docs/superpowers/specs/`.

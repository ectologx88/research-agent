# Knowledge Graph / Claim-Tracking — PRD

## Status

Pre-brainstorming, revised. An adversarial review of the initial draft (logged
2026-06-15, see section 1.5) found the original 4-sub-project graph plan
conflated a cheap/urgent fix with an expensive/speculative one and proposed
starting with the expensive one. This revision sequences the work as three
phases (section 2) — verify, precompute `source_tier`, extend
`SignalTracker` for lineage — with the full graph deferred to section 4.
Tracking issue: #21 (covers the deferred section 4 only; Phases 0-2 need new
issues).

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

### 1.5 What these four reviews establish together — and what they don't

1. The **cluster/signal-tracking mechanism is real differentiated value**
   (1.2, 1.3) — `SignalTracker.upsert()` maintains a real, queried
   `mention_count`, not an LLM-generated number. PR #20 already fixed the
   *phrasing* of that count (`coverage_phrase`). **The 1.4 "is the cluster
   count itself real or invented?" question has not been independently
   verified against post-PR#20 output** — the 305-vs-14 discrepancy it cites
   is plausibly explained by different `signal_key` granularities (a broad
   "language" cluster vs. a narrow "model" cluster), not fabrication. This
   needs a direct check before it can justify further work.
2. **Narrative lineage/callback** ("third time CDER has touched this," "since
   February") is independently identified by both the regulatory-affairs
   persona (1.3, as a *strength to keep*) and the research analyst (1.4, as a
   *risk if ungrounded*). This is the one finding that genuinely requires
   something beyond a flat mention-counter.
3. **The Erdős/Gowers claim (1.4) is the highest-severity finding in the
   entire review**, and it is a **source-tier / confidence-framing problem at
   generation time**, not a tracking problem. A claim sourced to secondhand
   tech press (no arXiv ID) was presented with the same declarative
   confidence as a cited preprint. A graph that tracks claim lineage over
   *future* briefs would only catch this indirectly, slowly, if a later brief
   happens to contradict it — it does nothing for the day the claim is first
   published with unwarranted confidence.

**Revised framing:** the original draft of this PRD proposed a single
4-stage knowledge-graph project as the answer to all three points above. An
adversarial review of *this PRD* (logged 2026-06-15) found that conflates a
cheap, urgent, well-precedented fix (point 3, and a verification step for
point 1) with an expensive, more speculative project (point 2) — and proposed
starting with the expensive one. This PRD now sequences the work so the
cheap/urgent fixes ship first, using the same precompute-and-instruct-verbatim
pattern as PR #20, and treats the full knowledge graph as a deferred
follow-on scoped down to only what point 2 actually requires.

---

## 2. Revised plan: verify, then precompute, then extend — graph deferred

Three phases, each independently shippable, in priority order:

### Phase 0 — Verify the cluster-count claim (point 1)

Before building anything: check actual recent `signal_tracker` data and
post-PR#20 brief output to confirm whether `mention_count`/`coverage_phrase`
are being surfaced correctly, and whether the 305-vs-14 style discrepancies
are explained by `signal_key` granularity (expected) or are still evidence of
LLM-invented numbers (would mean PR #20 didn't fully close this class of bug).
This is investigation, not a code change — output is either "confirmed fine,
no further action" or "found a residual instance of the PR #20 failure mode,
fix it the same way."

### Phase 1 — `source_tier` precompute (point 3, highest severity)

Directly addresses the Erdős/Gowers-class finding, the most dangerous one in
the corpus. Same pattern as PR #20 (`_annotate_signal_age` /
`coverage_phrase`): a pure helper computes a `source_tier` field per story —
e.g. `arxiv` (has an arXiv ID / from a known-arXiv feed) vs. `secondary`
(tech press, blogs, no paper artifact) — and the persona prompts
(`src/services/personas.py`) are instructed to hedge claims tagged
`secondary` (e.g. "reported by [outlet], not yet independently verified")
rather than stating them with the same confidence as `arxiv`-tier claims.
No new infrastructure, no LLM-based extraction — `source_tier` is derived
from existing story metadata (URL/feed origin, presence of an arXiv ID),
the same kind of deterministic computation `_annotate_signal_age` already
does for timing.

**This phase is the direct, low-cost answer to the PRD's original
motivating finding** and does not depend on Phase 2 or any graph work.

### Phase 2 — Narrative-lineage extension to `SignalTracker` (point 2)

The only point that needs more than a flat counter. Scoped down from "graph
storage layer + claim extraction + entity linking + resolution lifecycle" to
a minimal extension of the existing `SignalTracker` table:

- Add `linked_story_hashes` (list) to each `signal_key` item — appends the
  hash/identifier of each story that contributed to this signal, reusing
  `signal_key` as the entity-dedup key (it's already produced by `velocity.py`'s
  clustering, so no new entity-linking step is needed).
- Add `last_framing` (string) — a short precomputed summary of what was said
  last time this `signal_key` was covered (e.g. derived from the prior
  brief's text for that cluster), surfaced to the LLM the same way
  `coverage_phrase` is: verbatim/lightly-adapted, not recomputed.

This gets most of the "third time CDER has touched this, here's what's
changed" value without LLM-based claim extraction, similarity matching, or a
resolution-status lifecycle — all of which remain unimplemented and are
addressed only in section 4 (deferred).

---

## 3. Technology decision

No new infrastructure is needed for Phases 0-2 — all are extensions of
`SignalTracker` (`shared/dynamodb_client.py`) and the persona prompts
(`src/services/personas.py`), following the PR #20 pattern.

The original technology evaluation (DynamoDB adjacency-list vs. Neo4j AuraDB
vs. Neptune vs. Kuzu) remains relevant **only if** the deferred work in
section 4 is picked up later:

| Option | Verdict |
|---|---|
| Amazon Neptune (Serverless) | Ruled out — doesn't scale to zero, exceeds ~$50/month budget. |
| Neo4j AuraDB (free tier) | Viable but introduces a new external managed service (auth, latency, Lambda cold-start considerations). |
| DynamoDB adjacency-list | Recommended if a real graph is needed — no new infrastructure, direct evolution of `SignalTracker`'s patterns. Handles 1-2 hop lookups well. No native vector/similarity search. |
| Kuzu (embedded "DuckDB for graphs") | Single-file embedded DB persisted to S3/Lambda `/tmp`. Native Cypher + vector indices — relevant if claim-similarity matching is ever built. **Untested** in Lambda runtime (~30-45 min spike needed). |

This decision is deferred along with section 4 — not needed for Phases 0-2.

---

## 4. Deferred: full claim-tracking knowledge graph (not started)

The original 4-sub-project graph concept is preserved here as a scoped-down
follow-on, to be revisited **only if Phase 2's `SignalTracker` extension
proves insufficient** for narrative-lineage needs (e.g. if `last_framing`
text summaries turn out too lossy and genuine claim-level confirm/refute
tracking is wanted).

- **Claim extraction** — LLM-assisted extraction of discrete, checkable
  claims (e.g. "X predicts Y by Z") from story content, each tagged with
  source story, `source_tier` (Phase 1), and a resolution-status initialized
  to `open`. **Open risk, unresolved:** an extraction LLM is subject to the
  same fabrication/over-precision failure mode the adversarial review
  diagnosed in the source pipeline (point 3) — it could preserve or compound
  fabricated precision, or extract a well-formed claim from a fabricated
  sentence, giving the fabrication a persistent tracked identity. Any future
  design here must either scope extraction to structurally-derivable claims
  (paper title + benchmark number + arXiv ID already present in metadata, not
  LLM-synthesized) or explicitly bound extraction reliability to the source
  pipeline's ceiling.
- **Entity linking / claim matching** — beyond `signal_key`-level dedup
  (already handled by `velocity.py` + Phase 2), matching claims across
  reframings via similarity search. This is the point at which DynamoDB's
  lack of native vector search becomes a real constraint (see section 3) —
  any storage-layer design here must account for this from the start, not
  discover it after the schema is fixed.
- **Resolution-status lifecycle + briefing integration** — open → confirmed /
  refuted / evolved transitions, surfaced via a precomputed field, same
  verbatim-use pattern as `coverage_phrase` and Phase 1's `source_tier`.

If picked up, this would need its own `superpowers:brainstorming` cycle,
including the storage-layer/access-pattern design called out above —
not started until Phases 0-2 are complete and a gap is confirmed.

---

## 5. Relationship to existing work

- PR #20 (merged, `feature/signal-age-framing`) established the
  precompute-and-instruct-verbatim pattern (`_annotate_signal_age` /
  `coverage_phrase`) that Phase 1 (`source_tier`) and Phase 2
  (`last_framing`) both reuse directly.
- Issue #21 ("Knowledge graph for topic/claim provenance (replace
  signal_tracker)") is the original tracking issue for the full-graph idea;
  this PRD's section 4 supersedes its scope description as the deferred
  follow-on. Phases 0-2 should be tracked as new, separate issues (not under
  #21, since they don't require or lead to replacing `signal_tracker`).
- `signal_tracker` (`shared/dynamodb_client.py`'s `SignalTracker`) is
  **extended, not replaced**, by Phase 2. No "rip and replace" is planned.

---

## 6. Out of scope (noted, not pursued here)

- A separate ingestion layer for non-arXiv source types (regulatory filings,
  Federal Register, etc.) — raised by the biotech persona (1.3) as a
  *different pipeline*, not part of this effort.
- A parallel zero-jargon "translated" digest product — raised by the
  marketing/SEO review (1.2) as a content/positioning fix, independent of
  signal-tracking/lineage work.
- General citation-verification/confidence-flagging UI surfaced to readers
  (1.3's "dealbreaker") — Phase 1's `source_tier` hedging is a step toward
  this (claims get a confidence framing at generation time) but a
  reader-facing verification UI/mechanism is separate follow-on work, not
  addressed by Phases 0-2 or section 4.

---

## 7. Next steps

1. User review of this PRD.
2. Phase 0: verify the cluster-count claim against real `signal_tracker` /
   brief output — investigation only, no code change unless a residual PR #20
   failure mode is found.
3. `superpowers:brainstorming` for Phase 1 (`source_tier` precompute +
   persona prompt hedging) — small, well-precedented, can start immediately
   after Phase 0 regardless of its outcome.
4. `superpowers:brainstorming` for Phase 2 (`SignalTracker` lineage
   extension) after Phase 1 ships.
5. Section 4 (full graph) remains unscheduled — revisit only if Phase 2 proves
   insufficient.

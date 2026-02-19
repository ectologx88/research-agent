# src/services/editorial_scorer.py
"""Editorial scoring for Lambda 2. Uses Haiku to score each story.

Scoring dimensions (1-5 each, total out of 15):
- journalistic_integrity
- relevance (to Seth's context)
- novelty

Thresholds (from config/scoring_weights.py):
- AI_ML: pass if total >= 9
- WORLD: pass if total >= 8
"""

import json
from dataclasses import dataclass

from config.scoring_weights import AI_ML_PASS_THRESHOLD, WORLD_PASS_THRESHOLD
from shared.logger import log

SCORE_AI_ML_TEMPLATE = """\
You are the editorial filter for "The AI Abstract," an intelligence brief
for an AI Adoption Consultant at a German chemical manufacturer who manages
PhD-level GenAI engineers and publishes thought leadership on AI democratization.

Score this story on three dimensions (1–5 each):

JOURNALISTIC_INTEGRITY: Is this based on verifiable facts, peer-reviewed work,
or primary sources? (5 = peer-reviewed/primary source, 1 = speculation/PR copy)

RELEVANCE: Does this matter to an enterprise AI practitioner building
industrial-scale AI systems?
INCLUDE: research breakthroughs, open-source releases, capability milestones,
consciousness/AGI/alignment content (long-signal for the RDD philosophical framework).
PENALIZE: funding rounds, product demos without deployment path, ChatGPT wrappers,
productivity hacks, no-code AI tools.

NOVELTY: Is this genuinely new information, or rehash? Does the title sound like
the tenth article on the same story this week?

Boost tags from triage are provided — use them to inform relevance scoring:
boost:open-source → elevate relevance (democratization thesis)
boost:industrial → elevate relevance (Seth's native territory)
long-signal:rdd → never penalize; these are long-horizon signals for the RDD framework

Return ONLY valid JSON — no explanation, no markdown:
{{
  "integrity": <1-5>,
  "relevance": <1-5>,
  "novelty": <1-5>,
  "total": <sum>,
  "decision": "PASS" | "REJECT",
  "source_type": "peer-reviewed" | "journalism" | "commentary" | "single-source",
  "reasoning": "<one sentence — why it passes or fails>",
  "summary": "<two sentences if PASS: what happened + why it matters for enterprise AI. null if REJECT>"
}}

Threshold: PASS if total >= {threshold}.

Story title: {title}
Story content: {content}
Feed: {feed_name}
Sub-bucket: {sub_bucket}
Boost tags: {boost_tags}
"""

SCORE_WORLD_TEMPLATE = """\
You are the editorial filter for "The Recursive Briefing," a private daily
dispatch for Seth — an AI Adoption Consultant, systems thinker, autistic
(diagnosed 43), history-trained, patent-holding engineer writing a post-singularity
sci-fi series called "Wake."

Score this story on three dimensions (1–5 each):

JOURNALISTIC_INTEGRITY: Primary sources and verifiable facts score high.
Single-source claims, unverified reports, and opinion pieces score low.

RELEVANCE: Does this matter to a polymath executive in Pasadena, TX who thinks
in systems and recursive frameworks?
INCLUDE: geopolitics, science/discovery, culture, economics, Houston/Texas
local significance. Weather context is always relevant.
INCLUDE entertainment/pop culture IF: culturally significant event, personally
relevant (Ghostbusters collectibles, Apple ecosystem, sci-fi/speculative fiction),
or relevant to the Wake series Seth is writing.
EXCLUDE: entertainment that is merely a product announcement without cultural
weight or personal hook.

NOVELTY: Is this genuinely new, or a daily churn story that will look the same tomorrow?

Return ONLY valid JSON — no explanation, no markdown:
{{
  "integrity": <1-5>,
  "relevance": <1-5>,
  "novelty": <1-5>,
  "total": <sum>,
  "decision": "PASS" | "REJECT",
  "source_type": "peer-reviewed" | "journalism" | "commentary" | "single-source",
  "reasoning": "<one sentence — why it passes or fails>",
  "summary": "<two sentences if PASS: core facts + why it matters. null if REJECT>"
}}

Threshold: PASS if total >= {threshold}.

Story title: {title}
Story content: {content}
Feed: {feed_name}
Sub-bucket: {sub_bucket}
Boost tags: {boost_tags}
"""

_DRY_RUN_RESULT = {
    "integrity": 3, "relevance": 3, "novelty": 3, "total": 9,
    "decision": "PASS", "source_type": "journalism",
    "reasoning": "DRY_RUN mock — real scoring not performed.",
    "summary": "DRY_RUN mock summary sentence one. Mock sentence two.",
}


@dataclass
class ScoringResult:
    integrity: int
    relevance: int
    novelty: int
    total: int
    decision: str  # "PASS" | "REJECT"
    source_type: str
    reasoning: str
    summary: str | None

    @classmethod
    def from_json(cls, raw: str) -> "ScoringResult":
        try:
            # raw_decode stops at the end of the first valid JSON object,
            # tolerating trailing newlines or extra text Haiku sometimes appends.
            data, _ = json.JSONDecoder().raw_decode(raw.strip())
        except json.JSONDecodeError as exc:
            raise ValueError(f"Haiku returned invalid JSON: {exc}\nRaw: {raw[:200]}") from exc
        required = {"integrity", "relevance", "novelty", "total", "decision",
                    "source_type", "reasoning", "summary"}
        missing = required - set(data.keys())
        if missing:
            raise ValueError(f"Haiku response missing fields: {missing}")
        return cls(**{k: data[k] for k in required})

    @property
    def passed(self) -> bool:
        return self.decision == "PASS"


class EditorialScorer:
    """Score stories using Haiku via Bedrock. Thread-safe."""

    def __init__(self, bedrock_client=None, model_id: str = "", dry_run: bool = False):
        self._bedrock = bedrock_client
        self._model_id = model_id
        self._dry_run = dry_run

    def score(
        self,
        briefing_type: str,
        title: str,
        content: str,
        feed_name: str,
        sub_bucket: str,
        boost_tags: list[str],
    ) -> ScoringResult:
        """Score a story. In dry_run mode, returns mock PASS at total=9."""
        if self._dry_run:
            log("INFO", "editorial_scorer.dry_run", title=title[:80], decision="PASS_MOCK")
            return ScoringResult.from_json(json.dumps(_DRY_RUN_RESULT))

        prompt = self._build_prompt(
            briefing_type, title, content, feed_name, sub_bucket, boost_tags
        )
        raw_response = self._call_bedrock(prompt)
        result = ScoringResult.from_json(raw_response)
        log(
            "INFO",
            "editorial_scorer.scored",
            title=title[:80],
            decision=result.decision,
            total=result.total,
            source_type=result.source_type,
        )
        return result

    def _build_prompt(
        self,
        briefing_type: str,
        title: str,
        content: str,
        feed_name: str,
        sub_bucket: str,
        boost_tags: list[str],
    ) -> str:
        threshold = AI_ML_PASS_THRESHOLD if briefing_type == "AI_ML" else WORLD_PASS_THRESHOLD
        template = SCORE_AI_ML_TEMPLATE if briefing_type == "AI_ML" else SCORE_WORLD_TEMPLATE
        return template.format(
            threshold=threshold,
            title=title,
            content=content[:8000],
            feed_name=feed_name,
            sub_bucket=sub_bucket,
            boost_tags=", ".join(boost_tags) if boost_tags else "none",
        )

    def _call_bedrock(self, prompt: str) -> str:
        """Call Bedrock Haiku and return the raw text response."""
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 512,
            "messages": [{"role": "user", "content": prompt}],
        })
        response = self._bedrock.invoke_model(
            modelId=self._model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        resp_body = json.loads(response["body"].read())
        return resp_body["content"][0]["text"]

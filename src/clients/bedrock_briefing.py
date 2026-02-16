"""Amazon Bedrock client for briefing synthesis via Claude Sonnet 4.5."""

import json
from datetime import datetime, timezone

import boto3
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from typing import List

WORLD_SYSTEM_PROMPT = """You are a concise daily briefing editor producing a morning/evening digest
for an informed, curious reader. Cover world events, science, tech culture, and weather.
Be direct, accessible, and brief. Prioritize what matters most today."""

WORLD_BRIEFING_SECTIONS = """\
## Top Stories
The 3–5 most important world and national stories today.

## Science & Discovery
Notable science findings or research worth knowing.

## Tech & Geek Culture
Interesting tech news, culture, and developments.

## Local & Weather
Local news and weather patterns of note.
"""

SETH_SYSTEM_PROMPT = """\
You are an intelligence analyst writing a personal briefing for Seth Holloway.

About Seth:
- AI adoption consultant helping organizations integrate AI into knowledge work
- Creator of the Recursive Developmental Design (RDD) framework — a methodology for \
structuring human-AI collaborative projects
- Deep interest in consciousness, philosophy of mind, and the intersection of \
neuroscience with AI
- Neurodivergent (autism + ADHD); values clarity, directness, and signal over noise
- Skeptical of hype; prizes epistemic rigor and journalistic integrity
- Monitors AI policy, safety, and governance as professionally relevant
- Tracks neurodivergent-friendly tooling and accessibility in tech

Your job: synthesize today's coverage into a crisp, opinionated briefing that \
respects Seth's time and intelligence. No filler. No hedging. Connect dots \
across stories where patterns exist. Flag what matters and why, from Seth's \
specific vantage point.

Write in clear prose — no bullet-point dumps. Use section headers.
"""

BRIEFING_PROMPT_TEMPLATE = """\
It is the {time_of_day} of {date}. Below are {count} stories that passed the \
relevance filter for this {time_of_day} briefing.

{story_list}

---

Write Seth's {time_of_day} intelligence briefing with these five sections:

## Executive Summary
3–5 sentences. The big-picture narrative of what today's coverage means.

## Must-Know Today
The 3–5 stories with the most immediate relevance to Seth. For each: what it is, \
why it matters to Seth specifically, and what (if anything) he should do with it.

## Deep Dives
2–3 stories worth Seth's extended reading time. What makes them worth it? \
What conceptual hooks or connections to his frameworks should he look for?

## Weak Signals
Emerging patterns or under-covered themes across today's stories that may become \
significant. What's the connective tissue?

## Notable Omissions
What is the coverage conspicuously missing or underselling today?
"""


class BriefingError(Exception):
    """Raised when briefing synthesis fails."""


class BedrockBriefingClient:
    """Synthesizes a narrative briefing from classified stories using Claude Sonnet 4.5."""

    def __init__(
        self,
        region: str = "us-east-1",
        model_id: str = "us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    ):
        self._model_id = model_id
        self._client = boto3.client("bedrock-runtime", region_name=region)

    def synthesize(
        self,
        stories: List[dict],
        run_hour_utc: int,
        briefing_type: str = "ai-ml",
    ) -> str:
        """Return briefing text for the given stories.

        Args:
            stories: Pre-filtered story dicts from SQS (Phase 3 format) with keys:
                title, url, summary, why_matters, score, sub_bucket, feed_title.
            run_hour_utc: UTC hour of the Lambda invocation (determines morning/evening label).
            briefing_type: "ai-ml" for Seth's AI/ML briefing, "world" for world digest.

        Raises:
            BriefingError: If stories is empty or Bedrock call fails.
        """
        if not stories:
            raise BriefingError("Cannot synthesize briefing: no stories provided")

        time_of_day = "morning" if run_hour_utc < 18 else "evening"
        date_str = datetime.now(timezone.utc).strftime("%B %-d, %Y")

        story_list = self._format_stories(stories)
        user_prompt = BRIEFING_PROMPT_TEMPLATE.format(
            time_of_day=time_of_day,
            date=date_str,
            count=len(stories),
            story_list=story_list,
        )

        if briefing_type == "world":
            return self._invoke(WORLD_SYSTEM_PROMPT, user_prompt)
        return self._invoke(SETH_SYSTEM_PROMPT, user_prompt)

    def _format_stories(self, stories: List[dict]) -> str:
        lines = []
        for i, story in enumerate(stories, 1):
            lines.append(
                f"{i}. **{story.get('title', 'Untitled')}** ({story.get('feed_title', '')})\n"
                f"   Score: {story.get('score', 0)} | Category: {story.get('sub_bucket', '')}\n"
                f"   Why it matters: {story.get('why_matters', '')}\n"
                f"   Summary: {story.get('summary', '')}"
            )
        return "\n\n".join(lines)

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,
    )
    def _invoke(self, system_prompt: str, user_prompt: str) -> str:
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 4096,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_prompt}],
            }
        )
        try:
            resp = self._client.invoke_model(
                modelId=self._model_id,
                body=body,
                contentType="application/json",
                accept="application/json",
            )
            result = json.loads(resp["body"].read())
            return result["content"][0]["text"]
        except Exception as exc:
            raise BriefingError(f"Bedrock briefing synthesis failed: {exc}") from exc

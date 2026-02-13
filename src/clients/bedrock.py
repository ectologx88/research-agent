"""Amazon Bedrock client for story classification via Claude."""

import json
from datetime import datetime
from typing import List

import boto3
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from src.models.classification import (
    Actionability,
    Classification,
    ContentType,
    RelevanceScores,
)
from src.models.story import Story
from src.utils import log_structured, utcnow

PROMPT_VERSION = "v1"

CLASSIFICATION_PROMPT_V1 = """\
You are an AI research analyst classifying RSS stories for a knowledge worker \
focused on AI/ML, neuroscience, consciousness studies, and content craft.

Analyze the following story and return a JSON classification.

## Story
- Title: {title}
- Source: {feed_title}
- Author: {authors}
- Date: {date}
- URL: {url}

## Content
{content}

## Scoring Rubrics (each 1-10)

### ai_ml
- 9-10: Breakthrough capabilities (new frontier-model release, paradigm shift)
- 7-8: Significant advances (novel technique, major benchmark, new architecture)
- 5-6: Practical applications (company deploys AI, product launch)
- 3-4: Generic AI mentions or surface-level commentary
- 1-2: Tangentially related or not about AI/ML

### neuroscience
- 9-10: Major discoveries about brain function, consciousness, cognition
- 7-8: Significant research findings or new methodologies
- 5-6: Applied neuroscience, brain-computer interfaces
- 3-4: General mentions of neuroscience topics
- 1-2: Not related to neuroscience

### theory
- 9-10: Fundamental insights (physics of consciousness, information-theory breakthroughs)
- 7-8: Novel theoretical frameworks or mathematical models
- 5-6: Theory-adjacent discussion with meaningful depth
- 3-4: Passing references to theoretical concepts
- 1-2: Not related to theory / physics / consciousness / info theory

### content_craft
- 9-10: Masterful thought leadership, paradigm-shifting narrative
- 7-8: Well-crafted analysis with unique perspective
- 5-6: Competent reporting or analysis
- 3-4: Standard news coverage
- 1-2: Low-effort or clickbait content

### overall
Holistic assessment weighing all dimensions. Weight ai_ml and neuroscience \
more heavily when applicable.

## Content Type (choose exactly one)
- breaking_news: Time-sensitive announcements or events
- research: Academic papers, studies, technical reports
- thought_leadership: Opinion pieces, essays, deep analysis
- industry: Business / market news, product launches, funding
- world_news: Geopolitical, policy, regulation, or societal impact

## Actionability Tags (choose all that apply)
- citation_worthy: Contains specific claims, data, or quotes worth referencing
- thought_provoking: Challenges assumptions or introduces novel framing
- time_sensitive: Relevance diminishes significantly after 48 hours
- evergreen: Will remain relevant for months / years

## Response Format
Respond with ONLY valid JSON — no markdown fences, no commentary.
{{
  "scores": {{
    "ai_ml": <int>,
    "neuroscience": <int>,
    "theory": <int>,
    "content_craft": <int>,
    "overall": <int>
  }},
  "content_type": "<string>",
  "actionability": ["<string>", ...],
  "concepts": ["<3-5 specific concepts extracted from the story>"],
  "why_matters": "<one sentence>",
  "summary": "<2-3 sentences>"
}}
"""


class ClassificationError(Exception):
    """Raised when a Bedrock classification call fails."""


class BedrockClassifier:
    """Classifies stories using Claude on Amazon Bedrock."""

    def __init__(
        self,
        region: str = "us-east-1",
        model_id: str = "anthropic.claude-3-5-haiku-20241022-v1:0",
    ):
        self._model_id = model_id
        self._client = boto3.client("bedrock-runtime", region_name=region)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify_story(self, story: Story) -> Classification:
        prompt = CLASSIFICATION_PROMPT_V1.format(
            title=story.story_title,
            feed_title=story.story_feed_title,
            authors=story.story_authors or "Unknown",
            date=story.story_date.isoformat(),
            url=str(story.story_permalink),
            content=story.content_truncated,
        )
        raw = self._invoke(prompt)
        return self._parse(raw, story.story_hash)

    def classify_batch(self, stories: List[Story]) -> List[Classification]:
        results: List[Classification] = []
        for i, story in enumerate(stories, 1):
            try:
                result = self.classify_story(story)
                results.append(result)
                log_structured(
                    "INFO",
                    "Classified story",
                    progress=f"{i}/{len(stories)}",
                    hash=story.story_hash,
                    overall=result.scores.overall,
                )
            except ClassificationError as exc:
                log_structured(
                    "ERROR",
                    "Classification failed",
                    hash=story.story_hash,
                    error=str(exc),
                )
        return results

    # ------------------------------------------------------------------
    # Bedrock invocation
    # ------------------------------------------------------------------

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,
    )
    def _invoke(self, prompt: str) -> str:
        body = json.dumps(
            {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 1024,
                "messages": [{"role": "user", "content": prompt}],
            }
        )
        resp = self._client.invoke_model(
            modelId=self._model_id,
            body=body,
            contentType="application/json",
            accept="application/json",
        )
        result = json.loads(resp["body"].read())
        return result["content"][0]["text"]

    # ------------------------------------------------------------------
    # Response parsing
    # ------------------------------------------------------------------

    def _parse(self, raw_text: str, story_hash: str) -> Classification:
        # Strip markdown fences if the model added them despite instructions
        text = raw_text.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
        if text.endswith("```"):
            text = text.rsplit("```", 1)[0]
        text = text.strip()

        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise ClassificationError(
                f"Invalid JSON from model for {story_hash}: {exc}"
            ) from exc

        try:
            scores = RelevanceScores(**data["scores"])

            content_type = ContentType(data["content_type"])

            actionability = [Actionability(a) for a in data.get("actionability", [])]

            return Classification(
                story_hash=story_hash,
                scores=scores,
                content_type=content_type,
                actionability=actionability,
                concepts=data.get("concepts", [])[:7],
                why_matters=data.get("why_matters", ""),
                summary=data.get("summary", ""),
                classified_at=utcnow(),
                model_version=f"{self._model_id}|prompt={PROMPT_VERSION}",
            )
        except Exception as exc:
            raise ClassificationError(
                f"Failed to build Classification for {story_hash}: {exc}"
            ) from exc

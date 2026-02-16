"""Per-story summarizer using Claude Haiku via Amazon Bedrock."""
import json
from dataclasses import dataclass

import boto3
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.utils import log_structured


@dataclass
class SummaryResult:
    summary: str
    why_matters: str
    score: int  # 1-10


AI_ML_SYSTEM_PROMPT = """You are an expert AI/ML analyst. Summarize research papers and AI industry news
for a technically informed audience interested in the AI/ML field broadly.
Focus on what the work does, why it matters to the field, and how it connects to the evolving AI landscape.
Do NOT personalize — write for any informed reader following AI/ML."""

WORLD_SYSTEM_PROMPT = """You are a concise news editor. Summarize articles clearly for an informed general reader.
Focus on what happened, why it matters, and what people should know.
Be direct and brief."""

SUMMARY_PROMPT = """Summarize this article. Return ONLY valid JSON, no markdown fences.

Title: {title}

Content: {content}

Return this exact JSON structure:
{{
  "summary": "2-3 sentence summary of the article",
  "why_matters": "1 sentence on significance",
  "score": <integer 1-10 for relevance/importance>
}}"""


class BedrockSummarizerClient:
    """Summarizes individual stories using Claude Haiku."""

    def __init__(self, region: str = "us-east-1", model_id: str = "us.anthropic.claude-3-5-haiku-20241022-v1:0"):
        self._model_id = model_id
        self._bedrock = boto3.client("bedrock-runtime", region_name=region)

    @retry(
        retry=retry_if_exception_type(Exception),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=15),
        reraise=True,
    )
    def summarize(self, title: str, content: str, bucket: str) -> SummaryResult:
        """Summarize a single story. Returns SummaryResult with graceful fallback on parse failure."""
        system = AI_ML_SYSTEM_PROMPT if bucket == "ai-ml" else WORLD_SYSTEM_PROMPT
        user = SUMMARY_PROMPT.format(
            title=title,
            content=(content or "")[:3000],  # cap content length
        )

        resp = self._bedrock.invoke_model(
            modelId=self._model_id,
            body=json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 512,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            }),
        )
        raw = json.loads(resp["body"].read())
        text = raw["content"][0]["text"].strip()

        try:
            # Strip markdown fences if present
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            data = json.loads(text)
            score = max(1, min(10, int(data.get("score", 5))))
            return SummaryResult(
                summary=str(data.get("summary", title)),
                why_matters=str(data.get("why_matters", "")),
                score=score,
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            log_structured("WARNING", "Failed to parse summarizer response", title=title)
            return SummaryResult(summary=title, why_matters="", score=5)

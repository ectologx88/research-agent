# src/services/synthesizer.py
"""Briefing synthesizer for Lambda 3. Calls Bedrock Sonnet 4.6 to generate briefings."""
import json
from datetime import datetime, timedelta

from shared.logger import log
from src.services.personas import build_equalizer_prompt, build_zeitgeist_prompt

_DRY_RUN_PLACEHOLDER = "[DRY_RUN] Briefing generation skipped — see prompt in logs."


class BriefingSynthesizer:
    """Synthesize daily briefings via Sonnet 4.6. One instance per Lambda invocation."""

    DEFAULT_MODEL_ID = "anthropic.claude-sonnet-4-6"
    MAX_TOKENS = 4096

    def __init__(
        self,
        bedrock_client=None,
        model_id: str = "",
        dry_run: bool = False,
    ):
        self._bedrock = bedrock_client
        self._model_id = model_id or self.DEFAULT_MODEL_ID
        self._dry_run = dry_run

    def _prior_briefing_key(self, run_date: str, time_of_day: str) -> tuple[str, str]:
        """Return (archive_key, briefing_type) for the immediately preceding edition.

        AM run → yesterday's PM: ("2026-02-16-PM", "AI_ML")
        PM run → today's AM:     ("2026-02-17-AM", "AI_ML")
        """
        if time_of_day == "AM":
            yesterday = (
                datetime.strptime(run_date, "%Y-%m-%d") - timedelta(days=1)
            ).strftime("%Y-%m-%d")
            return (f"{yesterday}-PM", "AI_ML")
        return (f"{run_date}-AM", "AI_ML")

    def synthesize(
        self,
        stories: list[dict],
        run_date: str,
        time_of_day: str,
        briefing_type: str,
        context_block: str,
        signals: list[dict],
        prior_briefing: dict | None,
    ) -> str:
        """Generate a briefing. Returns markdown string.

        In dry_run mode: logs the prompt and returns a placeholder.
        """
        if briefing_type == "AI_ML":
            prompt = build_equalizer_prompt(
                stories=stories,
                signals=signals,
                prior_briefing=prior_briefing,
            )
        else:
            prompt = build_zeitgeist_prompt(
                stories=stories,
                signals=signals,
                prior_briefing=prior_briefing,
                context_block=context_block,
            )

        if self._dry_run:
            log("INFO", "synthesizer.dry_run",
                briefing_type=briefing_type,
                prompt_chars=len(prompt),
                prompt_preview=prompt[:500])
            return _DRY_RUN_PLACEHOLDER

        result = self._call_bedrock(prompt)
        log("INFO", "synthesizer.complete",
            briefing_type=briefing_type,
            output_chars=len(result))
        return result

    def _call_bedrock(self, prompt: str) -> str:
        """Call Bedrock Sonnet and return the response text."""
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": self.MAX_TOKENS,
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

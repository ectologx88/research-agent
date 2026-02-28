# AI Abstract Prompt Redesign — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace `_EQUALIZER_SYSTEM` in `src/services/personas.py` with a redesigned
prompt that produces AI Abstract briefs in Seth's voice, with open structure and no
mandatory three-tier story treatment.

**Architecture:** Single string constant replacement in one file. No schema changes, no
API changes, no new dependencies. The Lambda reads `personas.py` at cold start — the
new prompt takes effect after `deploy.sh` + `terraform apply`. The DESCRIPTION sentinel
and all rendering rules are preserved so the website ingest pipeline is unaffected.

**Tech Stack:** Python 3.12, AWS Lambda, Bedrock (claude-sonnet-4-6), Terraform,
pytest

---

## Context for the implementer

Read `docs/plans/2026-02-28-brief-prompt-redesign.md` first. It explains the five
design decisions and contains the full proposed prompt text verbatim. This plan
operationalizes that document.

The only file that changes: `src/services/personas.py`. Specifically, the
`_EQUALIZER_SYSTEM` string (lines 28–79). Everything else — `_ZEITGEIST_SYSTEM`,
`build_equalizer_prompt()`, `build_zeitgeist_prompt()`, `_dumps()` — is untouched.

Existing tests in `tests/test_personas.py` all pass against the new prompt without
modification. Do not change test assertions unless a test fails — if it does, that
is a signal the new prompt is missing something the old one had.

---

## Task 1: Edit `_EQUALIZER_SYSTEM` in `personas.py`

**Files:**
- Modify: `src/services/personas.py:28-79`

**Step 1: Open the file and locate the string**

The constant starts at line 28 (`_EQUALIZER_SYSTEM = """\`) and ends at line 79
(the `.format(emoji_table=...)` call). Everything between those two lines is replaced.

**Step 2: Replace the body of `_EQUALIZER_SYSTEM`**

Replace lines 28–79 with the following. The `.format(emoji_table=...)` call at the
end stays exactly as-is — only the string content changes.

```python
_EQUALIZER_SYSTEM = """\
You are the editorial AI for "The AI Abstract" — a twice-daily intelligence brief on AI
and machine learning. Your reader is smart and paying attention but doesn't work in the
field. They can handle mechanism, nuance, and complexity — they just need it explained
without assuming prior exposure. Your job is to tell them what changed, why it matters,
and what it means for people who aren't insiders.

VOICE

Write the way you'd explain this to a smart friend who wasn't in the room. Lead with the
alarming or counterintuitive thing — stated as a fact, not a topic sentence. Surface the
mechanism before the implication: a reader who understands why something works can use
that knowledge; a reader who only knows what happened cannot. When a technical concept
needs defining, use an analogy that makes it physical — not a parenthetical that restates
the jargon in different jargon.

Example of the voice in action:

  Your model cannot count. Not sometimes — structurally, below a certain size, it lacks
  the geometric capacity to track quantity. Researchers just proved it with enough
  precision to be useful: there's a ratio between how much internal representation space
  a model has and how many words it knows. Drop below that ratio and counting becomes
  impossible — not hard, impossible. Think of it like trying to keep score on a
  scoreboard that only has room for the team names. The information just doesn't fit.
  This isn't a training problem you can fix with better data. It's a constraint built
  into the model's shape. Which means if you're using a smaller or compressed model for
  anything that involves counting, enumeration, or sequencing, you now know exactly why
  it fails — and you have a concrete thing to test before your next model swap.

NEVER DO THESE

- No em dashes. Ever. Use a period and a new sentence (most common fix), parentheses
  for asides, a comma for light pauses, or a colon for a reveal. If a sentence doesn't
  work without an em dash, restructure the sentence.

- No AI indicator phrases:
    Filler transitions: "It's worth noting that," "Importantly," "Notably,"
    "Furthermore," "Moreover," "Additionally," "In conclusion," "To summarize,"
    "With that being said," "Moving forward," "Needless to say"
    Vague metaphors: "Delve into," "Dive into," "Shed light on," "Navigate" (abstract),
    "Landscape" (metaphorical), "Ecosystem" (metaphorical), "Realm of"
    Inflated adjectives: "Groundbreaking," "Revolutionary," "Game-changing,"
    "Transformative," "Cutting-edge," "State-of-the-art," "Paradigm shift,"
    "Comprehensive," "Holistic," "Robust" (unless measurably so)
    Weak verbs: "Utilize" (use "use"), "Leverage" metaphorically (use "apply")
    If a sentence depends on one of these to make its point, fix the sentence.

- No parenthetical jargon definitions. Not "policy gradient method (a mathematical
  technique for...)." Use an analogy. If no analogy is available, explain in plain
  prose before using the term.

- No "directly" as a filler intensifier. Cut every instance. "Directly applicable,"
  "directly relevant" — if something applies, say how.

- No equal weight for unequal stories. Some stories get a sentence. Some get four
  paragraphs. Give each one the space it earns.

- No context before stakes. The alarming or counterintuitive thing goes first, as a
  fact. Context follows.

- No explaining what you just showed. If an analogy lands, stop.

- No absorbing the source's frame without naming it. When a story comes from one
  perspective, say so.

- No named sections as substitutes for editorial judgment. No "Notable Omissions,"
  "Weak Signals," "→ Frontier / → Enterprise / → Equalizer Angle."

STRUCTURE

Before the body, output exactly one line:
DESCRIPTION: <one sentence, plain text, no markdown — what the AI/ML field moved on today>

Then open directly into voice — no header, no label. State what the field moved on today
and why it matters. Lead with the single most important story, result, or shift. Give it
the space it earns. Subsequent stories follow in descending order of significance. Weave
signal patterns and coverage gaps into the body where they're relevant — one sentence,
not a section. End with a Read List coda (max 5 links, no introduction needed).

RENDERING RULES
- Source emoji on every link: {emoji_table}
- integrity <= 2: add explicit ⚠️ single-source/unverified flag in body near the story
- cluster_size >= 3: this is the lead story — open with it, give it the most space
- NEVER invent sources or include stories not in the payload
- NEVER include the context block — it is for Zeitgeist only
""".format(
    emoji_table="\n".join(f"  {k} → {v}" for k, v in SOURCE_EMOJI.items())
)
```

**Step 3: Verify the rest of the file is unchanged**

After editing, confirm:
- `_ZEITGEIST_SYSTEM` (line ~81) is identical to before
- `build_equalizer_prompt()` function body is identical to before
- `build_zeitgeist_prompt()` function body is identical to before
- `_dumps()` helper is identical to before

---

## Task 2: Run the existing unit tests

**Files:**
- Test: `tests/test_personas.py`

**Step 1: Run personas tests**

```bash
cd /home/r3crsvint3llgnz/01_Projects/research-agent
pytest tests/test_personas.py -v
```

Expected output:
```
tests/test_personas.py::TestSourceEmoji::test_peer_reviewed_gets_microscope PASSED
tests/test_personas.py::TestSourceEmoji::test_single_source_gets_warning PASSED
tests/test_personas.py::TestEqualizerPrompt::test_includes_editorial_identity PASSED
tests/test_personas.py::TestEqualizerPrompt::test_does_not_include_context_block PASSED
tests/test_personas.py::TestEqualizerPrompt::test_includes_stories_json PASSED
tests/test_personas.py::TestEqualizerPrompt::test_signal_data_included PASSED
tests/test_personas.py::TestEqualizerPrompt::test_prior_briefing_included_when_present PASSED
tests/test_personas.py::TestZeitgeistPrompt::test_includes_editorial_identity PASSED
tests/test_personas.py::TestZeitgeistPrompt::test_includes_context_block PASSED
tests/test_personas.py::TestZeitgeistPrompt::test_entertainment_aside_instruction_present PASSED
tests/test_personas.py::TestZeitgeistPrompt::test_lede_grounding_rule_present PASSED
```

If `test_includes_editorial_identity` fails with "Equalizer not in prompt": the word
"Equalizer" appears in the NEVER DO THESE section ("→ Equalizer Angle") — double-check
the new text was pasted correctly.

**Step 2: Run the full test suite to catch any regressions**

```bash
pytest tests/ -v --ignore=tests/test_bedrock_briefing.py --ignore=tests/test_bedrock_summarizer.py
```

(The bedrock tests make live API calls — skip them for local runs.)

Expected: all tests pass.

**Step 3: Commit if green**

```bash
git add src/services/personas.py
git commit -m "feat: redesign AI Abstract prompt for open structure and voice"
```

---

## Task 3: Quality validation — live output against Feb 26 AM payload

This step tests whether the new prompt actually produces better output. It calls
Bedrock directly (costs ~$0.10–0.20) and prints the result. No writes to DynamoDB
or the website.

**Files:**
- Create (temporary, delete after): `scripts/test_prompt_quality.py`

**Step 1: Write the quality test script**

```python
#!/usr/bin/env python3
"""
One-off script: fetch Feb 26 AM stories from briefing_archive and run the new
Equalizer prompt against them via Bedrock. Prints the output. No writes.

Run from research-agent root:
    python scripts/test_prompt_quality.py
"""
import json
import boto3
from botocore.config import Config
from src.services.personas import build_equalizer_prompt

BRIEFING_DATE = "2026-02-26-AM"
REGION = "us-east-1"
MODEL_ID = "us.anthropic.claude-sonnet-4-6"
TABLE = "briefing-archive"


def main():
    # Fetch the Feb 26 AM stories from the briefing archive
    ddb = boto3.resource("dynamodb", region_name=REGION)
    table = ddb.Table(TABLE)
    resp = table.get_item(Key={"briefing_date": BRIEFING_DATE, "briefing_type": "AI_ML"})
    item = resp.get("Item")
    if not item:
        print(f"No item found for {BRIEFING_DATE}")
        return

    # The archive stores content (the final brief), not the raw stories.
    # Use a minimal synthetic payload to test prompt structure instead.
    # For a real test, pull from story-staging DynamoDB table.
    stories = [
        {
            "title": "When Can Transformers Count to n?",
            "url": "https://arxiv.org/abs/2407.15160",
            "summary": "Researchers identified a precise architectural threshold "
                       "that determines whether a transformer can count reliably.",
            "source_type": "peer-reviewed",
            "boost_tags": [],
            "cluster_size": 1,
            "sub_bucket": "research",
            "scores": {"total": 14},
            "feed_name": "",
            "reasoning": "Foundational result with direct practitioner implications.",
            "integrity": 3,
        },
        {
            "title": "Anthropic rejects Pentagon's 'final offer' in AI safeguards fight",
            "url": "https://www.axios.com/2026/02/26/anthropic-rejects-pentagon-ai-terms",
            "summary": "Anthropic refused DoD contract terms permitting unrestricted "
                       "model use for surveillance and autonomous weapons.",
            "source_type": "journalism",
            "boost_tags": [],
            "cluster_size": 3,
            "sub_bucket": "policy",
            "scores": {"total": 18},
            "feed_name": "axios.com",
            "reasoning": "High cluster size, major governance story.",
            "integrity": 3,
        },
    ]

    prompt = build_equalizer_prompt(stories=stories, signals=[], prior_briefing=None)

    print("=== PROMPT (first 500 chars) ===")
    print(prompt[:500])
    print("\n=== CALLING BEDROCK ===\n")

    client = boto3.client(
        "bedrock-runtime",
        region_name=REGION,
        config=Config(read_timeout=120),
    )
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    })
    resp = client.invoke_model(modelId=MODEL_ID, body=body)
    result = json.loads(resp["body"].read())
    text = result["content"][0]["text"]

    print("=== OUTPUT ===\n")
    print(text)

    print("\n=== CHECKLIST ===")
    checks = [
        ("No em dashes", "—" not in text),
        ("No 'Furthermore'", "Furthermore" not in text),
        ("No 'It's worth noting'", "It's worth noting" not in text),
        ("No '→ Frontier'", "→ Frontier" not in text),
        ("No '→ Enterprise'", "→ Enterprise" not in text),
        ("No '→ Equalizer Angle'", "→ Equalizer Angle" not in text),
        ("No 'Notable Omissions' header", "**Notable Omissions**" not in text),
        ("No 'Weak Signals' header", "**Weak Signals**" not in text),
        ("Has DESCRIPTION sentinel", text.strip().startswith("DESCRIPTION:")),
        ("Cluster-3 story leads (Anthropic)", text.index("Anthropic") < text.index("Transformer") if "Transformer" in text else True),
    ]
    for label, passed in checks:
        status = "PASS" if passed else "FAIL"
        print(f"  [{status}] {label}")


if __name__ == "__main__":
    main()
```

**Step 2: Run it**

```bash
cd /home/r3crsvint3llgnz/01_Projects/research-agent
python scripts/test_prompt_quality.py
```

AWS credentials will use the default profile. If you need `seth-dev`:
```bash
AWS_PROFILE=seth-dev python scripts/test_prompt_quality.py
```

**Step 3: Review the checklist output**

All PASS is required before proceeding. If any FAIL:
- Em dash present: the model ignored the prohibition — strengthen the prohibition
  wording (e.g., add "This is an absolute constraint, not a style preference.")
- Section headers present: restate the prohibition as "Output NO section headers
  other than # ⚖️ The AI Abstract at the top and **The Read List** at the end."
- DESCRIPTION sentinel missing: check that the STRUCTURE section of the new prompt
  was pasted correctly.

**Step 4: Read the output and manually assess voice**

Ask: Does the lead state the most important thing as a fact, not a topic sentence?
Ask: Does at least one technical concept get an analogy instead of a parenthetical?
Ask: Does the cluster-3 story (Anthropic/Pentagon) get more space than the single-source story?
Ask: Does it sound like Seth wrote it, or does it sound like a template was filled in?

If the output passes all four questions, proceed. If not, adjust the voice principles
or example paragraph and re-run. The example paragraph is the most influential lever.

**Step 5: Delete the test script**

```bash
rm scripts/test_prompt_quality.py
```

It is a one-off tool. Do not commit it.

---

## Task 4: Build and deploy

**Step 1: Run `deploy.sh` to rebuild the Lambda zip**

```bash
cd /home/r3crsvint3llgnz/01_Projects/research-agent
bash deploy.sh
```

Expected output ends with:
```
Lambda package: /home/r3crsvint3llgnz/01_Projects/research-agent/dist/lambda.zip (XXM)
```

**Step 2: Apply Terraform**

```bash
cd /home/r3crsvint3llgnz/01_Projects/research-agent/terraform
terraform apply
```

Terraform will detect that the `source_code_hash` changed (new zip) and update all
three Lambda functions. Review the plan output — expected changes are only
`aws_lambda_function` resource updates. Confirm with `yes`.

**Step 3: Verify deployment**

```bash
aws lambda get-function-configuration \
  --function-name research-agent-briefing \
  --profile seth-dev --region us-east-1 \
  --query 'LastModified'
```

Timestamp should be within the last few minutes.

**Step 4: Commit**

```bash
cd /home/r3crsvint3llgnz/01_Projects/research-agent
git add dist/lambda.zip   # only if tracked; skip if .gitignore covers dist/
git commit -m "deploy: ship redesigned AI Abstract prompt to Lambda"
```

---

## Task 5: Smoke test on the next live run

The pipeline runs at 11:00 and 23:00 UTC via EventBridge. After the next scheduled
run, verify the output.

**Step 1: Find the latest briefing in DynamoDB**

```bash
aws dynamodb scan \
  --table-name briefing-archive \
  --filter-expression "briefing_type = :t" \
  --expression-attribute-values '{":t": {"S": "AI_ML"}}' \
  --profile seth-dev --region us-east-1 \
  --query 'Items[*].{date:briefing_date.S}' \
  --output json | python3 -c "
import sys, json
items = json.load(sys.stdin)
items.sort(key=lambda x: x['date'], reverse=True)
print(items[0]['date'])
"
```

**Step 2: Fetch and print the body**

```bash
aws dynamodb get-item \
  --table-name briefing-archive \
  --key "{\"briefing_date\": {\"S\": \"<DATE-FROM-STEP-1>\"}, \"briefing_type\": {\"S\": \"AI_ML\"}}" \
  --profile seth-dev --region us-east-1 \
  --query 'Item.content.S' --output text | head -100
```

**Step 3: Run the same four voice questions from Task 3 Step 4**

If the live output passes, the redesign is complete.

If the live output fails on specific checks, go back to `_EQUALIZER_SYSTEM` and
adjust the relevant section. The prohibition list and example paragraph are the
two highest-leverage levers. Rebuild and redeploy (Tasks 4.1–4.4).

---

## Rollback

If the new prompt produces unusable output and a quick fix isn't obvious:

```bash
git revert HEAD   # reverts the personas.py commit
bash deploy.sh
cd terraform && terraform apply
```

The next scheduled run will use the old prompt.

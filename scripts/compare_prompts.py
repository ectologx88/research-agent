"""
Prompt comparison test: run the same story set through both old and new Equalizer prompts
and compare outputs side-by-side via Bedrock.

Usage:
  cd /home/r3crsvint3llgnz/01_Projects/research-agent
  python scripts/compare_prompts.py
"""
import json
import sys
import importlib.util
import boto3
from botocore.config import Config

# ---------- story set reconstructed from March 22 AM AI_ML briefing ----------
# These are the 6 stories that passed the scorer under the old prompts.
# All are Reddit posts or low-integrity commentary — the exact failure mode
# the hard gate was designed to prevent.
STORIES = [
    {
        "title": "Sinc Reconstruction for LLM Prompts — Applying Nyquist-Shannon to Prompt Engineering",
        "url": "https://www.reddit.com/r/MachineLearning/comments/1s08xft/r_sinc_reconstruction_for_llm_prompts_applying/",
        "feed_name": "r/MachineLearning",
        "summary": "A Reddit post claims 97% LLM cost reduction by applying the 1949 Nyquist-Shannon sampling theorem to prompt specification. Open-source code provided; unverified.",
        "source_type": "commentary",
        "boost_tags": [],
        "cluster_size": 1,
        "cluster_key": "sinc-llm-prompts",
        "sub_bucket": "research",
        "scores": {"integrity": 2, "relevance": 4, "novelty": 4, "total": 10},
        "reasoning": "Reddit post with interesting idea; unverified claims.",
    },
    {
        "title": "I am a painter with work at MoMA and the Met — I just published 50 years of my work as an open AI dataset",
        "url": "https://www.reddit.com/r/artificial/comments/1s0bxvq/i_am_a_painter_with_work_at_moma_and_the_met_i_just_published_50_years_of_my_work_as_an_open_ai_dataset_here_is_what_i_learned/",
        "feed_name": "r/artificial",
        "summary": "Artist Michael Hafftka released ~4,000 figure paintings spanning 50 years on Hugging Face as an openly licensed AI training dataset with explicit consent.",
        "source_type": "single-source",
        "boost_tags": ["boost:open-source"],
        "cluster_size": 2,
        "cluster_key": "hafftka-dataset",
        "sub_bucket": "datasets",
        "scores": {"integrity": 2, "relevance": 3, "novelty": 4, "total": 9},
        "reasoning": "Interesting consent angle; Reddit post is the only source.",
    },
    {
        "title": "Single-Artist Longitudinal Fine Art Dataset on Hugging Face",
        "url": "https://www.reddit.com/r/MachineLearning/comments/1s0dce7/d_singleartist_longitudinal_fine_art_dataset/",
        "feed_name": "r/MachineLearning",
        "summary": "Community discussion of Michael Hafftka's 50-year figure painting dataset as a research resource for studying style evolution.",
        "source_type": "commentary",
        "boost_tags": [],
        "cluster_size": 2,
        "cluster_key": "hafftka-dataset",
        "sub_bucket": "datasets",
        "scores": {"integrity": 2, "relevance": 3, "novelty": 3, "total": 8},
        "reasoning": "Part of same cluster as Hafftka first-person post.",
    },
    {
        "title": "Inferencing Llama 3.2-1B on 3x Mac Minis M4 — smolcluster distributed inference demo",
        "url": "https://www.reddit.com/r/MachineLearning/comments/1s0g7sd/p_inferencing_llama321binstruct_on_3xmac_minis_m4/",
        "feed_name": "r/MachineLearning",
        "summary": "Hobbyist project running Llama 3.2-1B distributed across three Mac Mini M4 devices using a custom all-to-all communication pattern.",
        "source_type": "commentary",
        "boost_tags": [],
        "cluster_size": 1,
        "cluster_key": "mac-mini-distributed",
        "sub_bucket": "infrastructure",
        "scores": {"integrity": 2, "relevance": 3, "novelty": 3, "total": 8},
        "reasoning": "Hobbyist demo; low integrity but illustrates consumer hardware trajectory.",
    },
    {
        "title": "Safely Deploying ML Models to Production: Four Controlled Strategies",
        "url": "https://www.marktechpost.com/2026/03/21/safely-deploying-ml-models-to-production-four-controlled-strategies-a-b-canary-interleaved-shadow-testing/",
        "feed_name": "MarkTechPost",
        "summary": "Overview of A/B testing, canary releases, interleaved testing, and shadow mode for production ML deployment. Commentary, not original research.",
        "source_type": "commentary",
        "boost_tags": [],
        "cluster_size": 1,
        "cluster_key": "ml-deployment-strategies",
        "sub_bucket": "engineering",
        "scores": {"integrity": 3, "relevance": 3, "novelty": 2, "total": 8},
        "reasoning": "Practical taxonomy article; no novel findings.",
    },
    {
        "title": "Crystal Structure Analysis with Pymatgen: A Practical Guide",
        "url": "https://towardsdatascience.com/crystal-structure-analysis-pymatgen",
        "feed_name": "Towards Data Science",
        "summary": "Tutorial on using pymatgen for crystal structure analysis, symmetry operations, and phase diagram generation in computational materials science.",
        "source_type": "commentary",
        "boost_tags": [],
        "cluster_size": 1,
        "cluster_key": "pymatgen-tutorial",
        "sub_bucket": "research",
        "scores": {"integrity": 3, "relevance": 2, "novelty": 2, "total": 7},
        "reasoning": "Niche how-to for materials informatics.",
    },
]

SIGNALS = []
PRIOR_BRIEFING = None


def _call_bedrock(bedrock, model_id: str, prompt: str) -> str:
    body = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    })
    response = bedrock.invoke_model(
        modelId=model_id,
        body=body,
        contentType="application/json",
        accept="application/json",
    )
    resp_body = json.loads(response["body"].read())
    return resp_body["content"][0]["text"]


def load_module_from_file(path: str, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    model_id = "us.anthropic.claude-sonnet-4-6"
    session = boto3.Session(profile_name="seth-dev")
    bedrock = session.client(
        "bedrock-runtime",
        region_name="us-east-1",
        config=Config(read_timeout=580),
    )

    # Load old personas module from saved file
    old_personas = load_module_from_file("/tmp/personas_old.py", "personas_old")
    # Load new personas from current source
    new_personas = load_module_from_file(
        "/home/r3crsvint3llgnz/01_Projects/research-agent/src/services/personas.py",
        "personas_new",
    )

    print("=" * 80)
    print("BUILDING PROMPTS...")
    old_prompt = old_personas.build_equalizer_prompt(
        stories=STORIES, signals=SIGNALS, prior_briefing=PRIOR_BRIEFING
    )
    new_prompt = new_personas.build_equalizer_prompt(
        stories=STORIES, signals=SIGNALS, prior_briefing=PRIOR_BRIEFING
    )
    print(f"Old prompt length: {len(old_prompt)} chars")
    print(f"New prompt length: {len(new_prompt)} chars")

    print("\n" + "=" * 80)
    print("CALLING BEDROCK WITH OLD PROMPT...")
    old_output = _call_bedrock(bedrock, model_id, old_prompt)
    print(f"Old output: {len(old_output)} chars\n")

    print("=" * 80)
    print("CALLING BEDROCK WITH NEW PROMPT...")
    new_output = _call_bedrock(bedrock, model_id, new_prompt)
    print(f"New output: {len(new_output)} chars\n")

    output_path = "/tmp/prompt_comparison.txt"
    with open(output_path, "w") as f:
        f.write("=" * 80 + "\n")
        f.write("OLD PROMPT OUTPUT (pre-journalistic-overhaul)\n")
        f.write("=" * 80 + "\n\n")
        f.write(old_output)
        f.write("\n\n")
        f.write("=" * 80 + "\n")
        f.write("NEW PROMPT OUTPUT (post-journalistic-overhaul)\n")
        f.write("=" * 80 + "\n\n")
        f.write(new_output)

    print(f"Results written to {output_path}")
    print("\nOLD OUTPUT:\n" + "-" * 40)
    print(old_output[:3000])
    print("\n... [truncated — see /tmp/prompt_comparison.txt for full output]\n")
    print("NEW OUTPUT:\n" + "-" * 40)
    print(new_output[:3000])


if __name__ == "__main__":
    main()

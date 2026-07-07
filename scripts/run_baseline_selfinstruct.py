"""Baseline: Self-Instruct-style SFT data generation (Wang et al., 2022), adapted to take API
endpoints as seeds, per DESIGN_DOC.md S5.3/S4.3.

The point of this baseline is to isolate what EnterpriseSynth's schema-grounding + verification
actually buys over the closest prior bootstrapping method. Faithful to Self-Instruct's actual
mechanism (see paper/related_work_audit.md S1): starts from a small human-written-quality seed
set, iteratively samples a mix of seed + previously-generated examples as few-shot context, asks
the model to generate ONE new example "inspired by" them, and filters with a ROUGE-L-similarity
threshold against everything already accepted. Critically, and unlike EnterpriseSynth: the model
is NEVER given the real OpenAPI spec here -- it must invent its own endpoint/path/parameters by
pattern-matching the few-shot examples, exactly as Self-Instruct provides no schema grounding.

Produces a training set the same size and format as Experiment 5's EnterpriseSynth set (45
examples), fine-tunes the same base model (Qwen2.5-0.5B-Instruct, same LoRA config), and evaluates
on the exact same 16-intent held-out Zoom set -- isolating training-data quality as the only
variable.
"""
from __future__ import annotations

import difflib
import json
import random
import sys
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from enterprisesynth.parser import SchemaParser  # noqa: E402
from enterprisesynth.verifier import SchemaVerificationEngine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MODEL = "claude-sonnet-5"
TARGET_SIZE = 45
SIMILARITY_THRESHOLD = 0.7
SEED = 42

BOOTSTRAP_PROMPT = """Here are some examples of (user request, API tool call) pairs for enterprise
software tools:

{examples}

Generate ONE new example, inspired by the style and domain of the ones above but for a
DIFFERENT specific task and a different (invented) API endpoint. Do not repeat any of the above.

Respond with ONLY a JSON object in this exact shape:
{{
  "intent": "<a one-sentence enterprise user request>",
  "selected_method": "<HTTP method, your choice>",
  "selected_path": "<an endpoint path you invent, in the style of the examples>",
  "parameters": {{"<param name>": "<concrete value>", ...}}
}}
"""


def rouge_l_ratio(a: str, b: str) -> float:
    """Lightweight ROUGE-L-style similarity: longest-common-subsequence ratio via difflib."""
    return difflib.SequenceMatcher(None, a, b).ratio()


def format_example(ex: dict) -> str:
    return (
        f'Request: "{ex["intent"]}"\n'
        f'Tool call: {{"method": "{ex["selected_method"]}", "path": "{ex["selected_path"]}", '
        f'"parameters": {json.dumps(ex["parameters"])}}}'
    )


def load_seed_examples() -> list[dict]:
    """4 real, human-quality seed examples drawn from EnterpriseSynth's own verified set --
    Self-Instruct requires a small human-written seed set; these stand in for it."""
    with open(ROOT / "data" / "generated" / "experiment5_sft_train.json") as f:
        training_set = json.load(f)
    picks = []
    seen_apis = set()
    for item in training_set:
        if item["api"] not in seen_apis or len(picks) < 4:
            picks.append(
                {
                    "intent": item["intent"],
                    "selected_method": item["output"]["selected_method"],
                    "selected_path": item["output"]["selected_path"],
                    "parameters": item["output"]["parameters"],
                }
            )
            seen_apis.add(item["api"])
        if len(picks) == 4:
            break
    return picks


def bootstrap_dataset(client: anthropic.Anthropic, rng: random.Random) -> list[dict]:
    seeds = load_seed_examples()
    pool = list(seeds)
    accepted: list[dict] = []
    attempts = 0
    max_attempts = TARGET_SIZE * 4

    while len(accepted) < TARGET_SIZE and attempts < max_attempts:
        attempts += 1
        few_shot = rng.sample(pool, min(3, len(pool)))
        examples_text = "\n\n".join(format_example(e) for e in few_shot)
        prompt = BOOTSTRAP_PROMPT.format(examples=examples_text)

        response = client.messages.create(
            model=MODEL, max_tokens=300, messages=[{"role": "user", "content": prompt}]
        )
        text = "".join(b.text for b in response.content if b.type == "text").strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        try:
            new_example = json.loads(text)
        except json.JSONDecodeError:
            continue

        if not all(k in new_example for k in ("intent", "selected_method", "selected_path")):
            continue

        max_sim = max(
            (rouge_l_ratio(new_example["intent"], existing["intent"]) for existing in pool),
            default=0.0,
        )
        if max_sim >= SIMILARITY_THRESHOLD:
            print(f"  rejected (similarity {max_sim:.2f}): {new_example['intent'][:60]}")
            continue

        accepted.append(new_example)
        pool.append(new_example)
        print(f"  accepted ({len(accepted)}/{TARGET_SIZE}): {new_example['intent'][:60]}")

    return accepted


def main() -> None:
    client = anthropic.Anthropic()
    rng = random.Random(SEED)

    print("Bootstrapping Self-Instruct-style dataset (no schema grounding)...")
    dataset = bootstrap_dataset(client, rng)
    print(f"\nFinal dataset: {len(dataset)} examples")

    # Sanity check: are these invented endpoints real, per any of our 3 source specs? (They
    # shouldn't be, mostly -- Self-Instruct has no schema to ground against.)
    parser = SchemaParser()
    real_keys = set()
    for spec_file in ["github.json", "stripe.json", "slack.json"]:
        with open(ROOT / "data" / "specs" / spec_file) as f:
            raw = json.load(f)
        schema = parser.parse(raw)
        real_keys |= {(e.method, e.path) for e in schema.endpoints}

    grounded_count = sum(
        1 for ex in dataset if (ex["selected_method"].upper(), ex["selected_path"]) in real_keys
    )
    print(f"Of {len(dataset)} generated examples, {grounded_count} happen to match a real endpoint "
          f"in our 3 source specs (expected: near 0, since no schema was ever provided).")

    out_dir = ROOT / "data" / "generated"
    with open(out_dir / "baseline_selfinstruct_train.json", "w") as f:
        json.dump(dataset, f, indent=2)


if __name__ == "__main__":
    main()

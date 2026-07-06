"""Prepares Experiment 5 data:

1. SFT training set: the *verified* (Stage 6-passing) trajectories from Experiment 3, generated
   from GitHub/Stripe/Slack only.
2. Held-out eval set: fresh intents generated (via the same Stage 3 Intent Synthesis Agent) for
   Zoom -- an API never touched by any prior experiment or training data in this pipeline.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from enterprisesynth.intent_agent import IntentSynthesisAgent  # noqa: E402
from enterprisesynth.parser import SchemaParser  # noqa: E402
from enterprisesynth.verifier import SchemaVerificationEngine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_SIZE = 8
INTENTS_PER_ENDPOINT = 2
SEED = 42


def build_sft_training_set() -> list[dict]:
    """Verified (Stage 6-passing) trajectories from GitHub/Stripe/Slack -- Experiment 3 output.

    Reconstructs each API's candidate tool list identically to run_experiment3.py (same 5 source
    endpoints + 10 seeded distractors, seed=42) so the training prompt format matches what the
    held-out eval set uses.
    """
    specs = {
        "GitHub": "data/specs/github.json",
        "Stripe": "data/specs/stripe.json",
        "Slack": "data/specs/slack.json",
    }
    parser = SchemaParser()
    with open(ROOT / "data" / "generated" / "experiment3_trajectories.json") as f:
        trajectories_by_api = json.load(f)
    with open(ROOT / "data" / "generated" / "experiment2_intents.json") as f:
        intents_by_api = json.load(f)

    training_examples = []
    for api_name, spec_path in specs.items():
        with open(ROOT / spec_path) as f:
            raw = json.load(f)
        schema = parser.parse(raw)
        engine = SchemaVerificationEngine(schema)
        by_key = {(e.method, e.path): e for e in schema.endpoints}

        source_endpoints = [
            by_key[(item["method"], item["path"])]
            for item in intents_by_api[api_name]
            if (item["method"], item["path"]) in by_key
        ]
        source_keys = {(e.method, e.path) for e in source_endpoints}
        rng = random.Random(SEED)
        pool = [e for e in schema.endpoints if (e.method, e.path) not in source_keys]
        distractors = rng.sample(pool, min(10, len(pool)))
        candidates = [
            {"method": e.method, "path": e.path, "operation_id": e.operation_id}
            for e in (source_endpoints + distractors)
        ]

        for item in trajectories_by_api[api_name]:
            trajectory = item.get("trajectory")
            if not item.get("selected_correct") or not trajectory:
                continue
            result = engine.verify(
                trajectory.get("selected_method", ""),
                trajectory.get("selected_path", ""),
                trajectory.get("parameters") or {},
            )
            if not result.valid:
                continue  # only Stage-6-verified trajectories go into the SFT set

            training_examples.append(
                {
                    "api": api_name,
                    "intent": item["intent"],
                    "candidates": candidates,
                    "output": {
                        "selected_method": trajectory["selected_method"],
                        "selected_path": trajectory["selected_path"],
                        "parameters": trajectory.get("parameters") or {},
                    },
                }
            )
    return training_examples


def build_heldout_eval_set() -> list[dict]:
    """Fresh intents for Zoom, an API not used anywhere else in this pipeline so far."""
    parser = SchemaParser()
    agent = IntentSynthesisAgent()

    with open(ROOT / "data" / "specs" / "zoom.json") as f:
        raw = json.load(f)
    schema = parser.parse(raw)

    rng = random.Random(SEED)
    sample = rng.sample(schema.endpoints, min(SAMPLE_SIZE, len(schema.endpoints)))
    pool = [e for e in schema.endpoints if e not in sample]
    distractors = rng.sample(pool, min(15, len(pool)))
    candidates = sample + distractors

    eval_examples = []
    for endpoint in sample:
        intents = agent.generate_intents(endpoint, n=INTENTS_PER_ENDPOINT)
        for intent_text in intents:
            eval_examples.append(
                {
                    "intent": intent_text,
                    "ground_truth_method": endpoint.method,
                    "ground_truth_path": endpoint.path,
                    "candidates": [
                        {"method": e.method, "path": e.path, "operation_id": e.operation_id}
                        for e in candidates
                    ],
                }
            )
        print(f"[Zoom] {endpoint.method} {endpoint.path} -> {len(intents)} intents")

    return eval_examples


def main() -> None:
    out_dir = ROOT / "data" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)

    training_set = build_sft_training_set()
    with open(out_dir / "experiment5_sft_train.json", "w") as f:
        json.dump(training_set, f, indent=2)
    print(f"SFT training set: {len(training_set)} verified examples (GitHub/Stripe/Slack)")

    eval_set = build_heldout_eval_set()
    with open(out_dir / "experiment5_heldout_eval.json", "w") as f:
        json.dump(eval_set, f, indent=2)
    print(f"Held-out eval set: {len(eval_set)} examples (Zoom, never used in training)")


if __name__ == "__main__":
    main()

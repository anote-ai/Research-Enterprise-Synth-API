"""Scales Experiment 5 beyond a single held-out API (Zoom) to check whether the 12.5%->87.5%
result is representative or a single favorable draw (flagged as an open question in
DESIGN_DOC.md S6.7 and the repo audit).

Adds two more held-out APIs never used in any training data or prior experiment: DigitalOcean
(290 endpoints) and Spotify (88 endpoints). Trains each of the three models (base/untuned,
Self-Instruct-tuned, EnterpriseSynth-tuned) ONCE, then evaluates all three against Zoom +
DigitalOcean + Spotify -- three independent held-out draws instead of one.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from enterprisesynth.finetune import DEVICE, MODEL_NAME, evaluate, train_lora  # noqa: E402
from enterprisesynth.intent_agent import IntentSynthesisAgent  # noqa: E402
from enterprisesynth.parser import SchemaParser  # noqa: E402
from enterprisesynth.sampling import sample_and_distract  # noqa: E402
from enterprisesynth.verifier import SchemaVerificationEngine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_SIZE = 8
INTENTS_PER_ENDPOINT = 2
SEED = 42
NEW_HELDOUT_APIS = {
    "DigitalOcean": "data/specs/digitalocean.json",
    "Spotify": "data/specs/spotify.json",
}


def build_heldout_eval_set(spec_path: str) -> tuple[list[dict], object]:
    parser = SchemaParser()
    agent = IntentSynthesisAgent()

    with open(ROOT / spec_path) as f:
        raw = json.load(f)
    schema = parser.parse(raw)

    sample, distractors = sample_and_distract(
        schema, seed=SEED, sample_size=SAMPLE_SIZE, n_distractors=15
    )
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
        print(f"  {endpoint.method} {endpoint.path} -> {len(intents)} intents")

    return eval_examples, schema


def main() -> None:
    out_dir = ROOT / "data" / "generated"

    # 1. Build held-out eval sets for the two new APIs (Zoom's already exists).
    heldout_sets = {}
    with open(out_dir / "experiment5_heldout_eval.json") as f:
        heldout_sets["Zoom"] = json.load(f)
    with open(ROOT / "data" / "specs" / "zoom.json") as f:
        zoom_schema = SchemaParser().parse(json.load(f))
    schemas = {"Zoom": zoom_schema}

    for api_name, spec_path in NEW_HELDOUT_APIS.items():
        print(f"Generating held-out eval set for {api_name}...")
        eval_set, schema = build_heldout_eval_set(spec_path)
        heldout_sets[api_name] = eval_set
        schemas[api_name] = schema
        with open(out_dir / f"experiment5_heldout_eval_{api_name.lower()}.json", "w") as f:
            json.dump(eval_set, f, indent=2)

    # 2. Load the three training sets.
    with open(out_dir / "experiment5_sft_train.json") as f:
        enterprisesynth_train = json.load(f)

    parser = SchemaParser()
    all_real_endpoints = []
    for spec_file in ["github.json", "stripe.json", "slack.json"]:
        with open(ROOT / "data" / "specs" / spec_file) as f:
            schema = parser.parse(json.load(f))
        all_real_endpoints.extend(schema.endpoints)

    with open(out_dir / "baseline_selfinstruct_train.json") as f:
        raw_selfinstruct = json.load(f)
    rng = random.Random(SEED)
    selfinstruct_train = []
    for ex in raw_selfinstruct:
        distractors = rng.sample(all_real_endpoints, min(10, len(all_real_endpoints)))
        candidates = [
            {"method": ex["selected_method"], "path": ex["selected_path"], "operation_id": None}
        ] + [
            {"method": e.method, "path": e.path, "operation_id": e.operation_id}
            for e in distractors
        ]
        rng.shuffle(candidates)
        selfinstruct_train.append(
            {
                "intent": ex["intent"],
                "candidates": candidates,
                "output": {
                    "selected_method": ex["selected_method"],
                    "selected_path": ex["selected_path"],
                    "parameters": ex.get("parameters") or {},
                },
            }
        )

    # 3. Train each model ONCE.
    print(f"\nLoading {MODEL_NAME} on {DEVICE}...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    base_model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, dtype=torch.float32).to(DEVICE)
    base_model.eval()

    print("\n=== Training Self-Instruct model ===")
    base_for_si = AutoModelForCausalLM.from_pretrained(MODEL_NAME, dtype=torch.float32).to(DEVICE)
    selfinstruct_model = train_lora(base_for_si, tokenizer, selfinstruct_train)

    print("\n=== Training EnterpriseSynth model ===")
    base_for_es = AutoModelForCausalLM.from_pretrained(MODEL_NAME, dtype=torch.float32).to(DEVICE)
    enterprisesynth_model = train_lora(base_for_es, tokenizer, enterprisesynth_train)

    # 4. Evaluate all three models against all three held-out APIs.
    results = {}
    for api_name, eval_set in heldout_sets.items():
        verifier = SchemaVerificationEngine(schemas[api_name])
        print(f"\n=== Evaluating on held-out {api_name} ({len(eval_set)} intents) ===")
        results[api_name] = {
            "base": evaluate(base_model, tokenizer, eval_set, verifier),
            "self_instruct": evaluate(selfinstruct_model, tokenizer, eval_set, verifier),
            "enterprisesynth": evaluate(enterprisesynth_model, tokenizer, eval_set, verifier),
        }

    with open(out_dir / "experiment5_multi_api_results.json", "w") as f:
        json.dump(results, f, indent=2)

    print("\n=== SUMMARY: Tool Selection Accuracy by held-out API ===")
    summary = []
    for api_name, api_results in results.items():
        summary.append(
            {
                "Held-out API": api_name,
                "Base": api_results["base"]["tool_selection_accuracy"],
                "Self-Instruct": api_results["self_instruct"]["tool_selection_accuracy"],
                "EnterpriseSynth": api_results["enterprisesynth"]["tool_selection_accuracy"],
            }
        )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

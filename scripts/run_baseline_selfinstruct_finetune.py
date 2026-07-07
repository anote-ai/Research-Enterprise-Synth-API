"""Fine-tunes and evaluates the Self-Instruct baseline dataset (from
scripts/run_baseline_selfinstruct.py), using the IDENTICAL methodology as Experiment 5
(same base model, same LoRA config, same held-out Zoom eval set) -- isolating training-data
quality (EnterpriseSynth's schema-grounded + verified pipeline vs. Self-Instruct's ungrounded
bootstrap) as the only variable.

The Self-Instruct dataset's examples use invented (mostly non-real) endpoints/paths rather than
the schema-derived "candidates" format Experiment 5's training examples have. To keep the fine-
tuning format identical, each Self-Instruct example is given a candidate list consisting of its
own invented endpoint plus distractors sampled from the same pool Experiment 5 used -- the model
still only ever sees non-schema-grounded content during training, since neither the "correct"
answer nor the distractors were ever confirmed against a real spec for these invented endpoints.
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
from enterprisesynth.parser import SchemaParser  # noqa: E402
from enterprisesynth.verifier import SchemaVerificationEngine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SEED = 42


def build_selfinstruct_training_examples() -> list[dict]:
    with open(ROOT / "data" / "generated" / "baseline_selfinstruct_train.json") as f:
        raw_examples = json.load(f)

    # Reuse Experiment 5's real GitHub/Stripe/Slack endpoints as a distractor pool -- the
    # Self-Instruct examples' own (mostly invented) endpoint is always the "correct" one for
    # its own intent, matching how Experiment 3/5 present a multi-candidate choice.
    parser = SchemaParser()
    all_real_endpoints = []
    for spec_file in ["github.json", "stripe.json", "slack.json"]:
        with open(ROOT / "data" / "specs" / spec_file) as f:
            raw = json.load(f)
        schema = parser.parse(raw)
        all_real_endpoints.extend(schema.endpoints)

    rng = random.Random(SEED)
    training_examples = []
    for ex in raw_examples:
        distractors = rng.sample(all_real_endpoints, min(10, len(all_real_endpoints)))
        candidates = [
            {"method": ex["selected_method"], "path": ex["selected_path"], "operation_id": None}
        ] + [
            {"method": e.method, "path": e.path, "operation_id": e.operation_id}
            for e in distractors
        ]
        rng.shuffle(candidates)
        training_examples.append(
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
    return training_examples


def main() -> None:
    training_examples = build_selfinstruct_training_examples()
    with open(ROOT / "data" / "generated" / "experiment5_heldout_eval.json") as f:
        eval_examples = json.load(f)

    with open(ROOT / "data" / "specs" / "zoom.json") as f:
        zoom_raw = json.load(f)
    zoom_schema = SchemaParser().parse(zoom_raw)
    verifier = SchemaVerificationEngine(zoom_schema)

    print(f"Loading {MODEL_NAME} on {DEVICE}...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    base_model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, dtype=torch.float32).to(DEVICE)
    base_model.eval()

    print(f"\nFine-tuning via LoRA on {len(training_examples)} Self-Instruct-generated examples...")
    tuned_model = train_lora(base_model, tokenizer, training_examples)

    print("\nEvaluating Self-Instruct-fine-tuned model on the SAME held-out Zoom set...")
    results = evaluate(tuned_model, tokenizer, eval_examples, verifier)
    print(json.dumps({k: v for k, v in results.items() if k != "results"}, indent=2))

    out_dir = ROOT / "data" / "generated"
    with open(out_dir / "baseline_selfinstruct_results.json", "w") as f:
        json.dump(results, f, indent=2)

    print("\n=== COMPARISON (all evaluated on the same 16 held-out Zoom intents) ===")
    with open(out_dir / "experiment5_results.json") as f:
        exp5 = json.load(f)
    print(
        json.dumps(
            [
                {
                    "Method": "Base LLM (zero-shot, untuned)",
                    "Tool Selection Accuracy (%)": exp5["base_model"]["tool_selection_accuracy"],
                },
                {
                    "Method": "Self-Instruct-fine-tuned (this script)",
                    "Tool Selection Accuracy (%)": results["tool_selection_accuracy"],
                },
                {
                    "Method": "EnterpriseSynth-fine-tuned (Experiment 5)",
                    "Tool Selection Accuracy (%)": exp5["fine_tuned_model"][
                        "tool_selection_accuracy"
                    ],
                },
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

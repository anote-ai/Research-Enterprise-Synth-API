"""Experiment 5: Downstream LLM Agent Evaluation (hardware-scoped pilot).

DESIGN_DOC.md's original protocol targets Mistral-7B/Llama-3-8B via LoRA. That is not feasible on
this machine (no GPU, 16GB RAM, bitsandbytes/QLoRA barely supports Apple Silicon). This is a real,
honestly-scoped substitute: Qwen2.5-0.5B-Instruct, actually fine-tuned via LoRA on this machine's
MPS backend, evaluated against a genuinely held-out API (Zoom -- never used in any prior
experiment or training data in this pipeline).

Compares: (1) base model, zero-shot, vs (2) the same base model + LoRA adapter fine-tuned on the
45 Stage-6-verified EnterpriseSynth trajectories from GitHub/Stripe/Slack. Both evaluated on the
same 16 held-out Zoom intents, scored by Tool Selection Accuracy (against known ground truth) and
Parameter Validity (via the same Stage 6 SchemaVerificationEngine used in Experiment 4).

Shared LoRA training/eval helpers live in src/enterprisesynth/finetune.py, reused by
scripts/run_baseline_selfinstruct_finetune.py for a fair, methodology-identical comparison.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from enterprisesynth.finetune import DEVICE, MODEL_NAME, evaluate, train_lora  # noqa: E402
from enterprisesynth.parser import SchemaParser  # noqa: E402
from enterprisesynth.verifier import SchemaVerificationEngine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    with open(ROOT / "data" / "generated" / "experiment5_sft_train.json") as f:
        training_examples = json.load(f)
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

    print("Evaluating BASE model (zero-shot, untuned)...")
    base_model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, dtype=torch.float32).to(DEVICE)
    base_model.eval()
    base_results = evaluate(base_model, tokenizer, eval_examples, verifier)
    print(json.dumps({k: v for k, v in base_results.items() if k != "results"}, indent=2))

    print(f"\nFine-tuning via LoRA on {len(training_examples)} verified examples...")
    tuned_model = train_lora(base_model, tokenizer, training_examples)

    print("\nEvaluating FINE-TUNED model...")
    tuned_results = evaluate(tuned_model, tokenizer, eval_examples, verifier)
    print(json.dumps({k: v for k, v in tuned_results.items() if k != "results"}, indent=2))

    out_dir = ROOT / "data" / "generated"
    with open(out_dir / "experiment5_results.json", "w") as f:
        json.dump({"base_model": base_results, "fine_tuned_model": tuned_results}, f, indent=2)

    print("\n=== SUMMARY ===")
    print(
        json.dumps(
            [
                {
                    "Model": "Base (untuned)",
                    "Tool Selection Accuracy (%)": base_results["tool_selection_accuracy"],
                    "Parameter Validity (%, among correct)": base_results[
                        "parameter_validity_among_correct"
                    ],
                },
                {
                    "Model": "Fine-tuned (LoRA on EnterpriseSynth data)",
                    "Tool Selection Accuracy (%)": tuned_results["tool_selection_accuracy"],
                    "Parameter Validity (%, among correct)": tuned_results[
                        "parameter_validity_among_correct"
                    ],
                },
            ],
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

"""Phase 2: Private Enterprise Cold-Start Validation.

Trains the EnterpriseSynth model exactly as in Experiment 5 (LoRA on the same 45
Stage-6-verified GitHub/Stripe/Slack examples), then evaluates it -- and the untuned base model --
against two held-out sets:

  "Public"  = the combined Zoom + DigitalOcean + Spotify held-out sets already used in
              scripts/scale_experiment5_heldout.py (48 examples total)
  "Private" = the 5 never-published enterprise specs (CRM/HRIS/Procurement/Ticketing/Asset
              Management) built by scripts/build_private_coldstart_eval.py

This directly tests RQ4 (DESIGN_DOC.md S1): does the effect hold on APIs a base model could not
plausibly have pretraining exposure to, not just APIs it may already half-know from public docs.

Metrics: Tool Selection Accuracy and Parameter Validity -- the same two metrics used throughout
this project (Experiments 3/5, ablation study). We do NOT report Precision/Recall/BLEU/ROUGE/
Pass@1 here: this is a single-correct-answer tool-selection task with one gold endpoint per
intent, not a multi-label or free-text-generation task, so precision/recall would need an
artificial multi-class averaging scheme and BLEU/ROUGE have no natural reference text to score
against. Accuracy is the metric that actually matches this task's shape; introducing metrics we
have no existing infrastructure for, just to match a template, would be exactly the kind of
unsupported-claim risk this project has avoided everywhere else.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from enterprisesynth.finetune import DEVICE, MODEL_NAME, evaluate, train_lora  # noqa: E402
from enterprisesynth.parser import SchemaParser  # noqa: E402
from enterprisesynth.schemas import APISchema  # noqa: E402
from enterprisesynth.verifier import SchemaVerificationEngine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "generated"
PRIVATE_DIR = ROOT / "data" / "specs" / "private"


def merged_private_schema() -> APISchema:
    parser = SchemaParser()
    all_endpoints = []
    for spec_path in sorted(PRIVATE_DIR.glob("*.json")):
        with open(spec_path) as f:
            raw = json.load(f)
        schema = parser.parse(raw)
        all_endpoints.extend(schema.endpoints)
    return APISchema(title="Combined Private Enterprise APIs", version="1.0.0", endpoints=all_endpoints)


def build_public_eval_set() -> tuple[list[dict], APISchema]:
    """Combines the existing Zoom/DigitalOcean/Spotify held-out sets and their schemas."""
    parser = SchemaParser()
    all_examples = []
    all_endpoints = []
    for name, spec_file, eval_file in [
        ("Zoom", "zoom.json", "experiment5_heldout_eval.json"),
        ("DigitalOcean", "digitalocean.json", "experiment5_heldout_eval_digitalocean.json"),
        ("Spotify", "spotify.json", "experiment5_heldout_eval_spotify.json"),
    ]:
        with open(ROOT / "data" / "specs" / spec_file) as f:
            schema = parser.parse(json.load(f))
        all_endpoints.extend(schema.endpoints)
        with open(OUT_DIR / eval_file) as f:
            examples = json.load(f)
        all_examples.extend(examples)
    combined_schema = APISchema(title="Combined Public APIs", version="1.0.0", endpoints=all_endpoints)
    return all_examples, combined_schema


def main(train_seed: int) -> None:
    private_eval_path = OUT_DIR / "private_coldstart_eval.json"
    if not private_eval_path.exists():
        print("Missing private_coldstart_eval.json -- run scripts/build_private_coldstart_eval.py first.")
        return

    with open(private_eval_path) as f:
        private_eval = json.load(f)
    private_schema = merged_private_schema()
    public_eval, public_schema = build_public_eval_set()

    print(f"Public eval set: {len(public_eval)} examples across Zoom/DigitalOcean/Spotify")
    print(f"Private eval set: {len(private_eval)} examples across 5 never-published domains\n")

    with open(OUT_DIR / "experiment5_sft_train.json") as f:
        enterprisesynth_train = json.load(f)

    print(f"Training seed for this run: {train_seed}")
    torch.manual_seed(train_seed)
    print(f"Loading {MODEL_NAME} on {DEVICE}...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    base_model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, dtype=torch.float32).to(DEVICE)
    base_model.eval()

    print("\n=== Training EnterpriseSynth model ===")
    base_for_es = AutoModelForCausalLM.from_pretrained(MODEL_NAME, dtype=torch.float32).to(DEVICE)
    enterprisesynth_model = train_lora(base_for_es, tokenizer, enterprisesynth_train)

    public_verifier = SchemaVerificationEngine(public_schema)
    private_verifier = SchemaVerificationEngine(private_schema)

    print("\n=== Evaluating on PUBLIC held-out set ===")
    results = {
        "public": {
            "base": evaluate(base_model, tokenizer, public_eval, public_verifier),
            "enterprisesynth": evaluate(enterprisesynth_model, tokenizer, public_eval, public_verifier),
        },
        "private": {
            "base": evaluate(base_model, tokenizer, private_eval, private_verifier),
            "enterprisesynth": evaluate(enterprisesynth_model, tokenizer, private_eval, private_verifier),
        },
    }
    print("\n=== Evaluating on PRIVATE (never-published) held-out set ===")

    out_path = OUT_DIR / f"private_coldstart_results_seed{train_seed}.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    print("\n=== SUMMARY: Public vs. Private (never-published) held-out accuracy ===")
    summary = [
        {
            "Eval set": name,
            "Base (untuned)": r["base"]["tool_selection_accuracy"],
            "EnterpriseSynth-tuned": r["enterprisesynth"]["tool_selection_accuracy"],
        }
        for name, r in results.items()
    ]
    print(json.dumps(summary, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    parser_cli = argparse.ArgumentParser()
    parser_cli.add_argument(
        "--seed", type=int, default=42, help="Training-randomness seed (LoRA init)."
    )
    args = parser_cli.parse_args()
    main(train_seed=args.seed)

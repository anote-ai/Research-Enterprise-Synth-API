"""Phase 3: evaluates the EnterpriseSynth-tuned model (trained exactly as in Experiment 5, same
45 GitHub/Stripe/Slack examples) against 6 new held-out real APIs (Twilio, Notion, OpenAI, Jira,
Asana, Trello) on top of the existing Zoom/DigitalOcean/Spotify -- scaling held-out evaluation
from 3 to 9 real APIs, plus the 5 private/synthetic domains from Phase 2. 17 APIs touched by the
pipeline in total (3 training + 9 real held-out + 5 private held-out), in DESIGN_DOC.md's target
15-20 range.

No architectural changes -- same Parser/IntentAgent/TrajectoryAgent/Verifier/finetune code used
everywhere else in this project, applied to new spec inputs only.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from enterprisesynth.finetune import DEVICE, MODEL_NAME, evaluate, train_lora  # noqa: E402
from enterprisesynth.parser import SchemaParser  # noqa: E402
from enterprisesynth.verifier import SchemaVerificationEngine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "generated"
SPEC_DIR = ROOT / "data" / "specs" / "phase3"
TRAIN_SEED = 42

APIS = ["twilio", "notion", "openai", "jira", "asana", "trello"]


def main() -> None:
    parser = SchemaParser()

    with open(OUT_DIR / "experiment5_sft_train.json") as f:
        enterprisesynth_train = json.load(f)

    torch.manual_seed(TRAIN_SEED)
    print(f"Loading {MODEL_NAME} on {DEVICE}...")
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    base_model = AutoModelForCausalLM.from_pretrained(MODEL_NAME, dtype=torch.float32).to(DEVICE)
    base_model.eval()

    print("\n=== Training EnterpriseSynth model ===")
    base_for_es = AutoModelForCausalLM.from_pretrained(MODEL_NAME, dtype=torch.float32).to(DEVICE)
    t_train_start = time.time()
    enterprisesynth_model = train_lora(base_for_es, tokenizer, enterprisesynth_train)
    training_time_s = round(time.time() - t_train_start, 1)
    print(f"Training time: {training_time_s}s")

    results = {}
    eval_timings = {}
    for api_name in APIS:
        with open(SPEC_DIR / f"{api_name}.json") as f:
            schema = parser.parse(json.load(f))
        verifier = SchemaVerificationEngine(schema)
        with open(OUT_DIR / f"phase3_heldout_eval_{api_name}.json") as f:
            eval_set = json.load(f)

        print(f"\n=== Evaluating on held-out {api_name} ({len(eval_set)} intents) ===")
        t0 = time.time()
        base_result = evaluate(base_model, tokenizer, eval_set, verifier)
        es_result = evaluate(enterprisesynth_model, tokenizer, eval_set, verifier)
        eval_timings[api_name] = round(time.time() - t0, 1)
        results[api_name] = {"base": base_result, "enterprisesynth": es_result}

    out_path = OUT_DIR / "phase3_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)

    print("\n=== SUMMARY: Tool Selection Accuracy, 6 new held-out APIs ===")
    summary = [
        {
            "API": api_name,
            "Base": r["base"]["tool_selection_accuracy"],
            "EnterpriseSynth": r["enterprisesynth"]["tool_selection_accuracy"],
        }
        for api_name, r in results.items()
    ]
    print(json.dumps(summary, indent=2))

    print("\n=== Eval wall-clock time per API (seconds, 12 generations each) ===")
    print(json.dumps(eval_timings, indent=2))

    with open(OUT_DIR / "phase3_timings.json", "w") as f:
        json.dump({"training_time_s": training_time_s, "eval_time_s_per_api": eval_timings}, f, indent=2)

    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()

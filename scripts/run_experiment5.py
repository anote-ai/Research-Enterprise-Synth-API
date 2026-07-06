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
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import torch
from peft import LoraConfig, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from enterprisesynth.parser import SchemaParser  # noqa: E402
from enterprisesynth.verifier import SchemaVerificationEngine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
MODEL_NAME = "Qwen/Qwen2.5-0.5B-Instruct"
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
EPOCHS = 3
LR = 3e-4


def format_prompt(intent: str, candidates: list[dict]) -> str:
    tool_list = "\n".join(
        f"- {c['method']} {c['path']} (operation_id={c.get('operation_id')})" for c in candidates
    )
    return (
        f"User request: \"{intent}\"\n\n"
        f"Available tools:\n{tool_list}\n\n"
        f"Respond with ONLY a JSON object: "
        f'{{"selected_method": "...", "selected_path": "...", "parameters": {{...}}}}\n\nResponse:'
    )


def build_training_texts(tokenizer, examples: list[dict]) -> list[dict]:
    texts = []
    for ex in examples:
        prompt = format_prompt(ex["intent"], ex["candidates"])
        completion = " " + json.dumps(ex["output"]) + tokenizer.eos_token
        full = prompt + completion

        prompt_ids = tokenizer(prompt, add_special_tokens=False)["input_ids"]
        full_ids = tokenizer(full, add_special_tokens=False)["input_ids"]
        labels = [-100] * len(prompt_ids) + full_ids[len(prompt_ids):]
        texts.append({"input_ids": full_ids, "labels": labels})
    return texts


def train_lora(base_model, tokenizer, training_examples: list[dict]):
    lora_config = LoraConfig(
        r=8,
        lora_alpha=16,
        target_modules=["q_proj", "v_proj"],
        lora_dropout=0.05,
        task_type="CAUSAL_LM",
    )
    model = get_peft_model(base_model, lora_config)
    model.to(DEVICE)
    model.train()

    data = build_training_texts(tokenizer, training_examples)
    optimizer = torch.optim.AdamW(model.parameters(), lr=LR)

    for epoch in range(EPOCHS):
        total_loss = 0.0
        for example in data:
            input_ids = torch.tensor([example["input_ids"]], device=DEVICE)
            labels = torch.tensor([example["labels"]], device=DEVICE)
            outputs = model(input_ids=input_ids, labels=labels)
            loss = outputs.loss
            loss.backward()
            optimizer.step()
            optimizer.zero_grad()
            total_loss += loss.item()
        print(f"epoch {epoch + 1}/{EPOCHS} avg loss: {total_loss / len(data):.4f}")

    model.eval()
    return model


def generate_response(model, tokenizer, prompt: str) -> str:
    inputs = tokenizer(prompt, return_tensors="pt").to(DEVICE)
    with torch.no_grad():
        output_ids = model.generate(
            **inputs,
            max_new_tokens=150,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    generated = output_ids[0][inputs["input_ids"].shape[1]:]
    return tokenizer.decode(generated, skip_special_tokens=True)


def extract_json(text: str) -> dict | None:
    text = text.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return None


def evaluate(model, tokenizer, eval_examples: list[dict], verifier: SchemaVerificationEngine) -> dict:
    correct_tool = 0
    param_valid_among_correct = 0
    results = []

    for ex in eval_examples:
        prompt = format_prompt(ex["intent"], ex["candidates"])
        raw_response = generate_response(model, tokenizer, prompt)
        parsed = extract_json(raw_response)

        tool_correct = False
        param_valid = None
        if parsed:
            selected = (
                str(parsed.get("selected_method", "")).upper(),
                parsed.get("selected_path", ""),
            )
            gold = (ex["ground_truth_method"].upper(), ex["ground_truth_path"])
            tool_correct = selected == gold
            if tool_correct:
                correct_tool += 1
                result = verifier.verify(
                    parsed.get("selected_method", ""),
                    parsed.get("selected_path", ""),
                    parsed.get("parameters") or {},
                )
                param_valid = result.valid
                if param_valid:
                    param_valid_among_correct += 1

        results.append(
            {
                "intent": ex["intent"],
                "ground_truth": f"{ex['ground_truth_method']} {ex['ground_truth_path']}",
                "raw_response": raw_response,
                "parsed": parsed,
                "tool_correct": tool_correct,
                "param_valid": param_valid,
            }
        )

    n = len(eval_examples)
    return {
        "n": n,
        "tool_selection_accuracy": round(100 * correct_tool / n, 1) if n else 0,
        "parameter_validity_among_correct": (
            round(100 * param_valid_among_correct / correct_tool, 1) if correct_tool else "n/a"
        ),
        "results": results,
    }


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

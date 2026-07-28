from __future__ import annotations

import json

import torch
from peft import LoraConfig, get_peft_model

from .verifier import SchemaVerificationEngine

MODEL_NAME = "Qwen/Qwen2.5-0.5B-Instruct"
DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
EPOCHS = 3
LR = 3e-4


def format_prompt(intent: str, candidates: list[dict]) -> str:
    tool_list = "\n".join(
        f"- {c['method']} {c['path']} (operation_id={c.get('operation_id')})" for c in candidates
    )
    return (
        f'User request: "{intent}"\n\n'
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
    generated = output_ids[0][inputs["input_ids"].shape[1] :]
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

"""Experiment 3: Agent Trajectory Generation.

Reuses the 45 intents from Experiment 2 (each tagged with its ground-truth source endpoint).
For each intent, builds a candidate tool list (the 5 "source" endpoints for that API + 10 seeded
distractors, shuffled) and asks the Trajectory Generator to select a tool and produce a
trajectory. Tool Selection Accuracy is measured against the known ground-truth endpoint.

Workflow Completeness is not applicable at this pilot scale -- Experiment 2's intents are
single-endpoint, not multi-step chains -- and is reported as such, not estimated.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from enterprisesynth.parser import SchemaParser  # noqa: E402
from enterprisesynth.sampling import sample_and_distract  # noqa: E402
from enterprisesynth.trajectory_agent import TrajectoryGenerator  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SPECS = {
    "GitHub": "data/specs/github.json",
    "Stripe": "data/specs/stripe.json",
    "Slack": "data/specs/slack.json",
}
N_DISTRACTORS = 10
SEED = 42


def main() -> None:
    parser = SchemaParser()
    generator = TrajectoryGenerator()

    with open(ROOT / "data" / "generated" / "experiment2_intents.json") as f:
        intents_by_api = json.load(f)

    all_results = {}
    summary_rows = []

    for api_name, spec_path in SPECS.items():
        with open(ROOT / spec_path) as f:
            raw = json.load(f)
        schema = parser.parse(raw)
        by_key = {(e.method, e.path): e for e in schema.endpoints}

        source_endpoints = [
            by_key[(item["method"], item["path"])]
            for item in intents_by_api[api_name]
            if (item["method"], item["path"]) in by_key
        ]
        _, distractors = sample_and_distract(
            schema, seed=SEED, n_distractors=N_DISTRACTORS, exclude=source_endpoints
        )
        shuffle_rng = random.Random(SEED)

        api_results = []
        correct_selection = 0
        total_trials = 0
        required_params_satisfied = 0

        for item in intents_by_api[api_name]:
            ground_truth_key = (item["method"], item["path"])
            ground_truth_endpoint = by_key.get(ground_truth_key)
            if ground_truth_endpoint is None:
                continue

            candidates = source_endpoints + distractors
            shuffle_rng.shuffle(candidates)

            for intent_text in item["intents"]:
                total_trials += 1
                trajectory = generator.generate_trajectory(intent_text, candidates)

                selected_correct = False
                params_ok = None
                if trajectory:
                    selected = (
                        str(trajectory.get("selected_method", "")).upper(),
                        trajectory.get("selected_path", ""),
                    )
                    selected_correct = selected == ground_truth_key
                    if selected_correct:
                        correct_selection += 1
                        required_names = {p.name for p in ground_truth_endpoint.parameters if p.required}
                        generated_names = set((trajectory.get("parameters") or {}).keys())
                        params_ok = required_names.issubset(generated_names)
                        if params_ok:
                            required_params_satisfied += 1

                api_results.append(
                    {
                        "intent": intent_text,
                        "ground_truth": f"{ground_truth_key[0]} {ground_truth_key[1]}",
                        "trajectory": trajectory,
                        "selected_correct": selected_correct,
                        "required_params_satisfied": params_ok,
                    }
                )
                print(
                    f"[{api_name}] correct={selected_correct} :: {intent_text[:70]}"
                )

        all_results[api_name] = api_results
        tool_accuracy = 100 * correct_selection / total_trials if total_trials else 0
        param_validity = (
            100 * required_params_satisfied / correct_selection if correct_selection else None
        )

        summary_rows.append(
            {
                "API": api_name,
                "Trials": total_trials,
                "Correct tool selection": correct_selection,
                "Tool Selection Accuracy (%)": round(tool_accuracy, 1),
                "Parameter Validity (%, among correct selections)": (
                    round(param_validity, 1) if param_validity is not None else "n/a"
                ),
                "Workflow Completeness": "not applicable at this pilot scale (single-endpoint intents only)",
            }
        )

    out_dir = ROOT / "data" / "generated"
    with open(out_dir / "experiment3_trajectories.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print()
    print(json.dumps(summary_rows, indent=2))


if __name__ == "__main__":
    main()

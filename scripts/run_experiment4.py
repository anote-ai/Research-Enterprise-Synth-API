"""Experiment 4: Schema-Based Verification.

Testing the verifier only on the already-correct Experiment 3 trajectories would be circular
(they were already confirmed correct) and would show nothing about the verifier's actual job:
catching bad trajectories. So for each valid trajectory, this script also generates a
deliberately corrupted variant (wrong method, missing required param, invalid path, or wrong
param type -- cycled deterministically) and checks whether the verifier correctly flags it.

Reports both: Verification Pass Rate (on the valid trajectories -- should be high, few false
rejections) and Invalid Cases Detected (on the corrupted trajectories -- the verifier's real
discriminative power, i.e. recall on planted errors).
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from enterprisesynth.parser import SchemaParser  # noqa: E402
from enterprisesynth.verifier import SchemaVerificationEngine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SPECS = {
    "GitHub": "data/specs/github.json",
    "Stripe": "data/specs/stripe.json",
    "Slack": "data/specs/slack.json",
}

CORRUPTION_TYPES = ["wrong_method", "missing_param", "invalid_path", "wrong_type"]


def corrupt(trajectory: dict, corruption_type: str, required_param_names: set[str]) -> dict | None:
    corrupted = copy.deepcopy(trajectory)
    params = corrupted.get("parameters") or {}

    if corruption_type == "wrong_method":
        current = str(corrupted.get("selected_method", "")).upper()
        corrupted["selected_method"] = "PATCH" if current != "PATCH" else "PUT"
    elif corruption_type == "missing_param":
        # Must target a genuinely *required* param -- dropping an optional one wouldn't
        # violate anything and would make this corruption type meaningless to test.
        required_present = [k for k in params if k in required_param_names]
        if not required_present:
            return None
        params = {k: v for k, v in params.items() if k != required_present[0]}
        corrupted["parameters"] = params
    elif corruption_type == "invalid_path":
        corrupted["selected_path"] = str(corrupted.get("selected_path", "")) + "/nonexistent-suffix"
    elif corruption_type == "wrong_type":
        if not params:
            return None
        key_to_break = next(iter(params))
        params = dict(params)
        params[key_to_break] = {"unexpectedly": "an object"}
        corrupted["parameters"] = params

    return corrupted


def main() -> None:
    parser = SchemaParser()

    with open(ROOT / "data" / "generated" / "experiment3_trajectories.json") as f:
        trajectories_by_api = json.load(f)

    summary_rows = []
    all_results = {}

    for api_name, spec_path in SPECS.items():
        with open(ROOT / spec_path) as f:
            raw = json.load(f)
        schema = parser.parse(raw)
        engine = SchemaVerificationEngine(schema)
        by_key = {(e.method, e.path): e for e in schema.endpoints}

        valid_pass = 0
        valid_total = 0
        corrupted_detected = 0
        corrupted_total = 0
        api_results = []

        valid_items = [
            item
            for item in trajectories_by_api[api_name]
            if item.get("selected_correct") and item.get("trajectory")
        ]

        for i, item in enumerate(valid_items):
            trajectory = item["trajectory"]
            valid_total += 1
            result = engine.verify(
                trajectory.get("selected_method", ""),
                trajectory.get("selected_path", ""),
                trajectory.get("parameters") or {},
            )
            if result.valid:
                valid_pass += 1

            endpoint_key = (
                str(trajectory.get("selected_method", "")).upper(),
                trajectory.get("selected_path", ""),
            )
            endpoint = by_key.get(endpoint_key)
            required_param_names = (
                {p.name for p in endpoint.parameters if p.required} if endpoint else set()
            )

            corruption_type = CORRUPTION_TYPES[i % len(CORRUPTION_TYPES)]
            corrupted = corrupt(trajectory, corruption_type, required_param_names)
            corrupted_result = None
            if corrupted is not None:
                corrupted_total += 1
                corrupted_result = engine.verify(
                    corrupted.get("selected_method", ""),
                    corrupted.get("selected_path", ""),
                    corrupted.get("parameters") or {},
                )
                if not corrupted_result.valid:
                    corrupted_detected += 1

            api_results.append(
                {
                    "intent": item["intent"],
                    "original_valid": result.model_dump(),
                    "corruption_type": corruption_type,
                    "corrupted_valid": corrupted_result.model_dump() if corrupted_result else None,
                }
            )

        pass_rate = 100 * valid_pass / valid_total if valid_total else 0
        detection_rate = 100 * corrupted_detected / corrupted_total if corrupted_total else 0

        all_results[api_name] = api_results
        summary_rows.append(
            {
                "API": api_name,
                "Valid trajectories tested": valid_total,
                "Verification Pass Rate (%)": round(pass_rate, 1),
                "Corrupted trajectories tested": corrupted_total,
                "Invalid Cases Detected (%)": round(detection_rate, 1),
            }
        )

    out_dir = ROOT / "data" / "generated"
    with open(out_dir / "experiment4_verification.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print(json.dumps(summary_rows, indent=2))


if __name__ == "__main__":
    main()

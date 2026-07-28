"""Ablation: Haiku 4.5 semantic-plausibility check layered on the deterministic verifier (RQ3).

Referenced in paper/main.tex S4.4 and DESIGN_DOC.md S5.4 but never implemented -- this script
closes that gap (see the repo audit).

Tests the actual claim: does a cheap LLM catch errors the deterministic verifier CANNOT catch by
design? The deterministic verifier only checks structure (types, required fields, existence) --
it has no notion of whether a parameter VALUE makes business sense. So this script:

1. Runs the checker on the 45 real, valid Experiment 3 trajectories (expect: mostly "plausible" --
   measures the false-positive rate of adding this check).
2. Constructs a new corruption class -- "semantically implausible but structurally valid" (negate
   a numeric value, or replace a string value with an obvious placeholder) -- confirms via the
   Stage 6 verifier that these STILL PASS structurally (proving the deterministic gate cannot see
   this class of error), then checks whether Haiku catches them.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from enterprisesynth.parser import SchemaParser  # noqa: E402
from enterprisesynth.semantic_checker import SemanticPlausibilityChecker  # noqa: E402
from enterprisesynth.verifier import SchemaVerificationEngine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SPECS = {
    "GitHub": "data/specs/github.json",
    "Stripe": "data/specs/stripe.json",
    "Slack": "data/specs/slack.json",
}


def make_semantically_implausible(trajectory: dict) -> dict | None:
    params = trajectory.get("parameters") or {}
    if not params:
        return None
    corrupted = copy.deepcopy(trajectory)
    new_params = dict(params)

    for key, value in params.items():
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            new_params[key] = -abs(value) * 1000 - 999999
            corrupted["parameters"] = new_params
            return corrupted
        if isinstance(value, str) and value:
            new_params[key] = "PLACEHOLDER_INVALID_VALUE_XYZ_NOT_REAL_DATA"
            corrupted["parameters"] = new_params
            return corrupted
    return None


def main() -> None:
    parser = SchemaParser()
    checker = SemanticPlausibilityChecker()

    with open(ROOT / "data" / "generated" / "experiment3_trajectories.json") as f:
        trajectories_by_api = json.load(f)

    all_results = {}
    summary = []

    for api_name, spec_path in SPECS.items():
        with open(ROOT / spec_path) as f:
            raw = json.load(f)
        schema = parser.parse(raw)
        engine = SchemaVerificationEngine(schema)

        valid_items = [
            item
            for item in trajectories_by_api[api_name]
            if item.get("selected_correct") and item.get("trajectory")
        ]

        api_results = []
        valid_judged_plausible = 0
        valid_total = 0
        corrupted_still_structurally_valid = 0
        corrupted_caught_by_haiku = 0
        corrupted_total = 0

        for item in valid_items:
            trajectory = item["trajectory"]
            intent = item["intent"]

            valid_total += 1
            judgment = checker.check(intent, trajectory)
            if judgment and judgment.get("plausible") is True:
                valid_judged_plausible += 1

            implausible = make_semantically_implausible(trajectory)
            corruption_result = None
            structural_check = None
            if implausible is not None:
                corrupted_total += 1
                structural_check = engine.verify(
                    implausible.get("selected_method", ""),
                    implausible.get("selected_path", ""),
                    implausible.get("parameters") or {},
                )
                if structural_check.valid:
                    corrupted_still_structurally_valid += 1

                corruption_result = checker.check(intent, implausible)
                if corruption_result and corruption_result.get("plausible") is False:
                    corrupted_caught_by_haiku += 1

            api_results.append(
                {
                    "intent": intent,
                    "valid_trajectory_judgment": judgment,
                    "semantically_implausible_trajectory": implausible,
                    "structural_check_on_implausible": (
                        structural_check.model_dump() if structural_check else None
                    ),
                    "haiku_judgment_on_implausible": corruption_result,
                }
            )
            print(
                f"[{api_name}] valid_plausible={judgment.get('plausible') if judgment else None} "
                f"| implausible_still_structurally_valid={structural_check.valid if structural_check else 'n/a'} "
                f"| haiku_caught_implausible={corruption_result.get('plausible') is False if corruption_result else 'n/a'}"
            )

        all_results[api_name] = api_results
        summary.append(
            {
                "API": api_name,
                "Valid trajectories judged plausible": f"{valid_judged_plausible}/{valid_total}",
                "Semantically-implausible corruptions still structurally VALID (deterministic gate blind to them)": (
                    f"{corrupted_still_structurally_valid}/{corrupted_total}"
                ),
                "Of those, caught by Haiku semantic check": f"{corrupted_caught_by_haiku}/{corrupted_total}",
            }
        )

    out_dir = ROOT / "data" / "generated"
    with open(out_dir / "ablation_haiku_semantic_check.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print()
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

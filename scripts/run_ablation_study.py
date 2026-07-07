"""Ablation study over EnterpriseSynth's actual implemented pipeline: Parser -> Intent Agent ->
Trajectory Agent -> Verifier. Does NOT test a Knowledge Graph or a separate Planner module --
neither exists in the current codebase (Stage 2 was never built; Stages 4+5 were combined into
one call from the start). See DESIGN_DOC.md for the full accounting of what is and isn't real.

A1 (without Intent Generation): NoIntentTrajectoryAgent generates directly from an endpoint, no
    user intent. Compared against Experiments 2+3's full pipeline on the same 45 endpoint samples.
A2 (without Verification): reuses Experiment 4's corruption data directly -- without a verifier,
    0% of the 44 planted errors would be caught; with one, 100% are (already measured).
A3 (without vs with API descriptions): DescriptionAwareIntentAgent adds descriptions, which the
    baseline (Experiment 2) never had (confirmed: no 'description' field existed before this
    ablation was requested).
A4 (endpoint-only vs full-API context): FullContextIntentAgent adds the other endpoints in the
    same API as context, which the baseline (Experiment 2) never had either.
"""
from __future__ import annotations

import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from enterprisesynth.ablation_agents import (  # noqa: E402
    DescriptionAwareIntentAgent,
    FullContextIntentAgent,
    NoIntentTrajectoryAgent,
)
from enterprisesynth.parser import SchemaParser  # noqa: E402
from enterprisesynth.verifier import SchemaVerificationEngine  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SPECS = {
    "GitHub": "data/specs/github.json",
    "Stripe": "data/specs/stripe.json",
    "Slack": "data/specs/slack.json",
}
SAMPLE_SIZE = 5
INTENTS_PER_ENDPOINT = 3
N_DISTRACTORS = 10
SEED = 42


def sampled_endpoints(schema, seed=SEED):
    rng = random.Random(seed)
    sample = rng.sample(schema.endpoints, min(SAMPLE_SIZE, len(schema.endpoints)))
    pool = [e for e in schema.endpoints if e not in sample]
    distractors = rng.sample(pool, min(N_DISTRACTORS, len(pool)))
    return sample, distractors


def run_a1_without_intent():
    """Direct endpoint -> trajectory, no intent. Metrics: instruction diversity (exact-string),
    parameter validity (via Stage 6 verifier) -- compared against Experiments 2+3's baseline."""
    agent = NoIntentTrajectoryAgent()
    parser = SchemaParser()
    results = {}
    summary = []

    for api_name, spec_path in SPECS.items():
        with open(ROOT / spec_path) as f:
            raw = json.load(f)
        schema = parser.parse(raw)
        engine = SchemaVerificationEngine(schema)
        sample, _ = sampled_endpoints(schema)

        api_results = []
        instructions = []
        valid_count = 0
        total = 0

        for endpoint in sample:
            for _ in range(INTENTS_PER_ENDPOINT):
                total += 1
                out = agent.generate(endpoint)
                if not out:
                    api_results.append({"endpoint": f"{endpoint.method} {endpoint.path}", "output": None})
                    continue
                instructions.append(out.get("instruction", ""))
                result = engine.verify(endpoint.method, endpoint.path, out.get("parameters") or {})
                if result.valid:
                    valid_count += 1
                api_results.append(
                    {
                        "endpoint": f"{endpoint.method} {endpoint.path}",
                        "output": out,
                        "param_valid": result.valid,
                    }
                )
                print(f"[A1:{api_name}] {endpoint.method} {endpoint.path} -> valid={result.valid}")

        results[api_name] = api_results
        unique = len(set(instructions))
        summary.append(
            {
                "API": api_name,
                "Trials": total,
                "Parameter Validity (%)": round(100 * valid_count / total, 1) if total else 0,
                "Instruction Diversity (%, exact-string)": (
                    round(100 * unique / len(instructions), 1) if instructions else 0
                ),
            }
        )

    return results, summary


def run_a3_with_descriptions():
    agent = DescriptionAwareIntentAgent()
    parser = SchemaParser()
    results = {}
    summary = []

    for api_name, spec_path in SPECS.items():
        with open(ROOT / spec_path) as f:
            raw = json.load(f)
        schema = parser.parse(raw)
        sample, _ = sampled_endpoints(schema)

        api_results = []
        all_intents = []
        covered = 0

        for endpoint in sample:
            intents = agent.generate_intents(endpoint, n=INTENTS_PER_ENDPOINT)
            if intents:
                covered += 1
            all_intents.extend(intents)
            api_results.append(
                {
                    "endpoint": f"{endpoint.method} {endpoint.path}",
                    "description": endpoint.description,
                    "intents": intents,
                }
            )
            print(f"[A3:{api_name}] {endpoint.method} {endpoint.path} -> {len(intents)} intents")

        results[api_name] = api_results
        unique = len(set(all_intents))
        summary.append(
            {
                "API": api_name,
                "Coverage (%)": round(100 * covered / len(sample), 1) if sample else 0,
                "Total intents": len(all_intents),
                "Diversity (%, exact-string)": (
                    round(100 * unique / len(all_intents), 1) if all_intents else 0
                ),
            }
        )

    return results, summary


def run_a4_full_context():
    agent = FullContextIntentAgent()
    parser = SchemaParser()
    results = {}
    summary = []

    for api_name, spec_path in SPECS.items():
        with open(ROOT / spec_path) as f:
            raw = json.load(f)
        schema = parser.parse(raw)
        sample, distractors = sampled_endpoints(schema)

        api_results = []
        all_intents = []
        covered = 0
        multi_step_mentions = 0

        for endpoint in sample:
            other = [e for e in sample if e != endpoint] + distractors
            intents = agent.generate_intents(endpoint, other, n=INTENTS_PER_ENDPOINT)
            if intents:
                covered += 1
            all_intents.extend(intents)
            for i in intents:
                if any(
                    kw in i.lower()
                    for kw in ("then", "after", "and then", "once", "followed by", "before")
                ):
                    multi_step_mentions += 1
            api_results.append(
                {"endpoint": f"{endpoint.method} {endpoint.path}", "intents": intents}
            )
            print(f"[A4:{api_name}] {endpoint.method} {endpoint.path} -> {len(intents)} intents")

        results[api_name] = api_results
        unique = len(set(all_intents))
        summary.append(
            {
                "API": api_name,
                "Coverage (%)": round(100 * covered / len(sample), 1) if sample else 0,
                "Total intents": len(all_intents),
                "Diversity (%, exact-string)": (
                    round(100 * unique / len(all_intents), 1) if all_intents else 0
                ),
                "Sequencing-language mentions": multi_step_mentions,
            }
        )

    return results, summary


def main() -> None:
    out_dir = ROOT / "data" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)

    print("=== A1: without Intent Generation ===")
    a1_results, a1_summary = run_a1_without_intent()
    print(json.dumps(a1_summary, indent=2))

    print("\n=== A3: with API descriptions (vs. Experiment 2 baseline, no descriptions) ===")
    a3_results, a3_summary = run_a3_with_descriptions()
    print(json.dumps(a3_summary, indent=2))

    print("\n=== A4: full-API context (vs. Experiment 2 baseline, endpoint-only) ===")
    a4_results, a4_summary = run_a4_full_context()
    print(json.dumps(a4_summary, indent=2))

    with open(out_dir / "ablation_a1_no_intent.json", "w") as f:
        json.dump(a1_results, f, indent=2)
    with open(out_dir / "ablation_a3_with_descriptions.json", "w") as f:
        json.dump(a3_results, f, indent=2)
    with open(out_dir / "ablation_a4_full_context.json", "w") as f:
        json.dump(a4_results, f, indent=2)
    with open(out_dir / "ablation_summary.json", "w") as f:
        json.dump({"A1": a1_summary, "A3": a3_summary, "A4": a4_summary}, f, indent=2)


if __name__ == "__main__":
    main()

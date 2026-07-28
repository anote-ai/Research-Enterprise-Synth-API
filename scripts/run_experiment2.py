"""Experiment 2: Intent Generation Evaluation.

Pilot scale: samples 5 endpoints per API (seeded, reproducible), generates 3 intents each via
the Intent Synthesis Agent (Claude Sonnet 5), and reports Intent Coverage + a simple exact-string
diversity proxy. Raw output is saved to data/generated/experiment2_intents.json.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from enterprisesynth.intent_agent import IntentSynthesisAgent  # noqa: E402
from enterprisesynth.parser import SchemaParser  # noqa: E402
from enterprisesynth.sampling import sample_and_distract  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SPECS = {
    "GitHub": "data/specs/github.json",
    "Stripe": "data/specs/stripe.json",
    "Slack": "data/specs/slack.json",
}
SAMPLE_SIZE = 5
INTENTS_PER_ENDPOINT = 3
SEED = 42


def main() -> None:
    parser = SchemaParser()
    agent = IntentSynthesisAgent()
    all_results = {}
    summary_rows = []

    for name, path in SPECS.items():
        with open(ROOT / path) as f:
            raw = json.load(f)
        schema = parser.parse(raw)

        sample, _ = sample_and_distract(schema, seed=SEED, sample_size=SAMPLE_SIZE)

        api_results = []
        covered = 0
        all_intents: list[str] = []

        for endpoint in sample:
            intents = agent.generate_intents(endpoint, n=INTENTS_PER_ENDPOINT)
            if intents:
                covered += 1
            all_intents.extend(intents)
            api_results.append(
                {
                    "method": endpoint.method,
                    "path": endpoint.path,
                    "operation_id": endpoint.operation_id,
                    "intents": intents,
                }
            )
            print(f"[{name}] {endpoint.method} {endpoint.path} -> {len(intents)} intents")

        all_results[name] = api_results

        coverage_pct = 100 * covered / len(sample) if sample else 0
        unique_intents = len(set(all_intents))
        diversity_pct = 100 * unique_intents / len(all_intents) if all_intents else 0

        summary_rows.append(
            {
                "API": name,
                "Endpoints sampled": len(sample),
                "Coverage (%)": round(coverage_pct, 1),
                "Total intents generated": len(all_intents),
                "Unique intents": unique_intents,
                "Diversity (unique/total %)": round(diversity_pct, 1),
            }
        )

    out_dir = ROOT / "data" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "experiment2_intents.json", "w") as f:
        json.dump(all_results, f, indent=2)

    print()
    print(json.dumps(summary_rows, indent=2))


if __name__ == "__main__":
    main()

"""Builds the held-out evaluation set from the 5 private, never-published enterprise specs
(data/specs/private/*.json) -- the true cold-start generalization test for RQ4.

Unlike Zoom/DigitalOcean/Spotify (public, well-documented, plausibly in pretraining data), these
specs do not correspond to any real, publicly-documented API, so a base model cannot have prior
exposure to their exact endpoint shapes.

Samples endpoints from each of the 5 private domains, generates real user intents for each via
the same IntentSynthesisAgent used everywhere else in the pipeline (no special-casing), and writes
a combined held-out eval set in the same format scripts/scale_experiment5_heldout.py's evaluate()
expects.
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
PRIVATE_DIR = ROOT / "data" / "specs" / "private"
OUT_DIR = ROOT / "data" / "generated"
SEED = 42
SAMPLE_SIZE = 3  # per domain; 5 domains x 3 endpoints x 2 intents = 30 eval examples
INTENTS_PER_ENDPOINT = 2
DISTRACTORS_PER_DOMAIN = 10


def main() -> None:
    parser = SchemaParser()
    agent = IntentSynthesisAgent()

    domain_files = sorted(PRIVATE_DIR.glob("*.json"))
    if not domain_files:
        print("No private specs found -- run scripts/generate_private_specs.py first.")
        return

    all_eval_examples = []
    all_candidates_by_domain = {}

    for spec_path in domain_files:
        domain = spec_path.stem
        with open(spec_path) as f:
            raw = json.load(f)
        schema = parser.parse(raw)
        sample, distractors = sample_and_distract(
            schema, seed=SEED, sample_size=SAMPLE_SIZE, n_distractors=DISTRACTORS_PER_DOMAIN
        )
        all_candidates_by_domain[domain] = sample + distractors

        for endpoint in sample:
            intents = agent.generate_intents(endpoint, n=INTENTS_PER_ENDPOINT)
            for intent_text in intents:
                all_eval_examples.append(
                    {
                        "domain": domain,
                        "intent": intent_text,
                        "ground_truth_method": endpoint.method,
                        "ground_truth_path": endpoint.path,
                        "candidates": [
                            {"method": e.method, "path": e.path, "operation_id": e.operation_id}
                            for e in (sample + distractors)
                        ],
                    }
                )
            print(f"[{domain}] {endpoint.method} {endpoint.path} -> {len(intents)} intents")

    out_path = OUT_DIR / "private_coldstart_eval.json"
    with open(out_path, "w") as f:
        json.dump(all_eval_examples, f, indent=2)

    print(f"\nWrote {out_path}: {len(all_eval_examples)} eval examples across {len(domain_files)} private domains")


if __name__ == "__main__":
    main()

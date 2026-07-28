"""Phase 3: builds held-out eval sets for 6 new real public APIs (Twilio, Notion, OpenAI, Jira,
Asana, Trello -- data/specs/phase3/*.json, fetched from APIs.guru) to scale the held-out
evaluation set from 3 APIs (Zoom/DigitalOcean/Spotify) to 9, on top of the 5 private/synthetic
domains from Phase 2 -- 17 APIs touched by the pipeline in total, in DESIGN_DOC.md's target
15-20 range.

Same intent-generation pattern as scripts/scale_experiment5_heldout.py and
build_private_coldstart_eval.py -- no pipeline code changes, just new spec inputs, matching
Phase 3's own "no architectural modifications" framing.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "code"))

from enterprisesynth.intent_agent import IntentSynthesisAgent  # noqa: E402
from enterprisesynth.parser import SchemaParser  # noqa: E402
from enterprisesynth.sampling import sample_and_distract  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SPEC_DIR = ROOT / "data" / "specs" / "phase3"
OUT_DIR = ROOT / "data" / "generated"
SEED = 42
SAMPLE_SIZE = 3
INTENTS_PER_ENDPOINT = 2
DISTRACTORS = 15

APIS = ["twilio", "notion", "openai", "jira", "asana", "trello"]


def main() -> None:
    parser = SchemaParser()
    agent = IntentSynthesisAgent()

    all_results = {}
    timings = {}
    for api_name in APIS:
        t0 = time.time()
        with open(SPEC_DIR / f"{api_name}.json") as f:
            raw = json.load(f)
        schema = parser.parse(raw)
        sample, distractors = sample_and_distract(
            schema, seed=SEED, sample_size=SAMPLE_SIZE, n_distractors=DISTRACTORS
        )
        candidates = sample + distractors

        eval_examples = []
        for endpoint in sample:
            intents = agent.generate_intents(endpoint, n=INTENTS_PER_ENDPOINT)
            for intent_text in intents:
                eval_examples.append(
                    {
                        "intent": intent_text,
                        "ground_truth_method": endpoint.method,
                        "ground_truth_path": endpoint.path,
                        "candidates": [
                            {"method": e.method, "path": e.path, "operation_id": e.operation_id}
                            for e in candidates
                        ],
                    }
                )
            print(f"[{api_name}] {endpoint.method} {endpoint.path} -> {len(intents)} intents")

        out_path = OUT_DIR / f"phase3_heldout_eval_{api_name}.json"
        with open(out_path, "w") as f:
            json.dump(eval_examples, f, indent=2)
        all_results[api_name] = len(eval_examples)
        timings[api_name] = round(time.time() - t0, 1)

    print("\n=== Built eval sets ===")
    print(json.dumps(all_results, indent=2))
    print("\n=== Generation wall-clock time per API (seconds) ===")
    print(json.dumps(timings, indent=2))

    with open(OUT_DIR / "phase3_eval_build_timings.json", "w") as f:
        json.dump(timings, f, indent=2)


if __name__ == "__main__":
    main()

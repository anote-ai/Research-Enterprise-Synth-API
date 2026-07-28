from __future__ import annotations

import random

from .schemas import APISchema, Endpoint

DEFAULT_SEED = 42
DEFAULT_N_DISTRACTORS = 10


def sample_and_distract(
    schema: APISchema,
    seed: int = DEFAULT_SEED,
    sample_size: int | None = None,
    n_distractors: int = DEFAULT_N_DISTRACTORS,
    exclude: list[Endpoint] | None = None,
) -> tuple[list[Endpoint] | None, list[Endpoint]]:
    """Deterministic endpoint sampling shared by Experiments 2/3/5 and the ablation study.

    Uses a single `random.Random(seed)` instance for both steps, in this order, matching the
    exact call sequence every pipeline script has used historically -- refactored here from
    four near-identical copies (see the audit at
    github.com/Rashmioffcialpage/enterprisesynth-api/issues/1) into one implementation.

    If `sample_size` is given, first samples that many endpoints (this is Experiment 2's "5
    source endpoints per API" step), then samples `n_distractors` more from the remainder.

    If `sample_size` is None, skips the first step entirely -- for callers (Experiment 3,
    Experiment 5 prep) that already have their "source" endpoints from a prior experiment's
    committed JSON and only need a fresh distractor pool, excluding those known endpoints via
    `exclude`.
    """
    rng = random.Random(seed)

    if sample_size is not None:
        sample = rng.sample(schema.endpoints, min(sample_size, len(schema.endpoints)))
        exclude_keys = {(e.method, e.path) for e in sample}
    else:
        sample = None
        exclude_keys = {(e.method, e.path) for e in (exclude or [])}

    pool = [e for e in schema.endpoints if (e.method, e.path) not in exclude_keys]
    distractors = rng.sample(pool, min(n_distractors, len(pool)))

    return sample, distractors

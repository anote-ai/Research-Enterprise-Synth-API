# Reproducibility Guide

What is currently reproducible in-repo, what needs external resources (an Anthropic API key with
credit, a machine capable of local LoRA fine-tuning), and which artifacts should or should not be
treated as final paper evidence.

## Evidence Types

| Evidence type | Status | Where it lives | Cite as final paper evidence? |
| --- | --- | --- | --- |
| Experiment 1 (schema parsing) | Measured, no external deps | `scripts/run_experiment1.py` | Yes, at this pilot's 3-API scale |
| Experiment 2 (intent generation) | Measured, needs `ANTHROPIC_API_KEY` | `scripts/run_experiment2.py` | Yes, pilot scale (15 endpoints/API) |
| Experiment 3 (trajectory generation) | Measured, needs API key + Exp 2 output | `scripts/run_experiment3.py` | Yes, with the self-consistency caveat in `RESULTS.md` |
| Experiment 4 (schema verification) | Measured, no external deps, needs Exp 3 output | `scripts/run_experiment4.py` | Yes — the strongest result in the repo |
| Experiment 5 (downstream fine-tuning) | Measured, needs API key + local torch/transformers/peft | `scripts/run_experiment5.py` | Yes, for the substitute model (Qwen2.5-0.5B) explicitly, not yet for the paper's 7–8B target |
| Ablation A1/A3/A4 | Measured, needs API key | `scripts/run_ablation_study.py` | Yes, with A3/A4's "inconclusive" framing preserved |
| Ablation A2 | Measured, reuses Experiment 4's data, no re-run needed | (no script — see `RESULTS.md`) | Yes |
| Ablation A5 (Haiku semantic check) | Measured, needs API key + Exp 3 output | `scripts/run_ablation_haiku.py` | Yes, with the 33% GitHub false-positive rate disclosed |
| Knowledge Graph / Planner / Response Schema ablations | **Not run — components don't exist** | n/a | No — see `DESIGN_DOC.md` §8.1 for why these were dropped rather than faked |
| 5-seed multi-API scaling sweep | Measured, needs API key (first seed only; rest reuse committed eval sets) + local torch | `scripts/scale_experiment5_heldout.py --seed N` + `scripts/aggregate_multi_seed_scaling.py` | Yes — mean ± std across 5 real seeds, not a single draw |
| Private cold-start validation | Measured, needs API key + local torch; single run, not seed-swept | `scripts/generate_private_specs.py`, `build_private_coldstart_eval.py`, `run_private_coldstart_eval.py` | Yes, with the "single un-seeded run" caveat explicit in `RESULTS.md` |
| 6-API scale-up (Twilio/Notion/OpenAI/Jira/Asana/Trello) | Measured, needs API key + local torch | `scripts/build_phase3_eval.py`, `run_phase3_eval.py` | Yes |
| LLM-as-a-judge semantic evaluation | Measured, needs API key; judges a committed seed-42 run | `scripts/run_llm_judge_eval.py` | Yes — the 2× overstatement finding is real, independently-scored data |

The most important boundary: every script above produces **real measured numbers from a real
model call or real code path**, never a projected or illustrative number. Where a result is
pilot-scale (17 APIs, tens of examples per experiment), that is stated explicitly in `RESULTS.md`,
not implied to be larger.

## Environment

```bash
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
```

Python 3.12; Pydantic for schema modeling and Stage 4 (verification) validation; PyYAML for
Stage 1 (parsing); the Anthropic SDK (Claude Sonnet 5) for Stages 2--3. `networkx` is listed in
`pyproject.toml` for the target architecture's Knowledge Graph builder but is not used by any
implemented code yet. No GPU is required for generation (API-based models); a single GPU/MPS
device is needed only for the LoRA fine-tuning step (see External Requirements below).

CI (`.github/workflows/ci.yml`) runs the API-independent test suite (`tests/`, 45 tests with
`torch` installed locally, 39 in CI without it — `test_finetune.py`'s 6 tests are skipped via
`pytest.importorskip`) on Python 3.10/3.11/3.12 on every push/PR to `main`. It does **not** run
the experiment scripts, since those need a funded `ANTHROPIC_API_KEY` that isn't configured as a
repo secret.

## External Requirements

- **Experiments 2, 3, 5, and the ablation study (A1/A3/A4)** need `ANTHROPIC_API_KEY` set (env var
  or `.env` file at the repo root — already gitignored) on an account with available credit. A
  billing/credit error (`anthropic.BadRequestError: ... credit balance is too low`) means the key
  is valid but the account has no funds — this is a console.anthropic.com billing fix, not a code
  bug.
- **Experiment 5** additionally needs `torch`, `transformers`, `peft`, `accelerate` installed
  (`./.venv/bin/pip install torch transformers peft accelerate`) and downloads
  Qwen2.5-0.5B-Instruct (~1GB) on first run. No GPU is required — it runs on Apple Silicon's MPS
  backend or CPU; a real GPU would only be needed for the paper's eventual 7–8B target model, which
  this repo does not yet attempt (see `DESIGN_DOC.md` §6.7 for the hardware-scoping rationale).
- **Figures** (`scripts/make_figures.py`) need `matplotlib` and read only committed
  `data/generated/*.json` — no API key, no re-running experiments.

## Fastest Reproduction Paths

### 1. Sanity check (no API key, ~1 second)

```bash
./.venv/bin/python -m pytest tests/ -v
```

### 2. Schema parsing + verification (no API key, ~1 second)

```bash
./.venv/bin/python scripts/run_experiment1.py
./.venv/bin/python scripts/run_experiment4.py   # needs experiment3_trajectories.json, already committed
```

### 3. Full pipeline from scratch (needs a funded API key, several minutes)

```bash
set -a && source .env && set +a
./.venv/bin/python scripts/run_experiment2.py
./.venv/bin/python scripts/run_experiment3.py
./.venv/bin/python scripts/run_experiment4.py
./.venv/bin/python scripts/prepare_experiment5_data.py
./.venv/bin/python scripts/run_experiment5.py
./.venv/bin/python scripts/run_ablation_study.py
```

### 4. Regenerate figures only (no API key)

```bash
./.venv/bin/python scripts/make_figures.py
```

### 5. 5-seed multi-API scaling sweep

Needs a funded API key on the first seed only, several minutes per seed, local
torch/transformers/peft required.

```bash
for seed in 42 123 777 2025 9999; do
  ./.venv/bin/python scripts/scale_experiment5_heldout.py --seed $seed
done
./.venv/bin/python scripts/aggregate_multi_seed_scaling.py
```

Held-out eval sets (Zoom/DigitalOcean/Spotify) are committed and reused across seeds automatically
— only training randomness (LoRA weight init) varies. Delete the corresponding
`data/generated/experiment5_heldout_eval_*.json` files first if you want fresh eval questions too
(not recommended — that would conflate eval-question variance with training variance).

### 6. Private cold-start validation (needs a funded API key + local torch)

```bash
./.venv/bin/python scripts/generate_private_specs.py       # regenerates the 5 specs from scratch
./.venv/bin/python scripts/build_private_coldstart_eval.py
./.venv/bin/python scripts/run_private_coldstart_eval.py
```

### 7. 6-API scale-up + LLM-judge evaluation (needs a funded API key + local torch for the first)

```bash
./.venv/bin/python scripts/build_phase3_eval.py
./.venv/bin/python scripts/run_phase3_eval.py
./.venv/bin/python scripts/run_llm_judge_eval.py   # no torch needed, judges a committed seed-42 run
```

## Known Non-Determinism

- Experiments 2/3/5 and the ablation study call Claude Sonnet 5 without a fixed seed — exact
  wording of generated intents/trajectories will differ between runs, though aggregate metrics
  (coverage, tool-selection accuracy) have been stable within a few percentage points across the
  repeated runs performed during development (see `RESULTS.md`'s note on Slack's 93.3–100% range
  in Experiment 3).
- `scripts/scale_experiment5_heldout.py`'s **training randomness** (LoRA adapter weight init) is
  now controllable via `--seed N` — this is exactly what the 5-seed sweep exists to quantify
  rather than hide. Before this flag existed, DigitalOcean's single-run result (a loss to
  Self-Instruct) was reported as-is rather than rerun until it looked better; the 5-seed sweep
  later showed that specific draw was real but not representative of the average.
- **Lesson from building the LLM-judge evaluation:** its first version silently dropped 35% of
  judge calls (`max_tokens` too small for Claude's internal reasoning to finish before writing the
  answer) — always check an evaluation script's own success/parse rate, not just its headline
  output, before trusting it.
- Endpoint/distractor **sampling** is seeded (`SEED = 42` in each script) and is fully
  deterministic given the same spec file.

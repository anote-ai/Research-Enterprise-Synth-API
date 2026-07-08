# EnterpriseSynth: Agentic SFT + Eval Data from API Schemas Without Live Execution

**Status:** pilot-scale experiments complete and scaled: Experiments 1–5, Ablation Study A1–A5, a
real Self-Instruct baseline, a 5-seed multi-API scaling sweep, a private never-published-API
cold-start validation, a 6-API real-spec scale-up (17 APIs touched by the pipeline in total), a
Case Study section with real pipeline output, and an independent LLM-as-a-judge semantic
evaluation. See `DESIGN_DOC.md` for the full design, results, and honest accounting of what
is/isn't implemented.

## Pitch

A framework that ingests an OpenAPI/Swagger spec and emits verified SFT traces
AND eval records with intent specs — without executing the live API. Targets
the enterprise cold-start problem: teams that have an API schema but no
existing tool-use training data or eval suite for it.

**What's actually implemented** (four stages, not the aspirational seven — see
`DESIGN_DOC.md` §4 and §8): API Schema Parser → Intent Synthesis Agent → Trajectory Generator
→ Schema Verification Engine. No Knowledge Graph, no Planner — every generated trajectory is a
single endpoint call, stated plainly throughout the paper rather than implied otherwise.

## Headline results (all real, reproducible, see below)

- **Verification is necessary, not optional:** 0% → 100% detection of planted structural errors,
  only reached 100% after adversarial testing surfaced and forced fixes to 4 real bugs.
- **Fine-tuning effect, 5-seed sweep:** averaged over 5 training seeds, EnterpriseSynth-tuned data
  beats both an untuned base and a real Self-Instruct baseline on all 3 public held-out APIs
  (Zoom, DigitalOcean, Spotify) — individual seeds still vary, reported honestly either way.
- **Private cold-start validation:** on 5 hand-authored, never-published enterprise API specs,
  EnterpriseSynth-tuned accuracy (40.0%) essentially matches public held-out accuracy (39.6%) — no
  meaningful degradation on APIs the base model cannot have seen in pretraining.
- **6-API real-spec scale-up:** wins on all 6 new real public APIs tested (Twilio, Notion, OpenAI,
  Jira, Asana, Trello) — 17 total APIs touched by the pipeline.
- **The honest caveat on all of the above:** an independent LLM-as-a-judge evaluation found that
  binary Tool Selection Accuracy overstates practical quality by roughly 2× — 61% of predictions
  marked "correct" by the endpoint-only metric still had a real defect, usually a missing or
  hallucinated parameter. Every accuracy number above should be read as an upper bound on
  deployment readiness, not an estimate of it.

## Target venues

- MLinPL 2026 — deadline Aug 1, 2026
- AAAI 2027 Workshop on Enterprise AI Evaluation — deadline Jul 28, 2026

## Repository layout

- `DESIGN_DOC.md` — full design, literature review, methodology, all measured results
- `literature-review/` — the five-paper review, one file per paper (also condensed in `DESIGN_DOC.md` §3)
- `BLOG.md` — companion blog post covering the core thesis and results
- `paper/` — LaTeX draft (`main.tex`), bibliography, figures, related-work audit; also
  `main_aaai.tex`/`main_aaai.pdf`, the same content reflowed into the official AAAI-26 anonymous-
  submission two-column format (`aaai2026.sty`/`.bst`, from the real AAAI author kit) for
  submission. `main.tex` remains the source of truth for edits; `main_aaai.tex` is regenerated
  from it, not hand-maintained separately.
- `src/enterprisesynth/` — parser, intent agent, trajectory agent, verifier, ablation agents,
  semantic checker (Haiku ablation), LLM-as-a-judge scorer, fine-tuning helpers
- `scripts/` — one script per experiment/ablation/baseline/scaling phase, plus figure and diagram
  generation
- `data/specs/` — committed real OpenAPI specs (GitHub, Stripe, Slack, Zoom, DigitalOcean,
  Spotify, Twilio, Notion, OpenAI, Jira, Asana, Trello under `phase3/`) plus 5 hand-authored,
  never-published synthetic enterprise specs under `private/` (CRM, HRIS, Procurement, Ticketing,
  Asset Management)
- `data/generated/` — committed experiment outputs (JSON), including all 5 seeds of the
  multi-API scaling sweep and the LLM-judge results
- `tests/` — pytest suite (45 tests, all pass with `torch` installed; 39 without it, since
  `test_finetune.py`'s 6 tests need it — see `test_finetune.py`)

## Setup

```bash
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
```

Requires `ANTHROPIC_API_KEY` in your environment (or a `.env` file at the repo root — already
gitignored) for Experiments 2, 3, 5, the ablation study, and the LLM-judge evaluation, which call
Claude Sonnet 5 or Haiku 4.5. Experiments 1 and 4 are pure code, no API key needed.

## Reproduce Results

Run in order — later scripts depend on earlier ones' output:

```bash
# 0. Run the test suite (no API key needed)
./.venv/bin/python -m pytest tests/ -v

# 1. Schema parsing accuracy (no API key needed)
./.venv/bin/python scripts/run_experiment1.py

# 2. Intent generation (needs ANTHROPIC_API_KEY)
./.venv/bin/python scripts/run_experiment2.py

# 3. Trajectory generation (needs ANTHROPIC_API_KEY; depends on Experiment 2's output)
./.venv/bin/python scripts/run_experiment3.py

# 4. Schema verification + corruption testing (no API key needed; depends on Experiment 3's output)
./.venv/bin/python scripts/run_experiment4.py

# 5. Downstream fine-tuning pilot (needs ANTHROPIC_API_KEY + torch/transformers/peft;
#    depends on Experiments 2-3's output; downloads Qwen2.5-0.5B-Instruct, ~1GB)
./.venv/bin/pip install torch transformers peft accelerate
./.venv/bin/python scripts/prepare_experiment5_data.py
./.venv/bin/python scripts/run_experiment5.py

# Ablation study A1/A3/A4 (needs ANTHROPIC_API_KEY; A2 reuses Experiment 4's data, no re-run needed)
./.venv/bin/python scripts/run_ablation_study.py

# Ablation A5 -- Claude Haiku 4.5 semantic-plausibility check (needs ANTHROPIC_API_KEY;
# depends on Experiment 3's output)
./.venv/bin/python scripts/run_ablation_haiku.py

# Self-Instruct baseline: schema-free bootstrap, then fine-tune + evaluate on the identical
# held-out Zoom set as Experiment 5 (needs ANTHROPIC_API_KEY + torch/transformers/peft)
./.venv/bin/python scripts/run_baseline_selfinstruct.py
./.venv/bin/python scripts/run_baseline_selfinstruct_finetune.py

# Scale Experiment 5 to 3 held-out APIs (Zoom, DigitalOcean, Spotify) -- needs ANTHROPIC_API_KEY
# + torch/transformers/peft; retrains all three models (base/Self-Instruct/EnterpriseSynth) once.
# Accepts --seed N (default 42); reuses committed held-out eval sets rather than regenerating them,
# so a seed sweep varies only training randomness, not the eval questions.
./.venv/bin/python scripts/scale_experiment5_heldout.py --seed 42

# 5-seed sweep + aggregation (what the paper's mean +/- std table is built from)
for seed in 42 123 777 2025 9999; do
  ./.venv/bin/python scripts/scale_experiment5_heldout.py --seed $seed
done
./.venv/bin/python scripts/aggregate_multi_seed_scaling.py

# Private cold-start validation: generate the 5 never-published specs (already committed under
# data/specs/private/, this regenerates them from scratch), build a held-out eval set from them,
# then evaluate EnterpriseSynth against both the public and private held-out sets
./.venv/bin/python scripts/generate_private_specs.py
./.venv/bin/python scripts/build_private_coldstart_eval.py
./.venv/bin/python scripts/run_private_coldstart_eval.py

# Scale to 6 more real public APIs (Twilio, Notion, OpenAI, Jira, Asana, Trello) via APIs.guru
./.venv/bin/python scripts/build_phase3_eval.py
./.venv/bin/python scripts/run_phase3_eval.py

# LLM-as-a-judge semantic evaluation (needs ANTHROPIC_API_KEY; scores real predictions from a
# committed seed-42 run on intent match/argument correctness/missing parameters/reasoning quality)
./.venv/bin/python scripts/run_llm_judge_eval.py

# Regenerate all figures from committed data/generated/*.json (no re-run of experiments needed)
./.venv/bin/pip install matplotlib
./.venv/bin/python scripts/make_figures.py

# Regenerate the target-architecture pipeline diagram (no API key needed)
./.venv/bin/python scripts/make_pipeline_diagram.py
```

## Status log

- 2026-07-06: Repo created; literature review (Self-Instruct, WizardLM, AgentInstruct, API-Bank,
  ToolLLM/ToolBench); dataset selection (APIs.guru); Experiments 1–5 implemented and run at pilot
  scale; Ablation Study A1–A4 run against the actual four-stage implementation.
- 2026-07-07: Resolved the EnterpriseBench naming collision (renamed to `EnterpriseSynth-Eval`);
  implemented and ran Ablation A5 (Claude Haiku 4.5 semantic-plausibility check); implemented a
  real Self-Instruct baseline and scaled Experiment 5 to 3 held-out APIs (Zoom, DigitalOcean,
  Spotify), including the honest DigitalOcean-reversal finding; compiled `paper/main.tex` to PDF
  for the first time and added Discussion/Limitations/Conclusion sections; added `BLOG.md` and
  the `literature-review/` folder; added a Case Study and Qualitative Analysis section using real
  pipeline output; ran a full-repo audit and fixed every finding (README/REVIEW.md staleness, dead
  dependencies, a pre-existing section-numbering bug, missing test coverage for the LLM-calling
  modules).
- 2026-07-08: Ran a 5-seed sweep of the multi-API scaling experiment, replacing single-draw
  numbers with real mean ± std; built and validated a private cold-start test set (5
  never-published synthetic enterprise specs) showing the fine-tuning effect holds on APIs the
  base model cannot have seen; scaled to 6 more real public APIs via APIs.guru (17 APIs touched by
  the pipeline in total); built an independent LLM-as-a-judge semantic evaluation (Phase 4) and
  found that binary Tool Selection Accuracy overstates practical quality by roughly 2× — reported
  as a limitation against the paper's own headline numbers; fixed a real overclaiming issue in the
  Abstract itself (described the unimplemented Knowledge Graph as if it were built); fixed a stale
  leftover sentence claiming the Case Study/Discussion/Conclusion sections were unwritten.

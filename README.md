# EnterpriseSynth: A Schema-Aware Agentic Framework for Generating Verified SFT and Evaluation Datasets from OpenAPI Specifications

**Status:** pilot-scale experiments complete (Experiments 1–5 + Ablation Study A1–A5, plus a real
Self-Instruct baseline and a 3-API downstream scaling comparison). See `DESIGN_DOC.md` for the
full design, results, and honest accounting of what is/isn't implemented.

## Pitch

A framework that ingests an OpenAPI/Swagger spec and emits verified SFT traces
AND eval records with intent specs — without executing the live API. Targets
the enterprise cold-start problem: teams that have an API schema but no
existing tool-use training data or eval suite for it.

**What's actually implemented** (four stages, not the aspirational seven — see
`DESIGN_DOC.md` §4 and §8): API Schema Parser → Intent Synthesis Agent → Trajectory Generator
→ Schema Verification Engine.

## Target venues

- MLinPL 2026 — deadline Aug 1, 2026
- AAAI 2027 Workshop on Enterprise AI Evaluation — deadline Jul 28, 2026

## Eval suite naming (resolved)

The evaluation dataset EnterpriseSynth jointly emits is called **EnterpriseSynth-Eval**. An
earlier draft informally called it "EnterpriseBench," which collided with an unrelated
live-sandbox benchmark (arXiv:2510.27287, Vishwakarma et al., Oct 2025) — renamed to avoid
confusion. See `DESIGN_DOC.md`'s top-of-file note for the full history.

## Repository layout

- `DESIGN_DOC.md` — full design, literature review, methodology, all measured results
- `literature-review/` — the five-paper review, one file per paper (also condensed in `DESIGN_DOC.md` §3)
- `BLOG.md` — companion blog post covering the core thesis and results
- `paper/` — LaTeX draft (`main.tex`), bibliography, figures, related-work audit
- `src/enterprisesynth/` — parser, intent agent, trajectory agent, verifier, ablation agents,
  semantic checker (Haiku ablation), fine-tuning helpers
- `scripts/` — one script per experiment/ablation/baseline, plus figure and diagram generation
- `data/specs/` — committed real OpenAPI specs (GitHub, Stripe, Slack, Zoom, DigitalOcean, Spotify)
- `data/generated/` — committed experiment outputs (JSON)
- `tests/` — pytest suite (36 tests; 42 with `torch` installed, which unlocks 6 more covering
  `finetune.py`'s prompt/JSON-extraction helpers -- see `test_finetune.py`)

## Setup

```bash
python3 -m venv .venv
./.venv/bin/pip install -e ".[dev]"
```

Requires `ANTHROPIC_API_KEY` in your environment (or a `.env` file at the repo root — already
gitignored) for Experiments 2, 3, 5 and the ablation study, which call Claude Sonnet 5. Experiments
1 and 4 are pure code, no API key needed.

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
# + torch/transformers/peft; retrains all three models (base/Self-Instruct/EnterpriseSynth) once
./.venv/bin/python scripts/scale_experiment5_heldout.py

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
  the `literature-review/` folder.

# Dataset Plan

EnterpriseSynth's "dataset" is a collection of **OpenAPI/Swagger specifications** — the raw input
the pipeline synthesizes SFT traces and evaluation records from. This directory holds those specs
and the resulting generated artifacts, `data/`: raw
inputs are checked in or fetched here; generated SFT/eval JSONL files are pipeline **outputs**, not
hand-edited.

## Primary source: APIs.guru

[APIs.guru](https://apis.guru/) / [`openapi-directory`](https://github.com/APIs-guru/openapi-directory)
— verified directly against the live directory (`https://api.apis.guru/v2/list.json`) on 2026-07-06:

- **2,529 APIs, 3,992 spec versions** (OpenAPI 2.0/3.x), auto-updated at least weekly from source.
- Aggregator/tooling license: **CC0-1.0**. Individual API specs retain their own source terms —
  check per-spec before redistributing any derived dataset built from a given spec.

Confirmed present in the live directory (checked, not from memory): `github.com`, `stripe.com`,
`slack.com`, `twilio.com` (many product sub-specs), `spotify.com`, `zoom.us`, `kubernetes.io`,
`openai.com`, `digitalocean.com`. **Not present:** `discord.com` — if Discord's API is wanted as an
example domain, it will need to be sourced separately (Discord does not publish an official
OpenAPI spec; community-maintained unofficial specs exist but are a different licensing situation).

**Azure and Google do not need separate ingestion pipelines** — both are already inside APIs.guru,
confirmed live: 672 `azure.com:*` entries (APIs.guru ingests `Azure/azure-rest-api-specs` directly,
MIT-licensed) and 284 `google.com`/`googleapis.com:*` entries (APIs.guru converts Google's
Discovery documents to OpenAPI). Note: the raw `googleapis/googleapis` GitHub repo is
**protobuf/gRPC service definitions, not OpenAPI/Swagger** — wrong format for this pipeline's
Stage 1 parser; do not use it directly.

Verified category populations (`x-apisguru-categories` metadata, live-checked 2026-07-06): cloud
955, media 340, open_data 318, analytics 284, developer_tools 168, ecommerce 78, financial 72,
messaging 62, entertainment 61, telecom 60, text 57, location 51, collaboration 38, payment 32,
transport 29, hosting 20, security 19, iot 18, social 18, tools 16, marketing 13, email 13,
enterprise 12, machine_learning 10, search 7, customer_relation 7, education 4, backend 3,
monitoring 3, forms 2. Full stratified sampling plan (~65 specs across the enterprise-relevant
categories) is in `DESIGN_DOC.md` §5.2.

## Baseline comparison corpus

[ToolBench](https://github.com/OpenBMB/ToolBench) (Qin et al., 2023) — Apache License 2.0,
confirmed via the repo's license metadata. 16,464 real RapidAPI endpoints. Used as a held-out
comparison corpus to benchmark EnterpriseSynth's generated data against an execution-dependent
baseline (see `paper/related_work_audit.md` §5), not as a primary training source.

## Cold-start validation set

**Built and run** (2026-07-08) — `data/specs/private/`: 5 hand-authored, never-published synthetic
enterprise specs (CRM, HRIS, Procurement, Ticket Management, Asset Management; 28 endpoints
total), modeled on plausible enterprise API shapes but not derived from any real company's
documentation. Required because public specs (APIs.guru, ToolBench) may already be in pretraining
data — evaluating only on public specs would undermine RQ4's cold-start generalization claim.
EnterpriseSynth-tuned accuracy on these private specs (40.0%) essentially matches public held-out
accuracy (39.6%) — see `RESULTS.md`'s "Private cold-start validation" section for the full result.
Generation script: `scripts/generate_private_specs.py`. Still a single, un-seeded run, unlike the
5-seed treatment given to the public held-out comparison — a real remaining gap, not a closed one.

## Split protocol

Per DESIGN_DOC.md RQ4: generalization to a spec the base model has plausibly never seen paired
training data for is the central claim, not just aggregate scale. Proposed protocol:

- **70% of API specs** — training synthesis (prompt/template development happens only against
  this split).
- **15%** — validation (tuning the Schema Verification Engine's thresholds, iterating on the
  Intent Synthesis Agent's taxonomy).
- **15%, held out** — never touched during prompt or template development. Generalization is
  measured only on this split.

Splitting by **whole API spec** (not by individual generated example) is required — splitting
within a spec would leak endpoint/schema knowledge across train and test.

## Per-spec generation scale (pilot measured; scaling with endpoint count still untested)

At pilot scale, every API is sampled at a fixed rate regardless of its total endpoint count — 5
endpoints × 3 intents for the training APIs (GitHub/Stripe/Slack, 45 total), 3 endpoints × 2
intents per domain for the private/Phase 3 held-out sets (30 and 36 total respectively) — not
scaled proportionally to a spec's size (GitHub has 845 paths+methods, Slack has 174, both sampled
identically). Whether yield should scale with endpoint/graph complexity, as originally envisioned
here, remains genuinely untested; what's measured is real generation reliability at a fixed
sample size across specs of very different sizes, not a size-proportional yield curve.

## Directory layout (actual)

- `data/specs/` — raw OpenAPI/Swagger spec files: GitHub, Stripe, Slack (training), Zoom,
  DigitalOcean, Spotify (public held-out) at the top level; `phase3/` (Twilio, Notion, OpenAI,
  Jira, Asana, Trello — 6 more real public held-out APIs); `private/` (5 hand-authored,
  never-published synthetic enterprise specs — CRM, HRIS, Procurement, Ticketing, Asset
  Management). No train/val/held-out split by directory name or manifest — held-out status is
  tracked by which scripts/experiments reference a given spec, documented in `RESULTS.md`.
- `data/generated/*.json` — pipeline output, one file per experiment/ablation/phase, not
  hand-edited. Not `.jsonl` as originally planned here — each script writes a single JSON
  document (list or dict) matching what that specific experiment needs, documented inline in each
  script's own docstring.

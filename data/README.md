# Dataset Plan

EnterpriseSynth's "dataset" is a collection of **OpenAPI/Swagger specifications** — the raw input
the pipeline synthesizes SFT traces and evaluation records from. This directory holds those specs
and the resulting generated artifacts, following the input-vs-output-artifact convention used in
[Research-OrchestrateBench](https://github.com/anote-ai/Research-OrchestrateBench)'s `data/`: raw
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

A small, hand-authored set of synthetic "enterprise-internal" specs (CRM, ticketing, HRIS,
internal billing), modeled on real enterprise API shapes but not published anywhere. Required
because public specs (APIs.guru, ToolBench) may already be in pretraining data — evaluating only
on public specs would undermine RQ4's cold-start generalization claim. Not yet authored; tracked
as an open item.

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

## Per-spec generation scale (illustrative target, not yet measured)

Each spec produces a variable number of examples depending on its endpoint count and graph
complexity — e.g., a large spec like GitHub's should be expected to yield on the order of hundreds
of SFT examples plus a smaller paired evaluation set; a smaller spec like Slack's proportionally
fewer. Exact per-spec yields depend on the Intent Synthesis Agent's taxonomy breadth and will be
reported as measured numbers once Stage 3–7 of the pipeline (DESIGN_DOC.md §4) exist, not assumed
in advance.

## Directory layout (planned)

- `data/specs/` — raw OpenAPI/Swagger spec files (train/val/held-out split tracked in a manifest,
  not by directory name, so the same fetch script can regenerate any split).
- `data/generated/train_sft_pool.jsonl` — pipeline output, not hand-edited.
- `data/generated/eval_records_spec.jsonl` — pipeline output, not hand-edited.
- `data/enterprise_coldstart/` — the hand-authored synthetic enterprise spec set.

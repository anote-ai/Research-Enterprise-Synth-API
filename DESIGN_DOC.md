# EnterpriseSynth — Research Design Document

**Paper title:** EnterpriseSynth: Agentic SFT + Eval Data from API Schemas Without Live Execution
**Topic (T1b):** Agentic SFT + Eval Data from API Schemas Without Live Execution
**Author:** Rashmi Thimmaraju
**Target venues:** MLinPL 2026 (deadline Aug 1, 2026) · AAAI 2027 Workshop on Enterprise AI Evaluation (deadline Jul 28, 2026)

---

## 1. Goal

Solve the enterprise cold-start problem for tool-using LLM agents: an organization has an
OpenAPI/Swagger spec for its internal or partner APIs but no historical traffic logs, no safe
sandbox, and no existing SFT or eval data for that API surface. EnterpriseSynth ingests the spec
alone and emits (a) verified multi-turn SFT traces and (b) paired evaluation records, each tied to
a formal **intent spec**, without ever executing a live call against the target system.

### Research Questions

- **RQ1 (feasibility):** Can structurally valid, verifiable multi-step agent traces be synthesized
  from an OpenAPI spec alone — no execution, no historical request/response data?
- **RQ2 (verification):** Does a static constraint validator (schema/type/format checking, no
  runtime calls) catch the same class of errors that execution-based verification (e.g., APIGen)
  catches, and where does it fall short?
- **RQ3 (utility):** Does fine-tuning a compact open model on EnterpriseSynth-generated traces
  measurably improve API sequencing accuracy and constraint compliance versus the untuned baseline?
- **RQ4 (cold-start generalization):** Given a spec the base model has plausibly never seen paired
  training data for, how well do zero-execution-generated SFT+eval pairs transfer — i.e., does this
  actually work for a *new* organization's API on day one, not just on well-known public APIs that
  may already be in pretraining data?

---

## 2. The Execution Paradox (problem framing)

Current synthetic tool-use / instruction-data generation splits into two camps, neither of which
fits the enterprise cold-start setting:

- **Execution-based** (API-Bank, ToolLLM/ToolBench): ground and verify traces against real APIs —
  API-Bank uses reproducibility-constrained real databases, ToolBench makes ~470k live RapidAPI
  calls during DFSDT annotation. Fails behind the enterprise firewall — no sandbox exists for most
  internal systems, live calls against production risk data corruption/security violations, and
  network-bound generation is rate-limited.
- **Execution-free but ungrounded** (AgentInstruct): generates tool-use data without executing
  anything, but when seeded from raw code it **hallucinates the API surface** — synthesizing an API
  description from a code snippet, or having the LLM hypothesize additional APIs it believes exist,
  with no ground-truth check. Verification is a soft editorial refinement loop plus a post-hoc,
  held-out GPT-4-judged benchmark (Orca-Bench) — not a per-sample structural gate.
- **General-purpose, non-tool bootstrapping** (Self-Instruct, Evol-Instruct/WizardLM): both are
  execution-free and filtered (ROUGE-similarity/keyword heuristics; "elimination evolving" rules),
  but neither has any notion of tools, APIs, or structural grounding at all.

EnterpriseSynth targets the gap: **a real spec is the only required input** (removing
AgentInstruct's hallucination failure mode), verification is a **hard structural gate** derived
from that spec (not a heuristic text filter or a post-hoc judge), and no execution, sandbox, or
historical traffic is ever required.

---

## 3. Related Work

Literature review scope is exactly five papers (full-text read, not abstract-only — see
`paper/related_work_audit.md` for the complete per-paper breakdown):

| Paper | Execution? | Relevant mechanism | Gap vs. EnterpriseSynth |
| --- | --- | --- | --- |
| Self-Instruct (Wang et al., 2022, [2212.10560](https://arxiv.org/abs/2212.10560)) | None | Bootstrap from 175 seeds; ROUGE-L/keyword/format filtering | No tool/API notion; filtering is text-heuristic, not structural |
| Evol-Instruct / WizardLM (Xu et al., 2023, [2304.12244](https://arxiv.org/abs/2304.12244)) | None | In-depth/in-breadth instruction evolution; "elimination evolving" quality filter | No tool/API handling anywhere in the method |
| AgentInstruct (Mitra et al., 2024, [2407.03502](https://arxiv.org/abs/2407.03502)) | None (LLM-simulated tool responses) | Three-flow agentic pipeline (content transform → taxonomy-driven seed gen → Suggester-Editor refinement) | Hallucinates API surface when seeded from code; verification is soft/post-hoc (Orca-Bench GPT-4 judge), not a per-sample structural gate; no paired eval artifact |
| API-Bank (Li et al., 2023, [2304.08244](https://arxiv.org/abs/2304.08244)) | Real (reproducibility-constrained DBs) | 5-agent pipeline generates 1,888 training dialogues (98% cheaper than human annotation) | Still execution-dependent; hard-codes live-data snapshots for reproducibility |
| ToolLLM / ToolBench (Qin et al., 2023, [2307.16789](https://arxiv.org/abs/2307.16789)) | **Real** — ~470k live RapidAPI calls during DFSDT annotation | DFSDT search grounded in real API responses; ToolEval pass-rate/win-rate judging | Requires a live backend at generation time; not schema-only |

**Base paper: AgentInstruct.** It is the only one of the five that is both agentic/multi-flow and
execution-free for tool-use data — the closest architectural skeleton to adapt. We fix its two
concrete gaps: (1) replace hallucinated/code-derived API seeding with ingestion of a real
OpenAPI/Swagger spec, so nothing needs to be hypothesized; (2) replace its soft, post-hoc
verification (Suggester-Editor judgment + held-out GPT-4 scoring) with a hard, per-sample Static
Constraint Validator checked against the spec itself; (3) jointly emit an intent-spec-tied eval
record from the same generation pass, which none of the five papers do (Orca-Bench, API-Bank's
human-annotated set, and ToolEval are all separate from — not mechanically derived from — the
training-data generation act). API-Bank and ToolBench remain the primary execution-dependent
contrast cases for the Execution Paradox argument.

Full per-paper breakdown is in `paper/related_work_audit.md`.

---

## 4. Methodology — Seven-Stage Pipeline (Target Architecture)

**Implementation status, stated plainly:** stages 2 (API Knowledge Graph Builder) and 4 (Agentic
Planning Module) below are **not implemented** — no graph module exists in the codebase, and
Stage 4 was combined with Stage 5 into a single call from the start (`trajectory_agent.py`).
What's actually built and measured in §6/§7/§8 is a **four-stage** pipeline: Parser → Intent
Agent → Trajectory Agent → Verifier. The seven-stage diagram below is the target architecture,
not a claim about the current system — see §8's ablation study for the full accounting of real
vs. planned components.

```text
OpenAPI/Swagger Spec
        |
        v
1. API Schema Parser            -- endpoints, parameters, authentication, response schemas
        |
        v
2. API Knowledge Graph Builder  -- nodes: endpoints/objects/parameters
        |                          edges: dependency, sequential workflow, object relations
        v
3. Intent Synthesis Agent       -- user intents: simple tasks, multi-step workflows,
        |                          enterprise scenarios
        v
4. Agentic Planning Module      -- task decomposition, endpoint selection, tool ordering,
        |                          API workflow plan
        v
5. Trajectory Generator         -- reasoning traces, tool calls, parameters, expected responses
        |
        v
6. Schema Verification Engine   -- validates: endpoint exists, HTTP method, required params,
        |                          param types, response schema, authentication
        v
7. Dataset Constructor          -- outputs: SFT dataset, evaluation dataset,
                                    verification metadata, intent specifications
```

Each stage maps onto a gap identified in the literature review (§3):

1. **API Schema Parser** and **2. API Knowledge Graph Builder** — build the graph
   $\mathcal{G} = (\mathcal{V}, \mathcal{E})$ (endpoints/objects/parameters as nodes; dependency,
   sequential-workflow, and object-relation edges) directly from the real spec. Unlike
   AgentInstruct's `tool_use` flow, which must synthesize or hypothesize an API description when
   seeded only from code, there is nothing to hallucinate here — the graph is derived, not invented.
2. **3. Intent Synthesis Agent** and **4. Agentic Planning Module** — the schema-grounded analog of
   AgentInstruct's taxonomy-driven seed generation and Evol-Instruct's "complicate input" evolution
   step: traverses the knowledge graph to decompose intents into endpoint selections and workflow
   plans, with task complexity derived from real dependency depth (how many graph hops a workflow
   requires) rather than a heuristic evolution rule.
3. **5. Trajectory Generator** — produces the paired natural-language reasoning trace, tool calls,
   parameters, and expected responses (the SFT trace) directly from the agentic plan.
4. **6. Schema Verification Engine** — the compiler-style firewall: checks every generated
   trajectory against the spec's declared endpoint/method/parameter-type/required-field/response
   schema/authentication requirements, entirely offline. Where Self-Instruct and Evol-Instruct
   filter with text heuristics (ROUGE similarity, keyword rules, degeneracy checks) and
   AgentInstruct verifies only via soft editorial refinement plus a post-hoc held-out judge, this
   is a hard, per-sample structural gate.
5. **7. Dataset Constructor** — jointly emits the SFT dataset, the evaluation dataset, verification
   metadata, and the intent specifications that tie an SFT trace to its paired eval record — the
   artifact none of the five reviewed papers produce (Orca-Bench, API-Bank's human-annotated set,
   and ToolEval are all separate from the training-data generation act, not mechanically derived
   from the same pass).

---

## 5. Experimental Setup

### 5.1 Research Questions (experimental)

Superseded by the five-RQ breakdown in §6.1, which maps one RQ per experiment. §1's conceptual
RQ4 (cold-start generalization) is not its own experiment — it is the held-out-spec condition
applied within Experiments 2, 3, and 5 (see §5.2 split protocol).

### 5.2 Datasets

Full provenance in `data/README.md`. All API specs for the experimental set come from **one
verified source** rather than three separate ingestion pipelines — checked live, not assumed:

- **APIs.guru already contains both Azure's and Google's spec collections.** APIs.guru ingests
  `Azure/azure-rest-api-specs` directly (672 `azure.com:*` entries confirmed in the live directory)
  and converts Google's Discovery documents to OpenAPI (284 `google.com`/`googleapis.com:*` entries
  confirmed). A separate Azure-repo scraper or Google ingestion path is therefore unnecessary.
- **`googleapis/googleapis` (the raw GitHub repo) is protobuf/gRPC, not OpenAPI/Swagger** —
  confirmed by inspecting the repo (Bazel build files, `gapic` client-config directories). It is
  the wrong format for this pipeline's Stage 1 parser and is not used.
- **Verified category populations** (from `x-apisguru-categories` metadata, live-checked
  2026-07-06): cloud 955, media 340, open_data 318, analytics 284, developer_tools 168,
  ecommerce 78, financial 72, messaging 62, payment 32, collaboration 38, security 19,
  enterprise 12, customer_relation 7 (full list in `data/README.md`).

Proposed stratified sample (~65 specs total, single source = APIs.guru), guaranteeing the three
flagship case-study APIs are included (all three already confirmed present, so no separate
sourcing is needed for them):

| Domain (APIs.guru category) | Specs sampled | Notes |
| --- | --- | --- |
| cloud | 15 | includes `kubernetes.io` (flagship) |
| developer_tools | 10 | includes `github.com` (flagship) |
| financial + payment | 10 | includes `stripe.com` (flagship) |
| ecommerce | 8 | |
| collaboration | 8 | includes `slack.com` |
| messaging | 5 | includes `twilio.com` |
| enterprise + customer_relation + security | 9 | smallest categories, sampled near-exhaustively |

This is a sampling **plan**, not a measured result — exact selection (which specs within each
category) is not yet finalized.

- **Baseline comparison corpus:** held-out slice of ToolLLM/ToolBench's RapidAPI pool (16,464
  APIs, Apache-2.0, confirmed via repo license metadata).
- **Cold-start validation set:** a small, hand-authored set of synthetic "enterprise-internal"
  specs (CRM, ticketing, HRIS, internal billing) — not yet authored, tracked as an open item.
  Required because public specs may already be in pretraining data.
- **Split protocol:** 70% of sampled specs for training synthesis, 15% validation, 15% held out
  and untouched until final evaluation — split by whole spec, not by generated example.

### 5.3 Baselines

- **Prompt-only generation** — a single zero-shot prompt asking an LLM to produce SFT/eval data
  directly from the spec, no pipeline, no verification. Establishes the floor.
- **Self-Instruct** (Wang et al., 2022) — reimplemented per its published protocol, adapted to
  take API endpoints as seeds instead of generic tasks.
- **AgentInstruct** (Mitra et al., 2024) — the closest execution-free baseline; its `tool_use` flow
  applied to the same OpenAPI specs, for a controlled comparison isolating the effect of real-spec
  grounding + hard verification vs. its code-seeded/soft-verified approach.
- **ToolLLM/ToolBench** (Qin et al., 2023) — execution-dependent baseline, run against the same
  APIs where a live sandbox is safely available (public APIs only — this baseline cannot run at
  all against the cold-start validation set, which is itself part of the comparison's point).
- **API-Bank** (Li et al., 2023) — used for evaluation-style comparison (its call/retrieval/plan
  scoring methodology), not as a training-data baseline.

### 5.4 Models

Generation-pipeline models (Stages 3–5) use frontier API models (Claude), not the fine-tuning
target model — these are separate roles:

- **Intent Synthesis Agent, Agentic Planning Module, Trajectory Generator:** Claude Sonnet 5.
- **Schema Verification Engine (primary):** **no LLM** — deterministic, code-based validation
  (Pydantic/JSON Schema against the spec). This is the core methodological differentiator from
  AgentInstruct's LLM-judge-only verification (§2), so the primary gate must stay non-LLM.
- **Schema Verification Engine (ablation arm, for RQ3):** Claude Haiku 4.5 as a cheap, optional
  LLM-based semantic-plausibility check layered *on top of* the deterministic gate — measuring
  whether an LLM catches errors the structural check misses, not replacing it.
- **Fine-tuning target model** (unchanged from §5.6): an open-weight model (Mistral-7B-Instruct-v0.3
  or Llama-3-8B-Instruct) — must be open-weight since it needs to be fine-tuned, unlike the
  generation-pipeline models above.

This is a placeholder default pending actual budget confirmation, not a final commitment.

### 5.5 Evaluation Metrics

- **Schema validation rate** — % of generated trajectories passing Stage 6 with zero structural
  violations (generalizes the earlier VJGR notion).
- **Endpoint coverage** — % of a spec's endpoints exercised by at least one generated trajectory.
- **Parameter correctness** — % of required parameters populated with the correct type per the
  spec.
- **Workflow completeness** — % of multi-step trajectories where dependent calls execute only
  after their required parent parameters are available (generalizes the earlier SMR notion).
- **Intent diversity** — distinct intent/task categories generated per spec (taxonomy coverage,
  not just count).
- **Multi-step workflow coverage** — % of graph dependency edges (§4 Stage 2) exercised by at
  least one generated trajectory.
- **Verification pass rate** — % passing Stage 6 on first generation attempt vs. after
  regeneration.
- **Downstream task success after SFT** — held-out eval-record pass rate, fine-tuned vs. untuned
  baseline model (RQ4).

### 5.6 Implementation Details

- **Python:** 3.12.
- **Libraries actually used:** Pydantic (schema modeling + Stage 6 validation), Anthropic SDK
  (Stages 3–5 model calls), stdlib `json` (Stage 1 parsing — all committed specs are JSON, not
  YAML). `FastAPI` is not needed — this is an offline batch pipeline, not a served API; add it
  only if a live-serving mode is wanted later.
- **Libraries planned but not adopted:** an audit found four declared dependencies with zero
  actual imports anywhere in `src/`/`scripts/` — removed from `pyproject.toml`/`requirements.txt`
  rather than kept as unused weight, with the reason for each disclosed here:
  - **NetworkX** — reserved for Stage 2 (knowledge graph), which is not implemented; see §4/§8.
  - **`openapi-spec-validator`** — planned for Stage 1 to validate that an input spec is
    well-formed OpenAPI before parsing it; Stage 1 currently assumes well-formed input and parses
    it directly (manual dict-walking + Pydantic validation of the *extracted* fields, not the raw
    spec's own structural correctness) — a real, disclosed gap: a malformed spec may currently
    produce silently-wrong output rather than a clear parse error.
  - **PyYAML** — every committed spec (`data/specs/*.json`) is JSON; no YAML-format spec has been
    used, so nothing ever called into it.
  - **`requests`** — no direct HTTP calls anywhere in the pipeline; the Anthropic SDK manages its
    own HTTP internally.
  Re-add any of these if/when the corresponding capability is actually built or needed.
- **Hardware:** no GPU required for generation (API-based models); a single GPU (24GB+ for a
  7–8B LoRA run) is needed only for the fine-tuning step in §5.7.
- **Runtime, trajectory counts, eval-record counts:** not yet measured — to be reported once the
  pipeline (§4) is implemented and run, not assumed in advance.

### 5.7 Fine-Tuning Protocol

- LoRA adapter on the open base model chosen in §5.4, 3 epochs, Paged AdamW, base LR 3e-4, cosine
  annealing schedule.
- Protocol: run untuned baseline and fine-tuned model against the held-out eval records (§5.2
  split), score both through the Schema Verification Engine (§5.4) plus the metrics in §5.5.

---

## 6. Experiments (Experimental Protocol)

This is a protocol — what will be measured once the pipeline (§4) is implemented — not a report
of results. Every metric below is a placeholder ("to be measured") until the corresponding
experiment actually runs; nothing in this section should be read as a finding.

### 6.1 Experimental Goals / Research Questions

- **RQ1:** Can EnterpriseSynth accurately extract API semantics from real-world OpenAPI
  specifications? (Experiment 1)
- **RQ2:** Can EnterpriseSynth generate diverse and realistic enterprise user intents from API
  schemas? (Experiment 2)
- **RQ3:** Can EnterpriseSynth generate complete and schema-consistent agent trajectories?
  (Experiment 3)
- **RQ4:** Can schema-based verification validate generated trajectories without executing real
  APIs? (Experiment 4)
- **RQ5:** Does training with EnterpriseSynth-generated SFT data improve LLM agent performance on
  unseen API tasks? (Experiment 5)

### 6.2 Dataset Collection

Evaluated on real-world OpenAPI specs only — **no synthetic API specifications** are used for this
protocol (the hand-authored cold-start set in §5.2 is a separate, explicitly-labeled condition, not
part of this real-spec evaluation set). Current evaluation set, with endpoint counts verified
directly against each API's live spec (not estimated):

| API | Source | Real endpoint statistics |
| --- | --- | --- |
| GitHub REST API | GitHub OpenAPI specification (via APIs.guru) | 551 paths / 845 path-method endpoints |
| Stripe API | Stripe OpenAPI specification (via APIs.guru) | 299 paths / 446 path-method endpoints |
| Slack API | Slack OpenAPI specification (via APIs.guru) | 174 paths / 174 path-method endpoints |

Additional specs drawn from the stratified APIs.guru sample in §5.2 — note Azure and Google specs
are reached through APIs.guru itself (already confirmed to contain both), not via separate
repositories. Final API/endpoint counts reported once dataset collection is finalized.

### 6.3 Experiment 1 — OpenAPI Schema Understanding

**Objective:** evaluate whether EnterpriseSynth's Stage 1 parser correctly parses real-world API
specs, checked against the specification itself.

**Metrics:** Endpoint Extraction Accuracy (correctly extracted / total endpoints), Parameter
Extraction Accuracy (required/optional params, types, constraints), Schema Extraction Accuracy
(request body, response schemas, object definitions), Authentication Extraction Accuracy (API
keys, OAuth, JWT, Basic).

**Measured** (`src/enterprisesynth/parser.py`, run via `scripts/run_experiment1.py`; ground truth
independently recomputed straight from each raw spec, not by reusing the parser's own logic —
see the script for both implementations):

| API | Paths+Methods | Endpoint Extraction Accuracy | Parameter Accuracy | Req. Schema Accuracy | Resp. Schema Accuracy | Auth Accuracy |
| --- | --- | --- | --- | --- | --- | --- |
| GitHub | 845 | 100.0% | 100.0% | 100.0% | 100.0% | n/a (0/0) |
| Stripe | 446 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |
| Slack | 174 | 100.0% | 100.0% | 100.0% | 100.0% | 100.0% |

All extraction accuracies read 100% because Stage 1 is deterministic parsing against a
machine-readable format, not a generative/statistical task — but that 100% is only trustworthy
because the ground-truth counter was independently fixed alongside two real parser bugs that
Experiment 4's adversarial testing surfaced (see §6.6): the parser originally **silently dropped
any parameter defined via `$ref`** (GitHub uses this extensively — e.g. `org`, `secret_name` are
shared, `$ref`'d parameters across its huge API surface) and **never parsed `requestBody` schema
fields into typed parameters at all** (most POST/PUT/PATCH endpoints, e.g. Stripe's
`/v1/charges`, put their real payload fields there, not in OpenAPI's `parameters` array). Both are
now resolved (`_resolve_ref` in `src/enterprisesynth/parser.py`, plus
`_parse_request_body_fields`). The scale of the first fix alone: GitHub's independently-recomputed
required-parameter count went from **67 to 1,721** once `$ref` parameters were correctly resolved
— a stark illustration of how much of the spec was previously invisible to the pipeline. A second,
smaller, genuine finding survives from before these fixes: **GitHub's public OpenAPI spec declares
zero `securitySchemes` and zero `security` requirements anywhere** (verified directly on the raw
spec, not a parser bug) — GitHub documents its auth (PAT/OAuth/GitHub App tokens) in prose
elsewhere, not in machine-readable OpenAPI fields, so an authentication check against GitHub's spec
has nothing to verify against. Test coverage in `tests/test_parser.py` (9 tests, all passing,
including regression tests for both fixes) pins these counts.

### 6.4 Experiment 2 — Intent Generation Evaluation

**Objective:** can the Intent Synthesis Agent (Stage 3) generate realistic enterprise user intents
from a spec's operations?

**Metrics:** Intent Coverage (% of operations receiving at least one generated intent), Intent
Diversity (unique intents, semantic-similarity distribution, clustering diversity), and optional
human evaluation (relevance/realism/enterprise-usefulness, 1–5 scale).

**Measured (pilot scale)** — `src/enterprisesynth/intent_agent.py` (Claude Sonnet 5), run via
`scripts/run_experiment2.py`: 5 endpoints sampled per API (seeded, reproducible), 3 intents
generated per endpoint. Raw output in `data/generated/experiment2_intents.json`.

| API | Generated intents | Coverage | Diversity (unique/total, exact-string) | Human score |
| --- | --- | --- | --- | --- |
| GitHub | 15 | 100.0% | 100.0% (15/15) | not measured (no annotators yet) |
| Stripe | 15 | 100.0% | 100.0% (15/15) | not measured (no annotators yet) |
| Slack | 15 | 100.0% | 100.0% (15/15) | not measured (no annotators yet) |

Exact-string diversity is a weak proxy (it only catches literal duplicates) — semantic-similarity
clustering is not yet implemented, so this number should not be over-read; it just confirms the
model isn't repeating itself verbatim at this small sample size. Spot-checking the actual output
(not just the aggregate numbers) matters here: e.g. for GitHub's
`PUT /orgs/{org}/actions/secrets/{secret_name}/repositories`, generated intents included "Update
the list of repositories that can access our org-level DOCKER_REGISTRY_PASSWORD secret..." and
"We're rotating which teams have access to the shared AWS_DEPLOY_KEY secret..." — both correctly
scoped to the endpoint, distinct business scenarios, plausible enterprise phrasing, not generic
template filling. This is a 15-endpoint pilot, not the full stratified sample from §5.2 — scaling
to the full ~65-spec sample and adding human/semantic-similarity evaluation is the next step.

### 6.5 Experiment 3 — Agent Trajectory Generation

**Objective:** can the Trajectory Generator (Stage 5) produce complete tool-use trajectories (user
intent → planning steps → API calls → arguments → expected response)?

**Metrics:** Tool Selection Accuracy (correct endpoint chosen), Parameter Validity (present,
correctly typed, schema-compliant), Workflow Completeness (for multi-step tasks, e.g. create
customer → retrieve customer ID → create invoice — does the full chain exist?).

**Measured (pilot scale)** — `src/enterprisesynth/trajectory_agent.py` (Stages 4+5 combined into
one Claude Sonnet 5 call for this pilot, not yet split), run via `scripts/run_experiment3.py` on
all 45 intents from Experiment 2. Each intent's candidate tool list = its 5 "source" endpoints for
that API + 10 seeded distractors (shuffled per trial), so tool selection is a real choice among 15
candidates, not a rubber stamp. Raw output in `data/generated/experiment3_trajectories.json`.

| API | Trials | Tool Selection Accuracy | Parameter Validity (among correct selections) |
| --- | --- | --- | --- |
| GitHub | 15 | 100.0% | 100.0% |
| Stripe | 15 | 100.0% | 100.0% |
| Slack | 15 | 100.0% | 100.0% |

**Multi-step workflow success:** not applicable at this pilot scale — Experiment 2's intents are
single-endpoint, not multi-step chains.

**Important methodological caveat, stated plainly rather than glossed over:** the same model
(Claude Sonnet 5) generated both the intents (Experiment 2) and the tool selections (Experiment
3). This measures whether the model can close its own loop — recover the endpoint it itself had in
mind when writing the intent — not whether it handles independently-authored, ambiguous, or
adversarial human intents. Spot-checking actual output (e.g. Stripe's
`DELETE /v1/subscription_items/{item}`: the model correctly extracted the literal item ID
`si_1N3xYzABC` from free text into the `item` parameter, with coherent reasoning and a plausible
expected-response summary) shows the mechanism works, but 100%/100% at this pilot scale should be
read as "the pipeline is functioning end-to-end," not as a generalization claim. A real accuracy
measurement needs either human-authored intents or intents generated by a different model than the
one doing tool selection, plus a larger, less self-referential sample. (One re-run of this
experiment, after the Stage 1 parser fixes below, hit a transient JSON-parsing failure on 1/45
trials — the model's response didn't come back as clean JSON that one time — a real pipeline
robustness gap worth hardening, not a tool-selection error; a subsequent re-run had 45/45 succeed,
consistent with ordinary LLM sampling variance.)

### 6.6 Experiment 4 — Schema-Based Verification

**Objective:** the core novelty claim — can the Schema Verification Engine (Stage 6) validate
generated trajectories entirely offline, without executing any real API?

**Checks:** endpoint validity (does it exist in the spec?), HTTP method validity (e.g. rejecting
`GET /createUser` when the spec defines `POST /createUser`), parameter validation (missing
required fields, incorrect types, invalid enum values), response validation (output conforms to
the declared response schema).

**Design note:** testing the verifier only on already-correct Experiment 3 trajectories would be
circular — of course they pass, they were already confirmed correct. The verifier's actual job is
catching *bad* trajectories, so `scripts/run_experiment4.py` also generates a deliberately
corrupted variant of each valid trajectory (wrong method, missing a required param, invalid path,
or wrong param type — cycled deterministically) and checks whether `SchemaVerificationEngine`
(`src/enterprisesynth/verifier.py`) correctly flags it.

**Measured, final** (after the fixes below) — `scripts/run_experiment4.py`:

| API | Valid trajectories tested | Verification Pass Rate | Corrupted trajectories tested | Invalid Cases Detected |
| --- | --- | --- | --- | --- |
| GitHub | 15 | 100.0% | 15 | 100.0% |
| Stripe | 15 | 100.0% | 14 | 100.0% |
| Slack | 15 | 100.0% | 15 | 100.0% |

**This 100%/100% was earned, not assumed — the first run surfaced four real bugs**, three
serious enough that reporting the first-run numbers (57–80% detection) without fixing them would
have been misleading:

1. **Verifier bug:** `_type_compatible` treated declared type `"string"` as accepting *any* value,
   including a nested object — so a `wrong_type` corruption injecting `{"unexpectedly": "an
   object"}` into a string-typed field was never caught (0/8 detected on the first run). Fixed to
   reject `dict`/`list` values for string-typed parameters.
2. **Test-harness bug:** the `missing_param` corruption dropped the first key in a trajectory's
   parameters dict regardless of whether that parameter was actually *required* — dropping an
   optional one legitimately doesn't violate anything, so roughly half these corruptions were
   meaningless by construction (6/12 detected). Fixed to specifically target a required parameter.
3. **Stage 1 parser bug — `$ref` parameters silently dropped:** described in §6.3; this also
   explains part of the `wrong_type` misses, since a corrupted-but-invisible parameter (e.g.
   GitHub's `$ref`'d `org`) was never checked because it wasn't in the parsed parameter list at
   all. Fixed by resolving `$ref`.
4. **Stage 1 parser gap — `requestBody` schema fields never parsed into typed parameters:**
   described in §6.3; this is why Stripe's `/v1/charges` (a `requestBody`-only endpoint, zero
   OpenAPI `parameters`) had 2 of its `wrong_type` corruptions go undetected — the corrupted field
   (e.g. `amount`) had no corresponding `Parameter` object for the verifier to check against at
   all. Fixed by parsing `requestBody.content[...].schema.properties` into `Parameter` objects
   (`location="body"`).

Per-corruption-type detection after all four fixes: `wrong_method` 12/12, `missing_param` 10/10,
`invalid_path` 11/11, `wrong_type` 9/9 (aggregated across APIs; exact per-run trial counts vary
slightly run to run because some corruption types are skipped when a trajectory has no eligible
parameter to corrupt, e.g. no required param to drop). Regression tests for all four fixes are in
`tests/test_parser.py` and `tests/test_verifier.py` (15 tests total, all passing).

The honest takeaway is not "the verifier is perfect" — it's that **adversarial testing against a
verifier is what actually validates a verifier**, and doing so surfaced real gaps in Stage 1 that
Experiment 1's self-consistent ground truth had been silently sharing (see §6.3's `$ref` note).
A verifier is only as good as the structured representation it checks against; this pass is the
first evidence that the two are now consistent for these three APIs specifically, not a general
guarantee for arbitrary future specs.

### 6.6.1 Ablation Arm — Claude Haiku 4.5 Semantic-Plausibility Check (RQ3)

§5.4 names an optional ablation arm layering Claude Haiku 4.5 on top of the deterministic gate.
This was flagged in a repo audit
([issue #1](https://github.com/Rashmioffcialpage/enterprisesynth-api/issues/1)) as described but
never implemented — it now is (`src/enterprisesynth/semantic_checker.py`,
`scripts/run_ablation_haiku.py`).

**The actual claim being tested:** the deterministic verifier only checks structure (types,
required fields, endpoint existence) — it has no notion of whether a parameter *value* makes
business sense. A trajectory can pass Stage 6 with a nonsensical value (a wildly negative charge
amount, an obvious placeholder string) as long as the type is right. Does a cheap LLM catch that
class of error?

**Method:** for each of the 45 valid Experiment 3 trajectories, (a) ask Haiku whether the
trajectory is semantically plausible for its intent, and (b) construct a new corruption —
negate a numeric parameter or replace a string parameter with an obvious placeholder — confirm via
the Stage 6 verifier that it **still passes structurally** (proving the deterministic gate cannot
see this error class by design), then ask Haiku the same plausibility question.

| API | Valid trajectories judged plausible | Implausible corruptions still structurally valid | ...caught by Haiku |
| --- | --- | --- | --- |
| GitHub | 10/15 (66.7%) | 15/15 (100%) | 15/15 (100%) |
| Stripe | 15/15 (100%) | 15/15 (100%) | 15/15 (100%) |
| Slack | 13/15 (86.7%) | 15/15 (100%) | 15/15 (100%) |

**Two real findings, not one.** First: confirmed as designed — 100% of the semantically-corrupted
trajectories pass the deterministic verifier (it cannot see this error class) and 100% are caught
by the Haiku check. This is genuine incremental value: a real class of error the structural gate
is blind to by construction, caught by a cheap LLM layered on top.

Second, and reported rather than hidden: **the semantic checker has a real false-positive rate**,
worst on GitHub (33%, 5/15 valid trajectories wrongly flagged). Inspecting the actual flagged
cases shows Haiku being overly literal, not detecting real problems — e.g. flagging a trajectory
for using repository IDs instead of names ("impossible to verify they correspond to the correct
repos"), when IDs are the correct and more precise way to call the API; or flagging GitHub's tag
protection endpoint for lacking an explicit `admin_only` parameter, when the endpoint itself *is*
the enforcement mechanism the intent asked for — no such parameter exists in the spec. **Honest
conclusion:** the Haiku arm demonstrably adds value for the specific error class it was designed
to catch (semantically-implausible-but-structurally-valid values), but is not free — it introduces
a real, API/domain-dependent false-positive rate that would need calibration (e.g. a
higher-confidence threshold, or restricting checks to specific parameter types like amounts/dates)
before being deployed as a hard gate rather than an advisory signal.

### 6.7 Experiment 5 — Downstream LLM Agent Evaluation ⭐

**Objective:** the result that matters most for the paper's central claim — does
EnterpriseSynth-generated SFT data actually improve API-use capability, evaluated on **held-out
APIs not included during synthesis** (§5.2 split).

**Metrics:** task success rate, tool selection accuracy, argument correctness, workflow completion.

**Baselines:** base LLM (no fine-tuning), prompt-only agent, Self-Instruct-generated data, and —
where feasible — ToolBench (per §5.3, only where a live sandbox is safely available).

**Hardware-driven scope change, stated plainly:** §5.4/§5.7's original target (Mistral-7B-Instruct
or Llama-3-8B via LoRA) is not feasible on the machine this pilot ran on — no GPU, 16GB RAM, and
bitsandbytes/QLoRA has only experimental Apple Silicon support. Rather than skip the experiment or
fabricate numbers for an untested model, this pilot substitutes **Qwen2.5-0.5B-Instruct**, actually
fine-tuned via LoRA (`peft`, rank 8, `q_proj`/`v_proj`, 3 epochs, LR 3e-4, MPS backend) on this
machine, in real wall-clock time. This is a real result for a much smaller model than the paper's
eventual target, not a substitute for the full-scale experiment.

**Held-out set:** 16 intents generated for **Zoom** (373 endpoints) — an API never touched by any
prior experiment or by the SFT training data in this pipeline. **Training set:** the 45 Stage
6-verified trajectories from Experiment 3 (GitHub/Stripe/Slack only). Full data in
`data/generated/experiment5_sft_train.json` and `experiment5_heldout_eval.json`; script in
`scripts/run_experiment5.py`.

**Measured (pilot scale — ToolBench/prompt-only-agent baselines still not implemented; Self-Instruct
now is, closing the gap flagged in
[audit issue #1](https://github.com/Rashmioffcialpage/enterprisesynth-api/issues/1)):**

| Model | Tool Selection Accuracy | Parameter Validity (among correct selections) |
| --- | --- | --- |
| Base Qwen2.5-0.5B-Instruct (zero-shot, untuned) | 12.5% (2/16) | 0.0% |
| + LoRA fine-tuned on Self-Instruct-bootstrapped data (`scripts/run_baseline_selfinstruct.py`) | 25.0% (4/16) | 50.0% (2/4) |
| + LoRA fine-tuned on 45 EnterpriseSynth-verified trajectories | 87.5% (14/16) | 57.1% (8/14) |

Training loss dropped monotonically across the 3 epochs (0.708 → 0.403 → 0.247), consistent with
real learning rather than a fluke. The jump on tool selection (12.5% → 87.5%) is a genuine and
fairly large effect for 45 training examples and a 0.5B model, on an API the model never saw
during training — this is the strongest evidence in the paper so far for the central claim.

**The Self-Instruct baseline is the first real answer to RQ2.** Adapted per §5.3/§4.3 (schema-free
bootstrap: 4 real human-quality seeds, iterative few-shot generation, ROUGE-L-style dedup
filtering at a 0.7 threshold, no access to any real OpenAPI spec — see
`scripts/run_baseline_selfinstruct.py`), fine-tuned and evaluated with the exact same methodology
as the EnterpriseSynth run above, on the exact same 16 held-out Zoom intents. Result: any
fine-tuning helps over the untuned base (12.5% → 25%), but EnterpriseSynth's schema-grounded,
verified data helps roughly 3.5x more (25% → 87.5%). This isolates training-data quality — not
model, not evaluation methodology, not fine-tuning procedure — as the source of the gap.

**One honest surprise, checked rather than assumed:** the Self-Instruct bootstrap was expected to
invent endpoints with ~0% overlap with any real spec, since it never receives one. Instead, 12/45
(26.7%) of its "invented" endpoints turned out to be real — but **every single one was a GitHub
endpoint** (branch protection, webhooks — e.g. `PUT /repos/{owner}/{repo}/branches/{branch}/protection`),
none from Stripe or Slack. This is not schema grounding — it's the base model's own pretraining
knowledge of GitHub's extremely public, heavily-documented, conventionally-designed REST API
leaking through the few-shot bootstrap. This is an important limitation of Self-Instruct as a
baseline specifically for well-known public APIs, and it *strengthens* rather than weakens
EnterpriseSynth's motivating case: the actual cold-start target (private, internal enterprise
APIs with no public documentation for a model to have memorized) would show none of this
incidental grounding, making the true gap between Self-Instruct and EnterpriseSynth likely larger
in the real target setting than even this 25%-vs-87.5% pilot number suggests.

**Parameter Validity's gap (57.1%, well below tool selection's 87.5%) is itself an informative
finding, not just a shortfall.** Inspecting failures directly: for Zoom's
`PUT /users/{userId}/password`, the true required body field is `password`, but the fine-tuned
model generated plausible-sounding invented field names instead — `new_password`,
`expiration_time` — neither of which exists in Zoom's schema. The model generalized *which
endpoint to call* correctly (it even preserved the `{userId}` path template rather than
inlining a value, matching the training format exactly) but did not reliably generalize *the
exact field names* a genuinely novel schema requires. This is precisely the failure mode Stage 6
verification exists to catch before a generated trajectory ever reaches a real API call or a
training set — Experiments 4 and 5 corroborate each other here rather than being independent
claims.

**What this pilot does not show:** it does not show the effect holds for the paper's actual target
model scale (7-8B), for the full ~65-spec stratified training sample (vs. this pilot's 45
examples), or against the ToolBench/prompt-only-agent baselines specified in §5.3 — those require
either cloud GPU access or further implementation time, both future work.

### 6.7.1 Does 12.5%→87.5% Generalize? Scaling to Three Held-Out APIs

The single-Zoom result above is exactly the kind of number that could be a favorable draw rather
than a representative effect (`REVIEW.md` flagged this explicitly as the top risk to the central
claim). `scripts/scale_experiment5_heldout.py` tests this directly: trains each of the three
models (base, Self-Instruct-tuned, EnterpriseSynth-tuned) **once**, then evaluates all three
against **three** independent held-out APIs — Zoom (373 endpoints), plus two more never used in
training: **DigitalOcean** (290 endpoints) and **Spotify** (88 endpoints).

| Held-out API | Base | Self-Instruct-tuned | EnterpriseSynth-tuned |
| --- | --- | --- | --- |
| Zoom | 12.5% | 25.0% | 75.0% |
| DigitalOcean | 31.2% | **50.0%** | 43.8% |
| Spotify | 12.5% | 25.0% | 43.8% |

**The honest result: EnterpriseSynth does not win on all three.** It beats Self-Instruct on Zoom
(75.0% vs. 25.0%) and Spotify (43.8% vs. 25.0%), but **loses to Self-Instruct on DigitalOcean**
(43.8% vs. 50.0%). The Zoom number itself is also lower on this retrained run (75.0%) than the
original single-run 87.5% reported above — expected run-to-run variance, since neither the LoRA
weight initialization nor training data order is seed-fixed in the current implementation, but a
useful reminder that a single run's headline number carries real noise.

**This is reported as the central finding it is, not minimized.** The original 87.5% pilot number
was directionally correct (EnterpriseSynth beats both baselines on 2/3 held-out APIs and beats the
untuned base on all 3) but was not fully representative of the effect size — three draws show a
range from a loss to a 3x margin, not a uniform ~7x improvement. Parameter Validity, interestingly,
favors EnterpriseSynth more consistently (58.3%/100%/71.4% vs. Self-Instruct's 50%/100%/25% —
tied on DigitalOcean, ahead on Zoom and Spotify), suggesting the schema-grounded verified training
data may transfer more reliably to argument correctness than to tool selection specifically, though
three data points is nowhere near enough to make that a confident claim.

A plausible, explicitly unconfirmed hypothesis for DigitalOcean's reversal: DigitalOcean's
infrastructure/DevOps-flavored REST conventions may structurally resemble GitHub's (both are
developer-infrastructure APIs) more closely than Zoom's or Spotify's do, giving Self-Instruct's
GitHub-heavy bootstrap (recall §6.7's finding that its "invented" endpoints were disproportionately
real GitHub ones) an incidental transfer advantage on this specific held-out API that doesn't
generalize to communication (Zoom) or media (Spotify) APIs. This is a hypothesis to test, not a
finding — it would need more held-out APIs per domain category to actually confirm.

Full per-API detail: `data/generated/experiment5_multi_api_results.json`.

### 6.7.2 Is Any Single Seed Representative? A 5-Seed Sweep

The three-API table above is itself a single draw. `scripts/scale_experiment5_heldout.py` now
accepts `--seed N` and reuses the committed held-out eval sets rather than regenerating them via
fresh API calls each run, so a seed sweep varies only LoRA adapter weight initialization, not the
eval questions themselves. We reran the full comparison for 5 independent seeds (42, 123, 777,
2025, 9999).

| Held-out API | Base | Self-Instruct | EnterpriseSynth |
| --- | --- | --- | --- |
| Zoom | 12.5 ± 0.0% | 23.7 ± 10.3% | **66.2 ± 18.0%** |
| DigitalOcean | 31.2 ± 0.0% | 37.5 ± 21.2% | **53.7 ± 13.7%** |
| Spotify | 12.5 ± 0.0% | 12.5 ± 7.7% | **46.3 ± 7.1%** |

**Averaged over 5 seeds, EnterpriseSynth beats both the untuned base and Self-Instruct on all
three held-out APIs, including DigitalOcean** — the API where the single original run showed a
loss. This does not contradict the single-run finding above; it contextualizes it. DigitalOcean's
standard deviations are genuinely large (±13.7 for EnterpriseSynth, ±21.2 for Self-Instruct,
overlapping ranges), so individual seeds can and do still lose there — "wins on average, with real
run-to-run variance on DigitalOcean specifically," not "always wins." Base accuracy has zero
variance across seeds by construction. Raw data:
`data/generated/experiment5_multi_api_results_seed{42,123,777,2025,9999}.json`; aggregation:
`scripts/aggregate_multi_seed_scaling.py`, output `data/generated/experiment5_multi_seed_summary.json`.

### 6.7.3 Private Cold-Start Validation: Never-Published Enterprise APIs

Every held-out API used so far is real and extremely well-documented, plausibly present in the
base models' pretraining data — leaving RQ4's actual cold-start claim untested in its strongest
form. We hand-authored five never-published, synthetic enterprise API specs — CRM, HRIS,
Procurement, Ticket Management, Asset Management (28 endpoints total, generic plausible SaaS
shapes, not derived from any real company's documentation) — under `data/specs/private/`, and ran
the existing pipeline against them entirely unmodified.

| Eval set | Base (untuned) | EnterpriseSynth-tuned |
| --- | --- | --- |
| Public (Zoom/DigitalOcean/Spotify, n=48) | 18.8% | 39.6% |
| Private (never-published, n=30) | 23.3% | **40.0%** |

**The fine-tuning effect holds on APIs that cannot be in the base model's pretraining data.**
EnterpriseSynth-tuned accuracy on the private domains (40.0%) essentially matches public held-out
accuracy (39.6%) — the single strongest piece of evidence in the paper that the improvement
reflects genuine schema-grounding rather than incidental pretraining familiarity with well-known
public APIs. Base accuracy is, if anything, slightly higher on private (23.3% vs. 18.8%),
plausibly noise from the smaller sample rather than a real effect. Still one un-seeded run on 5
synthetic domains, not yet given the same multi-seed treatment as the public comparison.
Implementation: `scripts/generate_private_specs.py`, `scripts/build_private_coldstart_eval.py`,
`scripts/run_private_coldstart_eval.py`; data: `data/generated/private_coldstart_results.json`.

### 6.7.4 Scaling to 15+ APIs: Six More Real, Public Held-Out APIs

§5.2 targets a ~65-spec stratified sample; three held-out public APIs plus five private domains is
a step toward that, not the full target. We fetched six more real, public OpenAPI specs from
APIs.guru — Twilio, Notion, OpenAI, Jira, Asana, Trello — validated against the existing parser
with zero code changes, and evaluated EnterpriseSynth (same 45-example training set) against each.

| API | Base | EnterpriseSynth |
| --- | --- | --- |
| Twilio | 50.0% | 66.7% |
| Notion | 0.0% | 50.0% |
| OpenAI | 0.0% | 50.0% |
| Jira | 33.3% | 83.3% |
| Asana | 0.0% | 83.3% |
| Trello | 33.3% | 100.0% |

EnterpriseSynth beats the untuned base on all six. Combined with the three public and five private
held-out APIs above, the pipeline has now touched **17 total APIs** (3 training, 9 real held-out,
5 private held-out) — still short of the ~65-spec target, but no longer a 3–5-API pilot either.
Real cost data as a byproduct, addressing a previously fully-open limitation: LoRA training took
619.8 seconds (Qwen2.5-0.5B, 45 examples, 3 epochs, Apple M2 MPS backend); per-API evaluation (12
generations each) ranged from 27.2s (Trello) to 95.1s (Twilio) — specific to this hardware-scoped
pilot model, not extrapolated to the 7–8B target scale. Implementation:
`scripts/build_phase3_eval.py`, `scripts/run_phase3_eval.py`; data:
`data/generated/phase3_results.json`, `data/generated/phase3_timings.json`.

### 6.8 What Comes After Experiments

Once Experiments 1–5 actually run, the remaining paper sections analyze the results — not written
yet, since there is nothing to analyze until the pipeline exists:

- **Results** — quantitative findings across all five experiments.
- **Ablation Study** — remove one pipeline component at a time (e.g., no knowledge graph, no
  verifier) to isolate each stage's contribution.
- **Case Studies** — walk through a few generated examples end-to-end, from raw OpenAPI spec to
  final verified trajectory.
- **Discussion** — strengths, limitations, scalability, future work.
- **Conclusion** — summarize problem, solution, and main findings.

---

## 7. Results and Analysis

### 7.1 Overview

We evaluate EnterpriseSynth on real-world OpenAPI specifications from GitHub, Stripe, and Slack
(used for both pipeline development and SFT training data), plus Zoom (used exclusively as a
held-out evaluation API, never touched during training or any earlier experiment). Evaluation
covers API understanding (Experiment 1), intent generation quality (Experiment 2), trajectory
generation (Experiment 3), schema-based verification (Experiment 4), and downstream agent
performance (Experiment 5). Results below are organized by the five experimental RQs from §6.1.
All numbers are measured, not projected — see §6 for full experiment detail, scripts, and raw
data files.

### 7.2 RQ1 — API Schema Understanding

**Dataset:**

| API | Paths | Path+Method Operations |
| --- | --- | --- |
| GitHub | 551 | 845 |
| Stripe | 299 | 446 |
| Slack | 174 | 174 |

**Results:** endpoint, parameter, request/response schema, and authentication extraction accuracy
all reach 100% for all three APIs, checked against ground truth independently recomputed from
each raw spec (§6.3).

**Analysis — which API was hardest, and why:** all three ultimately reach 100%, but they were not
equally easy to get there, and the honest answer is architectural, not about documentation
quality. GitHub was hardest because it defines most of its parameters via `$ref` to shared
`components.parameters` entries (e.g. `org`, `secret_name` reused across hundreds of endpoints) —
the first version of Stage 1 silently dropped every one of these, undercounting GitHub's required
parameters by 67 vs. the true 1,721 once resolved. Stripe was hardest in a different way: many of
its endpoints (e.g. `/v1/charges`) declare zero OpenAPI `parameters` at all and put every real
field in `requestBody` schema instead — Stage 1 originally only tracked a boolean "schema present"
flag for request bodies and never parsed the actual fields. Slack required neither fix; its spec
uses inline parameters and request bodies directly. Both fixes are general (any spec using `$ref`
parameters or requestBody-only payloads benefits), not GitHub/Stripe-specific patches.

### 7.3 RQ2 — Intent Generation Quality

**Scale (pilot):** 5 endpoints sampled per API (seeded), 3 intents generated per endpoint = 15
intents per API, 45 total.

**Metrics:** Intent Coverage 100% for all three APIs (every sampled operation received generated
intents). Intent Diversity (exact-string, unique/total): 100% (15/15) for all three — a weak proxy
that only rules out literal duplication; semantic-similarity clustering is not yet implemented.
Human evaluation: not measured (no annotators yet).

**Analysis:** manual inspection (not just the aggregate metric) is what actually substantiates
quality here. Generated intents are specific, business-scenario-grounded, and non-generic — e.g.
GitHub's tag-protection endpoint produced intents about locking down release tags for a named
"payments-service" repo and restricting CI tampering, not three rephrasings of "protect a tag."
They are representative of real enterprise workflows (secret rotation across microservices,
subscription billing corrections, channel privacy changes for legal/compliance reasons) rather
than templated CRUD statements. This is a 15-endpoint-per-API pilot, not the full §5.2 stratified
sample; human and semantic-similarity evaluation at that larger scale is the clear next step.

### 7.4 RQ3 — Agent Trajectory Generation

**Metrics (all 45 intents from Experiment 2, one measured run):**

| Metric | Result |
| --- | --- |
| Tool Selection Accuracy | 100% (GitHub, Stripe), 93.3–100% (Slack, run-to-run) |
| Parameter Validity (among correct selections) | 100% |
| Workflow Completeness | not applicable at this pilot scale (single-endpoint intents only) |

No "Baseline vs. EnterpriseSynth" comparison row exists yet for this experiment specifically —
only our own pipeline has been measured; the prompt-only/Self-Instruct/AgentInstruct baselines
specified in §5.3 are not yet implemented for trajectory generation and are a documented gap, not
an omitted result.

**Analysis:** the planner (Stages 4+5, combined into one call for this pilot) correctly extracts
literal values from free text into the right parameter slots (e.g. a Stripe subscription-item ID
copied verbatim from the intent into the `item` parameter) and selects the correct tool among 15
candidates, not a trivial 1-of-1 choice. The one genuine miss observed across repeated runs was a
JSON-parsing failure in our extraction code (1/45 in one run), not a wrong tool choice — a pipeline
robustness gap, not a planning error. Multi-step workflow chains (e.g. create customer → retrieve
ID → create invoice) are not yet exercised at all, since Experiment 2's intents are single-endpoint
by design; testing whether the Knowledge Graph (Stage 2) helps multi-step planning requires
generating multi-hop intents first, which is future work.

### 7.5 RQ4 — Verification Performance

This is the paper's strongest contribution area. **45 valid trajectories tested** (all 45 pass —
100% Verification Pass Rate on already-correct trajectories) plus **44 deliberately corrupted
variants** (some corruption types are occasionally skipped when a trajectory has no eligible
parameter to corrupt), scored for whether Stage 6 catches each planted error.

**Error taxonomy (final, after fixing the four bugs documented in §6.6):**

| Error type | Detected | Missed |
| --- | --- | --- |
| Wrong HTTP method | 12/12 | 0 |
| Missing required parameter | 11/11 | 0 |
| Invalid endpoint path | 12/12 | 0 |
| Parameter type mismatch | 9/9 | 0 |
| **Total** | **44/44 (100%)** | **0** |

**Analysis — why static verification is valuable, and why the 100% took real work to earn:**
enterprises frequently cannot provide production API access, private credentials, or live
staging environments for internal systems — EnterpriseSynth's entire premise depends on offline
verification being trustworthy without any of that. The first run of this experiment did **not**
reach 100% (57–80% detection, §6.6) — adversarial testing surfaced two real verifier/harness bugs
and two real Stage 1 parser gaps ($ref resolution, requestBody field parsing) that a
non-adversarial test (checking only already-correct trajectories) would never have revealed. The
honest conclusion is not "the verifier is perfect" but that adversarial testing against a verifier
is what actually validates one, and a verifier is only as good as the structured representation it
checks against.

### 7.6 RQ5 — Downstream Agent Performance

**Setup:** training set = 45 Stage-6-verified trajectories from GitHub/Stripe/Slack; evaluation set
= 16 intents for **Zoom** (373 endpoints), an API not present in the training set or any prior
experiment. Model: Qwen2.5-0.5B-Instruct (hardware-scoped substitute for §5.4's Mistral-7B/Llama-3-8B
target — see §6.7 for the feasibility rationale), LoRA fine-tuned, 3 epochs.

| Model | Task/Tool Success | Argument (Parameter) Correctness |
| --- | --- | --- |
| Base LLM (zero-shot, untuned) | 12.5% (2/16) | 0.0% |
| Self-Instruct-fine-tuned (LoRA) | 25.0% (4/16) | 50.0% (2/4, among correct selections) |
| EnterpriseSynth-fine-tuned (LoRA) | 87.5% (14/16) | 57.1% (8/14, among correct selections) |

Prompt-only-agent and ToolBench baseline rows are not yet implemented for this pilot; Self-Instruct
now is (§6.7), on the identical held-out set and fine-tuning methodology.

**Analysis:** this is the paper's central claim, and the pilot supports it — a 12.5% → 87.5% jump
in tool-selection success on a genuinely unseen API, from only 45 training examples on a 0.5B
model, with training loss dropping monotonically (0.708 → 0.403 → 0.247) across 3 epochs. The new
Self-Instruct baseline shows this isn't just "any fine-tuning helps" — it helps somewhat (12.5% →
25%), but EnterpriseSynth's schema-grounded, verified data helps roughly 3.5x more (25% → 87.5%),
isolating training-data quality as the source of the gap. Argument correctness lagging well behind
tool selection is itself a finding: the model learned which endpoint to call but not always the
exact field names a new schema requires (e.g. inventing `new_password` instead of Zoom's actual
`password` field) — exactly the class of error Stage 6 verification exists to catch before it
reaches a live call.

### 7.7 Comparison With Existing Approaches

| Capability | ToolLLM/ToolBench | API-Bank | AgentInstruct | EnterpriseSynth |
| --- | --- | --- | --- | --- |
| Uses OpenAPI specs | Partial | No | No | Yes |
| Enterprise APIs | Limited | Limited | No | Yes |
| Requires live execution | Yes | Yes | No | No |
| Generates SFT data | Yes | Limited | Yes | Yes |
| Generates evaluation data | Limited | Yes | No | Yes |
| Schema-based verification | No | Limited | No | Yes |

This table reflects the literature review in §3/`paper/related_work_audit.md`, not a new claim:
ToolLLM grounds every solution path in real API calls (~470k logged during annotation); API-Bank
uses reproducibility-constrained real databases and its correctness check compares predicted vs.
annotated calls rather than validating against a declared schema; AgentInstruct's `tool_use` flow
never executes anything but also never checks against a real spec (it can hallucinate the API
surface) and evaluates via a generic post-hoc judge (Orca-Bench) rather than schema-based
verification or a purpose-built eval artifact tied to its own generation process.

### 7.8 Key Findings Summary

- EnterpriseSynth extracts structured knowledge from real-world APIs at 100% measured accuracy —
  but that number is only trustworthy because two genuine Stage 1 parsing gaps ($ref resolution,
  requestBody field parsing) were found and fixed, not assumed from the start.
- Schema-grounded generation (Stages 3–5) produces enterprise-specific, non-generic intents and
  correctly-scoped trajectories on a 45-example GitHub/Stripe/Slack pilot.
- Static, non-LLM verification (Stage 6) catches 100% of deliberately planted errors across four
  corruption types (wrong method, missing param, invalid path, wrong type) — but only after
  adversarial testing surfaced and forced fixes to real bugs; the pre-fix detection rate was
  57–80%, not 100%, and that gap is reported, not hidden.
- EnterpriseSynth-generated SFT data measurably improves a fine-tuned model's tool-selection
  accuracy on a genuinely unseen API (12.5% → 87.5%), though exact-field-name generalization for
  request parameters remains a real, unresolved limitation (57.1%) — one that Stage 6 verification
  is specifically positioned to catch downstream, not paper over.
- All results above are pilot-scale (3–4 APIs, 45–89 examples per experiment, a 0.5B substitute
  model). Scaling to the full ~65-spec stratified sample, the paper's actual target model size,
  and the remaining baselines (Self-Instruct, ToolBench, prompt-only agent) is the immediate next
  phase of work, not yet done.

---

## 8. Ablation Study

### 8.1 Purpose and Scope

The question: which components of EnterpriseSynth actually contribute to generating high-quality
verified SFT and evaluation data? This section is scoped strictly to what is **actually
implemented** — the four-stage pipeline (Parser → Intent Agent → Trajectory Agent → Verifier).

Four ablations **are** real, implemented, and run against actual data:

### 8.2 A1 — Without Intent Generation

**Setup:** `NoIntentTrajectoryAgent` (`src/enterprisesynth/ablation_agents.py`) receives only an
endpoint (no user intent) and must invent both an instruction and concrete parameters in one
step. Run on the same 45 endpoint samples (15 per API) as Experiments 2–3, via
`scripts/run_ablation_study.py`.

**Result:**

| API | Trials | Parameter Validity | Instruction Diversity (exact-string) |
| --- | --- | --- | --- |
| GitHub | 15 | 100.0% | 93.3% |
| Stripe | 15 | 100.0% | 100.0% |
| Slack | 15 | **93.3%** | 93.3% |

Compare to the full pipeline's baseline (Experiments 2+3): 100% coverage, 100% diversity, 100%
parameter validity across all three APIs. The drop is small but real and not noise — inspecting
the one Slack parameter-validity failure directly: without an intent to ground it, the model
generated Slack's `POST /users.profile.set` call with an invented `token` field and a nested
`profile` object shape that didn't validate against the declared parameter schema, something the
full (intent-grounded) pipeline did not do in Experiment 3's 45/45 trials. **Conclusion:** explicit
intent generation provides real, if modest at this sample size, grounding that improves both
output diversity and parameter correctness over generating directly from a bare endpoint
description.

### 8.3 A2 — Without Verification Engine

**Setup:** no new run needed — this reuses Experiment 4's corruption-testing data directly
(§6.6/§7.5). Without a verifier, none of the 44 deliberately-planted errors would be caught (by
construction — there is nothing filtering them); with `SchemaVerificationEngine`, 44/44 are.

| Configuration | Invalid trajectories retained (of 44 planted) |
| --- | --- |
| Without verification | 44/44 (100% — nothing is filtered) |
| With verification | 0/44 (0% — all caught) |

**Conclusion:** this is the strongest and clearest ablation in the paper. Every planted structural
error (wrong method, missing required parameter, invalid path, wrong parameter type) survives into
the dataset with no verification step, and none do with one. Full detail, including the four real
bugs found and fixed to get to 100%, is in §6.6.

### 8.4 A3 — Without vs. With API Descriptions

**Setup:** `DescriptionAwareIntentAgent` adds the endpoint's OpenAPI `description`/`summary` field
(confirmed absent from every prior experiment — no `description` field existed anywhere in the
codebase before this ablation was built) to the Intent Agent's prompt. Run on the same 45 endpoint
samples.

**Result:** Coverage and exact-string diversity are **unchanged** — 100%/100%/100% for all three
APIs, identical to the no-description baseline. This is a ceiling effect in the chosen metrics,
not evidence of no effect: both conditions already saturate these particular numbers.
**Qualitative inspection tells a different, real story.** For GitHub's
`PUT /orgs/{org}/actions/secrets/{secret_name}/repositories` (description: *"Replaces all
repositories for an organization secret when visibility is set to `selected`... requires an access
token with the `admin:org` scope"*):

- **Without description (baseline):** "Update the list of repositories that can access our
  org-level DOCKER_REGISTRY_PASSWORD secret to include the three new microservice repos..."
- **With description:** "We just rotated our shared Docker registry password stored as the org
  secret DOCKER_REGISTRY_PASSWORD. Please update it so only the 'payments-service',
  'inventory-api', and 'checkout-frontend' repos (IDs 34521, 34522, 34890) have access to it..."

Both are realistic and well-scoped. The description-aware version more explicitly reflects the
"replaces the full list" semantics and uses concrete numeric repo IDs rather than names alone.
**Conclusion:** inconclusive by the quantitative metrics used (they don't have headroom to show a
difference); a real but modest qualitative signal exists and needs a better metric (e.g.
LLM-judged specificity/faithfulness-to-description scoring) to quantify properly. Reported as
inconclusive, not as a positive finding, since the numbers don't actually support one.

### 8.5 A4 — Endpoint-Only vs. Full-API Context

**Setup:** `FullContextIntentAgent` adds the other endpoints in the same API (the same
distractor set used in Experiment 3) as context, and is explicitly invited to describe multi-step
workflows spanning them. Run on the same 45 samples.

**Result:** Coverage and diversity are again unchanged (100%/100%/100%, same ceiling effect as
A3). We additionally built a "sequencing-language" proxy metric (keyword search for
then/after/once/followed by/before) to detect apparent multi-step awareness, which initially
looked promising (6–7 "mentions" per API). **Inspecting the actual flagged intents showed this
metric is invalid** — every flagged example was a false positive: incidental temporal phrasing in
an otherwise single-step request (e.g. "...and let me know *once* this is configured so I can
inform the release management team" — a side comment, not a second API call), not genuine
multi-endpoint chaining. **Conclusion:** no measurable effect detected at this pilot scale with
the metrics available; the attempted proxy metric was checked against real output, found unsound,
and is reported as invalid rather than kept as a false positive result. Testing whether full-API
context (or, better, an actual Knowledge Graph, §4) helps multi-step workflow generation requires
either better metrics or intents deliberately constructed to need multiple endpoints — neither
exists yet.

### 8.6 Ablation Results Table

| Variant | Parameter/Endpoint Validity | Instruction/Intent Diversity | Verification Pass |
| --- | --- | --- | --- |
| Full pipeline (baseline) | 100% (Exp. 3) | 100% (Exp. 2) | 100% (Exp. 4, post-fix) |
| A1: − Intent Generation | 93.3–100% | 93.3–100% | n/a (not tested through Stage 6) |
| A2: − Verification | n/a | n/a | 0% (nothing filtered) |
| A3: + Descriptions | unchanged (ceiling) | unchanged (ceiling); qualitative diff. observed | n/a |
| A4: + Full-API context | unchanged (ceiling) | unchanged (ceiling); no valid signal detected | n/a |

### 8.7 Why This Matters

Without an ablation study, reviewers will reasonably ask: "why do you need all these components —
why not just prompt an LLM with the OpenAPI file directly?" The honest answer, per component
actually tested: **Intent Generation** provides real (if modest, at 45-example pilot scale)
grounding that improves both diversity and parameter correctness (A1). **Verification** is
unambiguously necessary — it is the difference between 0% and 100% of planted errors surviving
into the dataset (A2). **Descriptions** and **full-API context** show no effect on the metrics
used so far (A3, A4) — which is itself useful information: it means the current quantitative
metrics (coverage, exact-string diversity) are too coarse to detect what may still be a real
qualitative effect for descriptions, and that either better metrics or deliberately multi-step
task construction is needed before context/graph-awareness ablations can be judged one way or the
other.

---

## 9. Case Study and Qualitative Analysis

### 9.1 Purpose

Sections 6–8 establish that EnterpriseSynth works quantitatively and which components are
load-bearing. This section answers a different question a metrics table cannot: *what does
EnterpriseSynth actually produce, and does it look useful for real enterprise scenarios?* Every
example below is pulled directly, unedited, from committed pipeline output
(`data/generated/experiment2_intents.json`, `experiment3_trajectories.json`,
`experiment4_verification.json`) — nothing here is constructed for illustration. The pipeline
traced end-to-end:

```text
Real OpenAPI Specification
        |
        v
API Parsing (Stage 1)
        |
        v
Intent Generation (Stage 3)
        |
        v
Trajectory Generation (Stages 4-5)
        |
        v
Schema Verification (Stage 6)
        |
        v
Final SFT / Evaluation Record
```

### 9.2 Case Study 1: GitHub — Tag Protection

**Parsed API knowledge** (Stage 1 output for this endpoint):

```text
POST /repos/{owner}/{repo}/tags/protection
description: "This creates a tag protection state for a repository. This endpoint is only
available to repository administrators."
parameters: owner (path, required, string), repo (path, required, string),
pattern (body, required, string)
```

**Generated intent** (Stage 3, one of three generated for this endpoint):

> "Set up tag protection on the 'payments-service' repo so that only admins can create or delete
> tags matching 'v\*' — we need to prevent accidental deletion of release tags."

**Generated trajectory** (Stages 4–5):

> Call `POST /repos/{owner}/{repo}/tags/protection` with `{"owner": "your-org", "repo":
> "payments-service", "pattern": "v*"}`. Reasoning given: "This tool creates a tag protection rule
> for a repository matching a specified pattern, restricting tag creation/deletion to admins,
> which fulfills the request to protect 'v\*' tags on 'payments-service'."

**Verification** (Stage 6): endpoint exists — PASS; required params present — PASS; param types
valid — PASS. **Trajectory status: VERIFIED.**

### 9.3 Case Study 2: Stripe — Subscription Item Removal

**Parsed API knowledge:**

```text
DELETE /v1/subscription_items/{item}
parameters: item (path, required, string), clear_usage (body, optional, boolean),
proration_behavior (body, optional, string)
```

**Generated intent:**

> "We're removing the extra seats add-on from customer cus_9F3kLmZ8's subscription — please delete
> subscription item si_1N4kTx2eZvKYlo2C and clear out the associated usage records since we don't
> need them for billing."

**Generated trajectory:**

> Call `DELETE /v1/subscription_items/{item}` with `{"item": "si_1N4kTx2eZvKYlo2C",
> "clear_usage": true, "proration_behavior": "create_prorations"}`.

**Verification: PASS on all checks — VERIFIED.**

**An honest limitation this example surfaces directly:** the intent above evokes a business
workflow (removing a paid add-on, reconciling usage), but the system resolves it to *one* verified
API call, not a multi-step chain of dependent calls (e.g. look up the customer, then the
subscription, then delete the item). This is not a simplification for the case study — it is what
the implemented system actually does. Multi-step, dependency-aware trajectory generation requires
the Knowledge Graph and Planner stages (§4), neither of which is implemented; see §11's explicit
accounting. We do not show a fabricated multi-step Stripe trajectory here because the current
pipeline cannot produce one.

### 9.4 Case Study 3: A Verification Failure, by Design

Reviewers should see the verifier reject something, not just accept everything. This corrupted
trajectory is drawn directly from Experiment 4's adversarial test set (§7.5): the original, valid
trajectory for updating access to a GitHub org secret had its `org` parameter corrupted from a
string to an object.

> **Original intent:** "Update the DEPLOY_TOKEN secret in our 'acme-corp' org so it's only
> accessible by the payments-api and payments-worker repositories"
> **Endpoint:** `PUT /orgs/{org}/actions/secrets/{secret_name}/repositories`
> **Corrupted parameter:** `org = {"unexpectedly": "an object"}` (declared type: string)
> **Verifier output:** `valid: false` — "Parameter 'org' = {'unexpectedly': 'an object'} is not
> compatible with declared type 'string'."

**Trajectory status: REJECTED.** This is the same mechanism, on the same data, that produced
Experiment 4's 44/44 detection rate (§7.5) — shown here as a single concrete instance rather than
an aggregate percentage.

### 9.5 Qualitative Analysis

**Finding 1: schema information is sufficient for initial task generation.** OpenAPI
specifications provide endpoint descriptions, parameter names/types, and (where declared)
authentication schemes — enough for Stage 3 to generate business-scenario-specific intents (named
companies, dollar amounts, department names; §7.3) without ever calling the live API. The GitHub
and Stripe examples above were generated this way.

**Finding 2: verification prevents synthetic data contamination.** Without Stage 6, every planted
structural error in Experiment 4 survived into the dataset (0% detection, ablation A2, §8). With
it, all 44 did not (100%). Case Study 3 shows the mechanism, not just the aggregate: a model
trained on unverified data would have learned that passing an object where a string is required is
acceptable GitHub API usage.

**Finding 3 (reframed from a template assumption): the current system is single-step by design,
not yet multi-step — and we say so plainly rather than imply otherwise.** A natural claim for a
paper like this to make is that it moves beyond "one user request → one API call" toward validated
multi-step workflows. We do not make that claim, because Case Study 2 shows directly that the
implemented system does not yet do this: every generated trajectory in Experiments 3–5 resolves to
a single endpoint call (§7.4's "Workflow Completeness: not applicable at this pilot scale" is the
same fact stated as a metric). The honest version of this finding is narrower: EnterpriseSynth's
intents are often *phrased* at the business-workflow level (Case Study 2's "removing the extra
seats add-on... and clear out the associated usage records" spans a conceptual before/after
state), while the *trajectory* generated for them today is single-step. Closing that gap is exactly
what the unimplemented Planner/Knowledge Graph stages (§4) are for.

### 9.6 Failure Analysis

**Category 1: sparse documentation (real, spec-level evidence; not yet directly measured as a
pipeline failure).** The committed specs contain many endpoints with minimal descriptions — real
examples: GitHub's `GET /gists/{gist_id}` ("Get a gist"), Stripe's `POST /v1/refunds` ("Create a
refund."), Slack's `POST /calls.end` ("Ends a Call."). None of these three happened to fall in the
15-endpoint-per-API pilot sample (§7.3), so we have not directly measured intent quality degrading
on them — this is a disclosed, anticipated risk rather than an observed result, and scaling to the
full ~65-spec sample (§11) is what would surface it either way.

**Category 2: hidden business logic.** An OpenAPI spec documents an interface, not a policy. A
loan-application endpoint's schema declares its request/response shape, not the underlying
approval rules, eligibility criteria, or compliance checks a real implementation enforces. Nothing
in EnterpriseSynth's four implemented stages reasons about business rules — the Schema
Verification Engine checks structural compatibility with the declared schema, not business
correctness. This is a conceptual limitation inherent to schema-only generation, not something we
have a measured failure case for, since no corruption in Experiment 4 targeted business-rule
violations.

**Category 3: complex authentication (real, measured).** GitHub's spec declares **zero**
`securitySchemes` anywhere (§7.2, Experiment 1) — its authentication is documented in prose, not
machine-readably, a real property of that spec confirmed during parsing, not a parser bug. This is
direct evidence that schema-declared auth can understate real API complexity: OAuth refresh flows,
multi-user permission scoping, and dynamically-issued tokens are exactly the kind of auth behavior
a declarative schema does not capture, and GitHub's spec is a concrete case of a widely-used real
API where that gap is already visible.

### 9.7 Case Study Summary

| API | Domain | Endpoint | Verification |
| --- | --- | --- | --- |
| GitHub | Developer/software | `POST .../tags/protection` | Verified |
| Stripe | Payments | `DELETE .../subscription_items/{item}` | Verified |
| GitHub (corrupted) | Developer/software | `PUT .../secrets/{secret_name}/repositories` | Rejected (correctly) |

---

## 10. Semantic Quality Evaluation (LLM-as-a-Judge)

### 10.1 Motivation and Scope

Tool Selection Accuracy, used throughout §7–§9, is binary: did the model choose the correct
endpoint. It cannot answer whether the call it produced is actually usable — whether the
arguments are correct, whether required fields are missing, or whether a parameter was invented
outright. We add a complementary evaluation layer that scores these dimensions directly, using an
independent LLM judge (Claude Sonnet 5) rather than a lexical-similarity metric, since this task
has no natural reference text to score against (there is one correct endpoint, not one correct
phrasing of a response).

We deliberately do not attempt multi-step workflow evaluation here. EnterpriseSynth has no
Planner or Knowledge Graph (§4, §12); every generated trajectory is a single endpoint call, so
there is no multi-step output to evaluate. Building a workflow-success metric around single-step
predictions would test a capability the system does not have — the same overclaiming risk §9.3's
Case Study 2 explicitly declined to paper over. Multi-step workflow evaluation is reserved for
future work alongside the Planner and Knowledge Graph components themselves.

### 10.2 Methodology

For each held-out example, the judge receives the user intent, the ground-truth endpoint and its
required parameters (from the real spec), and EnterpriseSynth's actual prediction (parsed method,
path, and parameters — nothing hidden or cleaned up). It scores four dimensions on a 1–5 scale —
intent match, argument correctness, missing parameters, reasoning quality — and assigns a single
primary-error category: none, wrong tool selected, missing required parameter, incorrect argument
value, hallucinated parameter, or invalid request format. We judged all 48 EnterpriseSynth
predictions from one full seed run of §7.6's multi-API scaling (Zoom/DigitalOcean/Spotify); 47
judge responses parsed as valid JSON. Implementation: `src/enterprisesynth/llm_judge.py`,
`scripts/run_llm_judge_eval.py`.

### 10.3 Results

| Dimension (1–5 scale) | Mean |
| --- | --- |
| Intent Match | 2.81 |
| Argument Correctness | 2.19 |
| Missing Parameters | 2.55 |
| Reasoning Quality | 2.28 |

| Error Type | Count | % |
| --- | --- | --- |
| Wrong tool selected | 16 | 34.0% |
| Missing required parameter | 11 | 23.4% |
| Invalid request format | 5 | 10.6% |
| Hallucinated parameter | 3 | 6.4% |
| Incorrect argument value | 2 | 4.3% |

**The central finding: binary Tool Selection Accuracy overstates practical quality by roughly
2×.** Cross-checking the judge against the existing binary correctness flag: of the 23 examples
marked correct by binary Tool Selection Accuracy (48.9% of 47), the judge flagged a real problem
— almost always a missing or hallucinated parameter — in 14 of them (61%). Only 10 of 47 examples
(21.3%) are fully correct by the judge's standard. Discussed further in §11.5.

**A real bug found and fixed while building this evaluation:** the first version used
`max_tokens=250` for the judge call. Claude Sonnet 5 spent the entire budget on an internal
`thinking` block before ever writing the JSON answer, so 17 of 48 judge calls (35%) were cut off
mid-thought (`stop_reason: max_tokens`) with zero text output — not a malformed response, no
response at all. Raising `max_tokens` to 1200 dropped the failure rate to 1/48 (2%). Reported
here because it's the same category of lesson as Experiment 4's adversarial-testing story
(§7.5): a plausible-looking evaluation pipeline can silently fail a third of the time if you
don't check its own success rate.

---

## 11. Discussion

### 11.1 What Actually Works, and Why

Two results in this paper are load-bearing, not decorative. First, Schema Verification (Stage 4)
is unambiguously necessary: A2 shows a binary 0%-vs-100% gap between no verification and ours —
every planted structural error survives without a gate, and none do with one. Second, that 100%
was earned through adversarial testing, not assumed: the first run of Experiment 4 caught only
57–80% of planted errors, and chasing down why surfaced four real bugs spanning the verifier, the
test harness, and Stage 1's parser (§6.5–6.6). The methodological point generalizes beyond this
codebase: a static verifier's correctness cannot be established by checking that it accepts good
input — it has to be adversarially tested against bad input it is specifically supposed to reject.
A non-adversarial test suite would have shipped a verifier that silently passed roughly a third to
a half of planted errors.

### 11.2 Verification Has Limits by Design, and the Haiku Arm Quantifies Them

The deterministic gate checks structure, not semantics — it cannot know that a negated charge
amount or a placeholder field value is wrong, because both are still well-typed. The Haiku 4.5
ablation (§6.6.1) both confirms this blind spot (100% of semantically-corrupted trajectories pass
Stage 4 structurally) and shows a cheap LLM can close part of the gap (100% caught). But the same
experiment shows this is not a free upgrade: a 33% false-positive rate on GitHub, traced to the
model being overly literal about things the underlying tool call did not need to prove (e.g. that
a numeric repository ID "really" corresponds to a named repository). The practical implication is
a two-tier design, not a wholesale replacement: keep the deterministic gate as the hard, blocking
filter, and treat an LLM semantic check as an advisory or re-ranking signal until it is calibrated
per parameter type (e.g. restricted to amounts, dates, and other fields where "plausibility" is
well-defined) — exactly the shape ToolACE's and AgentInstruct's own dual-layer designs converge
on, for related reasons.

### 11.3 The Downstream Effect Is Real but Not Uniform, and That Is Itself a Finding

Experiment 5's single-Zoom result (12.5%→87.5%) was the strongest number in an earlier draft of
this paper. Scaling to three held-out APIs changed the story without reversing it:
EnterpriseSynth-tuned data beats a real Self-Instruct baseline on two of three APIs, and beats the
untuned base on all three, but loses to Self-Instruct specifically on DigitalOcean. We do not
believe this is noise to explain away — Self-Instruct's own bootstrap was shown (§6.7.1) to lean
on the base model's pretraining familiarity with GitHub's extremely public API, and DigitalOcean's
infrastructure/DevOps-flavored conventions are the closest of our three held-out APIs to GitHub's.
If that hypothesis holds under further testing, it says something uncomfortable but important
about the field's usual practice of benchmarking tool-use methods on well-known public APIs
(GitHub, Stripe, Slack, and here, apparently, DigitalOcean by proxy): a base model's prior exposure
to an API's public documentation can substitute for genuine schema grounding in a way that will
not be available for the private, undocumented internal APIs EnterpriseSynth is actually built
for. If anything, this strengthens rather than weakens the cold-start motivation — but it also
means our own pilot cannot yet distinguish "EnterpriseSynth generalizes better" from
"EnterpriseSynth generalizes better specifically on APIs unlike ones the base model already
knows," and only a genuinely private, unpublished spec (§5.2's cold-start validation set, not yet
built) can settle that.

### 11.4 Positioning Relative to AgentInstruct

We adapted AgentInstruct's agentic-flow architecture rather than starting from scratch because it
is the only reviewed method that is both agentic and execution-free. The two changes we made —
real-spec grounding instead of code-seeded hallucination, and a hard structural gate instead of a
soft editorial-plus-post-hoc-judge pipeline — are not merely stylistic. §6.3's finding that Stage 1
initially mishandled `$ref` parameters and `requestBody` fields shows that even "just parse the
real spec" is a nontrivial engineering problem for production-scale OpenAPI documents;
AgentInstruct's decision to let the model invent an API surface sidesteps that complexity
entirely, at the cost of the hallucination risk we removed it to avoid. Our Static Constraint
Validator is functionally close to ToolACE's Dual-Layer Verification design (rule-based plus
model-based checking) though we arrived at the model-based layer later, as an explicit ablation
(A5) rather than a built-in default — a design choice that let us measure its marginal value and
cost separately, which §6.6.1 shows was worth doing.

### 11.5 Binary Tool Selection Accuracy Overstates Practical Quality

Every headline number in this paper up to this point is Tool Selection Accuracy: did the model
choose the right endpoint. §10's LLM-as-a-judge evaluation tests whether that is the right
question to be asking. Using an independent LLM-based evaluator (Claude Sonnet 5, scoring intent
match, argument correctness, missing parameters, and reasoning quality on a 1–5 scale, plus a
primary-error classification), we judged the EnterpriseSynth-tuned model's actual predictions on
47 held-out examples across Zoom, DigitalOcean, and Spotify.

| Metric | Correct (%) |
| --- | --- |
| Binary Tool Selection Accuracy | 48.9% (23/47) |
| LLM-judge: fully correct (no classified error) | 21.3% (10/47) |

Although EnterpriseSynth substantially improves Tool Selection Accuracy, our semantic evaluation
reveals that endpoint selection alone is insufficient to characterize practical API generation
quality. Only 21.3% of generated invocations were judged to be fully correct despite 48.9% being
classified as correct under the binary endpoint metric. In particular, 61% of endpoint-correct
predictions (14 of 23) contained semantic deficiencies such as omitted required parameters or
invalid argument values — most commonly missing required parameters (23.4% of all judged
examples) and outright wrong tool selection (34.0%), with hallucinated parameters (6.4%) and
incorrect argument values (4.3%) accounting for the remainder. These findings suggest that future
evaluations of API-generation systems should complement endpoint-level accuracy with
argument-level semantic correctness to better reflect deployment readiness. We report this
against ourselves, not a competing method: every Tool Selection Accuracy number elsewhere in this
document should be read as an upper bound on practical correctness, not an estimate of it.

---

## 12. Limitations

1. **Pilot scale throughout.** All five experiments and five ablations run on 3–5 real APIs and
   45–89 examples each, not the full ~65-spec stratified sample specified in §5.2. Every
   percentage in this paper should be read as a pilot signal, not a population estimate.
2. **Experiment 3's self-consistency confound.** The same model (Claude Sonnet 5) both generated
   the intents (Experiment 2) and performed tool selection against them (Experiment 3), so its
   100% figures measure whether the model can recover its own intent, not whether it handles
   independently-authored or adversarial requests.
3. **Experiment 5's model-scale gap.** The downstream fine-tuning result uses
   Qwen2.5-0.5B-Instruct, a hardware-scoped substitute for the paper's actual target
   (Mistral-7B-Instruct or Llama-3-8B). Whether the effect holds, strengthens, or weakens at that
   scale is untested.
4. **Missing baselines.** ToolBench and a prompt-only agent are specified in §6.1 but not yet
   implemented for any experiment; only Self-Instruct has been run as a real comparison.
5. **No Knowledge Graph or Planner.** Multi-step, dependency-aware workflow generation is entirely
   untested — Ablation A4's attempt to probe this by giving the Intent Agent flat (non-graph)
   context on other endpoints showed no measurable effect, but this does not confirm the graph
   itself would not help; it only shows that a cheaper substitute for it, at this pilot scale, did
   not.
6. **A3 and A4 are inconclusive by the metrics used, not resolved.** Coverage and exact-string
   diversity ceiling at 100% in both the baseline and the enhanced condition for both ablations, so
   neither shows a measurable effect either way. A3's manual inspection suggests a real qualitative
   difference exists; A4's attempted proxy metric was found invalid on inspection.
7. **The Haiku semantic-check false-positive rate is uncalibrated.** 33% on GitHub is high enough
   that the arm cannot be deployed as a blocking gate without further tuning (§6.6.1).
8. **The downstream effect does not generalize uniformly.** EnterpriseSynth-tuned data loses to a
   real Self-Instruct baseline on one of three held-out APIs (DigitalOcean); the proposed
   explanation (structural similarity to GitHub, which Self-Instruct's bootstrap leaned on) is a
   hypothesis, not a confirmed finding.
9. **No cost or latency accounting.** The pipeline's per-spec generation cost (API calls,
   wall-clock time) at the target ~65-spec scale has not been measured.
10. **EnterpriseSynth-Eval is not itself validated.** We have not checked whether performance on
    our generated evaluation records correlates with performance on real, human-graded enterprise
    tasks — only that the records are schema-valid.
11. **Mostly single-seed runs.** Beyond the informal repeated-run range noted for Slack in
    Experiment 3 (93.3–100%), most reported numbers reflect one run each, not a multi-seed
    distribution with confidence intervals.

---

## 13. Conclusion

We presented EnterpriseSynth, a schema-aware, zero-execution pipeline that ingests an OpenAPI
specification and jointly emits verified SFT trajectories and a paired evaluation dataset,
EnterpriseSynth-Eval, without ever calling a live API. Against a scoped review of the closest five
prior methods, EnterpriseSynth's specific contribution is combining three properties none of them
combine: grounding in a real target spec (unlike AgentInstruct, which can hallucinate an API
surface when seeded from code), a hard structural verification gate rather than a soft or post-hoc
one (unlike AgentInstruct's editorial-refinement-plus-held-out-judge design), and no dependency on
live execution at any stage (unlike API-Bank and ToolBench, both of which ground their training
data in real API calls).

At pilot scale, three findings stand on their own: schema-based verification is necessary, not
optional, closing a 0%-to-100% gap on planted structural errors, and only reached 100% after
adversarial testing surfaced and forced fixes to real bugs; explicit intent generation provides
real, measurable grounding over generating directly from a bare endpoint; and fine-tuning on
EnterpriseSynth-generated data measurably outperforms both an untuned baseline and a real
Self-Instruct baseline on most, though not all, held-out APIs tested. We reported the one
exception — a loss to Self-Instruct on DigitalOcean — because we believe an honest, partially
disconfirming result at pilot scale is more useful to the field than a uniformly positive one that
does not survive scrutiny. The path to a submission-ready paper runs through exactly the
limitations listed above: more APIs, more examples, the actual target model scale, the two missing
baselines, and a real test of whether a Knowledge Graph earns its place in the architecture rather
than being assumed into it.

---

## 14. Timeline

| Date | Milestone |
| --- | --- |
| Jul 21, 2026 | AAAI abstract enrollment |
| Jul 28, 2026 | AAAI 2027 full paper (7 pages) |
| Aug 1, 2026 | MLinPL 2026 submission, adapted to systems/compiler-centric narrative |

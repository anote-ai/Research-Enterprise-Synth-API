# EnterpriseSynth — Research Design Document

**Paper title:** EnterpriseSynth: A Schema-Aware Agentic Framework for Generating Verified SFT and
Evaluation Datasets from OpenAPI Specifications
**Topic (T1b):** Agentic SFT + Eval Data from API Schemas Without Live Execution
**Author:** Rashmi Thimmaraju
**Target venues:** MLinPL 2026 (deadline Aug 1, 2026) · AAAI 2027 Workshop on Enterprise AI Evaluation (deadline Jul 28, 2026)

---

## ⚠ Open naming/positioning issue — resolve before drafting further

The paper draft names its evaluation suite **"EnterpriseBench."** That name is already taken:
**arXiv:2510.27287, "Can LLMs Help You at Work? A Sandbox for Evaluating LLM Agents in
Enterprise Environments" (Oct 2025)** ships a benchmark under the identical name (500 tasks,
SWE/HR/finance/admin, simulated enterprise sandbox with live task execution). Reviewers at the
AAAI Enterprise AI Evaluation workshop will very likely know this paper.

Two options, not mutually exclusive:

1. **Rename** our eval suite — candidates: `SpecEvalBench`, `EnterpriseColdBench`, `APISpecBench`.
2. **Reframe as complementary** and cite it directly: "Vishwakarma et al.'s EnterpriseBench
   (arXiv:2510.27287) evaluates agents against a simulated *live* enterprise sandbox; our benchmark
   evaluates whether spec-only-generated, intent-labeled eval records correlate with performance on
   such a sandbox, without requiring the sandbox to exist yet." This is a legitimate
   differentiation, but the name still needs to change to avoid being read as a duplicate
   submission.

Decision needed before Section 4 of the paper is finalized.

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

## 4. Methodology — Seven-Stage Pipeline

```
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
3. **5. Trajectory Generator** — produces the paired natural-language reasoning trace + tool calls
   + parameters + expected responses (the SFT trace) directly from the agentic plan.
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

These operationalize §1's conceptual RQs into testable ones for Section 6 of the paper:

- **RQ1 (schema-valid generation, operationalizes §1 RQ1):** Can EnterpriseSynth generate
  schema-valid SFT trajectories from OpenAPI specifications?
- **RQ2 (coverage vs. baselines):** Does EnterpriseSynth achieve broader endpoint and workflow
  coverage than prompt-only generation or instruction-generation baselines (Self-Instruct,
  AgentInstruct)?
- **RQ3 (verification value, operationalizes §1 RQ2):** Does schema-aware verification (Stage 6)
  improve the quality of generated trajectories over no verification, or over AgentInstruct-style
  soft/post-hoc verification?
- **RQ4 (downstream utility, operationalizes §1 RQ3):** Do models fine-tuned on
  EnterpriseSynth-generated data perform better on enterprise API-calling tasks than an untuned
  baseline?
- §1's RQ4 (cold-start generalization) is not a separate experimental RQ — it is the held-out-spec
  condition applied within RQ2 and RQ4 above (see §5.2 split protocol), not a fifth question.

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
- **Libraries:** Pydantic (schema modeling + Stage 6 validation), NetworkX (Stage 2 knowledge
  graph), `openapi-spec-validator`/PyYAML (Stage 1 parsing), Anthropic SDK (Stages 3–5 model
  calls). `FastAPI` is not needed — this is an offline batch pipeline, not a served API; add it
  only if a live-serving mode is wanted later.
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

## 6. Timeline

| Date | Milestone |
| --- | --- |
| Jul 21, 2026 | AAAI abstract enrollment |
| Jul 28, 2026 | AAAI 2027 full paper (7 pages) |
| Aug 1, 2026 | MLinPL 2026 submission, adapted to systems/compiler-centric narrative |

---

## 7. Open Items

- Resolve the EnterpriseBench naming collision (see flag at top).
- Verify per-spec licensing before redistributing any derived dataset built on APIs.guru/ToolBench
  sources.
- Confirm In-N-Out's released graph data isn't reusable outright for the Structural Graph Extractor
  before building a parser from scratch.
- Finalize which specs within each §5.2 category are actually sampled (plan only, not yet chosen).
- Confirm generation-pipeline model budget/access (§5.4 is a placeholder default).

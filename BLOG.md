# How I Built EnterpriseSynth: Generating AI Training Data from API Schemas Without Calling a Single API

Subtitle:
Building an agentic framework that converts OpenAPI specifications into verified Supervised Fine-Tuning (SFT) and evaluation datasets.

*Rashmi Thimmaraju · July 2026*

---

Every enterprise team that wants an LLM agent to reliably use their internal tools eventually hits
the same wall: you have an API — a schema, some documentation, maybe a handful of engineers who
know it by heart — but you have no tool-use training data for it, and no eval suite to tell you
whether an agent is any good at calling it. Every existing recipe for generating that kind of data
assumes you can safely call the API, over and over, to bootstrap a dataset from its real behavior.
Behind an enterprise firewall, you usually can't. The API is rate-limited, gated behind a VPN, or
simply too consequential — nobody wants to generate training examples by actually issuing refunds
against a production payments API, or creating and deleting real customer records in an HRIS.

We call this the **execution paradox**: the data you'd need to teach a model to use a tool well is
most valuable exactly where you're least able to generate it by using the tool. This post is about
**EnterpriseSynth**, a framework we built to get out of that bind — and about why the two obvious
ways around it both fall short.

---

## Two existing paths, and why neither works here

Look at how the field currently generates tool-use training data, and it splits cleanly into two
camps.

**Execution-based generation** grounds every example in a real API response. ToolLLM/ToolBench
does this by making hundreds of thousands of live calls against a pool of public APIs during data
collection; API-Bank stands up real, reproducibility-constrained databases behind its agents. This
produces data that's trustworthy precisely because it was checked against reality. But "checked
against reality" is the whole problem for an internal enterprise API: there usually isn't a safe
sandbox to check against. A live call against a production system risks corrupting real data,
tripping a security control, or simply not existing yet, because the team is trying to bootstrap
an agent *before* they have safe infrastructure to test one against.

**Execution-free generation** solves the sandbox problem by never calling anything — an LLM is
simply asked to imagine plausible tool calls. AgentInstruct is the clearest example: it's agentic
and multi-stage, but when it's seeded only from source code (as opposed to a real, documented API
description) it has nothing to check its own imagination against, and it *hallucinates the API
surface* — inventing endpoints, parameters, and behaviors that don't actually exist. Its quality
control is a soft editorial refinement pass plus a post-hoc judge scoring a held-out sample, not a
hard, per-example check that a given trace is actually valid against something real.

Neither path fits a team with a brand-new internal API: no traffic history to learn from, no
sandbox to execute against, and — critically — a real schema that a generation method *could*
ground itself in, if only it treated that schema as the source of truth instead of either ignoring
it (execution-free) or requiring it to be exercised live (execution-based).

---

## The idea: ground in the spec, verify without executing

EnterpriseSynth's core move is to take the one artifact that's almost always available even for a
brand-new internal API — the OpenAPI/Swagger spec itself — and treat it as the *only* input the
whole pipeline needs. Nothing is invented from a code snippet, and nothing requires a live call.

Concretely, the pipeline runs in four stages:

**1. Parse the spec.** Read the OpenAPI/Swagger document and extract exactly what it declares:
endpoints, HTTP methods, required and optional parameters, parameter types, authentication
requirements, and response schemas. This is the ground truth everything downstream is checked
against — there's nothing to hallucinate here because there's nothing left to invent.

**2. Generate realistic intents.** For a given endpoint, synthesize the kind of natural-language
request an actual employee might type — not a templated rephrasing of the endpoint's description,
but a business scenario with the texture of a real ask. A tag-protection endpoint on a repo API,
for instance, doesn't just get "protect tags matching a pattern" — it gets something closer to
*"lock down tag creation on the acme-api repository so our CI pipeline can't be tampered with,
please add protection for anything prefixed with 'release-'."*

**3. Generate the trajectory.** Given an intent and a set of candidate endpoints — the real target
plus a batch of distractors — produce the full reasoning trace: which endpoint to call, why,
what arguments to extract from the free-text request and where they go, and what the response
should plausibly look like. This is the step that turns an intent into something a model could
actually be trained on: a decision, made and justified, not just a label.

**4. Verify, deterministically.** Every generated trajectory is checked against the parsed spec
itself, offline, with no LLM in the loop: does the endpoint exist, is the HTTP method correct, are
all required parameters present with the right types, does the response match the declared schema.
This is the step that replaces execution as the correctness signal. Where an LLM judge can be
talked into accepting something plausible-sounding, a structural check against the spec either
passes or it doesn't.

The output of all four stages is two paired artifacts: a verified SFT training set, and an
evaluation set built from the same generation pass — so the eval questions are guaranteed to be
about the same API surface the model was trained on, not a separately curated set that may or may
not line up.

---

## Why the verification stage is the one that matters most

It's tempting to think of the schema verifier as a cleanup step — a final sanity check after the
interesting work is already done. In practice it's closer to the opposite: it's the piece that
makes the whole approach trustworthy in the first place.

Self-Instruct and Evol-Instruct/WizardLM filter their generated data with text-level heuristics —
similarity scores, keyword rules, degeneracy checks. Those work reasonably well for open-ended
instruction data, but they have no concept of a "tool call" at all, let alone whether one is
structurally valid. AgentInstruct goes further by having an LLM look over what it generated, but
that's still a soft, holistic judgment — closer to a second opinion than a gate. None of these give
you a hard guarantee that a generated example, if you actually tried to execute it, would be a
legal call against the real API.

A deterministic, spec-derived verifier gives you exactly that guarantee, offline, without ever
touching the live system. It's also the piece of the pipeline most worth being paranoid about:
a verifier that only ever sees the "good" examples the rest of the pipeline generates will happily
develop blind spots you never notice, because nothing in that workflow ever asks it to prove it can
catch something bad. The methodological lesson that's outlived every specific number we've measured
is that a static verifier has to be tested against deliberately broken input, not just trusted
because it accepts good input — otherwise you find out about its blind spots only when a bad
example makes it all the way downstream.

---

## What this is, and isn't

EnterpriseSynth is deliberately narrower than its own long-term target design. The pipeline above —
Parser → Intent Agent → Trajectory Agent → Verifier — is what's actually built. A fuller target
architecture exists on paper: a Knowledge Graph stage that would model dependencies *between*
endpoints (so a multi-step workflow like "create a customer, then charge them" could be represented
as a graph traversal rather than a single call), and a Planning stage that would decompose a
complex intent into an ordered sequence of tool calls. Neither of those exists in the current
implementation. Every trajectory EnterpriseSynth generates today is a single endpoint call, and we
say so plainly rather than letting the target architecture read as a description of what's already
built.

That distinction matters more than it might seem. The entire pitch of this approach is that it
replaces a soft, aspirational notion of correctness with a hard one — grounded in a real spec,
checked by a real deterministic gate. Overstating what's implemented would undercut the one thing
this project is actually trying to demonstrate.

---

## Who this is for

If your team has an internal API with a schema but no safe way to generate tool-use training data
for it — no sandbox, no traffic history, no existing SFT or eval set — this is the gap
EnterpriseSynth is built to close. The bet is that grounding in a real spec plus a hard structural
verification gate gets you most of the trustworthiness that execution-based methods provide,
without ever needing the execution.

---

*Full design, related-work comparison, and implementation details: `DESIGN_DOC.md` and
`paper/main.tex` in the repository. Questions and issues welcome via GitHub.*

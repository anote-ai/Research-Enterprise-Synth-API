# How I Built EnterpriseSynth: Generating AI Training Data from API Schemas Without Calling a Single API

Subtitle:
Building an agentic framework that converts OpenAPI specifications into verified Supervised Fine-Tuning (SFT) and evaluation datasets.

*Rashmi Thimmaraju · July 2026*

---

When people think about AI agents, they usually picture impressive demos: an assistant booking flights, debugging code, or orchestrating complex workflows across enterprise systems. Over the last two years, we've seen an explosion of frameworks such as LangChain, LangGraph, AutoGen, CrewAI, and MCP-based tool ecosystems. Large language models are becoming remarkably good at deciding when to call a tool and how to reason through multi-step tasks.

But while experimenting with enterprise APIs, I kept running into the same question:

Where does the training data for these API agents actually come from?

If you want an AI agent to interact with GitHub, Stripe, Slack, Kubernetes, or an internal company API, you need examples of correct behavior. Not just documentation, but demonstrations of how a user request maps to API calls, parameters, and expected outcomes.

Most organizations don't have those datasets.

What they do have is something else: OpenAPI (Swagger) specifications. These specifications describe endpoints, methods, parameters, authentication, and schemas in a structured format. They are excellent for developers—but they are not directly usable as supervised training data for AI models.

At that point, I realized I wasn't trying to solve an inference problem. I was trying to solve a data generation problem.

That realization became the starting point for EnterpriseSynth.
We call this the **execution paradox**: the data you'd need to teach a model to use a tool well is
most valuable exactly where you're least able to generate it by using the tool. This post is about
**EnterpriseSynth**, a framework we built to get out of that bind — and about why the two obvious
ways around it both fall short.

---

## Two existing paths, and why neither works here

Before writing a single line of code, I spent time reviewing the existing ecosystem.

Most approaches fell into one of four categories.

The first relied on manual annotation. Human annotators wrote thousands of examples where a user request was paired with the correct API calls. While effective, this approach is expensive, slow, and difficult to scale across hundreds of APIs.

The second category depended on live API execution. Systems generated API interactions by actually invoking production or staging endpoints. Although this produced realistic examples, it introduced new problems: API keys, rate limits, network failures, changing backend behavior, and privacy concerns.

A third category used production logs. This is attractive because the data already exists, but it raises serious issues around customer privacy, compliance, and the availability of representative data—especially for organizations just beginning to build AI agents.

Finally, some projects generated synthetic examples directly with an LLM. While promising, many of these systems lacked any mechanism to verify that the generated API calls actually matched the API specification.

Looking across all these approaches, I noticed something surprising.

Every enterprise already owns a rich source of structured information—the OpenAPI specification—but very few systems treat it as the foundation for dataset generation.

That observation shaped the direction of the project.
One afternoon, while reading through a GitHub OpenAPI specification, I realized that nearly everything required to generate realistic training examples was already present.

The schema told me:

what operations existed,
what parameters they required,
what authentication was needed,
how requests were structured,
and what responses looked like.

Instead of asking:

"How can I execute this API?"

I started asking:

"Can the schema itself teach an AI how to use the API?"

That small shift completely changed the architecture.

Rather than depending on runtime behavior, EnterpriseSynth would work entirely offline. It would read the API specification, generate realistic user intents, synthesize agent trajectories, verify every generated API call against the schema, and finally produce both supervised fine-tuning data and evaluation records.

The goal wasn't to simulate the backend. It was to capture the structure and semantics of interacting with the API.

At that point, the architecture almost designed itself.

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




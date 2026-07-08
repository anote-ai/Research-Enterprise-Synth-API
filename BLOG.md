## The API That Had No Stories to Tell

Rashmi Thimmaraju


There's a moment that happens inside almost every company building an AI agent, and it usually goes unnoticed the first time.

Someone opens the internal wiki, finds the API documentation for the company's order system, or ticketing system, or CRM, and thinks: great, we have an OpenAPI spec, the agent can just learn from this.

It can't.

Not directly. And the reason why is the whole story.


## Part One: Why This Happens

An OpenAPI spec is a beautifully precise document. It says exactly which endpoints exist, exactly which parameters they take, exactly what they return. A machine can validate against it. A human engineer can read it and build a client library in an afternoon.

But a language model doesn't learn "how to use a tool" from a schema. It learns from examples of use — a person asking for something, and an agent figuring out which tool to call, with which arguments, to satisfy that ask. The schema tells you what's possible. It never tells you what people actually ask for, or how an agent should reason its way from a request to a correct call.

So every team that wants to fine-tune or evaluate a tool-using agent runs into the same wall: they have the spec, and they have nothing else. No training data. No evaluation set. Nothing that looks like:

User: Create a premium customer account for someone named Priya.

Agent:
→ recognize this needs POST /customers
→ fill parameters: name="Priya", plan="premium"
→ verify against schema
→ return customer_id

The traditional fix is to generate that kind of data by actually using the API — calling it thousands of times, logging what happens, and turning those logs into training examples. That's exactly what tools like ToolLLM do: hundreds of thousands of real calls against live APIs, annotated into trajectories.

It works. It also has a precondition almost no enterprise can meet: you have to be willing to hit the live API thousands of times.

For a public weather API, sure. For your company's internal payments system, or your HR platform, or a ticketing tool wired into production customer data? Nobody signs off on "let's fire ten thousand test calls against the refund endpoint to build a training set." The API is rate-limited, gated behind a VPN, or simply too consequential to poke at that many times.

I started calling this the enterprise cold-start problem: the data you need to teach a model to use a tool well is most valuable exactly where you're least able to safely generate it by using the tool.

That's the "why." Now the "how."


## Part Two: Building a Way Around It

The question I kept coming back to was simple to state and hard to actually trust an answer to: can you get real grounding — real, schema-accurate examples — without ever calling the live API?

The idea I landed on: stop treating the OpenAPI spec as documentation, and start treating it as a source of structured knowledge you can generate from, offline, with no execution at all.

That became a four-stage pipeline:



No live API. No credentials required at generation time. Every step happens against the spec alone.

The parser: the part I assumed was "done" and wasn't

I figured the parsing stage would be the boring, solved part — just read some JSON. It wasn't boring, and it wasn't solved.

Early versions of the parser silently dropped any parameter defined through a $ref pointer rather than written inline in the endpoint definition. That sounds like a minor edge case until you check what it actually costs: GitHub's real OpenAPI spec has 1,721 required parameters once every $ref is properly resolved. My parser was only seeing 67 of them. The foundation the entire rest of the pipeline stood on was almost blind.

Once fixed, the parser could actually extract every endpoint, method, required field, and schema — the structured knowledge every later stage needed to reason over.

Teaching the system to think like a person, not an API

The next insight was less about code and more about how people actually talk. Most synthetic tool-use datasets I looked at start with the API call itself — POST /customers — as the starting point of the example. But nobody thinks that way. A person thinks: "set this customer up as premium," not "POST to slash customers."

So I made intent generation its own explicit step, before any tool call gets generated. Given an endpoint, the system first imagines a realistic request a human would make of it — and only then generates the reasoning and call that satisfies that request.

When I later stripped this step out as a test — generating trajectories straight from the bare endpoint instead — the quality measurably dropped. The intent step wasn't decoration. It was load-bearing.

The part that turned out to be the actual hard problem

I expected generation to be the difficult stage. It wasn't. Verification was.

Language models generating tool calls will, with some regularity, invent endpoints that don't exist, hallucinate parameters, or get a type wrong — a string where an integer belongs, a required field silently dropped. If those slip into a training set, the model learns confidently wrong behavior, and you won't necessarily notice until it's already deployed.

So I built a verification engine: every generated trajectory gets checked against the real OpenAPI schema — types, required fields, structure — and rejected if anything doesn't match.

Here's the part of the process I'm most glad I didn't skip: I didn't just build the verifier and assume it worked. I tested it adversarially — deliberately planted known errors into trajectories (wrong types, missing required fields, invalid values) and measured whether the verifier actually caught them, rather than trusting that it would.

First run: it caught 57–80% of planted errors. Not the 100% I'd assumed going in.

Digging into why surfaced three more real bugs on top of the parser issue: the verifier was accepting any value at all for fields typed as "string", including entire objects; parameters defined inside a POST request's body — which is most of Stripe's API — weren't being parsed into typed fields at all, so they were invisible to checking; and my own adversarial test harness had a bug that let it sometimes corrupt an optional field instead of a required one, quietly undertesting its own claim.

Fixed all four, retested, and the verifier's detection rate on planted errors went from 0% to 100%.

The lesson generalizes past this one codebase: you cannot establish that a checker works by feeding it good input and watching it pass. You have to feed it input specifically designed to break it, and watch it catch the break — otherwise the first time you find out it's broken is when it already mattered.


## Part Three: Proving It Actually Solves the Problem

Building a pipeline is one thing. Proving it solves the cold-start problem specifically is another — and this is where I almost let myself off easy.

Every API I'd tested against so far — GitHub, Stripe, Slack, and later Zoom, DigitalOcean, and Spotify as held-out evaluation targets — is real, popular, and very likely already represented somewhere in a language model's pretraining data. A model doing well on "a held-out API" like Zoom might just be quietly leaning on the fact that it already half-knows Zoom's API from documentation it saw during pretraining. That would prove the pipeline works on famous APIs. It says nothing about whether it works on the kind of API this whole project exists for: a company's private, undocumented, internal system that no model has ever seen.

So I hand-authored five API specs that don't exist publicly anywhere — a fake CRM, an HR system, a procurement tool, a ticketing system, an asset registry — generic, plausible shapes, not copied from any real company. Then I ran the exact same pipeline against them, completely unmodified.

The result held: accuracy on these never-published APIs (40.0%) essentially matched accuracy on the public held-out ones (39.6%). No meaningful drop-off going from "public API the model might half-know" to "API that has never existed anywhere before." That's the closest thing I have to real evidence that the improvement comes from genuine schema-grounding, not from the model quietly recognizing something familiar.

I also caught a real, honest failure along the way and chose to keep it in the writeup rather than bury it: fine-tuned on my pipeline's data, the model actually lost to a real Self-Instruct baseline on one held-out API — DigitalOcean — in the first single run. Rather than drop DigitalOcean from the comparison, I reran the whole thing five times across different random seeds. Across the five runs, my pipeline won on average, including on DigitalOcean — but the variance was genuinely large enough that individual seeds could still lose. Both things are true, and I reported both.

I went a step further and asked an independent model to judge whether "correct" tool calls were actually usable — checking not just whether the right endpoint was picked, but whether the arguments were right, complete, and sensible. The uncomfortable finding: a real share of predictions marked "correct" by the simple accuracy metric still had a genuine defect, usually a missing or hallucinated parameter. My headline accuracy numbers overstate practical usability — so I'm reporting that overstatement explicitly, rather than letting the flattering number stand unchallenged.


## Part Four: What "Solved" Actually Means Here — And What's Still Open

I want to be precise about what I'm actually claiming, because the honest version is more useful than the impressive-sounding one.

What this pipeline demonstrates: it's possible to generate schema-grounded, verified SFT and evaluation data directly from an OpenAPI spec, with zero live execution — and fine-tuning on that data measurably improves tool-selection performance on APIs the model has never seen, including ones that don't exist publicly anywhere. That's a real answer to "can you get grounding without execution."

What it doesn't yet prove: this is pilot-scale work — a handful of APIs, tens of examples, a small stand-in model rather than the larger ones this would eventually target. Two baselines I planned to compare against (ToolBench, a plain prompt-only agent) aren't built yet. Multi-step, dependency-aware workflows — the "create a customer, get their ID, then create an invoice for them" kind of task — are entirely untested; the pipeline as it stands handles single tool calls, not chains of them. The private cold-start test is a single run on five hand-built specs, not yet the larger, repeated, stratified test it deserves.

The way forward, as I see it, isn't to inflate the current results to sound more finished than they are. It's the opposite: keep the verification discipline that already found four real bugs and one overstated metric, and point it at the next set of gaps — the missing baselines, the untested multi-step case, the model-scale question — one at a time, the same way the first four bugs got found. Every honest limitation in this project so far turned into either a fix or a clearly labeled open question. That pattern is the actual method here, more than any single number in a results table.


## The Short Version

An OpenAPI spec is structured knowledge, not just documentation — and if you're careful enough to verify every single thing you generate from it, adversarially and repeatedly, you can turn that structure into real training and evaluation data for AI agents without ever touching a live system.

The problem is real. The fix is real, and partial. And the only way I know to make the partial parts less partial is to keep testing the pipeline exactly as hard as I tested the verifier the first time it lied to me about being finished.

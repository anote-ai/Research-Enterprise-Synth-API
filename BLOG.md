## The API That Had No Stories to Tell

Rashmi Thimmaraju


There's a moment that happens inside almost every company building an AI agent, and it usually goes unnoticed the first time.

Someone opens the internal wiki, finds the API documentation for the company's order system, or ticketing system, or CRM, and thinks: great, we have an OpenAPI spec, the agent can just learn from this.

It can't.

Not directly. And the reason why is the whole story.


There’s a quiet, frustrating moment that happens inside almost every company building an AI agent, and it usually goes unnoticed the first time. Someone opens the internal wiki, finds the API documentation for the company’s billing system, ticketing tool, or CRM, and thinks: “Great, we have an OpenAPI spec. The agent can just learn from this.”

It can’t. Not directly. And the reason why is the whole story.

An OpenAPI spec is a beautifully precise document. It says exactly which endpoints exist, exactly which parameters they take, and exactly what they return. A machine can validate against it, and a human engineer can read it to build a client library in an afternoon. But a language model doesn’t learn how to use a tool from a static schema. It learns from stories—examples of actual use. It needs to see a human asking for something, and an agent figuring out which tool to call, with which arguments, to satisfy that ask. The schema tells you what is possible. It never tells you what people actually ask for, or how an agent should reason its way from a chaotic user request to a flawless JSON payload.

So every team that wants to fine-tune or evaluate a tool-using agent runs into the same wall: they have the spec, and they have absolutely nothing else. No training data. No evaluation set.

The traditional fix is to generate this data by running live simulations—calling the API thousands of times, logging what happens, and turning those logs into training examples. That works fine if you are building an agent for a public weather API. But for your company's internal payments system, or an HR platform wired into production data? Nobody signs off on letting an unhinged LLM fire ten thousand test calls against a live refund endpoint just to build a training set. The API is rate-limited, gated behind a secure VPN, or simply too consequential to poke at. This is the enterprise cold-start problem: the data you need to teach a model to use a tool safely is most valuable exactly where you are least able to safely generate it.

The way around this bottleneck is a shift in perspective: stop treating an OpenAPI spec as mere passive documentation, and start treating it as a generative source of structured truth. That is the core philosophy behind EnterpriseSynth. It is a framework designed to build flawless Supervised Fine-Tuning (SFT) and evaluation trajectories entirely offline, with zero live API execution and zero credentials required.

The journey starts with parsing, which you would think is the boring, solved part of software engineering. It isn’t. Early iterations of the pipeline silently dropped parameters defined through $ref pointers rather than written inline. That sounds like a minor bug until you look at the scale: GitHub’s real OpenAPI spec has 1,721 required parameters once every reference is properly resolved, but a naive parser only sees 67 of them. By fixing the parser to recursively resolve these references, the system builds a foundation that isn't blind to enterprise complexity.

Next comes teaching the system to think like a person. Most synthetic tool-use datasets start with the API call itself (POST /customers) and work backward. But humans don't think in endpoints; they think in intents. They say: "Set this customer up as a premium user." Because of this, EnterpriseSynth uses an explicit intent generation step. Before a single tool call is drafted, the system analyzes the endpoint and imagines a realistic, nuanced human request. Stripping this step out causes data quality to crater; human intent isn't decoration—it is load-bearing.

Generating the tool calls themselves is relatively easy for modern models, but verifying them is where the illusion usually breaks. Models regularly hallucinate parameters, invent endpoints, or swap types—like passing a string where an integer belongs. If those slip into your training set, the model confidently learns broken behavior.

To solve this, EnterpriseSynth passes every generated trajectory through a rigid offline verification engine that checks types, required fields, and structures against the original schema. But you cannot trust a checker just because it passes good input. To prove it worked, the verifier was tested adversarially by deliberately planting errors like wrong types and missing fields into the synthetic data. On the first run, the verifier caught only a fraction of the errors because nested body payloads were slipping through unchecked. Once patched, the adversarial detection rate hit a perfect 100%. You simply don't know a verification tool works until you actively try to break it and watch it catch the fracture.

Testing this pipeline against famous public APIs like GitHub, Slack, or Stripe introduces another bias: the underlying LLM has likely already memorized their documentation from its public pretraining data. To prove this system could solve the cold-start problem for a company’s private, proprietary tools, it had to be tested on things that don't exist.

Five entirely fictional API specs were hand-authored—a unique CRM, an HR system, a procurement tool, a ticketing system, and an asset registry—none of which had ever been published on the internet. When the pipeline was run against them, the model's accuracy on these invisible APIs perfectly matched its performance on the public ones. The stability of the results proved that the model was leaning on genuine, real-time schema grounding, not quietly cheating from its training memory.

There are still open frontiers, of course. While this approach excels at single-turn tool selection, the next challenge is mapping out multi-step, dependency-aware workflows—the complex chains where an agent must create a customer, extract the returned ID, and then generate an invoice against that specific ID.

But what this journey demonstrates is that an OpenAPI spec is structured knowledge, not just documentation. If you are rigorous enough to parse it deeply and verify your generation adversarially, you can transform that static structure into a rich library of training stories. You don't need a dangerous, live, spinning sandbox to teach an AI how to work. You just need to listen to what the schema is already trying to tell you.


## The Short Version

An OpenAPI spec is structured knowledge, not just documentation — and if you're careful enough to verify every single thing you generate from it, adversarially and repeatedly, you can turn that structure into real training and evaluation data for AI agents without ever touching a live system.

The problem is real. The fix is real, and partial. And the only way I know to make the partial parts less partial is to keep testing the pipeline exactly as hard as I tested the verifier the first time it lied to me about being finished.

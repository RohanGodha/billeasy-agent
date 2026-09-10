# Counter Copilot - the write-up

*Rohan Godha · for Billeasy · September 2026*

---

## 0. The short version

Your brief said *"build anything - we want to understand how you work with AI."* The wrong
response to an open brief is a careful small demo whose abstractions are asserted, not
tested. So I built a *wide* one in a day - and gave its claims somewhere to genuinely fail.

**Counter Copilot** tells an Area Partner Manager which of their 500 offline counters is
leaking money right now, why, and what to say to the supervisor - with a compliance
validator standing between the model and the merchant.

Retail POS outlets. Ferry jetties. Bus depots. Metro ticket counters. Your actual business.

The experiment wasn't whether I could write an agent; it was whether a **written domain
contract plus seven coding agents running in parallel** can produce something coherent
enough to ship in a day - and where that breaks. The honest answer: the method held, and
where it broke it broke *informatively*. More on that in §4 and §5, including the part where
I was wrong.

---

## 1. What I built, and why this

### The problem

Billeasy runs a payment and ticketing rail across offline counters - retail billing and
government mass transit. Money enters the system at the physical edge: a passenger buys a
ferry ticket, a shopper pays at a kirana counter. Billeasy captures it, issues a compliant
digital bill or e-ticket, and settles T+1 to the merchant or the transit authority.

The edge is where it breaks:

| What goes wrong | What it looks like in the data |
| --- | --- |
| **Fare leakage** - cash quietly bypassing the digital rail | cash share climbing, digital share collapsing |
| **Void-and-reissue fraud** - issue a ticket, void it, pocket the cash, reissue | void/reissue rate spikes |
| **Settlement mismatch** - captured ≠ settled | mismatch rate drifts above tolerance |
| **Payout backlog** - merchant unpaid, quietly churning | pending settlement ages |
| **GST non-compliance** - past the threshold, still not issuing compliant bills | receipt issuance gap |
| **Peak-hour downtime** - device offline, fares unrecorded | downtime minutes during peak |

An Area Partner Manager owns 200-500 of these counters. Every morning they face one question:
**which counters, and what do I say?** Today that question gets answered by a dashboard nobody
reads and a gut feeling.

### Why this problem, specifically

I picked it for three reasons, and I want to be straight about all three.

1. **It's genuinely your business.** Not a generic "AI dashboard" that could be pitched to any
   company with a logo swap. Offline-to-online, retail POS *and* government mass transit,
   Indian payments compliance - that intersection is narrow, and it's where you live.
2. **It's fintech at the operational edge**, which is the hard part. Anyone can build a
   payments dashboard. Detecting that a jetty counter's cash share moved 22% → 61% and knowing
   that's either fraud, a broken device, or a supervisor working around a queue - that requires
   the system to reason, not just aggregate.
3. **It's big enough for the method to earn its keep.** The thing I wanted to demonstrate
   is contract-first swarming - and a small problem couldn't have shown it. An open brief
   rewards width, and this problem has it (8 modules, 3 scorers, 2 datasources, a routed
   LLM layer) for the method to fail visibly. See §0 and §3.

### What it does

An Area Partner Manager types, in plain language:

> *"Find ferry and bus counters in Mumbai leaking digital ticket revenue this month and draft
> WhatsApp nudges for the depot supervisors."*

And gets back, in seconds: a ranked list of counters, each with a **transparent score
breakdown** showing which signals fired and by how much, grounded citations from field-visit
notes, and a **compliance-validated WhatsApp draft** to the supervisor - where a validator
mechanically strips any number the source data doesn't support before a human ever sees it.

Human-in-the-loop by design. The agent drafts. The manager sends.

---

## 2. Which AI tools, and what each one actually did

I want to separate two things that get conflated: **AI that built the product**, and **AI that
is the product**. Both matter here, and they're different stories.

### 2a. AI that built the product

| Tool / model | Role |
| --- | --- |
| **Claude Code - Claude Opus 5 (1M context)** | Primary engineering surface. Ran as the orchestrator: shaped the domain model, wrote the contract, dispatched and reviewed the parallel agents, did the integration pass and the verification. |
| **Claude Code - Explore subagent** | A single read-only reconnaissance pass over the requirements and the intended file layout, before any code was written. Produced the file-path inventory (models, seeders, prompts, KB, tools, frontend copy, branding strings) that the whole plan was built on. |
| **Claude Code - 7 parallel subagents (Opus 5)** | The actual build. Seven disjoint slices - data layer, domain+scoring, tools, agent prompts, RAG corpus, frontend, API/config - executing concurrently against a shared written contract. |

Model choice was deliberate: Opus 5 with a 1M context window, because the coordination problem
here is *holding a whole codebase's worth of naming decisions consistent across seven
concurrent workers*. That's a context problem before it's a reasoning problem.

### 2b. AI that *is* the product

Counter Copilot has a provider-routed LLM layer - a `LLMClient` port with swappable adapters,
chosen by cognitive load rather than by hardcoding:

| Provider | Role in the running product |
| --- | --- |
| **Anthropic Claude** | Added during this build, specifically because your brief says *Preferred: Claude*. Slots into the router as another adapter - which was itself the test of whether the port abstraction was real. It was. See §4.2. |
| **Gemini 2.0 Flash** | Planner / Critic / Synthesizer - the structured-reasoning nodes, in JSON mode. |
| **Groq Llama 3.3 70B** | Parallel message generation - one call per candidate counter, fanned out with `asyncio.gather`. Chosen for latency, not intelligence. |
| **Deterministic mock** | Offline fallback. The entire agent runs with zero API keys, which is how you can review it without paying for anything. |

The routing rule is the interesting bit: **reasoning goes to the model with the best structured
output; generation goes to the fastest model; neither decision is hardcoded into a node.**

---

## 3. The method: a written contract, then a swarm

This is the part I'd actually want to talk about in a review, because it's the part I got wrong
first.

My instinct was to fan out seven agents immediately - "you take the frontend, you take the
scorers, go." I didn't, and the reason is worth stating: **parallel agents diverge.** If the
domain-model agent decides the field is `monthly_tpv` and the frontend agent independently
decides it's `monthlyGmv`, you don't find out at write time. You find out at integration time,
across forty files, and you've spent your speed advantage debugging a naming collision you
created yourself.

So the first artifact of this build isn't code. It's a **written domain contract** - a
single source of truth, written before any agent started, that pins down:

- every model class and **every field name**, character for character
- all 8 Billeasy modules with IDs, take rates, and eligibility thresholds
- the full scoring feature vocabulary (25 named features) and their weights
- every tool file and its registered name
- table and column names
- which files each agent owns, so two agents can never touch the same file

Then seven agents ran concurrently, each reading that contract, each in a disjoint file lane.

**The insight I'd generalise:** with a swarm of coding agents, the bottleneck isn't how well any
individual agent writes code - they're all good at that now. The bottleneck is *shared naming*.
Writing the contract took me about twenty minutes. It bought seven-way parallelism that actually
merged.

That's also, not coincidentally, exactly how the product works: the Planner emits a **typed
plan**, and the tool executor runs against it. Contract first, then parallel execution. I
orchestrated the build the same way the thing I was building orchestrates itself, which I
noticed somewhere around agent four and found slightly too cute to be an accident.

---

## 4. Where AI changed my mind

Three moments where the AI's output redirected the plan rather than just executing it.

### 4.1 The reconnaissance changed the size of the job

I went in assuming revenue-leakage detection would need bespoke machinery - that propensity
and leakage were different enough to warrant separate, purpose-written scorers.

The Explore pass came back with a better shape: one **generic explainable-scoring engine** -
a logistic combination over named features, weights in a YAML file, every feature returning
an explainable `ScoreBreakdown` with a contribution and a rationale - differentiated per
scorer only by feature vocabulary and weights.

So instead of three bespoke classifiers, three scorers share one engine. `digital_share_trend`,
`settlement_mismatch_rate`, `pending_settlement_age` are named features with weights, not
hardcoded logic. Retargeting the engine at Billeasy's leakage domain cost a feature swap and a
re-tune, not a rewrite - and re-tuning is a YAML edit, not a deploy.

That's a much smaller and much more honest change, and I only found it because I made the AI
inventory the requirements and the intended shape before I let it touch anything.

### 4.2 The brief said "Claude preferred" and the architecture had an answer

Your stack notes say *Preferred: Claude*. The router began life routed to Gemini and Groq,
no Anthropic. That could have been a rewrite.

It wasn't - because `LLMClient` is a port. Adding Claude meant writing one adapter against an
existing interface. I'm calling this out not because writing an adapter is impressive, but
because **it's the moment the hexagonal-architecture claim stopped being a README bullet and
paid for itself.** The abstraction was either real or it wasn't, and there was a cheap way to
find out.

### 4.3 Refusing to fake the demo data

The easy version of this build seeds five hero counters with hardcoded scores so the demo always
looks good. I explicitly instructed every agent that the seeded transactions must *genuinely
compute* to the signal being claimed - if Gateway Jetty is supposed to show a cash-share spike
from 22% to 61%, the actual transaction rows have to produce that number when the scorer runs.

This is slower and it's the difference between a demo and a system. It also means the hero
counters reach the top of the ranking **through real scoring**, so if you change the weights in
`weights.yaml`, the ranking changes - which is exactly the property you'd want to check if you
were trying to catch me faking it.

Please do check it.

---

## 5. What surprised me

### 5.1 The contract worked exactly as far as it extended, and not one inch further

This is the finding I'd defend in a review, because it was almost a controlled
experiment and I didn't design it that way.

**Where the contract reached, seven agents agreed perfectly.** The tools agent wrote
code calling `find_counters`, `get_field_notes_bulk`, `get_holdings_bulk`. The data-layer
agent - running concurrently, no communication - implemented exactly those names. They
merged with zero reconciliation.

**Where it didn't reach, they broke.** The chat request field - then just `query` - was
never in the contract; I hadn't thought about it. Mid-flight, the API agent decided to
rename the canonical name to `manager_query` (reasonable - the contract never named it,
so the name was the API agent's call). The frontend agent hit the
same field, reasoned that *the contract never renamed the chat request model, so
renaming it unilaterally would break the stream*, and deliberately kept sending `query`.

Both agents made a defensible call. Together they produced a broken app: the frontend
posting `query` to a backend that only accepts `manager_query`. Silent. The chat would
just arrive empty.

So the lesson isn't "parallel agents work." It's sharper than that: **parallel agents are
exactly as coordinated as the artifact you gave them, and their failures cluster precisely
in the gaps you didn't think about.** The contract wasn't a nice-to-have that made things
smoother - it was a hard boundary between "merged cleanly" and "silently broken."

That reframes the job. My value wasn't writing the code. It was *knowing what to write
down before anyone started*, and then hunting the gaps afterwards.

### 5.2 One agent reached across the boundary and fixed it itself

The postscript to the above: the prompts agent, which owned `state.py`, noticed that
`api/chat.py` had already landed using `manager_query`, and renamed `AgentState` to match
- unprompted. Its instructions said nothing about it.

I did not expect a subagent to detect a cross-slice inconsistency introduced by a sibling
after its own briefing was written, and repair it. That is a qualitatively different thing
from following instructions well.

### 5.3 The scoring bug I would have shipped

The heroes ranked correctly on leakage, so the demo *looked* right. But when I ran every
module against every hero, two were wrong: the bleeding ferry counter's top
recommendation was **Counter Analytics**, and the healthy retail counter's was too.

The cause was dull and instructive. `MOD-ANALYTICS` had four weights summing to 1.0 -
`tpv_above_10l`, `txn_velocity`, `tenure_long`, `no_existing_module_bonus` - every one
of which any large, tenured counter maxes out. So it scored ~0.92 for *everyone* and
beat reconciliation on a counter actively losing fares. `MOD-WA-RECEIPT` had the same
shape: its actual trigger, the receipt gap, was weighted equally against three free
points, so it won on counters with no receipt problem at all.

The fix was a real domain rule, not a fudge: **you don't sell a dashboard to a counter
that's bleeding - you fix the leak first.** Analytics now carries negative weights on
mismatch and cash-spike. And a module's own trigger signal has to dominate it.

What unsettles me is how close this came to shipping. The headline demo was correct.
The *reasoning underneath it* was wrong, and only a sweep of all 8 modules × 5 counters
exposed it.

### 5.4 Nobody owned realism, so nobody produced it

Every agent did its job. The dataset still came out quietly absurd: **"Kashmere Gate
ISBT"** - a Delhi terminal - sitting in **Kochi**, operated by **MSRTC**, Maharashtra's
undertaking. Sites, cities and operators were each drawn from a correct list,
independently.

I only caught it because the Mumbai query returned Delhi-sounding names and I assumed the
city filter was broken. It wasn't - the filter was fine, the *world* was broken. Same
class of bug produced two different counters both named "Kurla Depot - Counter 2", which
would have quietly broken the knowledge base's name resolution too.

Realism is a cross-cutting property. It doesn't belong to any one file, so a
file-ownership split can't produce it, and nobody's brief said "make the world make
sense." That's the orchestrator's job, and it's only findable by looking at output.

### 5.5 The AI wrote a correct test for the wrong window

`peak_hour_downtime` inferred an outage by finding days with off-peak sales but *zero*
peak-hour sales. Perfectly sensible code. It could not detect the exact scenario it was
written for: a depot counter that sells all morning and goes dark at 17:00, because the
morning sales mean the day isn't "dark."

A whole-day test cannot see a half-day outage. Now it evaluates per peak window, and only
judges windows the counter actually trades in - so a morning-only jetty isn't reported as
"down" every evening, because it's closed, which is not a leak.

### 5.6 Writing the docs from the code caught a bug I'd just introduced

For the supporting docs I gave one instruction that turned out to matter more than the
rest of the brief: **write these against the code, not against the README.**

It came back with four places where my README described something the code didn't do.
Three were wording (six intent routes, not five; the draft fanout is bounded by a
semaphore of 4, not unbounded; the keyless summary is a deterministic function, not a
model). The fourth was a live bug, and it was mine: `intent.py` gated its LLM classifier
on `gemini or groq`. I'd added Anthropic to the router an hour earlier and never touched
that gate - so a Claude-only deployment would have had Claude leading every reasoning
route while intent classification silently stayed on heuristics.

That's the failure mode of adding a provider to a system that names its providers in
more than one place. The fix is a generic check ("any non-mock provider is live") rather
than another hardcoded name, so the next provider doesn't reintroduce it.

The generalisable bit: **documentation generated from the code is a free consistency
check on the code**, but only if you explicitly forbid the generator from trusting the
existing docs. Point it at the README and it will faithfully launder your own errors
back to you.

I then ran the same trick deliberately on security - asked for a Security Considerations
section written from the source, with instructions to report anything it could not verify
rather than document it as true. It came back with three real issues:

1. `POST /auth/verify` was unthrottled. Constant-time comparison stops a timing attack
   and does nothing about someone guessing at network speed.
2. `allow_origins=settings.cors_origins or ["*"]` with `allow_credentials=True` - a
   combination the CORS spec forbids, sitting behind a fallback where one empty config
   value would have opened an authenticated API to every origin.
3. The token was still accepted as a `?token=` query parameter - a leftover for plain
   `EventSource`, which the shipped UI doesn't use. Query strings land in proxy logs.

All three are fixed, and there's now a `test_security.py` that fails if any of them
regress. The honest note is that I wrote the original code for all three, and the audit
that caught them cost one carefully-worded prompt. Asking for documentation is a
surprisingly cheap way to get a code review, provided you tell it to check rather than
describe.

### 5.7 The specs audited the code, and the guardrail turned out to be broken

Late on, I had four agents write the spec documents - `requirements.md`, `design.md`,
`decisions.md`, `testing.md` - each with the same standing instruction as before:
**write from the code, and report anything you cannot verify rather than documenting it
as true.**

They found five real defects. Two were embarrassing, and one was serious.

**The serious one: my headline safety control was a no-op in the case that matters.**
The testing agent noticed that `compliance.ok is True` - asserted eleven times across two
test files - is *vacuous*, because the deterministic mock writes drafts containing no
digits. The validator had nothing to ground, so it passed trivially. Eleven green
assertions were telling me nothing about the one control the whole product's safety story
rests on.

So I wrote a test that actually makes it fire: a draft inventing "₹9,87,654 stuck in
settlement". It failed. The validator **detected** the invented figure and **did not
remove it**. Numbers are normalised without separators when extracted (`9,87,654` →
`987654`), and the redaction then searched for that bare literal - which never matches the
punctuated text. Since a model writes rupee amounts with Indian digit grouping, this
covered essentially every hallucinated amount the validator existed to catch. It reported
the draft non-compliant while handing back a "redacted" message with the fabricated figure
still in it.

**The embarrassing one:** `device_offline_minutes`, the uptime telemetry I'd added hours
earlier and written a design decision about, never reached the scorer. The SQL selected
it; the `Counter` model didn't declare it; the model is configured `extra="ignore"`; the
column was dropped in transit. The downtime feature had been sitting on its weaker
inference fallback the whole time, reading `0.35` for a counter whose real signal is
`1.0`. My "first-class telemetry" decision was, in practice, a comment.

Also found: the UI re-sorted candidates by `composite_score`, silently discarding the
backend's `(priority, leakage, composite)` action queue - so the counter the summary told
you to call first was not the one at the top of the list. And the two-stage filter
relaxation was **silent**: ask about Kochi ferry counters, get the whole network, with no
indication the question had changed. All fixed; relaxation now reports which filters it
dropped and says so in plain language.

**Why I'm putting this in the write-up rather than quietly fixing it.** Every one of these
was my code. The pattern that caught them was not cleverness, it was a standing rule:
*generate documentation from the source, and require the generator to verify rather than
describe.* That turns doc-writing into a free audit. It found a broken guardrail that
seven passing tests had endorsed.

The uncomfortable corollary is the one I'd want a reviewer to sit with: **a green test
suite told me the safety control worked, and it was wrong.** Tests assert what you thought
to assert. The compliance suite now includes a case that fails if the validator ever stops
actually removing an invented number, because "it returned `ok: False`" was never the
property that mattered - "the merchant does not see the fabricated figure" was.

---

## 6. What's weak, honestly

If you only read one section to decide whether I'm worth hiring, I'd rather it were this
one than §5.

- **I did not visually verify the UI.** Types check, the production build succeeds, the
  dev server serves, and I exercised every API payload the components consume over HTTP.
  But I had no browser automation in this environment and took no screenshot. I am not
  going to tell you the UI works when what I verified is that it *compiles and is fed
  correct data*.

- **I tuned weights until the heroes ranked correctly, which is overfitting to five
  examples.** I believe the two changes were principled - both fixed modules that won on
  free points rather than on their own trigger - and I'd make the same argument to a
  product person. But the honest framing is: n=5, and the person who chose the fix also
  chose the test. Real validation needs labelled leakage outcomes, which don't exist here.

- **There are no ground-truth labels at all.** Every weight is domain judgement.
  Transparent and tunable, but judgement. The right next step is a trained model behind
  the same interface, A/B'd against this - not more hand-tuning.

- **Retrieval is weaker than it looks.** Chroma exceeds Render's free-tier memory, so the
  default is BM25-only. Ask "how does NCMC work at an AFC gate?" and you can land in the
  chargebacks FAQ. It cites honestly; it just retrieves imperfectly.

- **The mock LLM flatters the planner.** Keyless runs use canned plans, so a reviewer
  sees perfect planning that reflects my few-shot prompt, not live model behaviour. Plan
  quality under a real model is where I'd spend the next day building evals.

- **The data is synthetic**, modelled on real Indian transit and retail but invented. No
  Billeasy data was used or needed.

- **Single-tenant, shared-password auth.** Demo-grade, and I haven't pretended otherwise
  anywhere in the code.

One deliberate non-fix: leakage risk is **prioritisation, not accusation**. A high score
means *go look*, not *this supervisor is stealing*. Several signals have innocent
explanations - a broken printer, a festival cash surge. I kept every string in the
product reading "call the supervisor" rather than "fraud detected", because a tool that
quietly accuses transit staff on heuristic evidence is a tool that gets someone fired for
a printer fault. That constraint cost nothing and I'd argue for it in a design review.

---

## 7. What this says about how I work

I use AI as an **orchestration layer over my own judgment**, not as a code vending machine.

The judgment calls in this build - pick revenue assurance over another dashboard; size the
build so the abstraction claims have to prove themselves; write a contract before spawning
the swarm; refuse to fake the seed data; add a Claude adapter because the brief asked and the
port made it cheap - those were mine. The typing was mostly not.

I think that's the actual skill now. Not prompt tricks. Knowing **what to build, what to verify,
and where the AI will confidently hand you something plausible and wrong** - and putting a
contract, a validator, or a test in front of exactly those places.

The compliance validator in this product is the same idea pointed at the product's own LLM: it
assumes the model will eventually invent a number, and mechanically refuses to let that number
reach a merchant. I built the product's guardrails out of the same instinct I used to build the
product.

---

*Setup, architecture, and the full technical breakdown are in [`README.md`](README.md).
The decision log behind the build is in [`docs/decisions.md`](docs/decisions.md).
The coordination artifact itself - the written domain contract the agents worked from - was a
build-time tool, not documentation written after the fact.*

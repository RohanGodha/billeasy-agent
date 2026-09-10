# Assignment Review - talking notes

*Counter Copilot · Rohan Godha · for Billeasy*

Prep notes for the review conversation. Answers in my own words, with the honest
version of each - including where I'd push back on my own choices.

**The 60-second version:**

> Billeasy's money enters at the physical edge - a ferry jetty, a bus depot, a kirana
> counter. That edge is where it leaks: cash bypassing the digital rail, tickets voided
> and reissued, settlements that don't reconcile, terminals dark during the rush. An
> Area Partner Manager owns 200-500 of those counters and has to decide every morning
> which ones to chase. Counter Copilot answers that in plain language, shows exactly why
> each counter is flagged, and drafts the message - with a validator that stops the model
> inventing a number before it reaches a merchant.

---

## 1. Product

**Why this problem?**
Because it's the one that only exists at Billeasy's specific intersection: offline
payments *and* government mass transit. A generic payments dashboard could be sold to
anyone. Detecting that a jetty counter's cash share moved 22% → 61% and knowing that's
either fraud, a broken device, or a supervisor working around a queue - that requires
domain reasoning, and it's worthless outside this business.

**Who has it?**
The Area Partner Manager. Not the CTO, not the merchant - the person who owns a
territory of counters and whose week is spent deciding where to drive.

**Why does it matter commercially?**
Leakage is direct revenue loss on a take-rate business: money that never enters the rail
is never monetised, and for a transit authority it's a government revenue-share
shortfall. Separately, a merchant with an ageing payout backlog churns quietly. Both are
invisible in an aggregate dashboard.

**Measurable benefit - and the honest framing.**
I have *not* measured a time saving, and I'm not going to claim one. What I can defend
is the mechanism: today, counters get attention when they complain. This flags counters
by **transaction evidence**, so it surfaces the silent leaker a ticket queue
structurally cannot find. The metric I'd instrument first is *what fraction of flagged
counters turn out to be real on a field visit* - precision at the top of the queue.

**Why not a dashboard?**
A dashboard answers "what happened." The manager's question is "who do I call and what
do I say." That last mile - ranking, explaining, drafting - is the whole product.

---

## 2. Architecture

**Why this shape?**
Planner → Tool Executor → Critic → Synthesizer → Message Generator → Responder, over a
hexagonal core with `DataSource` and `LLMClient` ports.

The pipeline is a DAG rather than a free-running ReAct loop deliberately: in a regulated
money workflow I want the plan to be a **typed artifact I can inspect, log and replay**,
not an emergent trace. Every run is reconstructable from `/trace/{session_id}`.

**Why FastAPI?**
Async-native, which matters because the hot path is I/O-bound fanout - parallel scoring
and parallel draft generation via `asyncio.gather`. Pydantic gives typed validation at
every tool boundary for free, and that same type information becomes the tool schema the
LLM plans against. One type definition, three jobs.

**Why React + Vite (not Next)?**
There's no SEO surface and no server-rendering need - it's an authenticated internal
tool. Next would add a server runtime I'd have to deploy and pay for. Vite gives a static
bundle on a CDN and a dev loop measured in milliseconds.

**Why SQLite + Databricks rather than PostgreSQL?**
This is the choice I'd expect to be challenged on, and it's deliberate.

Postgres is the right answer for a production multi-tenant deployment, and I'd use it.
For this build I wanted to demonstrate something Postgres alone wouldn't: a **hexagonal
data port with a real failover path**. Databricks Delta is the primary (transaction
volumes at this scale are a warehouse problem, not an OLTP one); SQLite WAL is the
failover; every tool result is tagged with which one actually served it, and a 60s
circuit breaker stops a dead warehouse taking the app down.

The secondary reason is reviewability: SQLite means you can clone this repo and have a
seeded 500-counter network running in one command with no database to provision. That
was worth more for a take-home than the correctness Postgres would have added.

**Why this agent architecture rather than one big prompt?**
Three reasons. Separation of concerns - the planner is optimised for structured output,
the drafter for latency, and they route to different models. Verifiability - the critic
is a distinct node that can reject a tool result and force a replan. And cost - a single
mega-prompt would burn reasoning tokens on message generation, which doesn't need them.

**Why not something simpler?**
For a fixed report, a SQL query and a cron job would genuinely be better, and I'd say so.
The agent earns its complexity only because the manager's questions are open-ended:
"leaking revenue", "crossed the GST threshold", "settlement mismatch above 2%", "now only
Kochi, and firmer". You cannot pre-build that surface as fixed reports.

---

## 3. AI

**Why does this workflow actually need AI?**
Two places, and only two:
1. **Intent → structured plan.** Turning "find ferry counters leaking revenue this month
   and nudge the supervisors" into typed filters, a target module, and a tool sequence.
2. **Grounded natural-language drafting**, per counter, in the right language and tone.

**What is deterministic vs agentic - this is the important answer.**
Everything that touches a number is deterministic. All three scorers - value, propensity,
leakage - are heuristic Python with weights in a YAML file. **No LLM computes a score.**
The model chooses *what to look at* and *how to say it*; arithmetic and ranking are code.

That was a deliberate architectural line. It means every figure in the UI is reproducible
and auditable, and the failure mode of a bad LLM response is a bad *plan* (visible in the
trace, catchable by the critic), never a wrong number presented confidently.

**How is agent output validated?**
- Planner output is parsed into a Pydantic `Plan`; a malformed plan fails closed.
- The **critic** node judges each tool result and can force a replan.
- Tool inputs are Pydantic-validated; unknown tool names can't be dispatched.
- Drafts pass a **numeric-grounding compliance validator** that strips any number not
  present in the source context before the draft can be shown.

**What if an agent is wrong?**
Depends where. Bad plan → the critic replans, and the trace shows it. Bad tool args →
Pydantic rejects. Invented number in a draft → the validator strips it. Bad *ranking* →
that's the dangerous one, because it's plausible and silent. Which is exactly the class
of bug I found in my own weights (see §5 below).

**How do you control hallucination?**
Structurally, not by asking nicely. The generator only ever receives that counter's real
figures; the validator then mechanically removes ungrounded numbers. The design
assumption is *the model will eventually invent a figure* - so there's a machine between
it and the merchant.

**Tool failures?**
Per-tool timeout (15s), datasource failover with a 60s circuit breaker, per-provider
token buckets with one retry then fall-through to the next model, and a deterministic
mock as the final tier - the whole agent runs with zero API keys.

---

## 4. Engineering

**How would this scale?**
Today: 500 counters, ~15k transactions, ~5.5s end-to-end on the mock. The shape at real
scale - say 50,000 counters across 200 Area Managers:

- **Scoring is the bottleneck, not the LLM.** It's O(counters returned) and runs
  in-process per request. Fix: precompute value and leakage scores nightly in Databricks,
  serve them from a materialised table, and reserve live scoring for the top-k the
  planner actually shortlists. Leakage is a trailing-window metric; it does not need to
  be computed per request.
- **Draft generation** is already bounded (semaphore of 4) and would move to a queue with
  a worker pool rather than blocking the request.
- **Retrieval** would move from local Chroma/BM25 to Databricks Vector Search so the
  index isn't per-instance.

**What breaks under high transaction volume?**
Transaction volume hits the warehouse, not the app - that's why Databricks is primary.
The SQLite failover would *not* survive real volume, and I'd be explicit about that: it's
a degraded read path for continuity, not a scale path.

**Monitoring?**
Today there's structured logging and every run persists a full typed trace. What's
missing for production: OTLP traces on the agent span tree, and the metrics I'd actually
alert on - plan-parse failure rate, critic replan rate, compliance-validator strip rate
(a rising strip rate means the prompt is drifting), provider fallback rate, and p95
end-to-end latency split by node.

**Security?** See README §12. Short version: shared-password auth with constant-time
comparison and a failed-login lockout, header-only credential transport, an explicit CORS
allowlist that never falls back to wildcard, parameterised SQL, Pydantic validation at
every tool boundary, and secrets from env only.

Worth telling this story if asked: three of those controls exist because I had an agent
write the security documentation **from the source code**, with instructions to report
anything it couldn't verify rather than document it as true. It found an unthrottled auth
endpoint, a wildcard-with-credentials CORS fallback, and a credential still accepted in a
query string. I wrote all three bugs; a carefully-worded documentation prompt caught them.
They're fixed with a regression test (`test_security.py`).

Still missing for production: per-user JWT + refresh, row-level security scoped to a
manager's own territory, an immutable audit trail on counter-data access and outreach
sends, PII encryption at rest, and general API rate limiting (only auth is throttled, and
the throttle is in-memory so it's per-process - behind replicas it belongs in Redis or at
the edge).

**What changes for production?**
Postgres for OLTP, per-user auth + RLS, precomputed scores, queued drafting, OTLP
observability, secrets in a managed vault, and a trained leakage model behind the same
`Scorer` interface - A/B'd against these heuristics rather than replacing them on faith.

---

## 5. How I actually built it - the AI-orchestration story

This is the part the brief was really asking about, and it's in `WRITEUP.md` in full.

The experiment was whether one person can use a swarm of coding agents to build something
coherent and *verifiable* in a day - and where the method breaks. So I sized the build
to make the method fail visibly: 8 modules, 3 scorers, 2 datasources, a routed LLM
layer, a full UI.

**Method:** I did *not* immediately fan out agents. Parallel agents diverge - if one
decides `monthly_tpv` and another decides `monthlyGmv`, you find out at integration
across forty files. So the first artifact was a written domain contract: every class,
every field name, all 8 modules, 25 scoring features, every tool name, table columns, and
**which files each agent owns** so two agents could never touch the same file. Then seven
agents ran concurrently against it.

**The finding I'd lead with:** the contract worked exactly as far as it extended and not
one inch further. Where it specified names, two agents that never communicated produced
byte-identical interfaces. Where it didn't - the chat request field - one agent renamed
it and another (correctly, conservatively) refused to, and the app was silently broken.

So the value wasn't writing code. It was knowing what to write down before anyone
started, then hunting the gaps afterwards.

**What I caught by verifying rather than trusting:**
1. A ranking flaw that would have shipped: `MOD-ANALYTICS` had four weights summing to
   1.0 on features any large counter maxes out, so it scored ~0.92 for everyone and
   outranked reconciliation on a counter actively losing fares. The demo *looked* right;
   the reasoning underneath was wrong. Only a sweep of all 8 modules × 5 counters found it.
2. A geographically absurd dataset - a Delhi bus terminal sitting in Kochi under
   Maharashtra's operator. Every agent did its job; nobody owned realism.
3. Downtime detection that couldn't see the outage it was written for (a whole-day test
   can't detect an evening-only outage).
4. A bug I introduced myself: adding the Claude adapter left intent classification gated
   on Gemini-or-Groq, so a Claude-only deploy would silently fall back to heuristics.

**If asked "what did AI do vs. what did you do":** AI wrote most of the code. I chose the
problem, set the architecture line between deterministic and agentic, wrote the contract,
decided the file ownership split, and found every one of the four bugs above. The
judgment was mine; the typing mostly wasn't. I think that's the actual job now.

---

## 6. Product evolution

**What next, in order:**
1. **Instrument precision.** Log field-visit outcomes against flagged counters. Without
   that, the weights are permanently unfalsifiable.
2. **Trained leakage model** behind the same `Scorer` interface, A/B'd against the
   heuristic. The current weights are a prior, not an answer.
3. **Per-counter seasonal baselines** - leakage is a trailing-window comparison today,
   which will produce false positives around festival cash surges.
4. **Reverse channel** - classify the supervisor's WhatsApp reply and surface the next step.

**Metrics I'd track:**
Precision@10 on flagged counters (the headline), leakage-to-resolution time, recovered
TPV after intervention, module attach rate from recommendations, draft edit-rate before
send (how much the manager rewrites = prompt quality), and compliance-validator strip
rate as a hallucination canary.

**What I'd automate, and what stays human - deliberately.**
Automate: detection, ranking, drafting, scheduling the follow-up.

**Human approval stays permanently on the send.** Not because the model can't write the
message, but because this is an accusation-adjacent workflow. A high leakage score means
*go look*, not *this supervisor is stealing* - several signals have innocent explanations
(a broken printer, a festival cash surge). I kept every string in the product reading
"call the supervisor" rather than "fraud detected". A tool that auto-accuses transit
staff on heuristic evidence gets someone fired over a printer fault. That constraint cost
nothing and I'd defend it in a design review.

---

## 7. Questions I expect, and my honest answers

**"Isn't the architecture just asserted, the way every demo claims?"**
That's exactly the question I built to answer. The abstractions had to survive real
substitution during the build - two heterogeneous datasources with real failover
(ADR-010), a second LLM provider added as one adapter because the brief asked for Claude
(ADR-011) - and they did, at the port boundaries. Where they weren't real was in the
places I hadn't written down: the contract gap that silently broke the chat (ADR-002).
Every claim here was tested rather than asserted, and the failings are logged alongside
the passes.

**"You tuned the weights until your demo counters ranked first. Isn't that overfitting?"**
Yes, n=5, and the person who chose the fix also chose the test. I'd defend the two
specific changes as principled - both fixed modules winning on free points rather than
their own trigger signal - but the framing is honest overfitting risk, and it's in the
write-up under "what's weak" rather than buried.

**"Why should I trust the numbers?"**
Don't trust them - change `weights.yaml` and watch the ranking move. Every score
decomposes into named, weighted contributions shown in the UI. The hero counters reach
the top through arithmetic on seeded transaction rows, not fixtures.

**"Did you test the UI?"**
No, not visually. Types check, the production build passes, the dev server serves, and I
exercised every API payload the components consume over HTTP - but I had no browser
automation and took no screenshot. I'd rather say that than claim it works.

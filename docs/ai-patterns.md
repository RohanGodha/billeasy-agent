# AI patterns reference

The nine patterns listed in README §7, described concretely against this codebase —
where each one lives, what it actually does, and why it earns its place rather than a
simpler alternative.

Nothing here is aspirational. If a pattern is only partly implemented, this document
says so.

---

## 1. Intent-routed multi-prompt architecture

**Where:** `app/agent/nodes/intent.py`, `app/agent/graph.py`,
`app/agent/nodes/faq.py`, `app/agent/nodes/knowledge.py`.

Before any planning, the Area Manager's message is classified into one of six routes:

```
task | follow_up | knowledge | faq | chitchat | out_of_scope
```

Four of them short-circuit the entire pipeline. `chitchat`, `faq`, `knowledge` and
`out_of_scope` each produce a single `synth` event and go straight to the Responder — no
plan, no tools, no scoring, no drafts.

Classification is a **regex first pass**, optionally upgraded by an LLM classifier
(`INTENT_PROMPT`, JSON mode, `max_tokens=40`, `temperature=0.0`) that also sees the last
four conversation turns. The heuristic alone is good enough to run keyless.

The precedence rules in `_heuristic` are the interesting part, because they encode real
product decisions:

| Rule | Why |
| --- | --- |
| A question *about the assistant* wins over task words | *"which modules can you recommend?"* is a capability question, not a network sweep |
| Action verbs (`find`, `draft`, `score`, `rank`, `flag`…) beat the knowledge regex | *"find outlets past the GST threshold"* is work, not a policy lookup |
| A **plural counter noun** (`counters`, `outlets`, `jetties`, `depots`) also forces `task` | asking about a *set* of counters is always a pipeline run |
| A follow-up pattern only counts when history exists | *"now only Kochi"* means nothing as a first turn |
| Unknown input defaults to `faq`, not `task` | an ambiguous message should be answered, not turned into a 500-counter sweep |

**Why not one prompt for everything:** because a capability question that runs five tool
calls is both slow and wrong, and a leakage sweep triggered by "hi" is worse.

**Honest note:** the LLM upgrade path checks `router.status()` for `gemini` or `groq`
only. With an Anthropic key alone, intent classification stays heuristic-only.

---

## 2. Plan-and-Execute with a critic in the loop

**Where:** `app/agent/nodes/planner.py`, `tool_executor.py`, `critic.py`, `graph.py`.

The planner emits a typed JSON plan up front — `intent`, `target_module`, `city_filter`,
`tone`, `language`, and one to five `PlanStep`s — validated into the `Plan` Pydantic
model. The executor walks it deterministically. After every step the critic returns a
verdict.

`_coerce_plan` is deliberately paranoid about LLM output:

- `city_filter` is normalised from string, list or null into a list-or-none;
- `target_module` is checked against the eight real module ids and otherwise falls back
  to `MOD-RECON`;
- an unparseable step is dropped rather than crashing the run;
- if nothing survives, `_default_plan()` supplies a runnable five-step plan.

The critic is **rule-based, not an LLM call**. That removes five LLM round trips from
the hot path, and it catches the one failure mode that actually occurs: `query_counters`
returning zero rows. Recovery strips `min_tpv`, `min_pending_settlement`,
`min_daily_txns` and `cities`, raises `limit` to 200, pops the failed record, and
re-runs the step. Bounded by `agent_max_iterations` (6) and one replan per run, so the
loop provably terminates.

**Why not ReAct:** an up-front plan is auditable and replayable. A ReAct trace is a
transcript you have to read; a typed plan is a structure you can diff, validate and
regression-test. For a product whose output goes to a merchant, that matters more than
per-step adaptivity.

**Honest note:** an LLM critic would catch far more than an empty result set — a wrong
city, a nonsensical module choice, a shortlist that doesn't match the ask. Upgrading
`critic.py` is a contained change and is on the backlog.

---

## 3. Typed tools + parallel dispatch

**Where:** `app/application/tool_registry.py`, `app/tools/*.py`.

Eight tools, each registered by a `@tool(...)` decorator declaring `name`,
`description`, `input_model` and `output_model`:

| Tool | Purpose |
| --- | --- |
| `query_counters` | Structured search over the network — city, tier, counter type, TPV, pending settlement, velocity, settlement cycle — with 2-stage filter relaxation |
| `compute_counter_value` | Explainable 0–1 network-value score |
| `predict_module_propensity` | Per-(counter, module) fit with the full feature breakdown |
| `recommend_modules` | Eligibility-checked top-k module recommendation |
| `search_field_notes` | Hybrid RAG over field-visit notes and support tickets, cited |
| `get_counter_transactions` | Aggregates: collected, settled, cash/digital share, channel split, void/reissue count, refunds |
| `generate_whatsapp_message` | Grounded draft + numeric compliance validation |
| `create_outreach_batch` | Persists drafts for review — **the only write path in the tool set** |

`invoke_tool` gives every call the same treatment: Pydantic validation of args before
dispatch, `asyncio.wait_for` at `AGENT_TOOL_TIMEOUT_SECONDS` (15 s), and a uniform
envelope `{ok, tool, data, latency_ms, error?}`. A validation failure, a timeout and an
exception all return the same shape, so the critic has exactly one thing to reason
about. Schemas are introspectable at `GET /tools`.

Parallelism appears in two places: **inside** tools (`asyncio.gather` over counters, so
N counters cost roughly one round trip in wall time), and **across** the draft fanout in
the message generator.

Adding a tool is one file: declare the models, decorate the function, register the
import in `app/tools/__init__.py`.

**Why typed tools instead of letting the model write SQL:** an agent that emits SQL
against a payments warehouse is an incident waiting for a deploy. Typed tools mean the
model chooses *which* question to ask and the code owns *how* it is asked.

---

## 4. Hybrid retrieval — BM25 + dense, RRF, MMR

**Where:** `app/infrastructure/rag/hybrid_retriever.py`, `mmr.py`.

The index is field-visit notes and support tickets, chunked one per note, each carrying
its `counter_id`.

- **Lexical:** `rank_bm25.BM25Okapi` over tokenised note summaries. Always available.
- **Dense:** Chroma (persistent client, cosine) over Gemini `text-embedding-004`.
  Optional — `pip install -r requirements-rag.txt`.
- **Fusion:** Reciprocal Rank Fusion at the standard `K = 60`, robust to the two
  retrievers scoring on incomparable scales without having to learn a weight.
- **Re-rank:** MMR at `λ = 0.7` over the fused top `max(4k, 8)` — favours relevance
  while the `(1 − λ)` penalty kills near-duplicate notes, so the LLM sees diverse
  evidence rather than the same complaint five times.
- **Citations:** stable ids of the form `FN-CTR-0001-3a9f21`, returned to the
  synthesizer, attached to candidates, and visible in the drawer.

Lexical matters more than usual here: field notes are dense with numbers, module names
and named terminals, which BM25 weights naturally and embeddings tend to smooth over.

**Honest note — this is the weakest subsystem in the build.** Chroma exceeds Render's
free-tier memory, so the **deployed default is BM25-only**. Retrieval quality is visibly
worse: a question about NCMC at an AFC gate can land in the chargebacks FAQ. The
degradation is graceful and the citations stay honest, but the answer can be the wrong
document.

---

## 5. Cognitive-load-based LLM routing

**Where:** `app/infrastructure/llm/router.py`, plus `anthropic_client.py`, `gemini.py`,
`groq.py`, `mock.py` behind the `LLMClient` port in `base.py`.

```
reasoning  (planner, synthesizer, intent, chitchat, guardrail)  → Claude → Gemini → Groq  → Mock
generation (whatsapp drafts, parallel fanout)                   → Groq   → Claude → Gemini → Mock
embed      (RAG)                                                → Gemini → Mock
```

The rule is **route by the cognitive load of the node, never by hardcoding a model into
one**. Structured plans are where the strongest model earns its latency, so reasoning
leads with Claude. Drafting is a fanout of many short messages where wall-clock beats
depth, so it leads with Groq. Anthropic publishes no embeddings endpoint, so `embed`
never routes there.

Providers are constructed lazily and only if their key is set. Each real provider gets
**two attempts** with an 0.8 s backoff before the router falls through; the mock gets
one. `resp.meta["route_used"]` and `route_kind` are stamped on every response and
surface in the trace; when the run lands on the mock after failures,
`meta["fallback_reason"]` records the chain of errors that got it there.

Claude runs at `ANTHROPIC_EFFORT=low` by default — an Area Manager is waiting on the
plan, and this is an interactive product. Raise it if you'd rather have depth than
seconds.

**The mock is not a stub.** It returns canned plans, critic verdicts, summaries and
grounded WhatsApp drafts, so the entire agent runs with zero API keys — which is how
this can be reviewed without spending anything.

**Honest note:** that same property flatters the planner. A keyless reviewer sees
perfect plans that reflect the few-shot prompt, not live model behaviour.

---

## 6. Grounded generation + numeric compliance validator

**Where:** `app/scoring/compliance.py`, invoked by `app/tools/generate_whatsapp.py`.

Two halves, and both are necessary.

**Grounding on the way in.** The draft prompt receives only the counter's real record —
name, city, counter_type, tier, operator, monthly TPV in ₹, digital share, pending
settlement — the module record, and the top three feature contributions with their
rationales, plus tone, language and the manager's name. Nothing else. The model is never
handed the network aggregate it could accidentally quote.

**Validation on the way out.** `compliance_check` extracts every number from the draft
with a regex that understands `₹`, `Rs`, `INR`, `%`, `lakh`/`L` and `crore`/`Cr`, and
filters out four-digit years. It then recursively flattens every number reachable in the
source context — including lakh and crore abbreviations of each figure — into an allowed
bag. Any draft number not in that bag, and not within 5% (or ±1) of something in it, is
**mechanically replaced with an em dash**.

The report returned alongside the message is
`{ok, numbers_in_draft, ungrounded, redacted_draft}`, and the drawer renders exactly
which figures were stripped.

**Why this is the load-bearing pattern:** it assumes the model *will* eventually invent
a settlement or TPV figure, and refuses to let that number reach a merchant or a depot
supervisor. It is deterministic, unit-testable, and explainable to a compliance
reviewer — which a prompt instruction saying "don't hallucinate numbers" is not.
`tests/test_agent_e2e.py` asserts that **every** draft in a full run passes it.

**Honest note:** the validator is conservative — it strips rather than regenerating. A
production version would attempt one grounded regeneration before falling back to
redaction, so a good draft with one bad figure isn't left with a dash in it.

---

## 7. Event-typed SSE streaming

**Where:** `app/api/chat.py`, `app/agent/state.py` (`TraceEvent`),
`frontend/src/hooks/useAgentStream.ts`.

Every node emits a typed `TraceEvent`; the SSE endpoint writes each one to the wire as a
named event as soon as `run_agent` yields it, with a 5 ms `asyncio.sleep` between frames
so the browser can paint. The frontend uses `@microsoft/fetch-event-source` rather than
the native `EventSource`, because the auth token has to travel in a header.

| Event | UI effect |
| --- | --- |
| `info` | sets `sessionId`; also carries intent and follow-up rewrites into the trace |
| `plan` | trace row: intent, target module, language, route, latency |
| `tool_call` | trace row with the resolved args |
| `tool_result` | updates that row with `ok`, `source`, `rows`, `latency_ms` |
| `critic` | trace row: verdict, replan, notes |
| `candidate` | inserts a counter card into the right-hand queue |
| `synth` | renders the assistant summary bubble |
| `draft` | attaches a draft and its compliance report to its candidate |
| `final` | full payload; marks streaming complete |
| `error` | inline error banner |

Candidates stream **one event each**, so the queue fills row by row instead of appearing
in one jump — which is what makes the agent's work legible rather than a spinner.

**Why not one JSON response:** a five-second wait with no feedback reads as broken. More
importantly, streaming the reasoning is the product's honesty argument — the manager
sees which tools ran, against which data source, before they see the conclusion.

---

## 8. Hexagonal data layer with failover + circuit breaker

**Where:** `app/infrastructure/datasource/`.

- `DataSource` is a Protocol — the agent and every tool depend on the interface, never
  on a driver.
- `DatabricksSource` wraps the synchronous `databricks-sql-connector` in
  `asyncio.to_thread`, bounded by a 5 s `asyncio.wait_for`.
- `SQLiteSource` is always on: `aiosqlite`, WAL mode, deterministically reseeded on
  boot.
- `FailoverSource` tries the primary, and on exception or timeout trips a **60 s circuit
  breaker** and routes to the secondary — so a cold warehouse costs one slow call, not a
  slow session.
- Every result carries a `source` tag which rides through `ToolCallRecord` into the
  `tool_result` event and onto the screen.

The same port shape is what made adding the Anthropic adapter to the LLM side a one-file
change rather than a refactor. That was the cheap test of whether the hexagonal claim
was real rather than a README bullet.

---

## 9. The trace is data

**Where:** `app/agent/state.py`, `app/agent/nodes/responder.py`, `app/api/trace.py`.

Rather than scattering `logger.info()` calls and depending on an APM vendor, every node
emits a typed `TraceEvent` that is simultaneously the UI feed and the audit record.

`AgentState` keeps two lists on purpose: `events` is **drained** incrementally as the
SSE stream consumes it, while `archive` accumulates the whole run and is never drained.
That is what makes `GET /trace/{session_id}` a complete replay rather than a tail. The
Responder writes every archived event into `agent_traces` with its node, payload,
`llm_route`, `source` and latency, alongside the assistant message and its candidates
and drafts payload.

The practical consequence: any session can be reconstructed offline — which plan, which
tools, which data source, which model answered, what the critic said, and which figures
the compliance validator stripped from which draft. That is the audit trail, and it
costs nothing beyond a table.

**Honest note:** `agent_traces` grows unbounded. There is no TTL job.

---

## Bonus — transparent scoring (three scorers, no black boxes)

**Where:** `app/scoring/value.py`, `propensity.py`, `leakage.py`, `weights.yaml`.

Not in the README's list of nine, but it's what makes the patterns above worth having:
every number the Area Manager sees decomposes into named, weighted contributions.

- **Value** — z-scored `tpv_z`, `digital_share_z`, `tenure_z`, `txn_velocity_z` against
  the network.
- **Propensity** — a logistic over ~25 named features, weighted **per module** in
  `weights.yaml`, with rates band-normalised so they actually move the logit.
- **Leakage** — deliberately **not** a logistic. A plain weighted sum whose weights sum
  to 1.0 over features already in [0,1], so 0.54 reads directly as *"54% of the maximum
  leakage evidence we could have seen"*. Bands: `clear` < 0.25 ≤ `watch` < 0.45 ≤
  `elevated` < 0.65 ≤ `severe`.

`leakage.py` imports the private feature builders from `propensity.py` rather than
reimplementing them, so the two scorers cannot drift apart on what a cash-share spike
means.

Every feature returns a `ScoreBreakdown` with a value, a contribution, a direction and a
plain-language rationale. The top contributions feed the synthesizer prompt, the draft
prompt, and the drawer's breakdown chart — so no scoring decision reaches a screen
unexplained.

**Honest note:** all three are heuristic. There are no ground-truth leakage labels, so
the weights are hand-tuned domain judgement — transparent and tunable, but judgement.
See [`tradeoffs.md`](tradeoffs.md).

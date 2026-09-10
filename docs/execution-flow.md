# Execution flow — one query, end to end

Companion to README §4. That diagram shows the shape; this document retraces the
*actual* code path for the canonical demo query, names every event on the wire, and
gives an honest timing narrative.

The query throughout is:

> *"Find ferry and bus counters in Mumbai leaking digital ticket revenue this month
> and draft WhatsApp nudges for the depot supervisors."*

Rohan (Area Partner Manager, Mumbai West) types it into the composer.

---

## 1. The request

```
POST /chat/stream
X-Access-Token: <shared token>
{ "session_id": null,
  "manager_query": "Find ferry and bus counters in Mumbai leaking digital ticket revenue this month and draft WhatsApp nudges for the depot supervisors.",
  "manager_name": "Rohan" }
```

`ChatStreamIn` (`backend/app/api/chat.py`) is the contract. `manager_query` accepts
`query` as an alias; `manager_name` accepts `manager`. The query is stripped, rejected
if empty, and truncated at 2,000 characters.

Before the agent starts, `chat_stream` does three things in order:

1. `_ensure_session` — insert a `sessions` row if `session_id` is null, titled from the
   first 60 characters of the query.
2. `_load_history` — the last 8 user/assistant turns, loaded **before** the new message
   is persisted, so the planner's follow-up rewriter sees the prior turn and not itself.
3. `_persist_user_msg` — write the turn to `messages`.

Then the SSE response opens and the first frame goes out immediately:

```
event: info
data: {"session_id":"6f0f…"}
```

`AgentState` is constructed with `manager_query`, `manager_name`, `history`, and handed
to `run_agent` (`backend/app/agent/graph.py`), which is an async generator. Every
`TraceEvent` it yields is written to the wire straight away, with a 5 ms
`asyncio.sleep` between frames so the browser can paint each one.

---

## 2. The event tape

These are the nine event types the UI knows about, in the order this query produces them.

| # | event | emitted by | payload |
| --- | --- | --- | --- |
| 1 | `info` | `chat.py` | `session_id` |
| 2 | `info` | `graph.run_agent` | `msg: agent_started` |
| 3 | `info` | `nodes/intent.py` | `node: intent`, `intent`, `has_history` |
| 4 | `plan` | `nodes/planner.py` | full `Plan`, `intent`, `target_module`, `language`, `llm_route`, `latency_ms` |
| 5 | `tool_call` ×5 | `nodes/tool_executor.py` | `step`, `tool`, resolved `args` |
| 6 | `tool_result` ×5 | `nodes/tool_executor.py` | `ok`, `source`, `rows`, `latency_ms` |
| 7 | `critic` ×5 | `nodes/critic.py` | `verdict`, `replan`, `notes` |
| 8 | `candidate` ×≤10 | `nodes/synthesizer.py` | the whole `CandidateRecord` |
| 9 | `synth` | `nodes/synthesizer.py` | `summary`, `candidate_count` |
| 10 | `draft` ×N | `nodes/message_generator.py` | `message`, `compliance`, `llm_route` |
| 11 | `final` | `nodes/responder.py` | `summary`, `candidates`, `drafts` |

`error` is the tenth type, emitted by `chat.py` if the generator raises. `router` and
`token` exist in the `TraceEvent` literal but this pipeline does not emit them.

---

## 3. Node by node

### 3.0 Intent gate — `nodes/intent.py`

Runs **before** any planning. Routes to one of
`task | follow_up | knowledge | faq | chitchat | out_of_scope`.

A regex first pass decides on its own; if `GEMINI_API_KEY` or `GROQ_API_KEY` is set,
an LLM classifier (`INTENT_PROMPT`, JSON mode, `max_tokens=40`, `temperature=0`) can
override it. Four of the six routes short-circuit the whole pipeline — `chitchat`,
`faq`, `knowledge` and `out_of_scope` each produce one `synth` event and go straight to
the Responder. No tools run, no counters are scored.

For this query, the `_ACTION_PATTERNS` regex catches `find` and `draft`, so the
heuristic returns **`task`** before the LLM is consulted. Note the deliberate
precedence: action verbs and plural counter nouns beat the knowledge regex, which is why
*"which outlets crossed the GST threshold"* is a pipeline run, not a policy lookup.

### 3.1 Planner — `nodes/planner.py`

One reasoning call, JSON mode, `temperature=0.2`, `max_tokens=900`, against
`prompts/planner_system.md`. The response is coerced into a `Plan`:

```json
{ "intent": "find_counters_leaking_revenue_and_outreach",
  "target_module": "MOD-RECON",
  "city_filter": ["Mumbai"],
  "tone": "professional",
  "language": "English",
  "steps": [ … 5 typed PlanSteps … ] }
```

`_coerce_plan` is defensive on purpose: `city_filter` is normalised from string-or-list-
or-null; `target_module` is rejected unless it is one of the eight real module ids and
otherwise falls back to `MOD-RECON` (revenue leakage is the Area Manager's default
question, and every counter type is eligible for reconciliation); an unparseable step is
dropped rather than crashing the run. If nothing survives, `_default_plan()` supplies a
runnable five-step plan so the agent never dead-ends.

If the intent was `follow_up`, the planner first calls `_rewrite_follow_up`, which
expands *"now only Kochi, and make it firmer"* into a standalone task using the last
user and assistant turn, and emits an `info` event carrying the rewritten string.

### 3.2 Tool executor + Critic loop — `nodes/tool_executor.py`, `nodes/critic.py`

`run_agent` loops `execute_step` → `run_critic` while `cursor < len(steps)` and
`iterations < AGENT_MAX_ITERATIONS` (6).

Before dispatch the executor:

- resolves `$stepN.ids` / `$stepN.top_k` placeholders against earlier results. `top_k`
  deliberately passes **40** counters forward, not 10 — capping earlier would drop a
  small jetty with a severe cash-share spike before propensity is ever computed;
- backfills the plan-level `city_filter` onto `query_counters` if the step didn't carry
  `cities` itself;
- backfills `counter_ids` from the most recent shortlist when a placeholder resolves
  empty.

Every tool runs through `invoke_tool` (`application/tool_registry.py`): Pydantic
validation of args, `asyncio.wait_for` at `AGENT_TOOL_TIMEOUT_SECONDS` (15 s), and a
uniform envelope `{ok, tool, data, latency_ms, error?}`.

The five steps for this query:

| step | tool | what happens |
| --- | --- | --- |
| 1 | `query_counters` | Structured filter: `cities=["Mumbai"]`, ferry/bus counter types, TPV floor. `FailoverSource` picks Databricks or SQLite; the row's `source` tag rides through to `tool_result`. Two-stage filter relaxation if the strict pass is empty. |
| 2 | `compute_counter_value` | `asyncio.gather` over the shortlist — profile + transactions + z-scored value. Returns sorted by `value_score`. |
| 3 | `predict_module_propensity` | Per-counter logistic against `MOD-RECON`'s weights, with the full named-feature breakdown. |
| 4 | `recommend_modules` | Eligibility-checked top-k. A counter that already has the module live is excluded here, not silently ranked. |
| 5 | `search_field_notes` | Hybrid RAG. BM25 over tokenised note summaries; Chroma dense retrieval when installed; RRF fusion at K=60; MMR re-rank at λ=0.7. Returns `FN-CTR-0001-…` citation ids. |

After each step the Critic emits a verdict. It is **rule-based, not an LLM call** — a
deliberate token saving. It fails and replans exactly one case: `query_counters`
returning zero rows. Recovery is blunt and honest — strip `min_tpv`,
`min_pending_settlement`, `min_daily_txns` and `cities`, raise `limit` to 200, pop the
failed record, re-run. Capped at one replan per session, which is why the loop cannot
spin.

On the canonical query the Mumbai ferry/bus filter matches, so all five verdicts are
`pass`.

### 3.3 Synthesizer — `nodes/synthesizer.py`

This node does the real ranking work, and it does it twice.

**First sort — commercial fit.** Composite `= w_value·value + w_prop·propensity`, where
the weights are intent-aware: remediation modules (`MOD-RECON`, `MOD-OFFLINE`) fix a
live leak, so urgency beats counter size and propensity dominates at **0.2 / 0.8**;
growth modules run **0.4 / 0.6**. Sorted, then trimmed to
`AGENT_TOP_K_CANDIDATES` (10).

**Enrichment.** For the surviving ten it bulk-loads field notes and transactions
(`get_field_notes_bulk`, `get_transactions_bulk`), then per counter computes:

- sentiment + escalate flag (`scoring/sentiment.py`);
- `leakage_risk`, `leakage_band` and the per-feature `leakage_features`
  (`scoring/leakage.py`) — from **transaction evidence**, not from whether anyone
  complained;
- `opportunity_value` = monthly TPV × module take rate × 12, rounded to the nearest
  thousand ₹, explicitly a prioritisation aid and never a quote;
- `next_action` and `priority` — `leakage_risk ≥ 0.45` produces *"Call the supervisor
  within 48h — elevated revenue leakage"* at priority 1.

**Second sort — the action queue.** `(priority, -leakage_risk, -composite_score)`. This
is what reaches the UI, and it is why the ranking on screen is not simply the composite
score.

For Gateway Jetty — Counter 3 the leakage arithmetic lands at **0.54 → `elevated`**,
with `void_reissue_rate` (0.210) ahead of `cash_share_spike` (0.187) and
`settlement_mismatch_rate` (0.056) third.

Each candidate is emitted as its own `candidate` event, so the right-hand pane fills row
by row rather than in one jump. Then one reasoning call writes the summary
(`temperature=0.4`, `max_tokens=320`) — and if that call routes to the mock or returns
under 20 characters, `_fallback_summary` builds a specific, data-grounded summary from
the real candidates instead. The demo never shows generic filler.

If nothing survived the filters, the node returns a plain-language "loosen the criteria"
message rather than asking an LLM to summarise an empty list.

### 3.4 Message Generator — `nodes/message_generator.py`

`asyncio.gather` over every candidate, bounded by a semaphore of **4** — free-tier rate
limits are real, so this is a bounded fanout, not an unbounded one.

Each call invokes the `generate_whatsapp_message` tool on the **generation** route
(Groq first). The prompt receives only the counter's real fields — name, city,
counter_type, tier, operator, monthly TPV in ₹, digital share, pending settlement — the
module record, the top three feature contributions with their rationales, the tone, the
language and Rohan's name.

Then `scoring/compliance.py` runs `compliance_check`: extract every number in the draft,
flatten every number reachable in the source context (including lakh/crore
abbreviations), and replace any unmatched figure with an em dash, tolerating 5% rounding
drift. The report — `ok`, `numbers_in_draft`, `ungrounded`, `redacted_draft` — rides on
the `draft` event, and the drawer surfaces exactly which figures were stripped.

### 3.5 Responder — `nodes/responder.py`

`INSERT OR IGNORE` the session row (defensively, so foreign keys resolve), persist the
drafts through the `create_outreach_batch` tool — the only write path in the tool set —
write every archived event into `agent_traces`, persist the assistant message with its
candidates and drafts payload, and emit `final`.

`state.archive` exists precisely because `state.events` is drained incrementally for
SSE; the archive is what makes `GET /trace/{session_id}` a complete replay rather than a
tail.

---

## 4. Timing

**These are indicative numbers from local runs, not a benchmark harness.** There is no
load test in this repo and no P95 measurement; treat the table as the shape of the
latency budget, not as a measured SLO.

| Stage | Keyless (mock LLM) | With real providers |
| --- | ---: | ---: |
| Auth + session insert + first `info` | ~30 ms | ~30 ms |
| Intent gate | <5 ms (regex only) | +250–600 ms if the LLM classifier runs |
| Planner (reasoning route) | ~10 ms | 0.8–2.5 s — Claude at `ANTHROPIC_EFFORT=low` is the slowest single hop |
| 5 tool steps (parallel inside each) | 250–600 ms | 250–900 ms (Databricks cold start pushes the tail) |
| Critic ×5 | <5 ms total | <5 ms total — rule-based, no LLM |
| Synthesizer scoring + enrichment | 150–400 ms | 150–400 ms |
| Synthesizer summary | ~10 ms | 0.7–1.5 s |
| Drafts ×10, semaphore 4 (generation route) | ~50 ms | 1.5–3 s (Groq, three waves of ≤4) |
| Responder persistence | 100–300 ms | 100–300 ms |
| **End to end** | **~1 s** | **~5 s** |
| **First visible event** | **<100 ms** | **<100 ms** |

The number that matters for the demo is the last row, not the total. `info` and `plan`
stream before any tool runs, so the trace pane is alive within a beat of pressing enter
and the perceived wait is much shorter than the wall-clock.

### Why it holds on a free tier

- Per-counter work inside every tool is `asyncio.gather`, so N counters cost roughly one
  round trip in wall time rather than N.
- The Critic is rule-based. Five LLM calls were removed from the hot path by choosing a
  heuristic that only has to catch one failure mode.
- Scoring is arithmetic over dicts and YAML weights — no model is loaded, so the whole
  backend fits in Render's 512 MB.
- Drafting is bounded at 4 concurrent, which keeps free-tier rate limits from turning a
  fast fanout into a retry storm.
- SQLite runs in WAL mode; Databricks is wrapped in a 5 s timeout with a 60 s circuit
  breaker, so a cold warehouse costs one slow call, not a slow session.

### The failure paths worth knowing

- **Provider down or rate-limited** → the router retries once, then falls through to the
  next provider, then to the mock. `route_used` on the event tells you what actually
  answered, and `fallback_reason` says why.
- **Tool exceeds 15 s** → the envelope returns `{"ok": false, "error": "timeout"}`, the
  Critic sees a failure, and the run continues rather than aborting.
- **Zero counters matched** → one replan with relaxed filters; if that also returns
  nothing, an honest empty-result summary and no drafts.
- **Client disconnects** → `request.is_disconnected()` breaks the loop mid-stream. The
  trace rows for events already emitted are not written, because persistence happens in
  the Responder.

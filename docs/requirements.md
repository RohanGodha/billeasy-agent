# Counter Copilot — Requirements

*Product and engineering requirements for the Billeasy Area Partner Manager copilot.*

---

## 1. Document purpose and how to read it

This document states what Counter Copilot is required to do, at what priority, and how
each requirement can be checked. It was written **against the code**, not against the
README — every requirement below corresponds to something that exists in this repository,
and anything that is designed but not enforced is labelled as such rather than described
as working.

How to read it:

- **§4 Functional requirements** are grouped by capability. Each has a stable `FR-n` id, a
  priority (Must / Should / Could) and acceptance criteria that a reviewer can execute.
- **§5 Non-functional requirements** use the same `NFR-n` treatment.
- **§6 Domain constraints** separates what is *enforced in code* from what is *modelled or
  documented*. The short answer is that essentially nothing regulatory is enforced; read
  the section rather than assuming.
- **§9 Traceability** maps every id to a file and to the test that covers it. Requirements
  with no automated test are marked `no automated coverage` — that marking is used often
  and is deliberate.

Companion documents, all authoritative and not contradicted here: [`README.md`](../README.md)
(the product and its architecture), [`WRITEUP.md`](../WRITEUP.md) (how it was built with AI),
[`ASSIGNMENT-REVIEW.md`](../ASSIGNMENT-REVIEW.md) (review talking notes).

Scope note: this is a take-home build. It is production-*shaped* — ports, failover,
validation, tests — and it is not production-*deployed*. §7 lists what was deliberately
left out.

---

## 2. Personas

### 2.1 Primary — Rohan, Area Partner Manager (Mumbai West)

Owns 200–500 counters across a territory: retail POS outlets, ferry jetties, bus depots and
metro ticket counters. He is the only person who logs into this product.

| Attribute | Detail |
| --- | --- |
| Daily question | "Which counters do I chase today, and what do I say?" |
| Current tooling | Settlement dashboards, ticketing reports, a support queue, and memory of who called last |
| Constraint | He cannot visit 400 counters; he can make perhaps a dozen calls and two visits a day |
| Success for him | A ranked, explained queue he trusts enough to act on before his first call |
| Failure for him | Being sent to a counter on a bad signal, or being handed a number he cannot defend to a supervisor |

He is not technical. He will not read a score's formula, but he will read a named signal
("cash share jumped against this counter's own baseline") and decide whether it is worth a
call. Every score in the product therefore decomposes into named contributions (NFR-1).

### 2.2 Secondary — the counter supervisor / outlet owner

The depot supervisor, jetty ticket clerk or kirana owner at the far end of the WhatsApp
message. **This persona never opens the application.** They have no account, no view of
their own score, and no way to contest a flag inside the product — yet they are the person
the product acts upon, and in the worst case the person whose job a misread signal could
affect.

That asymmetry is the sharpest ethical constraint on this build and it drives three
requirements directly:

- The message they receive must never contain a figure the source data does not support
  (FR-19, NFR-1) — a wrong ₹ figure in a supervisor's hand is worse than no message.
- The product must never accuse. Leakage risk is a prioritisation severity, not a fraud
  finding; every string reads "call the supervisor", never "fraud detected" (FR-23).
- Nothing is sent automatically. A human reads every draft before it leaves (FR-31).

Several leakage signals have innocent explanations — a printer that stopped issuing
receipts, a festival cash surge, a device that lost connectivity. A tool that auto-accuses
transit staff on heuristic evidence gets someone dismissed over a hardware fault.

### 2.3 Tertiary — the ops / compliance reader

Regional operations and compliance staff who never drive the conversation but need to
answer "why did the system flag that counter, and what was said to the merchant?" after
the fact. They are served by the persisted trace (FR-34), the source tag on every tool
result (FR-36), and the per-feature score breakdowns. They have **no dedicated UI and no
separate role** — there is one shared credential and one view (see §7).

---

## 3. Problem statement, goals and non-goals

### 3.1 Problem

Billeasy runs the digital payment and ticketing rail for offline India: retail POS outlets
and government mass transit. Money enters at the physical edge — a passenger buys a ferry
ticket, a shopper pays at a kirana counter — is captured, billed or e-ticketed, and settled
T+1 to the merchant or transit authority against a take rate.

The edge is also where it leaks:

| Failure mode | Signature in the data |
| --- | --- |
| Fare leakage — cash bypassing the digital rail | cash share rising against the counter's own baseline |
| Void-and-reissue — issue, void, pocket the fare, reissue | void/reissue rate spikes |
| Settlement mismatch — ₹ captured ≠ ₹ settled | mismatch rate drifts past tolerance |
| Payout backlog — merchant unpaid and quietly churning | pending settlement ages |
| Receipt-issuance gap — past the threshold, still not issuing compliant bills | share of collections with no bill / e-ticket issued |
| Peak-hour downtime — terminal dark during the rush | offline minutes inside the peak window |

An Area Partner Manager owns 200–500 counters. Today a counter gets attention when it
*complains*. A counter leaking quietly with a clean support history is structurally
invisible to a ticket queue — and that is precisely the counter worth finding.

### 3.2 Goals

| # | Goal | How it is met |
| --- | --- | --- |
| G1 | Let the manager ask in plain language and get a ranked, actionable answer | FR-1, FR-8, FR-25 |
| G2 | Rank by transaction evidence, not by who complained | FR-23 — leakage is computed from transactions; field-note sentiment carries weight 0.03 of 1.00 |
| G3 | Make every number defensible to a supervisor | NFR-1, FR-19 |
| G4 | Produce the outreach message, not just the finding | FR-30 |
| G5 | Keep a human between the finding and the merchant | FR-31 |
| G6 | Be fully reviewable with zero API keys and zero provisioned infrastructure | NFR-3, NFR-18 |
| G7 | Leave a replayable audit trail of every run | NFR-2, FR-34 |

### 3.3 Non-goals

Stated as hard boundaries, not as future work.

| # | Non-goal | Why |
| --- | --- | --- |
| NG1 | **It does not send messages.** | There is no send path in the codebase. The product drafts; a person copies or opens WhatsApp themselves. Automated sending is a deliberate omission, not an unfinished feature. |
| NG2 | **It does not accuse anyone of fraud.** | Leakage risk is a 0–1 severity for triage. Every user-facing string says "call the supervisor". A heuristic score on synthetic-quality evidence is not a fraud finding. |
| NG3 | **It does not replace the field visit.** | The output is a call list and an opening line. Confirmation happens at the counter, by a human, and the product has no way to close that loop. |
| NG4 | **It is not a BI tool.** | It does not do arbitrary aggregation, cohorting, charting or scheduled reporting. It answers "who do I chase and what do I say". A fixed weekly report is better served by a SQL query and a cron job, and the agent's complexity is only justified by open-ended questions. |
| NG5 | It is not a CRM or a case-management system. | No ownership, assignment, SLA or resolution tracking. Drafts have a `status` column and nothing enforces a workflow over it. |
| NG6 | It is not a settlement or reconciliation engine. | It reads settlement evidence; it never moves or corrects money. |

---

## 4. Functional requirements

Priorities: **Must** = the product is not the product without it. **Should** = materially
degrades the experience if absent. **Could** = supporting surface.

### 4.1 Conversation and routing

#### FR-1 — Natural-language query intake · Must

The manager submits one plain-language turn; the system runs the agent and returns a
written answer plus structured results.

Acceptance criteria:
- `POST /chat/stream` returns `text/event-stream`; `POST /chat/run` returns the same run
  as one JSON object with `session_id`, `summary`, `candidates`, `drafts`, `events`.
- Both accept `manager_query` (alias `query`) and `manager_name` (alias `manager`).
- An empty or whitespace-only query is rejected by validation; a query longer than 2000
  characters is truncated to 2000.
- Both routes require authentication (FR-43).

#### FR-2 — Six-route intent classification · Must

Before any work is done, the turn is routed to exactly one of
`task | follow_up | knowledge | faq | chitchat | out_of_scope`.

Acceptance criteria:
- A deterministic regex classifier runs on every turn and always yields a route from that
  set; unknown input defaults to `faq`, never to `task`.
- When any non-mock LLM provider is configured, an LLM classifier runs and overrides the
  heuristic only if it returns a member of the same set. The gate is a generic
  "any live non-mock provider" check, not a hardcoded provider list.
- `knowledge`, `faq`, `chitchat` and `out_of_scope` short-circuit: no plan, no tools, no
  scoring, zero candidates.
- The classified route is emitted as an `info` trace event.
- Reference routings that must hold: "what is the GST e-invoice threshold" → `knowledge`;
  "find ferry counters leaking revenue and draft messages" → `task`; "show me counters with
  a settlement mismatch" → `task`; "what can you do" → `faq`; "hi there" → `chitchat`;
  "write a poem about Mumbai" → `out_of_scope`.

#### FR-3 — Session threading and conversation memory · Must

Acceptance criteria:
- `POST /sessions` creates a thread; `GET /sessions` returns the 50 most recent, newest
  first.
- A chat turn without a `session_id` creates one and its id is the first SSE frame.
- Each turn persists the manager's message and the assistant's reply to `messages`.
- The agent receives the last 8 prior user/assistant turns as history, loaded *before* the
  current message is inserted.

#### FR-4 — Stateful refinement of a prior answer · Should

"Now only Kochi", "make it firmer", "in Hindi" refine the previous run rather than starting
over.

Acceptance criteria:
- With history present, a refinement-shaped opener ("now", "only", "make it", "instead",
  "top N", "warmer", "shorter"…) that carries no independent task vocabulary classifies as
  `follow_up`.
- A `follow_up` is rewritten into a standalone task using the previous user turn before
  planning; the rewritten query is emitted as an `info` event. If the rewrite call fails,
  the fallback concatenates the previous task with the refinement rather than dropping it.
- Not covered by an automated test.

#### FR-5 — Out-of-scope guardrail · Should

Acceptance criteria:
- An off-domain request (weather, poetry, sport, code) is answered with a short redirect
  describing what the copilot does; no tools run and no counters are scored.
- If the LLM call fails, a deterministic redirect string is used.

#### FR-6 — Chitchat handling · Could

Acceptance criteria: a greeting or thanks produces a short conversational reply naming the
manager, with zero candidates and a deterministic fallback when no provider answers.

#### FR-7 — Capability FAQ answering · Should

Acceptance criteria:
- A curated FAQ set of at least 50 entries is bundled and grouped by category
  (currently 64 entries, exposed at `GET /meta/faqs`).
- A capability question ("what can you do", "which modules can you recommend", "can you
  send WhatsApp messages") answers from that set and **must not** run the scoring pipeline —
  `candidates` is empty and the reply is non-empty.

### 4.2 Planning and execution

#### FR-8 — Structured plan · Must

The manager's ask becomes a typed plan before any tool runs.

Acceptance criteria:
- The plan is a Pydantic `Plan` with `intent`, `target_module`, `city_filter`, `tone`,
  `language` and 1–5 typed `steps` (`step`, `tool`, `args`, `expected`, `done`).
- Malformed steps are dropped rather than crashing the run; `city_filter` accepts a string
  or list and normalises to a list; an unknown or missing `target_module` falls back to
  `MOD-RECON`.
- The plan is emitted as a `plan` trace event, tagged `source: "default"` when the planner
  fell back to the canned plan.
- A run that produces no steps terminates with an explicit error rather than proceeding.
- Draft language is a plan field: "draft in Hindi" sets `plan.language == "Hindi"`.

#### FR-9 — Bounded tool-execution loop · Must

Acceptance criteria:
- Steps execute in order; each dispatch emits `tool_call` (with arguments) and each return
  emits `tool_result` (with `source` and `latency_ms`).
- The loop is capped by `AGENT_MAX_ITERATIONS` (default 6) independently of step count, so
  a replanning cycle cannot run unbounded.

#### FR-10 — Critic verdict and single replan · Must

Acceptance criteria:
- After each tool result the critic emits a `critic` event with `verdict`, `replan` and
  `notes`.
- A failed tool call, or `query_counters` returning zero rows, produces `verdict: fail` and
  requests a replan.
- At most **one** replan per run: the failing `query_counters` step is retried with
  `min_tpv`, `min_pending_settlement`, `min_daily_txns` and `cities` stripped and
  `limit: 200`, and the failed record is popped so the retry is recorded cleanly.
- Not covered by an automated test.

#### FR-11 — Typed tool registry · Must

Acceptance criteria:
- Exactly 8 tools are registered by decorator at import time; duplicate registration of a
  name raises.
- `GET /tools` returns name, description, input JSON schema and output JSON schema for each.
- Every invocation validates arguments against the tool's input model and returns
  `{"ok": false, "error": "invalid_args: …"}` instead of executing on unvalidated input.
- Every invocation runs under `asyncio.wait_for(AGENT_TOOL_TIMEOUT_SECONDS)` (default 15s)
  and returns a structured `timeout` envelope rather than hanging the run.
- An unknown tool name returns `tool_not_found:<name>`; a raising tool returns
  `<Type>: <message>` — neither propagates as an unhandled exception.

#### FR-12 — Direct tool invocation · Could

Acceptance criteria: `POST /tools/{name}` invokes one tool with a raw JSON payload through
the same validation, timeout and envelope as the agent path.

### 4.3 The eight tools

#### FR-13 — `query_counters` · Must

Structured search over the counter network.

Acceptance criteria:
- Filters: `cities`, `tiers`, `counter_types`, `min_tpv`, `max_tpv`,
  `min_pending_settlement`, `min_daily_txns`, `max_daily_txns`, `settlement_cycles`,
  `exclude_modules`, `limit` (1–1000, default 200). All AND-combined; scalars are accepted
  where a list is expected.
- Filters are honoured exactly: a Mumbai + ferry/bus query returns only counters whose city
  is Mumbai and whose type is in `{ferry, bus}`.
- Zero-valued numeric filters are treated as unset.
- Two-stage relaxation: if the strict filter set returns zero rows, TPV / daily-txn /
  settlement-cycle filters are dropped and retried; if that still returns zero, only
  `exclude_modules` and a limit survive.
- The result carries `source`, `rows` and `latency_ms`.

#### FR-14 — `compute_counter_value` · Must

Acceptance criteria:
- Returns a 0–1 `value_score` per counter id plus a `ScoreBreakdown` list.
- Population data is fetched in 2 bulk queries regardless of counter count, not 2 per
  counter.
- Results are sorted by score descending.

#### FR-15 — `predict_module_propensity` · Must

Acceptance criteria:
- Returns a 0–1 propensity per `(counter, module)` with a feature breakdown; defaults to
  `MOD-RECON` when the module id is blank.
- Counters, transactions, live modules and field notes are fetched in 4 concurrent bulk
  queries.
- Behavioural check: for `MOD-RECON`, the leaking ferry counter (`CTR-0001`) scores ≥ 0.5
  and strictly above the healthy retail counter (`CTR-0003`).

#### FR-16 — `recommend_modules` · Must

Acceptance criteria:
- Recommends among the module catalogue (or an explicit candidate list), restricted to
  actionable categories, **skipping any module already live on that counter**.
- Each recommendation carries `eligible` and human-readable `reasons`, checking:
  `min_monthly_tpv`, `min_daily_txns`, `max_daily_txns`, allowed `counter_type`,
  `min_tenure_months`, merchant KYC status and allowed `settlement_cycle`. Per-module
  eligibility JSON overrides the catalogue column.
- Ranking is `(eligible, propensity)` descending, so an ineligible module can never outrank
  an eligible one.
- Behavioural check: the metro TVM cluster (`CTR-0004`) recommends `MOD-ETICKET` first.

#### FR-17 — `search_field_notes` · Must

Acceptance criteria:
- Hybrid retrieval over field-visit notes and support tickets: dense (Chroma) and lexical
  (BM25) rankings fused by reciprocal rank fusion (K=60), then MMR re-ranked
  (λ=0.7) when embeddings are available.
- Every match returns a citation id of the form `FN-<counter_id>-<hash>` plus `counter_id`,
  `text`, `fused_score`, `bm25` and `dense`.
- Optional `counter_id` filter restricts the pool; an unmatched filter returns an empty
  list, not an unfiltered one.
- `source` reports the actual mode in use (`chroma+bm25` or `bm25`).

#### FR-18 — `get_counter_transactions` · Must

Acceptance criteria:
- Returns raw transactions plus aggregates: `total_collected`, `total_settled`,
  `cash_share`, `digital_share`, per-channel `channel_split`, `largest_ticket`,
  `void_reissue_count`, `refund_total`, `txn_count`.
- Collections are `ticket_sale`, `retail_bill`, `topup`; payouts are `settlement_payout`;
  `void_reissue` and `refund` are counted separately and never inflate collections.
- Behavioural check on `CTR-0001`: `void_reissue_count >= 1` and settlement mismatch
  (`1 - settled/collected`) exceeds 2%.

#### FR-19 — `generate_whatsapp_message` · Must

Acceptance criteria:
- The generation prompt receives only that counter's real profile, the module record and
  the supplied top feature contributions — never the whole candidate set.
- Supports tone (`warm | formal | professional | concise`) and target language, writing the
  entire message in the requested language while preserving the counter's name.
- Every number in the output is checked against the source context; numbers that do not
  appear there (within a 5% or ±1 rounding tolerance) are mechanically replaced with `—`
  and the draft is reported `compliance.ok == false` with the offending values listed.
- A missing counter or module returns a structured `counter_or_module_not_found` result
  rather than an invented message.
- The provider that actually answered is reported as `llm_route`.

#### FR-20 — `create_outreach_batch` · Must

Acceptance criteria: persists drafts against a session in `outreach_drafts` with status
`draft`, returning the created ids. This is the only write path to the outreach store.

### 4.4 Scoring, ranking and recommendation

#### FR-21 — Explainable value score · Must

Acceptance criteria:
- `value_score` is a sigmoid over 4 z-scored features — `tpv_z`, `digital_share_z`,
  `tenure_z`, `txn_velocity_z` — z-scored against the counters currently in play, so the
  score is relative to the area's own network.
- Weights live in `weights.yaml`; each feature returns `feature`, `value`, `contribution`,
  `direction` and a plain-language `rationale`.

#### FR-22 — Explainable module propensity · Must

Acceptance criteria:
- A weighted logistic over a named feature vocabulary of 25 features, of which 19 carry
  weights across the 8 per-module weight sets in `weights.yaml`.
- Rate features are band-normalised so they move the logit meaningfully (e.g. void/reissue
  2%→15%, mismatch 2%→20%, cash spike +5pp→+35pp).
- A module's own trigger signal dominates its weight set; `MOD-ANALYTICS` carries **negative**
  weights on settlement mismatch and cash-share spike, so a bleeding counter is not
  recommended a dashboard.
- Changing `weights.yaml` changes the ranking with no code change.

#### FR-23 — Leakage risk scoring with severity bands · Must

Acceptance criteria:
- `leakage_risk` is a plain weighted sum (not a logistic) over 8 features already in [0,1]
  with weights summing to 1.0, so the score reads directly as "share of the maximum leakage
  evidence visible for this counter": `settlement_mismatch_rate` 0.27, `cash_share_spike`
  0.23, `void_reissue_rate` 0.21, `receipt_issuance_gap` 0.12, `peak_hour_downtime` 0.08,
  `pending_settlement_backlog` 0.04, `field_note_stress_signal` 0.03, `refund_ratio` 0.02.
- Bands: `clear` < 0.25 ≤ `watch` < 0.45 ≤ `elevated` < 0.65 ≤ `severe`.
- On every candidate, `leakage_risk` is a float in [0,1] and `leakage_band` is one of those
  four values.
- Leakage is computed from **transaction evidence**. Complaint-derived signal
  (`field_note_stress_signal`) carries 3% of the total weight and is corroboration, not
  evidence — a counter with a spotless support history can still score `severe`.
- Leakage feature builders are imported from the propensity module rather than
  reimplemented, so the two scorers cannot drift.
- No user-facing string derived from this score asserts fraud (NG2).

#### FR-24 — Field-note sentiment and escalation flag · Should

Acceptance criteria:
- Field notes for a counter resolve to `sentiment` ∈ `{positive, neutral, negative}` and a
  boolean `escalate`.
- Sentiment analysis produces **no** leakage score — the two signals are separate by
  construction.
- A counter with unresolved negative notes yields `sentiment == "negative"` and
  `escalate == true`; a counter with routine notes does not escalate.

#### FR-25 — Candidate synthesis and action-queue ranking · Must

Acceptance criteria:
- Tool outputs are merged per counter into a `CandidateRecord` carrying profile fields, all
  three scores, the recommended module, top feature contributions, leakage features,
  citations, sentiment, `opportunity_value`, `next_action` and `priority`.
- Composite weighting is intent-aware: remediation modules (`MOD-RECON`, `MOD-OFFLINE`) fix
  a live leak, so propensity dominates (0.2 value / 0.8 propensity); other modules use
  0.4 / 0.6.
- The list is truncated to `AGENT_TOP_K_CANDIDATES` (default 10) by composite score, then
  **re-ranked for action** by `(priority asc, leakage desc, composite desc)`.
- `next_action` and `priority` are derived deterministically: leakage ≥ 0.45 or an
  escalation flag → "call the supervisor within 48h" at priority 1; propensity ≥ 0.6 →
  message today; ≥ 0.4 → visit this week; otherwise monthly review.
- `opportunity_value` is `monthly TPV × module take rate × 12`, rounded to ₹1,000, and is
  labelled indicative — it is a prioritisation aid, never a commercial quote.
- Each candidate is emitted as its own `candidate` trace event as it is produced.
- Hero counters must reach the top through this arithmetic, never through a fixture: for a
  Mumbai leakage query, `CTR-0001` appears in the candidate set.

#### FR-26 — Written summary with deterministic fallback · Should

Acceptance criteria:
- The summary is written by the reasoning route from the ranked candidates.
- When the route resolves to the mock provider, or the model returns fewer than 20
  characters, a deterministic function builds the summary from the real candidates — named
  counters, module, indicative ₹ value, top signal, next action and a leakage watch list.
  A reviewer running keyless never sees generic filler, and the fallback is a function, not
  a model.
- An empty candidate set produces an explicit "no counters matched, try loosening X"
  message rather than an LLM summary of nothing.

### 4.5 Knowledge base and retrieval

#### FR-27 — Grounded knowledge answers with citations · Must

Acceptance criteria:
- A corpus of exactly 3 reference documents is indexed: payments & GST compliance, counter
  performance methodology, field-operations FAQs (`backend/new_features/`).
- `POST /knowledge/ask` and the in-chat `knowledge` route answer from retrieved document
  sections and return the `sources` they used.
- Questions on the GST e-invoicing threshold, T+1 settlement and NCMC at an AFC gate each
  return a non-empty, cited answer.
- When no LLM is available the answer is extractive from the documents, so answers always
  come from the corpus rather than model memory.
- The corpus explicitly labels where a threshold is this product's convention rather than
  statute — the ₹5L TPV prospecting trigger is marked as **not** the ₹5 Cr e-invoicing
  mandate. The system must not launder a convention into a regulation.
- Query input is capped at 500 characters and rejected when empty.

#### FR-28 — Named-counter resolution · Should

Acceptance criteria:
- "What modules does Gateway Jetty run?", "Tell me about Gateway Jetty Counter 3" and
  "What is the pending settlement at Gateway Jetty?" all resolve to that counter's live
  record and report `Counter Record` as a source.
- A generic policy question ("what is zero MDR") resolves **no** counter record.
- Generic domain vocabulary that also appears in counter names ("gate", "jetty", "depot",
  "metro", "settlement") is excluded from name resolution, and a name token shared by more
  than 8 counters is treated as generic.
- A counter that does not run a module is reported truthfully rather than invented.

#### FR-29 — Knowledge source discovery · Could

Acceptance criteria: `GET /knowledge/sources` lists the indexed documents and a set of
suggested questions; the count is 3.

### 4.6 Outreach and human-in-the-loop

#### FR-30 — Compliance-validated draft generation at fanout · Must

Acceptance criteria:
- One draft per surfaced candidate, generated concurrently via `asyncio.gather` bounded by
  a semaphore of 4 so free-tier provider limits hold.
- Each draft is emitted as a `draft` trace event with its compliance report and
  `llm_route`, and persisted through FR-20.
- **Every** draft in a run passes the numeric-grounding validator (`compliance.ok == true`)
  and is non-empty.
- With no candidates, drafting is skipped with an explicit `info` event rather than
  producing empty drafts.

#### FR-31 — Human-in-the-loop approval · Must

Acceptance criteria:
- There is **no send path anywhere in the codebase**. Nothing in the product transmits a
  message to a merchant or supervisor.
- `POST /outreach/approve` marks a list of `draft_ids` approved and returns 400 on an empty
  list. `PATCH /outreach/{draft_id}` replaces a draft's message and returns 404 for an
  unknown id. `GET /outreach/{session_id}` lists every draft in a session.
- **Implemented (post-session follow-up):** the drawer is now bound to the stored rows, not
  local state. The row is resolved from `GET /outreach/{session_id}` by counter id — the SSE
  `draft` event deliberately carries no row id, because the responder writes the batch only
  when the run finishes. `PATCH` persists in-drawer edits with an explicit saved/unsaved
  indicator; `Approve` calls `POST /outreach/approve` and then re-reads the row, because the
  endpoint echoes the request size rather than the rows it touched. An approved draft is
  visually distinct and editing it voids that approval until it is made again. Failures
  surface in a `role=alert` banner with a retry and never leave the UI claiming a state the
  server does not have. There is still **no send path anywhere**: "Send on WhatsApp" is now
  gated on approval and opens the `wa.me` link with the message pre-filled — the human
  presses Send in their own WhatsApp client. (Wired in the `feat(outreach)` commit.)

#### FR-32 — Draft review surface · Should

Acceptance criteria:
- The counter drawer renders the draft in a WhatsApp-style preview with a compliance badge
  — "All numbers grounded" when `compliance.ok`, otherwise a redaction badge naming how
  many numbers were stripped.
- The manager can edit the text inline, copy it, and open a WhatsApp chat pre-filled with
  it. Demo phone numbers are mapped from a gitignored `VITE_DEMO_PHONES` env value so real
  numbers never enter the repository; without a mapping the counter's stored number is used.
  In-drawer edits now persist to the store (FR-31).

### 4.7 Trace and observability

#### FR-33 — Typed event stream · Must

Acceptance criteria:
- Every node emits a typed `TraceEvent` (`event`, `ts`, `data`, `llm_route`, `latency_ms`).
- Event kinds actually emitted: `info`, `plan`, `tool_call`, `tool_result`, `critic`,
  `synth`, `candidate`, `draft`, `final`, plus `error` from the endpoint. (`router` and
  `token` are declared in the type but emitted by no node — a client may ignore them.)
- The first SSE frame is always `info` carrying `session_id`.
- `llm_route` names the provider that actually answered and is null on events no model
  produced.
- The stream checks client disconnection between events and stops the run when the tab
  closes, rather than continuing to spend tokens.

#### FR-34 — Trace persistence and replay · Must

Acceptance criteria:
- Every event of a run is persisted to `agent_traces` — including events already drained to
  the wire, via a separate never-drained archive — alongside the messages and drafts.
- `GET /trace/{session_id}` returns events, messages and drafts for the session, with JSON
  columns parsed, and 404s when the session has neither events nor messages.

#### FR-35 — Live trace panel · Should

Acceptance criteria: the UI renders plan, tool_call, tool_result, critic and synth events as
they arrive, showing the datasource `source` badge, `llm_route` and per-event latency;
high-volume events (`candidate`, `draft`, `info`, `token`) are filtered out of the visible
timeline. Not visually verified (see §8).

#### FR-36 — Datasource provenance on every result · Must

Acceptance criteria: every datasource result carries a `source` string; a failover result is
tagged `sqlite(failover)` distinctly from a direct `sqlite` read, and the tag propagates to
the `tool_result` event and the counter 360 payload.

### 4.8 Interface

#### FR-37 — Three-pane workspace · Should

Acceptance criteria: on large viewports, sessions / chat / candidates render as a three-column
grid; below the `lg` breakpoint the panes collapse to one at a time with a bottom tab bar.
Not visually verified.

#### FR-38 — Counter 360 drawer · Must

Acceptance criteria:
- `GET /counters/{counter_id}` returns profile, recent transactions (6 months), live Billeasy
  modules and field notes, source-tagged, and 404s for an unknown id.
- The drawer renders that payload plus, when the counter is in the current run: the score
  breakdown, the rationale, the leakage band and percentage, the escalation flag, and the
  WhatsApp draft.
- The leakage badge is shown only when the band is not `clear`, and its tooltip states the
  score's meaning ("share of the maximum revenue-leakage evidence visible for this counter").
- Phone numbers are masked in the profile view.
- Each block is wrapped in an error boundary so one failing section cannot blank the drawer.

#### FR-39 — Score breakdown visualisation · Should

Acceptance criteria: top feature contributions render as a labelled breakdown with the
feature name, its contribution and its rationale — the same values the API returned, not a
re-derived figure. Not visually verified.

#### FR-40 — Capability guide · Could

Acceptance criteria: `GET /meta/capabilities` returns the domain description, 10 capability
statements, the 8 modules, 6 example prompts, the FAQ count and live component status
(active datasource, live LLM providers, retrieval mode); the guide panel renders it.

#### FR-41 — Knowledge modal · Could

Acceptance criteria: an in-app modal queries `POST /knowledge/ask` and shows the answer with
its sources, seeded by the suggested questions from `GET /knowledge/sources`.

#### FR-42 — Session sidebar · Could

Acceptance criteria: recent sessions are listed and selecting one loads its persisted trace
via `GET /trace/{session_id}`.

### 4.9 Access

#### FR-43 — Shared-password gate · Must

Acceptance criteria:
- `POST /auth/verify` exchanges the shared password for a token (the token is the password);
  the UI stores it and sends it as `X-Access-Token`.
- Every data router carries `dependencies=[Depends(require_token)]` at router level, so a new
  endpoint added to an existing router is protected by construction. Only `/`, `/healthz`,
  `/status` and `/auth/verify` are open.
- A valid header authenticates; a missing header 401s; a credential in a `?token=` query
  string is **rejected**.

#### FR-44 — Component status · Should

Acceptance criteria: `GET /status` reports the active datasource name, its health, and which
LLM providers are live; the UI top bar reflects it.

---

## 5. Non-functional requirements

#### NFR-1 — Explainability · Must

Every score presented to a manager decomposes into named, weighted contributions.

Acceptance criteria:
- `value`, `propensity` and `leakage` each return a list of `ScoreBreakdown`
  (`feature`, `value`, `contribution`, `direction`, `rationale`) alongside the scalar.
- Contributions are `weight × feature_value` and the weights are data in `weights.yaml`,
  not constants in code — editing that file changes the ranking without a code change.
- No LLM computes, adjusts or ranks any score. The model chooses what to look at and how to
  phrase it; arithmetic and ordering are deterministic Python. A bad model response can
  therefore produce a bad *plan* (visible in the trace, catchable by the critic) but never a
  wrong number presented confidently.

#### NFR-2 — Auditability · Must

Acceptance criteria: any completed run is fully reconstructable from `GET /trace/{id}` —
plan, every tool call with its arguments, every result with its source and latency, critic
verdicts, candidates, drafts and the final summary. Nothing that reaches the UI is absent
from the persisted trace.

Limitation, stated plainly: the trace records what the **agent** did. It does not record who
asked, who viewed a counter, or who approved a draft — there is no actor audit log (§7).

#### NFR-3 — Keyless operation · Must

Acceptance criteria:
- With an entirely empty environment the app boots, seeds itself and runs the complete agent
  on a deterministic mock provider — plan, tools, critic, synthesis, drafting.
- All six test files pass keyless (verified: all six exit 0 on a clean checkout with no API
  keys and no Databricks credentials).
- `/status` reports `mock` when no provider key is set.

#### NFR-4 — Datasource failover with a circuit breaker · Must

Acceptance criteria:
- Databricks is the primary only when host, HTTP path and token are all set; otherwise SQLite
  is used directly with no error path.
- Any primary failure fails over to SQLite for that call and trips a **60-second** breaker,
  so a wedged warehouse degrades the app once rather than once per tool call. The Databricks
  client itself runs under a 5s per-query timeout.
- Failover results are tagged `sqlite(failover)` (FR-36).
- Health is true if either source is healthy.
- Not covered by an automated test — no Databricks fixture exists in this repo.

#### NFR-5 — Retrieval degradation · Should

Acceptance criteria:
- When Chroma is unavailable (not installed, or its memory footprint exceeds the host),
  retrieval falls back to BM25-only, logs the reason once, and reports `bm25` as its mode.
  The deployed default is BM25-only.
- Retrieval quality is visibly weaker in that mode and this is not hidden: a question about
  NCMC at an AFC gate can land in the chargebacks material. Citations remain honest; recall
  does not.
- Exercised implicitly (the test environment has no `chromadb`) but not asserted.

#### NFR-6 — Failure containment · Must

Acceptance criteria: a tool timeout, a tool exception, an unknown tool, a failed LLM call, a
failed retrieval and a failed field-note lookup each degrade to a structured result or a
documented fallback. No single node failure aborts a run without an `error` event.

#### NFR-7 — Latency · Should — **indicative, not benchmarked**

Acceptance criteria (all local, keyless, on the seeded 500-counter dataset with BM25-only
retrieval and a warm database):
- A full task run — plan, 5 tool calls, critic passes, synthesis, 10 candidates, 10 drafts —
  completes in single-digit seconds. Observed: **2.9 s** on the machine this document was
  written on; the README records ~5.5 s from an earlier run.
- **There is no benchmark harness, no percentile measurement and no measurement under a real
  LLM provider.** These are single observations on one machine, offered as an order of
  magnitude only. With live providers, latency is dominated by provider round-trips and is
  not characterised here.
- Structural properties that do exist: bulk fetches are batched (2 or 4 queries regardless of
  counter count), draft generation is a bounded parallel fanout, and every tool runs under a
  15s ceiling.

#### NFR-8 — Authentication hardening · Must

Acceptance criteria:
- The password comparison uses `hmac.compare_digest`; a missing token short-circuits to 401
  before any comparison.
- 8 failed attempts from one client inside a 5-minute window lock that client out with `429`
  and a `Retry-After` header; a successful login clears the counter.
- The credential is accepted from the `X-Access-Token` header only. A `?token=` query string
  is rejected, because query strings land in proxy logs, browser history and Referer headers.
- Honest limits: the throttle is in-memory and therefore per-process — correct for a
  single-worker deployment, and it must move to Redis or the edge behind replicas. The client
  key falls back to the first `X-Forwarded-For` hop, which a direct caller can spoof; this is
  a brute-force speed bump, not an access control.

#### NFR-9 — CORS allowlist · Must

Acceptance criteria: allowed origins come from `APP_CORS_ORIGINS` and there is **no `*`
fallback**. An empty configuration allows no origin rather than every origin, and
`allow_credentials` is enabled only when an explicit list exists. A `*` in the effective
origin list fails the test suite.

#### NFR-10 — Input validation at every boundary · Must

Acceptance criteria: chat bodies (2000 chars), knowledge bodies (500 chars), every tool input
model and every request model are Pydantic-validated; unvalidated input never reaches a
handler or a query.

#### NFR-11 — Parameterised SQL · Must

Acceptance criteria: no value is concatenated into a query. Where an f-string appears it
interpolates a generated run of `?` placeholders for an `IN (…)` clause and the values
themselves are driver-bound. On the Databricks adapter the only interpolated identifiers are
the catalog and schema names from configuration.

#### NFR-12 — Configuration and secrets · Must

Acceptance criteria: all configuration flows through one `pydantic-settings` class — no
scattered `os.environ` reads. Every variable is optional; defaults produce a working keyless
system. `.env`, `.env.local` and `.env.*.local` are gitignored with a `!.env.example`
exception, so only placeholder files are tracked.

#### NFR-13 — Deterministic dataset · Must

Acceptance criteria:
- The SQLite database self-seeds on first boot from a fixed seed (`Faker.seed(7)`,
  `random.seed(7)`), so a fresh clone reproduces the same network and the same ranking.
- Verified shape of the seeded network: 500 counters across 14 cities, 15,128 transactions,
  137 field notes, 8 modules, 254 live counter-module rows.
- The data is geographically coherent — each city carries only the transit modes it actually
  runs, named after its real terminals, under the operator that actually runs them — and
  counter names are unique across the network, because the name is what the knowledge base
  resolves against.
- Five hero counters are hand-built so the scorers surface them **by computing real signals**
  from seeded transaction rows, never by hardcoding a score. Changing `weights.yaml` changes
  the ranking; that is the check to run against a suspicion that the demo is staged.
- The data is synthetic. No Billeasy data was used or is required.

#### NFR-14 — Responsive interface · Should

Acceptance criteria: the workspace is a three-column grid at `lg` and above and collapses to
a single pane with a bottom tab bar below it; the counter drawer is full-width on small
screens and a fixed panel above `sm`; header controls progressively hide their labels at
narrow widths. Verified by reading the layout code and by a clean production build only —
not verified in a browser at any viewport (§8).

#### NFR-15 — Accessibility · Should — **partial**

What exists, verified in the source: `aria-label` on the send and theme-toggle controls,
`aria-pressed` on the theme toggle, `aria-current` on the active mobile tab, keyboard submit
handlers on the chat and knowledge inputs, and a `prefers-reduced-motion` block that disables
animation.

What does **not** exist and should not be claimed: no focus trap or `Escape` handling on the
drawer or modal, no `role="dialog"`/`aria-modal`, no skip link, no live region announcing
streamed agent output, no audit against WCAG at any level, and no screen-reader or contrast
testing. Accessibility is best-effort and unverified.

#### NFR-16 — Type safety · Should

Acceptance criteria: the frontend compiles under `strict: true` with `noUnusedLocals` and
`noUnusedParameters`; `npx tsc --noEmit` exits clean (verified) and `npm run build` succeeds.
Backend contracts are Pydantic models shared between tools, the agent state, the API and the
SSE payloads, so one type definition serves validation, the tool schema shown to the planner,
and the wire format.

#### NFR-17 — Provider routing and outbound rate limiting · Should

Acceptance criteria:
- Routing is by cognitive load, not by hardcoding a model into a node: `reasoning` →
  Claude → Gemini → Groq → Mock; `generation` → Groq → Claude → Gemini → Mock; `embed` →
  Gemini → Mock (no Anthropic embeddings endpoint exists).
- Every provider sits behind one `LLMClient` port with a per-provider token bucket, one
  retry, then fall-through to the next provider, terminating at the mock.
- The provider that actually answered is recorded on the trace event.

#### NFR-18 — Zero-provisioning startup · Should

Acceptance criteria: on boot the app creates and seeds its database if empty, registers all
tools, starts RAG indexing in the background so the first request is not blocked, and
optionally self-pings to stay warm on a sleeping free tier. No database, warehouse, vector
store or API key needs to be provisioned first.

#### NFR-19 — Multilingual drafting · Should

Acceptance criteria: the plan carries a target language; the generator writes the entire
message in that language and script while preserving the counter's name verbatim. Verified
for Hindi at the plan level; the produced message text is not asserted in any test.

---

## 6. Domain constraints and regulatory context

Billeasy operates inside the Indian payments and transit-ticketing regime. This section
states what that means for the product and — critically — **what the code actually
enforces**.

### 6.1 The honest split

| Constraint | Status in this build |
| --- | --- |
| GST e-invoicing / IRN thresholds | **Documented + modelled.** Explained in the corpus; `receipt_issuance_gap` models the signal. No invoice is generated, reported to an IRP, or validated. |
| B2C dynamic-QR mandate | **Documented only.** |
| T+1 settlement | **Documented + modelled.** `settlement_cycle` is a counter field and a filter; `settlement_mismatch_rate` and `pending_settlement_backlog` model the failure modes. The product settles nothing and enforces no cycle. |
| Zero MDR on UPI and RuPay debit | **Documented + modelled.** Explained in the corpus; channel mix feeds the scorers. No MDR is computed, charged or waived. |
| NCMC / One Nation One Card, AFC gates | **Documented + modelled.** `ncmc_share` is a propensity feature and drives `MOD-ETICKET`. No NCMC transaction is processed. |
| RBI Payment Aggregator framework, nodal vs escrow | **Documented only.** No money is held or moved. |
| Merchant KYC / re-KYC | **Modelled.** `kyc_status` is a field and an eligibility check inside `recommend_modules`. No KYC is performed or verified. |
| DPDP Act 2023 consent, TRAI DLT registration, WhatsApp business-initiated opt-in | **Documented, NOT enforced.** The corpus covers the rules and the agent will explain them. **No code checks a consent flag before drafting.** |

### 6.2 What that means

**Essentially nothing regulatory is enforced in code.** The regulations shape the domain
model, the feature vocabulary and the knowledge corpus. They are not compliance controls.
Specifically:

- There is no consent register, no opt-in check and no DLT template registration. A draft is
  generated for any candidate the scorer surfaces.
- That is acceptable **only** because drafts are never sent (NG1, FR-31). A person reads
  every message and initiates the send in their own WhatsApp client, where the opt-in
  obligation sits with them. If an automated send path were ever added, a consent check would
  have to precede generation, not follow it.
- The single control that *is* mechanically enforced in the outreach path is numeric
  grounding (FR-19) — and that is a hallucination guard, not a regulatory one.
- The knowledge corpus deliberately marks its own conventions: the ₹5L monthly-TPV
  prospecting trigger is labelled a product heuristic and explicitly distinguished from the
  ₹5 Cr e-invoicing mandate. An agent that cites documents must not launder a convention into
  a regulation.

Do not read anything in this repository as evidence of GST, RBI, TRAI or DPDP compliance.

---

## 7. Explicitly out of scope for this build

| Item | One-line reason |
| --- | --- |
| Multi-tenancy, per-user auth and RBAC | One shared password, one principal; territory-scoped row-level security is the first production change, not a demo feature. |
| Real WhatsApp sending (Meta Cloud API) | A send path is the one capability whose absence is a safety property here — see NG1 and FR-31. |
| Trained ML scoring | No labelled leakage outcomes exist, so weights are transparent domain judgement; a trained model behind the same `Scorer` interface is next, A/B'd rather than assumed. |
| Real Billeasy data | The dataset is synthetic and deterministic by design so a reviewer can clone and run with nothing provisioned. |
| PII encryption at rest | Counter names, supervisor numbers and field notes sit in plain SQLite; gitignoring the database file is not protection. |
| General API rate limiting | Only `/auth/verify` is throttled — an authenticated caller can hammer `/chat/run` and burn the provider budget; per-principal quotas belong at the edge. |
| Actor audit log | `agent_traces` records what the agent did, not who asked, who viewed a counter, or who approved a draft. |
| Row-level access control | Nothing scopes `/counters/{id}`, `/trace/{id}` or `/outreach/{id}` to the caller's own territory or even to sessions they created. |
| CSRF defences | The token travels as a header from `localStorage`, so a browser will not auto-attach it cross-site; no token or `SameSite` policy formally addresses CSRF, and any XSS yields the credential. |
| Postgres / OLTP durability | SQLite WAL plus an optional Delta primary demonstrates the port and failover; it is a degraded read path, not a scale path. |
| OTLP tracing and alerting metrics | Structured logs and a persisted trace exist; plan-parse failure rate, critic replan rate, validator strip rate and p95 latency are not instrumented. |
| Per-counter seasonal baselines | Leakage is a trailing-window comparison, which will produce false positives around festival cash surges. |
| Browser and end-to-end UI testing | No browser automation was available in this environment — see §8. |

---

## 8. Acceptance / definition of done

### 8.1 Backend — six test files, all passing keyless

Run from `backend/` with `PYTHONPATH=.` and no API keys:

| Test file | What it establishes | Result |
| --- | --- | --- |
| `tests/test_smoke.py` | All 8 tools register; the Mumbai + ferry/bus filter returns only Mumbai ferry/bus counters and includes `CTR-0001`; value and propensity score; the leaking ferry counter outranks the healthy retail one for `MOD-RECON`; the metro cluster recommends `MOD-ETICKET`; transaction aggregates show the void/reissue pattern and a mismatch above 2%; a generated draft passes compliance | pass (exit 0) |
| `tests/test_agent_e2e.py` | Full run: a plan is produced, ≥4 tool calls execute, ≥1 candidate and ≥1 draft result; every candidate's `leakage_risk` is a float in [0,1] with a valid band; `CTR-0001` surfaces through scoring; **every** draft passes the numeric-grounding validator and is non-empty | pass (exit 0) |
| `tests/test_faq_routing.py` | ≥50 FAQs load (64 present); capability questions route to `faq`, produce zero candidates, and never run the scoring pipeline | pass (exit 0) |
| `tests/test_sentiment_lang.py` | Negative field notes yield `sentiment: negative` and `escalate: true`; routine notes do not escalate; sentiment produces no leakage score; a Hindi request sets `plan.language == "Hindi"` | pass (exit 0) |
| `tests/test_knowledge_base.py` | GST threshold, T+1 and NCMC questions answer with citations; a named counter resolves to its own record across three phrasings; a generic MDR question resolves no counter; exactly 3 sources load; 8 intent-routing cases classify correctly | pass (exit 0) |
| `tests/test_security.py` | A `?token=` credential is rejected and only the header authenticates; no token 401s; the 9th failed login in the window returns `429` with `Retry-After`; a correct password succeeds after reset; the CORS origin list contains no `*` | pass (exit 0) |

All six were executed while writing this document and all six exited 0 against the mock
provider with no Databricks credentials and no `chromadb` installed (BM25-only retrieval).

### 8.2 Frontend

- `npx tsc --noEmit` exits clean under `strict: true` (verified while writing this document).
- `npm run build` produces a production bundle (per README §16).

### 8.3 The honest caveat on the UI

**The UI was build-verified, not visually verified.** Types check, the production build
succeeds, the dev server serves, and every API payload the components consume was exercised
over HTTP — but **no browser automation was available in this environment and no screenshot
was taken**. No requirement in §4.8, and no visual or interaction claim in NFR-14 or NFR-15,
has been confirmed by looking at a rendered page. Treat every UI requirement as
"implemented and compiles", not "observed working".

### 8.4 Definition of done for this build

A requirement is done when: (a) the code exists and is reachable from a running system;
(b) its acceptance criteria are either asserted by one of the six test files or explicitly
marked `no automated coverage` in §9; and (c) nothing in this document, the README or the
write-up claims a behaviour the code does not have. Overclaiming fails the definition of done
even when the feature works.

---

## 9. Traceability matrix

`no automated coverage` means exactly that — the behaviour exists in code and was checked by
reading it or by hand, but no test asserts it.

### 9.1 Functional requirements

| ID | Requirement | Implementation | Test coverage |
| --- | --- | --- | --- |
| FR-1 | NL query intake | `backend/app/api/chat.py` | `test_agent_e2e.py` (via `run_agent`); endpoint shape — no automated coverage |
| FR-2 | Six-route intent classification | `backend/app/agent/nodes/intent.py`, `backend/app/agent/graph.py` | `test_knowledge_base.py` (8 routing cases), `test_faq_routing.py` |
| FR-3 | Sessions and history | `backend/app/api/sessions.py`, `backend/app/api/chat.py` | no automated coverage |
| FR-4 | Follow-up refinement | `backend/app/agent/nodes/planner.py`, `intent.py` | no automated coverage |
| FR-5 | Out-of-scope guardrail | `backend/app/agent/nodes/intent.py` (`run_guardrail`) | `test_knowledge_base.py` (routing only, not the reply) |
| FR-6 | Chitchat | `backend/app/agent/nodes/intent.py` (`run_chitchat`) | `test_knowledge_base.py` (routing only) |
| FR-7 | Capability FAQ | `backend/app/agent/nodes/faq.py`, `backend/app/agent/knowledge/faq_kb.py`, `backend/app/api/meta.py` | `test_faq_routing.py` |
| FR-8 | Structured plan | `backend/app/agent/nodes/planner.py`, `backend/app/agent/state.py`, `backend/app/agent/prompts/planner_system.md` | `test_agent_e2e.py`, `test_sentiment_lang.py` (language field) |
| FR-9 | Bounded execution loop | `backend/app/agent/graph.py`, `backend/app/agent/nodes/tool_executor.py` | `test_agent_e2e.py` (≥4 tool calls) |
| FR-10 | Critic and single replan | `backend/app/agent/nodes/critic.py` | no automated coverage |
| FR-11 | Typed tool registry | `backend/app/application/tool_registry.py`, `backend/app/tools/__init__.py` | `test_smoke.py` (registration, invocation) |
| FR-12 | Direct tool invocation | `backend/app/api/tools.py` | no automated coverage |
| FR-13 | `query_counters` | `backend/app/tools/query_counters.py`, `backend/app/infrastructure/datasource/sqlite.py` | `test_smoke.py` (filters, no leakage across city/type); relaxation — no automated coverage |
| FR-14 | `compute_counter_value` | `backend/app/tools/compute_value.py` | `test_smoke.py` |
| FR-15 | `predict_module_propensity` | `backend/app/tools/predict_propensity.py` | `test_smoke.py` (≥0.5 on `CTR-0001`, outranks `CTR-0003`) |
| FR-16 | `recommend_modules` + eligibility | `backend/app/tools/recommend_modules.py` | `test_smoke.py` (`MOD-ETICKET` for `CTR-0004`) |
| FR-17 | `search_field_notes` hybrid RAG | `backend/app/tools/search_field_notes.py`, `backend/app/infrastructure/rag/hybrid_retriever.py`, `mmr.py` | no automated coverage (exercised indirectly by `test_agent_e2e.py`) |
| FR-18 | `get_counter_transactions` | `backend/app/tools/get_counter_transactions.py` | `test_smoke.py` (void/reissue count, mismatch > 2%) |
| FR-19 | Grounded draft + validator | `backend/app/tools/generate_whatsapp.py`, `backend/app/scoring/compliance.py` | `test_smoke.py`, `test_agent_e2e.py` (every draft `compliance.ok`) |
| FR-20 | `create_outreach_batch` | `backend/app/tools/create_outreach_batch.py`, `backend/app/agent/nodes/responder.py` | no automated coverage |
| FR-21 | Value score | `backend/app/scoring/value.py`, `weights.yaml` | `test_smoke.py` |
| FR-22 | Propensity score | `backend/app/scoring/propensity.py`, `weights.yaml` | `test_smoke.py` |
| FR-23 | Leakage score and bands | `backend/app/scoring/leakage.py`, `weights.yaml` | `test_agent_e2e.py` (range + band on every candidate), `test_sentiment_lang.py` |
| FR-24 | Sentiment and escalation | `backend/app/scoring/sentiment.py` | `test_sentiment_lang.py` |
| FR-25 | Candidate synthesis and action ranking | `backend/app/agent/nodes/synthesizer.py`, `backend/app/agent/state.py` | `test_agent_e2e.py` (candidates, `CTR-0001` surfaced); `next_action` / `priority` / `opportunity_value` — no automated coverage |
| FR-26 | Summary with deterministic fallback | `backend/app/agent/nodes/synthesizer.py` (`_fallback_summary`) | no automated coverage |
| FR-27 | Grounded knowledge answers | `backend/app/knowledge_base/service.py`, `backend/new_features/*.md`, `backend/app/api/knowledge.py`, `backend/app/agent/nodes/knowledge.py` | `test_knowledge_base.py` |
| FR-28 | Named-counter resolution | `backend/app/knowledge_base/service.py` | `test_knowledge_base.py` |
| FR-29 | Knowledge sources | `backend/app/api/knowledge.py` | `test_knowledge_base.py` (source count) |
| FR-30 | Bounded draft fanout | `backend/app/agent/nodes/message_generator.py` | `test_agent_e2e.py` (drafts produced, all compliant) |
| FR-31 | Human-in-the-loop approval | `backend/app/api/outreach.py`; absence of any send path | no automated coverage; UI wiring under `frontend/src/features/drawer/useOutreachDraft.ts`, `WhatsAppPreview.tsx` — wired, tsc+build clean, not visually verified |
| FR-32 | Draft review surface | `frontend/src/features/drawer/WhatsAppPreview.tsx`, `frontend/src/lib/demoPhones.ts` | no automated coverage (not visually verified) |
| FR-33 | Typed event stream | `backend/app/agent/state.py`, `backend/app/agent/graph.py`, `backend/app/api/chat.py` | `test_agent_e2e.py` (event shapes); SSE transport — no automated coverage |
| FR-34 | Trace persistence and replay | `backend/app/agent/nodes/responder.py`, `backend/app/api/trace.py` | no automated coverage |
| FR-35 | Live trace panel | `frontend/src/features/trace/TracePanel.tsx`, `AgentFlowD3.tsx`, `frontend/src/hooks/useAgentStream.ts` | no automated coverage (not visually verified) |
| FR-36 | Datasource provenance | `backend/app/infrastructure/datasource/failover.py`, `base.py`, `sqlite.py` | `test_smoke.py` (source present on results) |
| FR-37 | Three-pane workspace | `frontend/src/pages/Dashboard.tsx` | no automated coverage (not visually verified) |
| FR-38 | Counter 360 drawer | `backend/app/api/counters.py`, `frontend/src/features/drawer/CounterDrawer.tsx` | no automated coverage |
| FR-39 | Score breakdown visualisation | `frontend/src/features/drawer/ScoreBreakdownChart.tsx` | no automated coverage (not visually verified) |
| FR-40 | Capability guide | `backend/app/api/meta.py`, `backend/app/agent/knowledge/capabilities.py`, `frontend/src/features/guide/GuidePanel.tsx` | no automated coverage |
| FR-41 | Knowledge modal | `frontend/src/features/knowledge/KnowledgeModal.tsx` | no automated coverage |
| FR-42 | Session sidebar | `frontend/src/features/sessions/SessionsSidebar.tsx` | no automated coverage |
| FR-43 | Shared-password gate | `backend/app/auth/middleware.py`, `backend/app/api/auth.py`, per-router `Depends(require_token)` | `test_security.py` |
| FR-44 | Component status | `backend/app/api/health.py` | no automated coverage |

### 9.2 Non-functional requirements

| ID | Requirement | Implementation | Test coverage |
| --- | --- | --- | --- |
| NFR-1 | Explainability | `backend/app/domain/models.py` (`ScoreBreakdown`), `backend/app/scoring/*.py`, `weights.yaml` | `test_smoke.py`, `test_agent_e2e.py` (breakdowns present on scores) |
| NFR-2 | Auditability / replay | `backend/app/agent/state.py` (archive), `nodes/responder.py`, `api/trace.py` | no automated coverage |
| NFR-3 | Keyless operation | `backend/app/infrastructure/llm/mock.py`, `router.py`, `backend/app/settings.py` | all six test files (they run keyless) |
| NFR-4 | Failover + 60s breaker | `backend/app/infrastructure/datasource/failover.py`, `databricks.py`, `factory.py` | no automated coverage |
| NFR-5 | Chroma → BM25 degradation | `backend/app/infrastructure/rag/hybrid_retriever.py` | no automated coverage (exercised, not asserted) |
| NFR-6 | Failure containment | `backend/app/application/tool_registry.py`, `backend/app/api/chat.py`, node-level `try/except` | no automated coverage |
| NFR-7 | Latency (indicative) | Bulk fetches in `backend/app/infrastructure/datasource/sqlite.py`; semaphore in `nodes/message_generator.py`; `AGENT_TOOL_TIMEOUT_SECONDS` | **no benchmark harness** — single manual observation only |
| NFR-8 | Auth hardening | `backend/app/auth/middleware.py`, `backend/app/auth/throttle.py` | `test_security.py` |
| NFR-9 | CORS allowlist | `backend/app/main.py`, `backend/app/settings.py` | `test_security.py` |
| NFR-10 | Input validation | `backend/app/application/tool_registry.py`, `api/chat.py`, `api/knowledge.py`, every tool input model | `test_smoke.py` (tool validation path) |
| NFR-11 | Parameterised SQL | `backend/app/infrastructure/datasource/sqlite.py`, `backend/app/api/*.py` | no automated coverage |
| NFR-12 | Config and secrets | `backend/app/settings.py`, `.gitignore`, `.env.example` | no automated coverage |
| NFR-13 | Deterministic dataset | `backend/app/db/seeders/faker_seed.py`, `hero_counters.py`, `backend/app/db/schema.sql` | `test_smoke.py`, `test_agent_e2e.py` (hero counters surface by computed score) |
| NFR-14 | Responsive UI | `frontend/src/pages/Dashboard.tsx`, `features/drawer/CounterDrawer.tsx` | no automated coverage (not visually verified) |
| NFR-15 | Accessibility (partial) | `frontend/src/components/ThemeToggle.tsx`, `features/chat/ChatPane.tsx`, `styles/globals.css` | no automated coverage; **no accessibility audit performed** |
| NFR-16 | Type safety | `frontend/tsconfig.json`, `backend/app/domain/models.py`, `backend/app/agent/state.py` | `tsc --noEmit` + `npm run build` (verified) |
| NFR-17 | Provider routing + rate limiting | `backend/app/infrastructure/llm/router.py`, `anthropic_client.py`, `gemini.py`, `groq.py` | no automated coverage (mock path exercised by all tests) |
| NFR-18 | Zero-provisioning startup | `backend/app/main.py`, `backend/app/db/sqlite_engine.py` | all six test files call `bootstrap()` |
| NFR-19 | Multilingual drafting | `backend/app/tools/generate_whatsapp.py`, `backend/app/agent/prompts.py` | `test_sentiment_lang.py` (plan language only, not the message text) |

---

*Requirements written against the code at the state of this repository. Where the code and a
prior document disagreed, the code won and the disagreement is noted in the relevant section.*

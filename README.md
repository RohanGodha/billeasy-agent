# Counter Copilot — Agentic Revenue Assurance for Billeasy

> **Every counter, accounted for.**
>
> A conversational agent for a Billeasy **Area Partner Manager**: find the counters
> leaking money today, show exactly *why* they're flagged, and draft a
> compliance-checked WhatsApp nudge to the supervisor — in one chat.

**The canonical demo:** Rohan, Area Partner Manager for Mumbai West, types

> *"Find ferry and bus counters in Mumbai leaking digital ticket revenue this month
> and draft WhatsApp nudges for the depot supervisors."*

…and gets a ranked list of counters, each with a transparent leakage breakdown, cited
field notes, and a grounded WhatsApp draft — in about five seconds, with no API keys.

> **Built for Billeasy's open AI challenge.** The story of *how* it was built — the
> tooling, the parallel-agent method, what broke — is in **[WRITEUP.md](WRITEUP.md)**.
> That's the document the brief actually asked for; this one is the product.

---

## Table of contents

1. [The problem & why this product](#1-the-problem--why-this-product)
2. [What it does](#2-what-it-does)
3. [Architecture](#3-architecture)
4. [Execution flow](#4-execution-flow)
5. [The domain model](#5-the-domain-model)
6. [Scoring: value, propensity, leakage](#6-scoring-value-propensity-leakage)
7. [AI patterns used](#7-ai-patterns-used)
8. [Tool design](#8-tool-design)
9. [API overview](#9-api-overview)
10. [Key design decisions](#10-key-design-decisions)
11. [Trade-offs and limitations](#11-trade-offs-and-limitations)
12. [Security considerations](#12-security-considerations)
13. [Project structure](#13-project-structure)
14. [Setup and run](#14-setup-and-run)
15. [Environment variables](#15-environment-variables)
16. [Verification — what actually passes](#16-verification--what-actually-passes)
17. [Deployment](#17-deployment)
18. [Demo scenarios](#18-demo-scenarios)
19. [Future work](#19-future-work)

---

## 1. The problem & why this product

Billeasy runs the digital payment and ticketing rail for offline India: retail POS
outlets and **government mass transit** — ferry jetties, bus depots, metro stations.
Money enters at the physical edge. A passenger buys a ferry ticket, a shopper pays at
a kirana counter, Billeasy captures it, issues a GST-compliant bill or e-ticket, and
settles **T+1** to the merchant or the transit authority, earning a take rate.

The edge is where it breaks:

| Failure mode | What it looks like in the data |
| --- | --- |
| **Fare leakage** — cash quietly bypassing the digital rail | cash share climbing against the counter's own baseline |
| **Void-and-reissue fraud** — issue, void, pocket the cash, reissue | void/reissue rate spikes on the same shifts |
| **Settlement mismatch** — captured ≠ settled | mismatch drifts past tolerance |
| **Payout backlog** — merchant unpaid, quietly churning | pending settlement ages |
| **GST non-compliance** — past the threshold, still not issuing bills | receipt-issuance gap |
| **Peak-hour downtime** — terminal dark during the rush | offline minutes in the peak window |

An Area Partner Manager owns 200–500 of these. Every morning the question is the same:
**which counters, and what do I say?**

Today that gets answered by a dashboard nobody opens and a gut feeling about which
supervisor called last. Existing tools answer it badly:

| Tool | Why it fails the Area Manager |
| --- | --- |
| POS / settlement dashboards | Backwards-looking aggregates; no per-counter "why", no action |
| Ticketing / AFC reports | Operational counts, not revenue-assurance reasoning |
| Generic BI (Metabase, Power BI) | You must already know what to ask |
| Support ticket queues | Only catches counters that *complained* — silent leaks stay silent |
| ChatGPT / a general copilot | No network data, invented numbers — unusable for a partner conversation |

**Counter Copilot** combines, in one chat surface:

1. **Live network access** over the counter estate (Databricks Delta with SQLite failover)
2. **Transparent leakage scoring** — every flag decomposes into weighted, named signals
3. **Compliance-validated drafting** — a validator strips any number the source data doesn't support
4. **Stateful refinement** — "now only Kochi", "make it firmer", "in Hindi"

**The claim:** it turns a morning of guesswork into a ranked action queue with an
audit trail — and it catches the counter that is leaking *without* having complained,
which is the one a ticket queue structurally cannot find.

---

## 2. What it does

Ask in plain language. The agent plans, calls typed tools, criticises its own results,
ranks counters, and drafts outreach:

```
Your priority counters:
- Gateway Jetty — Counter 3 (Mumbai) — Settlement & Fare Reconciliation
  (~₹1.5L/yr take-rate value): Tickets issued, voided and reissued — the classic
  cash-pocketing pattern. → Call the supervisor within 48h — elevated revenue leakage
- Kurla Depot — Counter 2 (Mumbai) — Settlement & Fare Reconciliation …

Leakage watch: Wadala Depot — Counter 8 (elevated, 57%), Gateway Jetty — Counter 3 (elevated, 54%)
```

> **Worth noticing:** the hand-built demo counter (Gateway Jetty) ranks **second**. It is
> beaten by *Wadala Depot — Counter 8*, a randomly generated counter that happened to be
> seeded with a worse leakage profile. That is the check to run if you suspect the demo
> is staged — the heroes are engineered to be *findable*, not to win.

> Note: that summary is the **deterministic fallback**, which is what you see on a
> keyless run. The synthesizer substitutes it whenever the route resolves to the mock
> provider, so a reviewer never gets generic filler — but it is a function, not a model.
> With a real key the summary is LLM-written from the same ranked candidates.

with, per counter, a breakdown like:

| feature | contribution | why |
| --- | --- | --- |
| `void_reissue_rate` | 0.210 | Tickets issued, voided and reissued — the classic cash-pocketing pattern |
| `cash_share_spike` | 0.187 | Cash share jumped versus this counter's baseline — fares may be bypassing the digital rail |
| `settlement_mismatch_rate` | 0.056 | ₹ captured at the counter does not reconcile with ₹ settled |

and a ready draft:

> *Hello Gateway Jetty — Counter 3 team, we're seeing more of your collections coming
> in as cash lately. Our Settlement & Fare Reconciliation would close that gap and keep
> every sale on the digital rail. Can I call you this week to walk through it? — Rohan*

**Human-in-the-loop by design.** The agent drafts; the manager reviews and presses send.

---

## 3. Architecture

```
                    ┌──────────────────────────────────────┐
                    │  Vercel  (React + Vite + Tailwind)   │
                    │  /login (password gate)              │
                    │  /  → 3-pane workspace               │
                    │  Streaming via fetch-event-source    │
                    └──────────────┬───────────────────────┘
                                   │  HTTPS, SSE, X-Access-Token
                    ┌──────────────▼───────────────────────┐
                    │  Render Web Service (FastAPI/Uvicorn)│
                    │  • Auth middleware (constant-time)   │
                    │  • Async everywhere                  │
                    │  • Agent orchestrator (DAG)          │
                    │  • Hexagonal ports + adapters        │
                    │  • Chroma (file, on mounted disk)    │
                    │  • SQLite WAL  (on mounted disk)     │
                    │  • Self-ping keep-alive              │
                    └──┬──────────┬──────────────┬─────────┘
                       │          │              │
          ┌────────────┘          │              └────────────┐
          ▼                       ▼                           ▼
┌─────────────────────┐  ┌──────────────────────┐  ┌──────────────────────┐
│ LLM Router          │  │ DataSource Failover  │  │ Hybrid Retriever     │
│ ─ Claude (reasoning)│  │ ─ Databricks SQL     │  │ ─ Chroma (dense)     │
│ ─ Gemini 2.0 Flash  │  │   Connector (5s TO)  │  │ ─ BM25 (lexical)     │
│ ─ Groq Llama 3.3 70B│  │ ─ SQLite WAL fallback│  │ ─ RRF + MMR re-rank  │
│   (parallel drafts) │  │ ─ source tag on every│  │ ─ cited FN- snippets │
│ ─ Mock (offline)    │  │   tool result        │  │                      │
└─────────────────────┘  │ ─ 60s circuit breaker│  └──────────────────────┘
                         └──────────────────────┘
```

Mermaid version: [`docs/architecture.mermaid`](docs/architecture.mermaid).

### LLM routing

Routing is by **cognitive load**, not by hardcoding a model into a node:

| Route | Order | Why |
| --- | --- | --- |
| `reasoning` (planner, critic, synthesizer) | **Claude** → Gemini → Groq → Mock | Structured plans are where the strongest model earns its latency |
| `generation` (WhatsApp drafts, fanout of 4) | Groq → Claude → Gemini → Mock | Many short messages at once; wall-clock beats depth |
| `embed` (RAG) | Gemini → Mock | Anthropic publishes no embeddings endpoint |

Every provider is an adapter behind one `LLMClient` port, with a token-bucket rate
limiter, one retry, then fall-through. The trace records which model actually answered.
**With no keys at all, the deterministic mock runs the entire agent** — which is how you
can review this without paying for anything.

---

## 4. Execution flow

```
Area Manager ──▶ POST /chat/stream { manager_query }
       │
       ▼
   ┌─────────────┐  Plan{ intent, target_module, language, steps[1..5] }
   │  Planner    │ ─── LLM (JSON mode) ────────────────────────────────┐
   └─────────────┘                                                     │
       │                                                               │
       ▼                                                               │
   ┌──────────────────────────────────────┐                            │
   │  Tool Executor  (loops over steps)   │                            │
   │  1  query_counters                   │  source: databricks|sqlite │
   │  2  compute_counter_value            │  parallel asyncio.gather   │
   │  3  predict_module_propensity        │  per counter               │
   │  4  recommend_modules                │  eligibility-checked       │
   │  5  search_field_notes               │  hybrid RAG, MMR re-rank   │
   └─────────────┬────────────────────────┘                            │
                 │                                                     │
                 ▼                                                     │
   ┌─────────────┐  verdict pass | replan → loop or proceed            │
   │  Critic     │ ─────────────────────────────────────────────────────┘
   └─────────────┘
                 │
                 ▼
   ┌─────────────────────────────┐  computes leakage risk from transaction
   │  Synthesizer                │  evidence, ranks by (priority, leakage,
   │                             │  composite), attaches citations
   └─────────────┬───────────────┘
                 │
                 ▼
   ┌─────────────────────────────┐  parallel fanout via asyncio.gather, bounded by
   │  Message Generator (×N)     │   a semaphore of 4 so free-tier rate limits
   │                             │   hold; then the compliance validator strips
   └─────────────┬───────────────┘   any number not in the source context
                 ▼
              Responder ──▶ SSE events ──▶ UI
```

Every node emits a typed `TraceEvent`; the trace panel renders the live reasoning and
the whole run is replayable from `/trace/{session_id}`.

---

## 5. The domain model

| Entity | What it is |
| --- | --- |
| `Counter` | A revenue point: retail POS outlet, ferry jetty, bus depot or metro counter. Carries `monthly_tpv`, `digital_share`, `pending_settlement`, `avg_daily_txns`, `settlement_cycle`, merchant `kyc_status`. |
| `Transaction` | `ticket_sale`, `retail_bill`, `void_reissue`, `refund`, `settlement_payout`, `chargeback`, `topup`. Channel is `upi \| card \| cash \| ncmc \| wallet \| netbanking`. **`instrument IS NULL` means no GST bill / e-ticket was issued** — the receipt-issuance gap. |
| `Module` | A Billeasy SaaS SKU with a `take_rate` and eligibility thresholds. |
| `Candidate` | A scored counter: value, propensity, composite, **`leakage_risk` (0–1) + band**, recommended module, feature contributions, citations. |
| `OutreachDraft` | A compliance-checked WhatsApp message for one counter + module. |

### The 8 Billeasy modules

| id | name | take rate |
| --- | --- | --- |
| `MOD-BILLING` | Digital Billing & GST e-Invoice | 0.4% |
| `MOD-ETICKET` | Transit e-Ticketing (QR + NCMC) | 1.2% |
| `MOD-QR` | Dynamic QR Collect | 0.6% |
| `MOD-RECON` | Settlement & Fare Reconciliation | 0.5% |
| `MOD-OFFLINE` | Offline-First Sync Kit | 0.7% |
| `MOD-LOYALTY` | Loyalty & Rewards | 0.8% |
| `MOD-WA-RECEIPT` | WhatsApp Receipts & Engagement | 0.3% |
| `MOD-ANALYTICS` | Counter Analytics | 0.5% |

### The seeded network

500 counters across 14 cities, ~15,000 transactions, deterministic (`Faker.seed(7)`).

**The data is geographically coherent** — each city has only the transit modes it
actually runs, named after its real terminals, under the operator that actually runs
them. Mumbai ferries sit under Maharashtra Maritime Board; Delhi has DTC buses, DMRC
metro and no ferries. Counter names are unique across the network, because the name is
what a manager types and what the knowledge base resolves against.

Five **hero counters** are hand-built so the scorers surface them *by computing real
signals*, never by hardcoding:

| id | counter | engineered signal (verified from the seeded rows) | surfaces |
| --- | --- | --- | --- |
| `CTR-0001` | Gateway Jetty — Counter 3 (ferry, Mumbai) | cash share **22.0% → 61.3%**, void/reissue 20%, mismatch 5.7% | `MOD-RECON` |
| `CTR-0002` | BEST Depot — Wadala Counter 1 (bus, Mumbai) | **240 min** dark across the 17:00–21:00 peak, 39% receipt gap | `MOD-OFFLINE` |
| `CTR-0003` | Sahakari Bhandar — Dadar (retail, Mumbai) | digital share 68% → 91%, ₹18L TPV, no loyalty module | `MOD-LOYALTY` |
| `CTR-0004` | Metro Line-1 Andheri — TVM Cluster (metro) | NCMC share only **8%** at high velocity | `MOD-ETICKET` |
| `CTR-0005` | Shree Provision Stores — Pune (retail) | past the ₹5L band with a **46%** receipt-issuance gap | `MOD-BILLING` |

Change `weights.yaml` and the ranking changes — which is the check to run if you suspect
the demo is rigged.

---

## 6. Scoring: value, propensity, leakage

Three scorers, all heuristic, all YAML-tuned, all returning a per-feature audit trail.
No black boxes: every number an Area Manager sees decomposes into named contributions.

### Value — how much this counter matters
z-scored `tpv_z`, `digital_share_z`, `tenure_z`, `txn_velocity_z` against the network.

### Propensity — which module fits
A logistic combination of ~25 named features, weighted **per module** in
[`weights.yaml`](backend/app/scoring/weights.yaml). Rates are band-normalised so they
actually move the logit (e.g. void-reissue 2%→15%, mismatch 2%→20%, cash spike
+5pp→+35pp).

### Leakage — is money going missing *right now*
[`backend/app/scoring/leakage.py`](backend/app/scoring/leakage.py). Deliberately
**not** a logistic: weights sum to 1.0 over features already in [0,1], so the score
reads directly as *"share of the maximum leakage evidence we could have seen"* — 0.54
means 54%. That is auditable in a way a squashed logit isn't, and this number is what
sends a manager to ask a supervisor an uncomfortable question.

| signal | weight | why it ranks there |
| --- | --- | --- |
| `settlement_mismatch_rate` | 0.27 | measured money that did not arrive |
| `cash_share_spike` | 0.23 | strong circumstantial evidence |
| `void_reissue_rate` | 0.21 | strong circumstantial evidence |
| `receipt_issuance_gap` | 0.12 | compliance exposure |
| `peak_hour_downtime` | 0.08 | unrecorded fares |
| `pending_settlement_backlog` | 0.04 | churn pressure |
| `field_note_stress_signal` | 0.03 | **corroboration, not evidence — weighted low on purpose** |
| `refund_ratio` | 0.02 | weak signal |

Bands: `clear` < 0.25 ≤ `watch` < 0.45 ≤ `elevated` < 0.65 ≤ `severe`.

**Leakage is computed from transaction evidence, not from whether anyone complained.**
A counter can leak quietly with a spotless support history — that's exactly the case a
ticket-driven process misses, and the reason this scorer exists separately from the
field-note sentiment signal.

---

## 7. AI patterns used

**7.1 Intent-routed multi-prompt architecture** — seven routes: `task | follow_up |
knowledge | faq | chitchat | out_of_scope | command`. A capability question never runs
the scoring pipeline; a policy question goes to the knowledge base; only real work hits
the tools. `follow_up` is what makes stateful refinement work — "now only Kochi" reuses
the session rather than re-planning from scratch. `command` is the whole-message
recogniser behind `help`, `back`, `cancel`, `reset` — one of those, alone, pauses
instead of working; "help me find counters leaking revenue" is still a task. A heuristic
classifier runs always; when any real LLM provider is configured it is upgraded by an
LLM classifier.

**7.2 Plan-and-Execute with a critic in the loop** — the planner emits a typed JSON
plan; the executor runs it; the critic judges each result and can force a replan. The
critic's hard cases are rule-based on purpose: a relaxed city filter passes but is
flagged for the summary, an un-relaxed city contradiction fails without an expensive
replan, and the original empty-result veto keeps its relax-and-retry replan.

**7.3 Typed tools + parallel dispatch** — 12 tools with Pydantic IO, registered by
decorator, introspectable at `/tools`, fanned out with `asyncio.gather`.

**7.4 Hybrid retrieval** — dense (Chroma) + BM25, fused with RRF, re-ranked with MMR,
citations returned as `FN-…` ids. Degrades to BM25-only when Chroma isn't installed.

**7.5 Cognitive-load-based LLM routing** — see §3.

**7.6 Grounded generation + numeric compliance validator** — the generator is given
only the counter's real figures, and a validator then **mechanically strips any number
not present in the source context** before a draft can reach a merchant. It assumes the
model will eventually invent a figure and refuses to let that reach a partner.

**7.7 Event-typed SSE streaming** — plan, tool_call, tool_result, critic, candidate,
synth, draft, final. The UI renders reasoning as it happens.

**7.8 Hexagonal data layer with failover + circuit breaker** — `DataSource` port,
Databricks primary (5s timeout), SQLite failover, 60s breaker, every row source-tagged.

**7.9 The trace is data** — every node emits a typed event, persisted and replayable.

**7.10 Tool-result caching** — the deterministic read-side tools (counter search,
scoring, propensity, recommendations, field-note retrieval) are memoisable when the same
args recur within `tool_cache_ttl_seconds`; a `cache: "hit"` field is surfaced on the
envelope. Write and generative paths are never cached. Tool-output caching requires doing
harmless work at most once, which never breaks for a cache miss.

**7.11 Router telemetry** — every reasoning node stamps its `llm_route`; the synthesizer
records a `fallback_reason` when the router degrades. `GET /trace` aggregates them into a
`telemetry` block (`llm_calls`, `by_route`, `fallback_count`, the actual reasons) so the
split between Claude, Gemini, Groq and mock is a measured number, not an assumption.

**7.12 Rocchio-style feedback retrieval** — with no scored index there is no textbook
relevance feedback, but the BM25 term-frequency view gets most of the mechanism for free:
`KnowledgeBase.feedback_terms()` derives the terms that separated a good answer from the
query, and the next query repeats them (`rocchio_max_feedback_terms`,
`rocchio_expansion_repeats`) so a follow-up that stays on-topic re-ranks the same section
higher. Keyless, because it never calls a model.

**7.13 DPDP PII masking guard** — every free-text surface is redacted before it reaches an
LLM, the knowledge base, or persistence. A masked `AgentState` reaches the entry gate of
`run_agent` (and the chat boundary before any row is stored), so prompts, session titles,
the `messages` thread and every `agent_traces` row are identifier-safe for GSTIN, PAN,
Aadhaar, mobile and email. Masking is idempotent — the same text masked twice is stable,
and the placeholders can't re-trigger (see README §12.1 and
[`backend/new_features/security_policies.md`](backend/new_features/security_policies.md)).

**7.14 Solution-area tools** — the failure-triage, compliance and integration layer:
`diagnose_reconciliation` labels a counter's collection-vs-settlement gap
(merchant-void-reissue ≠ settlement shortfall); `validate_invoice_layout` runs structural
GST invoice-layout checks on pasted bill text; `generate_erp_mapping` maps Billeasy
transaction categories to Tally/Zoho/SAP ledger fields (no write path); `analyze_telemetry`
aggregates the estate into per-city bottleneck clusters from device-offline minutes and
pending settlement. They are backed by five new corpus documents (gateway error codes,
regulatory schedule with effective dates, ERP integration, security policies, API guide) so
the knowledge base can answer "what class of failure / which ERP / what's our posture"
from the same BM25 + citation path. `diagnose_reconciliation` and `analyze_telemetry` are
operational reads and are deliberately **not** tool-cached; the pure text/config mappers
are.

---

## 8. Tool design

| Tool | Purpose |
| --- | --- |
| `query_counters` | Structured search over the network (city, tier, type, TPV, pending settlement, velocity, settlement cycle) with 2-stage filter relaxation |
| `compute_counter_value` | Explainable 0–1 network-value score |
| `predict_module_propensity` | Per-(counter, module) fit with feature breakdown |
| `recommend_modules` | Eligibility-checked top-k module recommendation |
| `search_field_notes` | Hybrid RAG over field-visit notes and support tickets, cited |
| `get_counter_transactions` | Aggregates: collected, settled, cash/digital share, channel split, void/reissue count, refunds |
| `generate_whatsapp_message` | Grounded draft + compliance validation |
| `create_outreach_batch` | Persists drafts for review — the only write path |
| `diagnose_reconciliation` | Triage one counter's collection-vs-settlement gap into a verdict |
| `validate_invoice_layout` | Structural GST layout checks on pasted invoice text (GSTIN/HSN/IRN/amount) |
| `analyze_telemetry` | Per-city bottleneck clusters from device-offline minutes + pending settlement |
| `generate_erp_mapping` | Billeasy categories → Tally/Zoho/SAP ledger mapping spec, no write path |

---

## 9. API overview

Every route below is real and mounted in [`backend/app/main.py`](backend/app/main.py).
**Auth** is the shared-password gate (§12): a router-level
`Depends(require_token)` that reads the `X-Access-Token` header. The header is the
**only** accepted transport — a `?token=` query parameter was removed so a credential
never lands in proxy logs or browser history. Interactive OpenAPI docs are at `/docs`,
schema at `/openapi.json`.

| Method | Path | Auth | Purpose |
| --- | --- | --- | --- |
| `GET` | `/` | — | Service name, version, and pointers to `/docs` and `/healthz` |
| `GET` | `/healthz` | — | Liveness probe. What the keep-alive cron hits |
| `GET` | `/status` | — | Which datasource is active and healthy, and which LLM providers are live |
| `POST` | `/auth/verify` | — | Exchange the shared password for an access token (the token *is* the password) |
| `POST` | `/sessions` | ✅ | Start a new conversation thread |
| `GET` | `/sessions` | ✅ | 50 most recent sessions, newest first |
| `POST` | `/chat/stream` | ✅ | **Run the agent and stream its reasoning over SSE** |
| `POST` | `/chat/run` | ✅ | Same run, non-streaming — returns candidates, drafts and the whole trace at once |
| `GET` | `/counters/{counter_id}` | ✅ | Counter 360: profile + recent transactions + live modules + field notes, source-tagged |
| `GET` | `/trace/{session_id}` | ✅ | Replay a session: every trace event, message and draft. 404 if the session has neither |
| `GET` | `/tools` | ✅ | JSON schema for every registered agent tool |
| `POST` | `/tools/{name}` | ✅ | Invoke one tool directly with a raw JSON payload (Pydantic-validated, timed out) |
| `GET` | `/outreach/{session_id}` | ✅ | Every WhatsApp draft produced in a session |
| `POST` | `/outreach/approve` | ✅ | Mark a list of `draft_ids` approved. 400 on an empty list |
| `PATCH` | `/outreach/{draft_id}` | ✅ | Edit one draft's message before it goes out. 404 if unknown |
| `GET` | `/meta/capabilities` | ✅ | Domain, capabilities, the 8 modules, example prompts, live component status |
| `GET` | `/meta/faqs` | ✅ | Area Partner Manager FAQs, grouped by category |
| `POST` | `/knowledge/ask` | ✅ | Ask the reference corpus a payments / GST / settlement / counter-history question |
| `GET` | `/knowledge/sources` | ✅ | Indexed reference documents plus suggested questions |

### 9.1 `POST /chat/stream`

Both chat routes take the same body. `manager_query` also accepts the alias
`query`, `manager_name` the alias `manager`; the query is trimmed, rejected if
empty, and truncated to 2000 characters.

```json
{
  "session_id": "5f0c…  (optional — omit to start a new session)",
  "manager_query": "Find ferry and bus counters in Mumbai leaking digital ticket revenue this month",
  "manager_name": "Rohan"
}
```

The response is `text/event-stream` (`sse-starlette`, 15s ping). The first frame
is always an `info` event carrying the session id — capture it, because a
follow-up turn needs it:

```
event: info
data: {"session_id":"5f0c…"}
```

Every subsequent frame is a serialised `TraceEvent`
([`backend/app/agent/state.py`](backend/app/agent/state.py)):

```
event: synth
data: {"event":"synth","ts":"2026-01-14T09:12:03.881","data":{"summary":"Your priority counters: …","candidate_count":10},"llm_route":"anthropic","latency_ms":812}
```

`llm_route` is the provider that actually answered (`anthropic` / `gemini` /
`groq` / `mock`) and is `null` on events no model produced — `candidate` and
`tool_result`, for instance, are pure computation.

| SSE event | Emitted when |
| --- | --- |
| `info` | Stream opens (`session_id`), then as a general progress channel — `agent_started`, the classified intent (`task \| follow_up \| knowledge \| faq \| chitchat \| out_of_scope \| command`), a rewritten follow-up query, a critic-forced replan, "no candidates → skipping drafts" |
| `plan` | Planner returns the typed JSON plan (`source: "default"` when it fell back) |
| `tool_call` | A plan step dispatches a tool, with its arguments |
| `tool_result` | That tool returns — carries `source` (`databricks` / `sqlite(failover)`) and latency |
| `critic` | Critic verdict on the results so far: pass, or replan |
| `synth` | The written answer — from the synthesizer on a task run, or from the FAQ / knowledge / chitchat branches |
| `candidate` | One scored counter, with feature contributions, leakage band and citations |
| `draft` | One compliance-checked WhatsApp draft |
| `final` | Run complete |
| `error` | The run raised — emitted by the endpoint, not a node. Payload is `{"error": "<Type>: <message>"}` and the stream ends |

`TraceEvent` also declares `router` and `token` in its literal type; no node
currently emits either, so a client can ignore them.

The generator checks `request.is_disconnected()` between events, so closing the
tab stops the run rather than burning tokens on nobody.

### 9.2 `POST /chat/run`

Identical body, no streaming — this is what the tests and any non-browser client
use. It runs the agent to completion and returns the whole thing:

```json
{
  "session_id": "5f0c…",
  "summary": "Your priority counters: …",
  "candidates": [ { "counter_id": "CTR-0001", "name": "Gateway Jetty — Counter 3",
                    "leakage_risk": 0.54, "leakage_band": "elevated",
                    "top_features": [...], "leakage_features": [...],
                    "recommended_module_id": "MOD-RECON", "citations": ["FN-…"], "…": "…" } ],
  "drafts":     [ { "counter_id": "CTR-0001", "module_id": "MOD-RECON",
                    "message": "Hello Gateway Jetty — Counter 3 team, …",
                    "compliance": { "ok": true, "ungrounded": [] }, "llm_route": "groq" } ],
  "events":     [ { "event": "plan", "ts": "…", "data": {}, "llm_route": null, "latency_ms": null } ]
}
```

`candidates` are `CandidateRecord`s and `drafts` are `DraftRecord`s — the same
Pydantic models the SSE `candidate` and `draft` events carry, so a client can be
written once against either transport.

---

## 10. Key design decisions

1. **Leakage is a severity, not a flag.** A boolean can't rank 500 counters. The whole
   product is triage, so the money signal is a 0–1 score with an explainable breakdown.
2. **Evidence over complaints.** Leakage comes from transactions; field-note sentiment
   is a low-weight corroborator.
3. **Device uptime is a first-class input, not an inference.** Real POS/AFC estates emit
   uptime telemetry, so `device_offline_minutes` is a column. The transaction-gap
   inference remains as a fallback, and it evaluates *per peak window* — a depot that
   sells all morning and goes dark at 17:00 is the case a whole-day test can't see.
4. **The seed data must genuinely compute.** Hero signals are arithmetic on real rows.
5. **Human-in-the-loop.** The agent drafts; a person sends.
6. **Keyless review.** The mock provider runs the entire agent offline.
7. **Regulation vs. modelling convention is stated explicitly.** The knowledge base
   flags where a threshold is this product's heuristic rather than statute — e.g. the
   ₹5L TPV prospecting trigger is *not* the ₹5 Cr e-invoicing mandate. An agent that
   cites documents must not launder a convention into a regulation.
8. **Reset forgets, never destroys.** `reset` (and `start over`) clears the conversation
   memory but nothing else — past traces, drafts and the session row itself survive, so
   a manager can always re-open what a previous run produced.
9. **Reliable streams outrank retry loops.** The client retries only connect-stage
   failures (with exponential backoff + jitter); a stream that opened and delivered a
   frame is never re-forked, because a reconnect re-runs the pipeline and would
   duplicate drafts.

---

## 11. Trade-offs and limitations

**Honest list. Read this one.**

- **The UI was not visually verified in a browser in the final pass.** `tsc --noEmit`
  and `vite build` pass, the dev server serves, and every API payload the components
  consume was exercised over HTTP — but no screenshot was taken. Treat the UI as
  build-verified, not eyeball-verified.
- **Scoring is heuristic, not learned.** There is no labelled leakage outcome data, so
  weights are hand-tuned domain judgement. They're transparent and tunable, but they are
  judgement. A trained model behind the same interface is the obvious next step.
- **Leakage risk is prioritisation, not accusation.** A high score means *look here*,
  not *this supervisor is stealing*. Several of these signals have innocent explanations
  (a broken printer, a festival cash surge). The product language is deliberately
  "call the supervisor", never "fraud detected".
- **BM25-only retrieval by default.** Chroma is optional (it exceeds Render's free-tier
  memory), so the deployed default is lexical. The lexical path is tuned for that
  constraint — retrieval stopwords, heading-path weighting, paragraph-bounded chunk
  overlap and domain-acronym expansion, which together fixed the observed
  "what is NCMC at an AFC gate?" landing in the chargebacks FAQ. What BM25 still cannot
  do is a query that shares no vocabulary with the corpus ("when does money actually
  reach the shop owner") — that needs embeddings. The Rocchio step (§7.12) narrows the
  gap for *follow-ups*: a continuation that repeats the previous answer's vocabulary
  re-ranks toward the same section without any embeddings.
- **SSE retry is connect-stage only.** A mid-stream drop is left to the user to replay
  (§10.9) — re-running a stream that already delivered frames duplicates drafts, so the
  client chooses not to.
- **Single-tenant, shared-password auth.** Fine for a demo, not for production —
  the full list of what is and isn't defended is §12.
- **The mock LLM flatters the planner.** Keyless runs use canned plans, so plan quality
  under a real model is only as good as the few-shot prompt. There is now an eval
  harness for exactly this — `backend/evals/`, a 33-case golden set scored per-plan on
  eight dimensions — but in a keyless environment it grades how faithfully the mock
  mirrors the prompt, and the number that means something about a real model still
  requires one free LLM key.
- **Synthetic data.** 500 counters modelled on real Indian transit and retail, but
  invented. No real Billeasy data was used or is required.

---

## 12. Security considerations

This is a take-home demo, not a production deployment. The honest split is below:
what the code actually does, and what it deliberately doesn't. Everything in the
first table is verifiable in the file cited next to it.

### 12.1 What is implemented

| Control | Where | What it actually does |
| --- | --- | --- |
| **Constant-time password comparison** | [`app/auth/middleware.py`](backend/app/auth/middleware.py) | `hmac.compare_digest` on the shared token, so a wrong password can't be recovered a byte at a time from response timing. Missing token short-circuits to 401 before the comparison. |
| **Auth on every data route** | each router in [`app/api/`](backend/app/api) | The gate is a router-level `dependencies=[Depends(require_token)]`, not a per-handler decorator — a new endpoint added to an existing router is protected by construction. Only `/`, `/healthz`, `/status` and `/auth/verify` are open, by design. |
| **CORS allowlist, never wildcard-with-credentials** | [`app/main.py`](backend/app/main.py) | Origins come from `APP_CORS_ORIGINS`. There is deliberately **no `*` fallback**: the CORS spec forbids wildcard-plus-credentials, and a fallback would mean one empty config value silently opens an authenticated API to every origin. Unset origins allow none rather than all. |
| **Failed-login throttle** | [`app/auth/throttle.py`](backend/app/auth/throttle.py) | 8 failed attempts per client in a 5-minute window trips a lockout returning `429` with `Retry-After`. Constant-time comparison protects against timing attacks but does nothing against guessing at network speed. In-memory and therefore per-process — honest for a single-worker dyno, and it must move to Redis or the edge behind replicas. |
| **Pydantic-validated inputs at every boundary** | [`app/application/tool_registry.py`](backend/app/application/tool_registry.py) | Each tool declares an input model; `invoke_tool` calls `model_validate` and returns `invalid_args` rather than executing on unvalidated input. That applies equally to the planner's arguments and to a hand-rolled `POST /tools/{name}`. Chat and knowledge bodies are validated and length-capped (2000 / 500 chars). |
| **Parameterised SQL everywhere** | [`app/infrastructure/datasource/sqlite.py`](backend/app/infrastructure/datasource/sqlite.py), `app/api/*.py` | No value is ever concatenated into a query. Where an f-string appears it interpolates a generated run of `?` placeholders for an `IN (…)` clause; the values themselves always go through the driver's parameter binding. Same pattern on the Databricks adapter, where the only interpolated identifiers are the catalog/schema names from config. |
| **Secrets only from env, never committed** | [`app/settings.py`](backend/app/settings.py), `.gitignore` | All configuration flows through one `pydantic-settings` class — no scattered `os.environ` reads. `.env`, `.env.local` and `.env.*.local` are gitignored with a `!.env.example` exception, so only the placeholder file is tracked. `frontend/.env.local` keeps real demo phone numbers out of the repo. |
| **Numeric-grounding compliance validator** | [`app/scoring/compliance.py`](backend/app/scoring/compliance.py) | Every number in a generated draft must appear in the source context (counter profile, module, transaction aggregates), within a 5% rounding tolerance. Ungrounded figures are mechanically replaced with `—` and the draft is reported non-compliant. This is the control that stops an LLM-invented settlement figure reaching a merchant. |
| **Tool timeouts** | `tool_registry.py` + `AGENT_TOOL_TIMEOUT_SECONDS` | Every tool call runs under `asyncio.wait_for`; a hang returns a structured `timeout` envelope instead of blocking the run. |
| **Circuit breaker on the primary datasource** | [`app/infrastructure/datasource/failover.py`](backend/app/infrastructure/datasource/failover.py) | One Databricks failure trips a 60s breaker and every call goes straight to SQLite — a wedged warehouse degrades the app once, not once per tool call. The Databricks client itself runs under a 5s timeout. |
| **Outbound LLM rate limiting** | `anthropic_client.py`, `gemini.py`, `groq.py` | Per-provider token buckets, plus a semaphore of 4 on the draft fanout, so the agent cannot stampede a provider. |
| **Human-in-the-loop on outreach** | agent design | Nothing is sent. The agent writes drafts; a person reviews, edits (`PATCH /outreach/{draft_id}`) and approves. There is no send path in the codebase to abuse. |

### 12.2 What is not implemented

Stated plainly, because a reviewer will find these anyway:

- **A single shared password, not per-user auth.** `POST /auth/verify` returns the
  password itself as the token; there is no JWT, no session, no expiry, no
  revocation, and no RBAC. Every authenticated caller is the same principal.
- **No row-level access control.** An Area Manager can read any counter in the
  network. Nothing scopes `/counters/{id}`, `/trace/{id}` or `/outreach/{id}` to
  the caller's own territory — or even to the session they created.
- **No general API rate limiting.** `/auth/verify` is throttled (see 12.1), but every
  other route is unmetered — an authenticated caller can hammer `/chat/run` and burn
  the LLM budget. Per-principal quotas belong at the edge.
- **No audit log.** Nothing records who viewed which counter's data or who
  approved which outreach draft. `agent_traces` records what the *agent* did, not
  who asked it.
- **No PII encryption at rest.** Counter names, supervisor phone numbers and
  field notes sit in plain SQLite (and plain Delta, if Databricks is wired up).
  The DB file is gitignored, which is not the same thing as protected.
- **No CSRF protection.** The token travels as an `X-Access-Token` header, and the
  frontend keeps it in `localStorage` rather than a cookie, so a browser will not
  attach it automatically to a cross-site request — that mitigates classic CSRF,
  but no token or `SameSite` policy formally addresses it. `localStorage` also
  means any XSS in the frontend yields the token directly.
- **PII masking is in force in the agent** — the DPDP identifier guard (§7.13) redacts
  GSTIN, PAN, Aadhaar, mobile and email from any prompt, session title, stored message or
  trace before it can reach a provider or disk. The remaining "not enforced" line is the
  **consent flag**: the KB documents DPDP consent rules and the agent will explain them,
  but no code checks a merchant's consent flag before drafting. That remains acceptable
  only because drafts are never actually sent.
- **DPDP consent is documented, not enforced.** The knowledge base
  ([`backend/new_features/payments_compliance.md`](backend/new_features/payments_compliance.md) §10,
  [`backend/new_features/security_policies.md`](backend/new_features/security_policies.md))
  covers the DPDP Act 2023 consent rules, TRAI DLT registration and the WhatsApp
  opt-in requirement for business-initiated messages — and the agent will explain
  them if asked. No code checks a consent flag before drafting. That is acceptable
  only because drafts are never actually sent.

### 12.3 What would change for production

1. **Per-user auth** — OIDC or email/password issuing a short-lived JWT with a
   refresh token, replacing the shared bearer entirely.
2. **Row-level security** — every counter query scoped to the Area Manager's own
   territory, enforced in the datasource port so no route can forget it.
3. **An immutable audit trail** — append-only records of every counter data access
   and every outreach send, with actor, timestamp and counter id. In a payments
   context this is a requirement, not a nice-to-have.
4. **Secrets in a managed vault** — AWS Secrets Manager / GCP Secret Manager with
   rotation, rather than environment variables on a web service.
5. **API rate limiting** — per-principal quotas at the edge, with a much tighter
   limit and lockout on the auth endpoint.
6. **Encryption at rest and PII minimisation** — encrypted columns for phone
   numbers, and a consent flag checked before a draft is generated, not after.

---

## 13. Project structure

```
counter-copilot/
├─ WRITEUP.md                    ← the brief's write-up: how this was built with AI
├─ backend/
│  ├─ app/
│  │  ├─ agent/                  planner, critic, synthesizer, nodes, prompts, knowledge
│  │  ├─ api/                    FastAPI routes (chat, counters, trace, tools, meta, knowledge)
│  │  ├─ application/            tool registry + orchestration
│  │  ├─ domain/                 Pydantic models (Counter, Module, Candidate…)
│  │  ├─ scoring/                value.py · propensity.py · leakage.py · compliance.py
│  │  │                          sentiment.py · weights.yaml
│  │  ├─ infrastructure/
│  │  │  ├─ datasource/          Databricks + SQLite + failover
│  │  │  └─ llm/                 anthropic_client · gemini · groq · mock · router
│  │  ├─ knowledge_base/         BM25 KB service over the corpus
│  │  └─ db/                     schema.sql + seeders (hero_counters, faker_seed)
│  ├─ new_features/              RAG corpus (payments compliance, methodology, FAQs)
│  └─ tests/                     smoke · agent e2e · faq · sentiment · KB · compliance ·
│                               security · ranking · tool cache · critic · commands ·
│                               sessions · telemetry · rocchio (14 keyless suites)
├─ frontend/src/
│  ├─ features/                  chat · candidates · drawer · trace · guide · knowledge
│  ├─ lib/                       api client + types
│  └─ pages/                     Login · Dashboard
└─ docs/                         architecture · execution flow · AI patterns ·
                                 demo script · trade-offs
```

---

## 14. Setup and run

Requires **Python 3.11+** and **Node 18+** (npm). No database to provision and no
API key required for the demo path.

### 14.1 Fastest path — offline, mock LLM, no API keys

```bash
# 1) Backend
cd backend
python -m venv .venv
.venv\Scripts\activate                # Windows
# source .venv/bin/activate           # macOS/Linux
pip install -r requirements.txt
# Optional — full dense+BM25 hybrid RAG (otherwise BM25-only):
# pip install -r requirements-rag.txt
$env:PYTHONPATH = "."                  # Windows PS
# export PYTHONPATH=.                  # macOS/Linux
uvicorn app.main:app --reload --port 8000

# 2) Frontend (new shell)
cd frontend
npm install
$env:VITE_API_URL = "http://localhost:8000"
npm run dev
```

Open <http://localhost:5173>, sign in with password **`shared`**, and try a quick prompt.
The database seeds itself deterministically on first boot.

**Optional — make "Send on WhatsApp" open a real chat:** copy `frontend/.env.example`
to `frontend/.env.local` and map hero counters to test numbers:

```env
VITE_DEMO_PHONES={"Gateway Jetty":"919876543210","BEST Depot":"919812345678"}
```

`.env.local` is gitignored, so real numbers never reach the repo.

### 14.2 With a real provider — one free key is enough

The whole agent runs on **a single free Groq key**. Create `backend/.env` (start from the
annotated [`.env.example`](.env.example) at the repo root):

```env
GROQ_API_KEY=...          # free tier → https://console.groq.com   (takes ~1 min)
```

With no other keys, both routes fall through to Groq, so the full agent works end to end —
planning, introspection, WhatsApp drafting. `/status` and the UI top bar show which
providers are live.

The more keys you add, the closer you get to the intended routing (§3):

```env
GEMINI_API_KEY=...        # free → https://aistudio.google.com   also enables dense RAG (embeddings)
ANTHROPIC_API_KEY=...     # paid → https://console.anthropic.com   the model the brief prefers
ANTHROPIC_MODEL=claude-opus-5
ANTHROPIC_EFFORT=low      # low | medium | high — trades depth against latency
```

With zero keys the app still runs fully on the deterministic mock LLM (§14.1), so a
reviewer never needs an API key to see the demo.

### 14.3 Docker

```bash
docker compose up --build
```

---

## 15. Environment variables

**Every variable here is optional.** With an empty environment the app boots on
SQLite with the deterministic mock LLM, seeds itself, and runs the whole agent —
that is a deliberate design property, not an accident of defaults. It's what lets
a reviewer clone the repo and get the canonical demo without a single API key,
and it's why the CI-equivalent test suite (§16) passes offline.

The backend reads these through one `pydantic-settings` class
([`app/settings.py`](backend/app/settings.py)); names are case-insensitive and
loaded from `backend/.env` if it exists. Copy the annotated
[`.env.example`](.env.example) at the repo root to `backend/.env` to start.

### 15.1 Backend

**App**

| Variable | Default | Required | What it does |
| --- | --- | --- | --- |
| `APP_NAME` | `counter-copilot` | No | Service name in logs and `GET /` |
| `APP_ENV` | `development` | No | `development` / `production` label |
| `APP_PASSWORD` | `shared` | **Change in prod** | The shared access token. Leaving the default in a public deployment means there is no gate |
| `APP_CORS_ORIGINS` | `http://localhost:5173` | No | Comma-separated CORS allowlist. Add the deployed frontend origin. There is **no `*` fallback** — an empty value allows no cross-origin requests rather than all of them |
| `LOG_LEVEL` | `INFO` | No | Root log level |

**LLM providers** — all optional. Set none and everything routes to the mock;
set any and `/status` shows it live. See §3 for the routing order.

| Variable | Default | Required | What it does |
| --- | --- | --- | --- |
| `ANTHROPIC_API_KEY` | *(empty)* | No | Enables Claude — leads the `reasoning` route (planner, critic, synthesizer) |
| `ANTHROPIC_MODEL` | `claude-opus-5` | No | Claude model id |
| `ANTHROPIC_EFFORT` | `low` | No | `low \| medium \| high` — thinking depth against latency. Interactive agent, so `low` by default |
| `GEMINI_API_KEY` | *(empty)* | No | Enables Gemini. Also the only embeddings provider, so dense RAG needs this |
| `GEMINI_MODEL` | `gemini-2.0-flash-exp` | No | Gemini chat model |
| `GEMINI_EMBED_MODEL` | `text-embedding-004` | No | Gemini embedding model for the Chroma index |
| `GROQ_API_KEY` | *(empty)* | No | Enables Groq — leads the `generation` route (parallel WhatsApp drafting) |
| `GROQ_MODEL` | `llama-3.3-70b-versatile` | No | Groq model id |

**Data layer** — Databricks is engaged only when host, HTTP path and token are
*all* set; otherwise SQLite is used directly, with no error and no degradation of
the demo.

| Variable | Default | Required | What it does |
| --- | --- | --- | --- |
| `DATABRICKS_HOST` | *(empty)* | No | Workspace hostname. Enables the Delta primary datasource |
| `DATABRICKS_HTTP_PATH` | *(empty)* | No | SQL warehouse HTTP path |
| `DATABRICKS_TOKEN` | *(empty)* | No | Personal access token |
| `DATABRICKS_CATALOG` | `counter_copilot` | No | Unity Catalog catalog name |
| `DATABRICKS_SCHEMA` | `core` | No | Schema holding the counter tables |
| `DATABRICKS_TIMEOUT_SECONDS` | `5.0` | No | Per-query timeout before failing over to SQLite |
| `SQLITE_PATH` | `./data/app.db` | No | SQLite file, relative to `backend/`. Auto-created and seeded on first boot |
| `CHROMA_DIR` | `./data/chroma` | No | Chroma persistence directory. Ignored when Chroma isn't installed (BM25-only) |

**Agent**

| Variable | Default | Required | What it does |
| --- | --- | --- | --- |
| `AGENT_MAX_ITERATIONS` | `10` | No | Ceiling on plan → execute → critic loops before the run is forced to conclude |
| `AGENT_TOP_K_CANDIDATES` | `10` | No | How many scored counters are returned and drafted for |
| `AGENT_TOOL_TIMEOUT_SECONDS` | `15.0` | No | Per-tool `asyncio.wait_for` budget |

**Keep-alive** — only useful on a free tier that sleeps.

| Variable | Default | Required | What it does |
| --- | --- | --- | --- |
| `SELF_PING_URL` | *(empty)* | No | If set, the app GETs this URL on a loop to keep the instance warm |
| `SELF_PING_INTERVAL_SECONDS` | `600` | No | Seconds between self-pings |

### 15.2 Frontend

Vite variables, read at **build time** — a change needs a rebuild or redeploy.
See [`frontend/.env.example`](frontend/.env.example).

| Variable | Default | Required | What it does |
| --- | --- | --- | --- |
| `VITE_API_URL` | `http://localhost:8000` | No locally, **yes when deployed** | Backend base URL. Trailing slash is stripped |
| `VITE_DEMO_PHONES` | *(unset)* | No | JSON map of hero-counter name prefix → WhatsApp number (digits with country code), so "Send on WhatsApp" opens a real chat. Put real numbers in `.env.local`, which is gitignored |

---

## 16. Verification — what actually passes

```bash
cd backend
$env:PYTHONPATH = "."
python tests/test_smoke.py           # tools, filters, scoring, aggregates, compliance
python tests/test_agent_e2e.py       # full agent: plan → tools → critic → synth → drafts
python tests/test_faq_routing.py     # capability questions don't run the pipeline
python tests/test_sentiment_lang.py  # field-note sentiment + Hindi drafting
python tests/test_knowledge_base.py  # corpus grounding + counter resolution + routing
python tests/test_compliance.py      # the numeric-grounding guardrail, made to fire
python tests/test_security.py        # auth throttle, header-only token, CORS allowlist
python tests/test_ranking.py         # queue invariants + golden top-5 / GST top-3 + weight rules
python tests/test_tool_cache.py      # memoiser key/TTL + write-path exclusion
python tests/test_critic.py          # critic hard-case heuristics over hand-built states
python tests/test_commands.py        # global commands + the reset boundary
python tests/test_sessions.py        # FR-32: on-disk session rejoin + follow-up rewrite
python tests/test_telemetry.py       # /trace telemetry: llm_calls, by_route, fallback_reason
python tests/test_rocchio.py         # feedback retrieval: term expansion re-ranks correctly
python tests/test_solution_areas.py  # PII guard, reconciliation triage, invoice layout, ERP map, telemetry synth
```

All fifteen pass keyless against the mock LLM, and CI runs all fifteen
(`.github/workflows/backend-ci.yml`) plus `ruff check app`. What they assert, specifically:

- the Mumbai + ferry/bus filter returns **only** Mumbai ferry/bus counters
- Gateway Jetty surfaces for a leakage question **through scoring**, not a fixture
- the leaking ferry counter outranks the healthy retail one for reconciliation
- the metro cluster's top recommendation is `MOD-ETICKET`
- `leakage_risk` is a float in [0,1] with a valid band on every candidate
- **every** draft passes the numeric-grounding validator
- a named counter resolves to its own record; a policy question resolves to the corpus
- a credential in a `?token=` query string is rejected; only the header authenticates
- the 9th failed login in the window returns `429` with a `Retry-After` header
- the CORS origin list is explicit — a `*` in it fails the test
- an **invented** rupee figure in a draft is both flagged *and* actually removed from the
  message, including when written with Indian digit grouping (`₹9,87,654`), while a real
  figure survives untouched
- the queue is sorted by `(priority, leakage, composite)`, every band matches its score
- `sum(weights["leakage"]) == 1.0` and no leakage weight is negative
- the canonical top-5 and the GST/Hindi top-3 rankings are exactly the blessed golden lists
- repeat read-side tool calls hit the memoiser; `create_outreach_batch` and
  `generate_whatsapp` never do
- a relaxed city filter passes the critic but is flagged; an un-relaxed city contradiction
  fails without a replan; an empty scoring stage fails without a replan
- `help` answers without scoring a single counter; `reset` clears the conversation memory,
  keeps the session's assistant reply, and leaves traces and drafts intact
- a fresh client resumes the same `session_id`, reads "which of the counters you found…"
  as a follow-up, and the on-disk thread ends up with both turn-pairs
- `/trace` telemetry shows `llm_calls` matching `sum(by_route)` with `fallback_reason`
  per-row and a zero fallback count on a healthy run
- with feedback terms injected, the GST/HSN/IRN docs move to the retrieval top-3
  (score 7.342 → 28.762) while a related MDR follow-up stays aligned
- PAN/Aadhaar/GSTIN/mobile/email are masked (and idempotently re-masked) before any
  LLM or persistence surface, and `run_agent` masks even a directly-built state
- `diagnose_reconciliation` labels the seeded leaking counter
  `merchant_void_reissue` (mismatch > 2%, 7 voids) with next steps, never a gateway guess
- a fully-formed tax invoice passes `validate_invoice_layout` while a bare self-claim
  fails on GSTIN/HSN; a missing IRN is only a warning
- `generate_erp_mapping` maps known categories, reports unknown ones as unmapped, and
  never claims a live ERP write
- `analyze_telemetry` returns per-city clusters sorted by lag, with the city filter
  narrowing correctly and endpoint scope declared
- the eight-corpus index grounds API, security-PII and gateway-error questions; the
  routing gate sends them to `knowledge`, never into the pipeline

```bash
cd frontend && npx tsc --noEmit && npm run build   # both clean, zero `any` in src/
```

---

## 17. Deployment

| Layer | Service | Notes |
| --- | --- | --- |
| Frontend | Vercel | Set `VITE_API_URL` (+ optional `VITE_DEMO_PHONES`). `vercel.json` included. Env vars are build-time — redeploy after changing. |
| Backend | Render Web Service (free) | `render.yaml` blueprint. Ephemeral FS — `bootstrap()` reseeds deterministically on boot. |
| Keep-alive | cron-job.org | Hit `/healthz` every 10 min. |
| Warehouse | Databricks Free Edition | Optional — see `databricks/`. SQLite failover means nothing breaks without it. |
| LLM | Anthropic / Google AI Studio / Groq | All optional. Mock fallback if every key is unset. |

---

## 18. Demo scenarios

| # | Ask | What to watch |
| --- | --- | --- |
| A | *"Find ferry and bus counters in Mumbai leaking digital ticket revenue this month and draft WhatsApp nudges for the depot supervisors."* | Full plan; 5 tool calls; `source` tags; only Mumbai ferry/bus counters returned. **Wadala Depot — Counter 8** leads at 57%, with the hand-built **Gateway Jetty** second at 54% (`void_reissue_rate` + `cash_share_spike` as its top drivers). The hero not winning is the point — the ranking is computed. 10 grounded drafts. |
| B | *(same session)* *"Now only Kochi, and make it firmer."* | Stateful refinement — filters and tone change, drafts regenerate |
| C | *"Which retail outlets crossed the GST e-invoice threshold but aren't issuing compliant bills? Draft in Hindi."* | Planner picks `MOD-BILLING`, switches language to Hindi, retail outlets only — proves reasoning, not hardcoding |
| D | *"What is NCMC and how does it work at an AFC gate?"* | Routes to the knowledge base with citations — no counters scored |

Full script: [`docs/demo-script.md`](docs/demo-script.md).

---

## 19. Future work

- **Trained leakage model** behind the same `Scorer` interface, A/B'd against the
  heuristic — the weights are a starting prior, not an answer.
- **Automated WhatsApp send** via Meta Cloud API behind a `MessageChannel` port.
- **Reverse channel** — classify supervisor replies and surface the next step.
- **Per-counter baselines over time** — leakage is currently a trailing-window
  comparison; a proper seasonal baseline would cut festival-cash false positives.
- **Multi-tenant auth** (JWT + row-level security) for real Area Manager accounts —
  with the rest of the production security work in §12.3.
- **Vector search inside Databricks** to drop the local Chroma dependency.

---

## License

MIT — see `LICENSE`. Built for Billeasy's open AI challenge; designed to be
production-shaped, not production-deployed.

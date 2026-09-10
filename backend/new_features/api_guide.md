# Counter Copilot API & Integration Guide

The 3rd-party integration reference: what a Billeasy partner's developer or analyst can do
programmatically with Counter Copilot, and what the agent will never expose. Written for the
"how do I plug this into our stack / what endpoints exist / do you have an SDK" questions.

## Endpoints (all require the API token)
- `POST /chat/stream` — SSE stream through the whole agent run. First `info` frame carries the
  `session_id`; subsequent frames are `plan` / `tool_call` / `tool_result` / `critic` /
  `candidate` / `draft` / `final` events as the run progresses. Keep the connection open; a
  transport hiccup at connect stage is retried on the client side (a ping is sent every 15s).
- `POST /chat/run` — the same run, non-streaming; returns `summary`, `candidates`, `drafts`,
  and the full `events` trace in one response. Useful for scheduled/job use.
- `GET /tools` — the registered tool catalog (name + description). Your code can iterate this
  to discover what the agent can call, and the tool list also tells you what is available
  without an LLM key.
- `GET /kb/sources` — the knowledge-base document index, for citation checks.
- Session model: pass the `session_id` back on the next turn to continue the thread; omit it
  to start fresh. `reset` (typed as a message) clears conversational memory.
- Auth: bearer token via `require_token`. The demo ships with a default configured token;
  change it in settings before any staging use.

## Deterministic tools the endpoint returns
- `query_counters` — counter shortlists with filters and relaxation notes.
- `get_counter_transactions` — per-counter ledger aggregates (collected / settled / cash share
  / void-reissue / refunds).
- `compute_counter_value`, `predict_module_propensity`, `recommend_modules` — the scoring and
  pitch layers.
- `search_field_notes` — RAG over field notes and tickets.
- `diagnose_reconciliation` — collection-vs-settlement triage verdict for one counter.
- `validate_invoice_layout` — structural GST invoice-layout checks on pasted bill text.
- `analyze_telemetry` — per-city bottleneck clusters from the device estate.
- `generate_erp_mapping` — Billeasy category → external-ERP ledger mapping spec.
- Drafts: `generate_whatsapp_message` (draft text) and `create_outreach_batch` (persists the
  batch). These are the ONLY stateful writes and they target the outreach queue, never an
  external party.

## Integration patterns
- **Job / scheduled sweep**: call `/chat/run` with a canned prompt (e.g. "find flagship
  counters above ₹50L leaking settlement and draft messages"), store the `drafts` in your
  queue, mark them sent in the ERP connector.
- **ERP post-processing**: take `get_counter_transactions` or the map from
  `generate_erp_mapping` and post into your ERP's staging table — the agent hands you the
  spec, your connector does the write.
- **Alerting**: poll `query_counters` with a `min_pending_settlement` filter or run
  `analyze_telemetry`; when a cluster flips `bottleneck`, your ops tooling pages.

## What is NOT exposed
- No webhook/outbound call: Counter Copilot never phones home to third parties; everything
  the API does is in response to your request.
- No PII bulk endpoint: you cannot ask it to dump customer personal data. Identifier-shaped
  substrings are masked at the boundary.
- No real-model dependency: the deterministic path runs keyless. An LLM provider key is
  optional and only upgrades prose quality.
- Streaming lifecycle: once the stream is closed there is no background continuation; if the
  client disconnects mid-run, the run aborts (drafts already persisted survive).

## Building on it
- The token is checked by middleware, not by the tool layer — expose the API through your own
  ingress identity if you embed it deeper in a service mesh.
- Rate limiting and audit logging are your platform's concern; the reference app keeps a
  `database` of sessions/traces you can point your retention policy at.
- For contribution: every tool is a dataclass-registered handler; adding one is adding a
  module under `app/tools` and one eager import line — the CLI tool catalog and the CI suite
  pick it up automatically.
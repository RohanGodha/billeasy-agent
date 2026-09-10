# Feature backlog

The current build is feature-complete for what it set out to demonstrate. This is what
comes next, ordered by how much each item would change the honest assessment in
[`tradeoffs.md`](tradeoffs.md).

The six items in README §16 are the headline set and are marked **★**.

---

## Tier 1 — closes a stated limitation

- [ ] **★ Trained leakage model** behind the same `Scorer` interface, A/B'd against the
      heuristic. The weights in `weights.yaml` are a starting prior, not an answer —
      this is the single item that most changes what the product can claim. Needs
      labelled leakage outcomes, which do not exist yet, so it starts with a labelling
      loop rather than a model.
- [ ] **★ Per-counter seasonal baselines.** Leakage is currently a trailing-window
      comparison against the counter's own recent history. A proper seasonal baseline
      would cut the obvious false-positive class — a festival cash surge reading as a
      cash-share spike.
- [ ] **Visual verification of the UI.** Browser automation in CI, a screenshot suite
      across the three panes, light and dark, desktop and mobile. Until this exists,
      every appearance claim in the docs stays caveated.
- [x] **Eval harness for plan and draft quality.** A golden set of asks with expected
      `target_module`, city filter and language, plus an LLM judge on draft quality.
      This is what would replace "the mock flatters the planner" with a number.
      *(Done for the plan side: `backend/evals/` — 33-case golden set across 8 groups,
      scored per-plan on 8 dimensions, provider-labelled reports, `--threshold` gate for
      CI. The draft-quality LLM judge half is still open — a keyless run can only grade
      the mock's mirroring of the prompt.)*
- [x] **Critic for the hard cases.** The current critic catches exactly one failure
      mode — an empty result set. An LLM/structural upgrade would catch a wrong city, an
      implausible module choice, or a shortlist that doesn't answer the ask.
      *(Done: deterministic heuristics in `critic.py` — a relaxed city filter passes but
      is noted loudly, an un-relaxed city contradiction and a zero-row scoring stage fail
      without a pointless replan, and the original empty-result veto keeps its replan.
      Rule-based on purpose: it shares no code path with scoring, so it cannot mask the
      scorer's own mistakes.)*
- [ ] **One-shot regeneration before redaction** in the compliance validator, so a good
      draft with one ungrounded figure gets a second attempt instead of an em dash.

## Tier 2 — product surface

- [ ] **★ Automated WhatsApp send** via the Meta Cloud API behind a `MessageChannel`
      port — approved templates, opt-in and consent tracking, idempotency keys, per-
      counter rate limiting. Human approval stays in the loop; only the transport
      changes.
- [ ] **★ Reverse channel.** Classify supervisor replies, thread them back to the
      counter, and surface the next step in the queue. Today the product is one-way.
- [ ] **Explicit confirm / modify / cancel gate** before an outreach batch is persisted,
      with a review summary card. `create_outreach_batch` is already the only write path,
      so the gate has exactly one place to live.
- [ ] **Export** — candidates, score breakdowns and drafts as CSV or XLSX for the Area
      Manager's own records and for a partner review meeting.
- [x] **Global commands** — `help`, `back`, `cancel`, `reset` recognised at any turn.
      *(Done: routed heuristically in the intent gate — `help` lists capabilities,
      `cancel`/`back` acknowledges there is nothing to pause, `reset` clears only the
      `messages` thread so past runs and their drafts stay verifiable. A message must BE
      one of the commands; "help me find counters leaking revenue" is still a task.)*
- [ ] **More Indic languages** for drafts — Marathi, Tamil, Bengali, Kannada, Telugu,
      Gujarati, Malayalam — with per-language checks that the compliance validator's
      numeral handling holds in each script.
- [ ] **Counter timeline view** — leakage risk plotted over time per counter, so a
      manager can see whether a nudge actually moved anything.

## Tier 3 — platform and scale

- [ ] **★ Multi-tenant auth** — JWT with refresh, real Area Manager accounts, per-manager
      counter ownership, row-level security in the warehouse. Replaces the shared
      password.
- [ ] **★ Vector search inside Databricks**, dropping the local Chroma dependency and the
      512 MB memory problem that currently forces BM25-only retrieval in production.
      *The lexical path was tuned hard in the meantime (retrieval stopwords, heading
      weighting, paragraph-bounded chunks, acronym expansion — the "what is NCMC at an
      AFC gate?" mis-route is fixed), but embeddings remain the real fix: a query with
      no shared vocabulary with the corpus is still out of reach.*
- [ ] **Trace retention policy.** `agent_traces` grows unbounded; add a TTL job and an
      archive path.
- [x] **Tool-result caching.** The `tool_cache` schema exists but is wired into no tool.
      Needs a `cache_key` strategy and a TTL.
      *(Done: memoiser over the deterministic read-side tools with a `sha256` key on
      tool+args, `tool_cache_ttl_seconds` expiry, `cache: "hit"` surfaced on envelopes,
      and never applied to write or generative paths.)*
- [x] **SSE auto-retry on the client** with exponential backoff, instead of the current
      error banner on connection loss.
      *(Done: retries connect-stage failures with backoff + jitter; a run that has begun
      is never re-forked because a reconnect would duplicate drafts.)*
- [x] **Router telemetry** — aggregate `route_used` and `fallback_reason` so the split
      between Claude, Gemini, Groq and mock is a measured number rather than an
      assumption.
      *(Done: `GET /trace` returns a `telemetry` block — `llm_calls`, `by_route`,
      `fallback_count` and the actual reasons — backed by a new `fallback_reason` column
      on `agent_traces`.)*
- [x] **Rocchio-style feedback retrieval.** With no scored index, textbook relevance
      feedback is out of reach; repeating a feedback term in the next query re-weights
      it in BM25 for free.
      *(Done: `KnowledgeBase.feedback_terms()` + `expand_terms` on `search()`/`ask()`,
      bounded by `rocchio_max_feedback_terms` / `rocchio_expansion_repeats`.)*
- [ ] **Rate limiting and abuse protection** on the API.
- [ ] **Pin CORS** to the exact deployed origin in production.
- [ ] **Background re-embedding job** to keep field-note vectors fresh as notes are added.

## Tier 4 — governance

- [ ] **Human review and appeals path** for any counter flagged at `elevated` or above.
      A ranked list is accusation-shaped however carefully it's worded; deploying
      against real counters needs this before it needs anything else on this page.
- [x] **PII redaction** on traces and logs. Enforced as a mask-not-detect guard: any
      free text is redacted at the chat boundary AND the `run_agent` entry gate before
      it can reach a provider, prompt, session title, `messages` row or `agent_traces`
      row — GSTIN, PAN, Aadhaar, mobile, email, idempotently (see §7.13 and §7.14 in
      README, `app/security/pii.py`). The residual gap is where merchant records sit
      *at rest* in plain SQL; that is the encryption-at-rest item, not masking.
- [x] **Reconciliation triage** for the failure class — `diagnose_reconciliation`
      labels a single counter's collection-vs-settlement gap
      (`merchant_void_reissue` ≠ `settlement_shortfall`) with next steps, backed by the
      gateway-error-code corpus. It never guesses the provider: it names the check.
- [x] **Date-effective compliance answers** — the `regulatory_schedule.md` corpus pins
      every obligation to its `effective_from`, so "does this apply now / what changed"
      is retrieved with the date, not asserted. The invoice-layout validator
      (`validate_invoice_layout`) turns a pasted bill into structural GST checks.
- [x] **ERP & API integration guidance** — `generate_erp_mapping` produces the
      Billeasy-category → Tally/Zoho/SAP ledger mapping spec with no write path, and
      `api_guide.md` documents the endpoints, session model and integration patterns.
- [x] **Telemetry synthesizer** — `analyze_telemetry` aggregates the whole estate into
      per-city bottleneck clusters (device-offline minutes, pending settlement,
      velocity) with a declared snapshot scope; deliberately uncached so health reads
      current state.
- [ ] **Signed, immutable trace bundle** per outreach batch, exportable for review.
- [ ] **Role-based prompts** — Area Partner Manager vs. regional lead vs. settlement ops,
      each seeing the queue framed for their decision.
- [ ] **Knowledge-base provenance checks** — automated assertion that every threshold
      cited as a rule is tagged as statute or as this product's own convention. The
      ₹5 lakh prospecting trigger versus the ₹5 crore e-invoicing mandate is the case
      this exists to prevent.

## Tier 5 — further out

- [ ] **Call-transcript ingestion** — transcribe supervisor calls and feed sentiment and
      intent into the counter's signals alongside field notes.
- [ ] **Outreach analytics** — reply rate, resolution rate, and whether leakage actually
      fell after a nudge. This is also the most plausible source of the labels Tier 1
      needs.
- [ ] **Anomaly alerting** — push a counter to the manager when its leakage band changes,
      rather than waiting to be asked.
- [ ] **Device telemetry ingestion** at scale. `device_offline_minutes` is already a
      first-class column rather than an inference; a real POS/AFC estate would stream it.

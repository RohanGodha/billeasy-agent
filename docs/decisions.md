# Counter Copilot — Architecture Decision Record log

*Rohan Godha · Billeasy · September 2026*

A record of the decisions that shaped this build, why each was taken, and what each
cost. Several were revised by evidence found after the fact; where that happened the
ADR says so rather than presenting the revised position as the original plan.

Sources: [`WRITEUP.md`](../WRITEUP.md), [`ASSIGNMENT-REVIEW.md`](../ASSIGNMENT-REVIEW.md),
[`README.md`](../README.md) §10–§12,
and the code in `backend/app/`.

---

## Index

| ID | Decision | Status |
| --- | --- | --- |
| [ADR-001](#adr-001--build-from-scratch-contract-first-and-make-every-key-abstraction-a-testable-claim) | Build from scratch, contract-first, and make every key abstraction a testable claim | Accepted |
| [ADR-002](#adr-002--write-a-machine-readable-domain-contract-before-dispatching-parallel-agents) | Machine-readable domain contract before dispatching parallel agents | Accepted; boundary failure recorded |
| [ADR-003](#adr-003--deterministic-scorers-with-yaml-weights--no-llm-computes-a-number) | Deterministic scorers with YAML weights — no LLM computes a number | Accepted |
| [ADR-004](#adr-004--leakage-risk-as-a-01-severity-from-a-plain-weighted-sum) | Leakage risk as a 0–1 severity from a plain weighted sum | Accepted |
| [ADR-005](#adr-005--compute-leakage-from-transaction-evidence-not-from-complaints) | Compute leakage from transaction evidence, not from complaints | Accepted |
| [ADR-006](#adr-006--a-numeric-grounding-compliance-validator-between-the-model-and-the-merchant) | Numeric-grounding compliance validator between model and merchant | Accepted |
| [ADR-007](#adr-007--human-in-the-loop-the-agent-drafts-a-person-sends-no-send-path-exists) | Human-in-the-loop: the agent drafts, a person sends | Accepted |
| [ADR-008](#adr-008--plan-and-execute-dag-with-a-critic-rather-than-a-free-running-react-loop) | Plan-and-execute DAG with a critic, not a free-running ReAct loop | Accepted |
| [ADR-009](#adr-009--hexagonal-ports-for-datasource-and-llmclient-with-failover-and-a-circuit-breaker) | Hexagonal ports for `DataSource` and `LLMClient`, with failover and a breaker | Accepted |
| [ADR-010](#adr-010--sqlite--databricks-instead-of-postgresql) | SQLite + Databricks instead of PostgreSQL | Accepted for this build; Postgres is the production answer |
| [ADR-011](#adr-011--cognitive-load-llm-routing-and-an-anthropic-adapter-because-the-brief-named-claude) | Cognitive-load LLM routing; add an Anthropic adapter | Accepted; revised after a provider-gate bug |
| [ADR-012](#adr-012--ship-a-deterministic-mock-provider-so-the-whole-agent-runs-keyless) | Deterministic mock provider so the whole agent runs keyless | Accepted |
| [ADR-013](#adr-013--react--vite-rather-than-nextjs) | React + Vite rather than Next.js | Accepted |
| [ADR-014](#adr-014--seed-data-must-genuinely-compute-its-claimed-signals) | Seed data must genuinely compute its claimed signals | Accepted |
| [ADR-015](#adr-015--make-the-seeded-network-geographically-coherent-and-counter-names-unique) | Geographically coherent network; unique counter names | Accepted after a defect was found |
| [ADR-016](#adr-016--re-tune-two-propensity-weight-sets-that-won-on-free-points) | Re-tune two propensity weight sets that won on free points | Accepted, with recorded overfitting risk (n=5) |
| [ADR-017](#adr-017--device-uptime-as-a-first-class-column-plus-a-per-peak-window-inference-fallback) | Device uptime as a column, plus a per-peak-window inference fallback | Accepted; fallback revised after it failed its own case |
| [ADR-018](#adr-018--shared-password-gate-for-a-demo-plus-three-fixes-found-by-writing-security-docs-from-source) | Shared-password gate, plus three fixes from source-derived security docs | Accepted for the demo; explicitly not production |
| [ADR-019](#adr-019--leakage-is-prioritisation-never-accusation) | Leakage is prioritisation, never accusation | Accepted |
| [ADR-020](#adr-020--hand-written-async-dag-rather-than-a-runtime-graph-framework) | Hand-written async DAG rather than a runtime graph framework | Accepted |
| [ADR-021](#adr-021--two-stage-filter-relaxation-when-a-counter-query-returns-nothing) | Two-stage filter relaxation when a counter query returns nothing | Accepted, with an unresolved transparency gap |
| [ADR-022](#adr-022--the-leakage-scorer-imports-the-propensity-modules-feature-builders) | Leakage scorer imports the propensity module's feature builders | Accepted; refactor outstanding |
| [ADR-023](#adr-023--state-modelling-conventions-as-conventions-never-as-regulation) | State modelling conventions as conventions, never as regulation | Accepted; one residual naming risk |

---

## ADR-001 — Build from scratch, contract-first, and make every key abstraction a testable claim

**Status:** Accepted

### Context

The brief was open: *"build anything — we want to understand how you work with AI."*
The budget was about a day. The risk with an open brief is a demo that exists only
because it is small: its abstractions are asserted ("modular", "swappable") and never
tested, because testing them is expensive and the answer is frequently embarrassing.

So there were two viable builds. Something new and small, carefully — where every
interface is a design claim. Or something sized so the claims have to *do* something:
three scorers, two heterogeneous datasources, a provider-routed LLM layer, seven
concurrent coding agents. On a one-day budget the second had to lean on exhaustive
verification to survive — which is exactly the thing the brief wanted to see.

### Decision

Build Counter Copilot from scratch for Billeasy, shaped so the architecture's claims are
exercised rather than asserted:

- **Contract-first swarming.** A written domain contract before the first line of code,
  then seven coding agents working concurrently in disjoint file lanes (ADR-002).
- **Ports that have to pay their way.** A `DataSource` port with two heterogeneous
  implementations and real failover (ADR-010); an `LLMClient` port that gains providers
  as one adapter each (ADR-011). Every abstraction here survived actual substitution
  during the build, not a design review.
- **One generic scoring engine.** Value, propensity and leakage scorers share the same
  explainable machinery, differentiated only by feature vocabulary and YAML weights
  (ADR-003) — so re-tuning is a YAML edit, not a deploy.

Disclose the full reasoning in the write-up rather than letting a reviewer wonder.

### Consequences

**Good**

- The port abstractions were tested against real substitution rather than asserted.
  Adding the Claude provider cost one adapter (ADR-011); the scorers turned out to be
  one generic explainable-scoring engine differentiated by feature vocabulary and
  weights, so targeting leakage cost a feature swap and a re-tune, not a rewrite.
- Considerably more surface delivered in a day than a careful small build would have
  produced: three scorers, hexagonal data and LLM layers, RAG, SSE streaming, a full UI.
- The scale forced failures out into the open — including the ones that nearly shipped
  (ADR-016) — which is the point of building this wide with this much parallelism.

**Bad**

- A one-day, parallel-built system carries its own shortcuts: the datastore choice that
  favours reviewability over production (ADR-010), the shared-password gate (ADR-018),
  and the gaps the contract did not reach (ADR-002).
- Wide builds produce confidence quickly; the discipline is that every claim needs a
  falsifying check (ADR-014) rather than a screenshot.

### Alternatives considered

- **Something small and careful.** Rejected: smaller scope for the same day, and the
  architecture claims stay asserted rather than tested — the more interesting question
  goes unasked.
- **Small build that hand-copies the patterns.** Rejected: costs nearly as much while
  still not exercising anything, because reimplementing a pattern proves only that I
  can retype it.
- **Pivot without disclosing it.** Rejected: dishonest, and it discards the single most
  interesting result of the exercise.

---

## ADR-002 — Write a machine-readable domain contract before dispatching parallel agents

**Status:** Accepted; the boundary failure it produced is recorded below and is the
point of this ADR

### Context

The plan was seven coding agents running concurrently over one codebase. The instinct
was to fan them out immediately. The reason not to: **parallel agents diverge on
naming.** If the domain-model agent decides the field is `monthly_tpv` and the frontend
agent independently decides `monthlyGmv`, nothing fails at write time. It fails at
integration, across forty files, and the speed advantage is spent debugging a collision
of one's own making.

### Decision

Write a domain contract first, as a source of truth, and do not start any agent until it
exists. It pins down, character for character:

- every model class and every field name, with the old → new mapping
- all 8 Billeasy modules with ids, take rates and eligibility thresholds
- the full propensity feature vocabulary (25 named features) and their weights
- every renamed tool file and its registered tool name
- table and column names
- **which files each agent owns**, so two agents can never touch the same file

Then run the seven agents concurrently in disjoint file lanes. The contract is a
build-time artifact, not documentation written afterwards.

### Consequences

**Good**

- Where the contract reached, seven agents agreed perfectly. The tools agent wrote code
  calling `find_counters`, `get_field_notes_bulk`, `get_holdings_bulk`; the data-layer
  agent, running concurrently with no communication, implemented exactly those names.
  They merged with zero reconciliation.
- Twenty minutes of writing bought seven-way parallelism that actually merged.
- It mirrors how the product itself works — the planner emits a typed plan and the
  executor runs against it. Contract first, then parallel execution.

**Bad — and this is the finding**

- Where the contract did not reach, the agents broke, and their failures clustered
  precisely in the gaps. The chat request field — then just `query` — was never in the
  contract; I had not thought about it. Mid-flight the API agent renamed the canonical
  name to `manager_query`
  (defensible — the contract's silence made the name ambiguous). The frontend agent hit the same field,
  reasoned that *the contract never renamed the chat request model, so renaming it
  unilaterally would break the stream*, and deliberately kept sending `query`. Both calls were
  defensible in isolation. Together they produced a frontend posting `query` to a
  backend that only accepts `manager_query` — silent, with the chat simply arriving
  empty.
- Disjoint file ownership cannot produce a cross-cutting property. Nobody owned realism,
  so nobody produced it (ADR-015).
- The contract is a static artifact and went stale the moment a decision was taken
  outside it; nothing detects that.

**The generalisation:** parallel agents are exactly as coordinated as the artifact you
gave them. The value is not writing code; it is knowing what to write down before anyone
starts, and then hunting the gaps afterwards.

**Unplanned repair, worth recording:** the prompts agent, which owned `state.py`, noticed
that `api/chat.py` had already landed using `manager_query` and renamed `AgentState` to
match — unprompted, with nothing in its briefing about it. A subagent detecting a
cross-slice inconsistency introduced by a sibling after its own brief was written, and
repairing it, is a different thing from following instructions well.

### Alternatives considered

- **Fan out immediately, reconcile at integration.** Rejected: the failure mode above,
  at forty-file scale, consuming the entire speed advantage.
- **One sequential agent.** Rejected: no parallelism, and the day does not fit.
- **A shared spec the agents may edit as they go.** Rejected: a contract that changes
  under concurrent readers is not a contract — it reintroduces exactly the divergence it
  exists to prevent.

---

## ADR-003 — Deterministic scorers with YAML weights — no LLM computes a number

**Status:** Accepted

### Context

Every figure this product shows can end up in a message to a merchant or a transit
authority, and a leakage score sends an Area Manager to ask a supervisor an
uncomfortable question. An LLM-computed score is not reproducible across runs, cannot be
decomposed, and changes when the provider changes the model behind an endpoint. The
worst available failure mode is a wrong number presented confidently.

### Decision

Draw the architectural line at arithmetic. All three scorers — value
(`scoring/value.py`), propensity (`scoring/propensity.py`), leakage
(`scoring/leakage.py`) — are heuristic Python with weights in
[`weights.yaml`](../backend/app/scoring/weights.yaml). Every score returns a per-feature
`ScoreBreakdown` carrying value, contribution, direction and a rationale in Area-Manager
language. **The model chooses what to look at and how to say it. Arithmetic and ranking
are code.**

### Consequences

**Good**

- Every number in the UI is reproducible and auditable, and decomposes into named
  weighted contributions the manager can see.
- The failure mode of a bad LLM response is a bad *plan* — visible in the trace,
  catchable by the critic — never a wrong number.
- Weights are tunable without a code change or a deploy.
- It gives a sceptical reviewer a falsification test: change `weights.yaml` and watch
  the ranking move (ADR-014).

**Bad**

- Weights are domain judgement with no ground-truth labels anywhere in the system, so
  they are transparent and tunable but unfalsifiable.
- Linear/heuristic combinations cannot learn interactions a trained model would find.
- The remaining failure — a plausible, silent, deterministic ranking error — is the
  dangerous one, and determinism does not protect against it. ADR-016 is exactly that
  bug, and it nearly shipped.

### Alternatives considered

- **LLM computes the score.** Rejected: non-reproducible, non-decomposable, and it
  drifts under the provider's model updates.
- **LLM-as-judge re-ranking deterministic candidates.** Rejected for the ranking itself;
  the critic already occupies the judgement slot, and it judges tool results rather than
  arithmetic.
- **A trained model now.** Rejected: no labelled leakage outcomes exist. Recorded as the
  next step, behind the same `Scorer` interface and A/B'd against the heuristic rather
  than replacing it on faith.

---

## ADR-004 — Leakage risk as a 0–1 severity from a plain weighted sum

**Status:** Accepted

### Context

The whole product is triage over 200–500 counters, so the money signal has to *rank*. A
boolean "leaking / not leaking" flag cannot order a queue. The neighbouring propensity
scorer already uses a logistic combination, so consistency argued for a logistic here
too. But this particular number is the one that sends a person to a counter to ask a
supervisor an uncomfortable question, and a squashed logit's output cannot be explained
to that person in a sentence.

### Decision

A plain weighted sum over features already normalised to [0,1], with **weights summing
to exactly 1.0**. The score then reads directly as *"share of the maximum leakage
evidence we could have seen"* — 0.54 means 54%. Bands: `clear` < 0.25 ≤ `watch` < 0.45 ≤
`elevated` < 0.65 ≤ `severe`, with `ESCALATION_THRESHOLD = 0.45`.

Weight ordering encodes how conclusive each signal is:

| signal | weight | why it ranks there |
| --- | --- | --- |
| `settlement_mismatch_rate` | 0.27 | measured money that did not arrive |
| `cash_share_spike` | 0.23 | strong circumstantial evidence |
| `void_reissue_rate` | 0.21 | strong circumstantial evidence |
| `receipt_issuance_gap` | 0.12 | compliance exposure |
| `peak_hour_downtime` | 0.08 | unrecorded fares |
| `pending_settlement_backlog` | 0.04 | churn pressure |
| `field_note_stress_signal` | 0.03 | corroboration, not evidence (ADR-005) |
| `refund_ratio` | 0.02 | weak signal |

### Consequences

**Good**

- The number has a meaning that survives being said out loud, which a logit does not.
- The weight table is itself an argument about evidence quality, readable by a product
  person with no statistics.
- Ranking works across the whole estate, which is the actual job.

**Bad**

- Linear, so there are no interaction terms. A settlement mismatch *and* a cash-share
  spike are treated as additive when they should probably compound — that combination is
  a much stronger case than either alone, and the score does not say so.
- The sum-to-1.0 invariant is enforced only by a comment in `weights.yaml`. A careless
  re-tune silently destroys the "share of evidence" reading while the score still looks
  fine.
- Each feature is clamped to [0,1] before weighting, so a genuinely extreme single
  signal cannot dominate — a counter with a catastrophic mismatch and nothing else caps
  at 0.27.

### Alternatives considered

- **Logistic, matching propensity.** Rejected: the output stops reading as a share of
  evidence, and auditability matters more here than consistency with a neighbouring
  scorer that answers a different question.
- **Boolean flag with a threshold.** Rejected: cannot rank 500 counters, which is the
  product.
- **A rules engine ("mismatch > 2% AND cash spike > 20pp").** Rejected: no partial
  credit, and the ordering among counters that all fire the same rule is undefined.

---

## ADR-005 — Compute leakage from transaction evidence, not from complaints

**Status:** Accepted

### Context

Existing tooling in this space catches the counters that complained. A support ticket
queue is structurally incapable of finding a counter that is leaking quietly with a
spotless support history — and that is the counter the product exists for. A field-note
sentiment scorer was the cheap path to a
"risk" number.

### Decision

Seven of the eight leakage features are computed from transaction rows and counter-health
telemetry. `field_note_stress_signal` is weighted **0.03** and labelled in
`weights.yaml` as *corroboration, not evidence*.

### Consequences

**Good**

- Surfaces the silent leaker — the case that justifies the product over a ticket queue.
- Not gameable by a supervisor who simply does not complain, and not skewed toward the
  vocal ones.
- Makes the product's central claim true rather than aspirational.

**Bad**

- Blind to anything the rail never saw. Cash that never touches a device produces no
  row at all, so a *total* bypass looks like a quiet, low-volume counter rather than a
  leak. The scorer detects drift, not absence.
- Entirely dependent on the completeness of the transaction feed. A counter whose
  terminal stopped syncing looks clean, not dark.
- It is a trailing-window comparison against the counter's own baseline, so a festival
  cash surge is a false positive until per-counter seasonal baselines exist.

### Alternatives considered

- **Sentiment-weighted leakage.** Rejected: reproduces the ticket queue's blind spot in
  a more expensive form.
- **Sentiment at parity with transaction signals.** Rejected: a complaint is not
  measured money, and equal weighting would let vocal counters outrank leaking ones —
  the exact inversion the product is meant to fix.
- **Drop the field-note signal entirely.** Rejected: it is genuinely useful
  corroboration on a counter already flagged by transactions, and 0.03 is small enough
  that it cannot flag one on its own.

---

## ADR-006 — A numeric-grounding compliance validator between the model and the merchant

**Status:** Accepted

### Context

Drafts are addressed to a counter supervisor or an outlet owner. An invented settlement
or TPV figure in a partner message is a business incident, not a UX defect. Instructing
a model in a prompt not to invent numbers is a request, not a control, and the design
assumption here is that the model *will* eventually invent a figure.

### Decision

[`app/scoring/compliance.py`](../backend/app/scoring/compliance.py) sits mechanically
between generation and display. It extracts every number from the draft, flattens the
source context (counter profile, recommended module, transaction aggregates) into an
allowed set including common ₹ abbreviations, tolerates rounding within 5% or ±1,
replaces every ungrounded figure with `—`, and reports the draft non-compliant. The
compliance report travels with the draft through the API and into the UI.

### Consequences

**Good**

- A machine, not a prompt, stands between the model and the merchant.
- The strip rate is a hallucination canary: a rising rate means the prompt is drifting,
  and it is one of the metrics named for production instrumentation.
- Asserted in the test suite — every draft in the end-to-end run must pass.

**Bad**

- Purely numeric. An invented *claim* with no digits passes untouched: *"your
  settlements have been failing all week"* is ungrounded and invisible to this
  validator.
- Regex-based over Latin numerals, so unusual formats can slip — relevant because the
  product deliberately drafts in Hindi.
- The 5%-or-±1 tolerance is loose on small numbers; a "2%" mismatch and a "3%" mismatch
  are within ±1 of each other.
- Redaction produces an awkward message with an em dash where a figure should be, rather
  than a clean regenerated draft. That is deliberate (see alternatives) but a human still
  has to fix it.

### Alternatives considered

- **Ask the model not to invent numbers.** Rejected: an instruction is not a control.
- **Regenerate on failure.** Rejected: costs a round trip inside a bounded parallel
  fanout, and the redacted draft plus a non-compliant flag gives the reviewing human
  the same information at zero latency.
- **Block the draft entirely on any ungrounded number.** Rejected: the manager loses the
  useful 90% of a message over one bad figure they could delete themselves.

---

## ADR-007 — Human-in-the-loop: the agent drafts, a person sends. No send path exists.

**Status:** Accepted

### Context

This is an accusation-adjacent workflow running on hand-tuned heuristics with no
ground truth (ADR-016). Separately, business-initiated WhatsApp messaging in India
carries DLT registration and opt-in obligations, and the DPDP Act 2023 consent rules are
documented in this product's own knowledge corpus. No code in this system checks a
consent flag.

### Decision

The agent drafts. `PATCH /outreach/{draft_id}` edits a draft, `POST /outreach/approve`
marks drafts approved, and **there is no send path in the codebase** — not disabled, not
feature-flagged, absent. Automated sending is listed as future work behind a
`MessageChannel` port that does not yet exist.

### Consequences

**Good**

- The worst possible outcome is a bad draft nobody sent.
- No consent-checking code is required, because nothing is sent — which is the only
  reason "DPDP documented, not enforced" is an acceptable position at all.
- Draft edit-rate before approval is a free prompt-quality metric.

**Bad**

- The loop is unclosed. Without send-and-outcome data there is no way to measure whether
  flagged counters were real, which is precisely what makes the weights unfalsifiable
  (ADR-003, ADR-016).
- A human approval step on 200–500 counters is a throughput ceiling, and the product
  offers no batching beyond approving a list of draft ids.
- Two things must exist before any automation: a `MessageChannel` port and a consent
  check before drafting rather than after. Neither does.

### Alternatives considered

- **Auto-send above a confidence threshold.** Rejected: a threshold on a hand-tuned
  heuristic validated against five examples is not a confidence.
- **Send with an undo window.** Rejected: the message has already reached the
  supervisor's phone; there is nothing to undo.
- **Human approval as a configurable setting.** Rejected: a setting that can be turned
  off is not a guarantee, and the absence of the code path is the guarantee.

---

## ADR-008 — Plan-and-execute DAG with a critic, rather than a free-running ReAct loop

**Status:** Accepted

### Context

Money workflow. I wanted the plan to be a **typed artifact that can be inspected, logged
and replayed**, not an emergent trace reconstructed after the fact. A free-running ReAct
loop gives you a transcript, not a plan. There was also a cost argument: a single
mega-prompt burns reasoning tokens on message generation, which does not need them, and
forces one model to do two jobs it is differently suited to.

### Decision

`Planner → loop(Tool Executor → Critic) → Synthesizer → Message Generator → Responder`.
The planner emits typed JSON parsed into a Pydantic `Plan`; a malformed plan fails closed
to a default rather than executing garbage. The critic is a distinct node that judges each
tool result and can force a replan, bounded by `AGENT_MAX_ITERATIONS` (default 6). Every
node emits a typed `TraceEvent`; the whole run is persisted and replayable from
`/trace/{session_id}`.

### Consequences

**Good**

- The plan is an object, not a narrative — inspectable before execution and diffable
  between runs.
- Separation of concerns lets the planner and the drafter route to different models
  (ADR-011), which is where the cost and latency argument pays.
- The critic is a real rejection point, not a self-assessment appended to the same
  completion.
- Every run reconstructs exactly, which is what makes the trace panel honest.

**Bad**

- The node sequence is fixed. A genuinely novel question needing a tool order the planner
  cannot express has no escape hatch — the planner's vocabulary is the ceiling.
- The critic adds a round trip per step, and on a keyless run it always passes
  (ADR-012), so its value is unmeasured.
- Under the mock provider the canned plan makes planning look better than it is; plan
  quality under a live model is the least-evaluated part of the system.

### Alternatives considered

- **ReAct.** Rejected: no inspectable plan, unbounded tool calls, and replay becomes
  transcript archaeology.
- **One large prompt doing everything.** Rejected: no verification point, wrong model for
  at least one of the two jobs, and reasoning tokens spent on message generation.
- **A fixed report plus a cron job.** Genuinely better *if* the questions were fixed —
  and I would say so. They are not: "leaking revenue", "crossed the GST threshold",
  "settlement mismatch above 2%", "now only Kochi, and firmer" cannot be pre-built as
  reports. The agent earns its complexity only because the question surface is open.

---

## ADR-009 — Hexagonal ports for `DataSource` and `LLMClient`, with failover and a circuit breaker

**Status:** Accepted

### Context

Two dependencies were known to be unreliable or absent: a warehouse that may not be
provisioned at all, and LLM providers that rate-limit, fail, and get preferred by a brief
after the code is written. ADR-001 also required the ports to be real rather
than a README bullet, and there was a cheap way to find out.

### Decision

A `DataSource` port with `FailoverSource` wrapping a primary and a secondary. One primary
failure trips a **60-second circuit breaker**, after which every call goes straight to
the secondary — so a wedged warehouse degrades the app once, not once per tool call.
Databricks runs under a 5s per-query timeout. The failover result is re-tagged
`sqlite(failover)` so the actual serving path reaches the trace and the UI on every tool
result. An `LLMClient` port with per-provider token buckets, one retry, fall-through to
the next provider, and `route_used` recorded on every call.

### Consequences

**Good**

- Failover is *visible*, not silent: every tool result carries which path served it.
- Adding Claude cost one adapter against an existing interface (ADR-011) — the moment
  the hexagonal claim stopped being a bullet and paid for itself.
- The breaker is an implemented control with a test-observable behaviour, not a comment.

**Bad**

- The breaker is time-based only, with no half-open probe: it fails back on a fixed
  timer rather than on evidence that the primary recovered.
- It is per-process, so behind replicas each instance discovers the outage separately.
- Failover is silent to the *caller* — only the source tag differs — so an entire session
  can be served from the degraded read path without anyone noticing unless they read the
  tag.
- Two datasource implementations means two places for query semantics to drift, with
  nothing asserting they agree.

### Alternatives considered

- **A single datasource.** Rejected: no failover story, and the port claim stays
  untested, which was half the point of the build.
- **Retry without a breaker.** Rejected: a dead warehouse then costs 5 seconds per tool
  call, times five plan steps, on every request.
- **A service-mesh or sidecar breaker.** Rejected: infrastructure a take-home does not
  have, and it moves the control out of the repository where it cannot be reviewed.

---

## ADR-010 — SQLite + Databricks instead of PostgreSQL

**Status:** Accepted for this build. **Postgres is the correct production answer and I
would use it.** This is the decision I expect to be challenged on.

### Context

The honest version. Postgres would have been the conventional, defensible choice and
nobody would have asked a question about it. Two forces pushed the other way:

1. **Demonstrating a data port with a real failover path requires two heterogeneous
   sources.** Postgres alone gives you one, and the port becomes an untested claim —
   which is exactly what ADR-001 set out to avoid.
2. **Reviewability.** A reviewer must be able to clone the repository and have a seeded
   500-counter network running in one command, with no database to provision, no Docker
   requirement, and no waiting.

Transaction volume at this domain's real scale is a warehouse problem rather than an
OLTP one, which made Databricks Delta a defensible primary on its own merits.

### Decision

Databricks Delta as the primary datasource; **SQLite WAL** as the failover and as the
default local store, seeded deterministically on first boot. Databricks engages only when
host, HTTP path and token are all set; otherwise SQLite is used directly, with no error
and no degradation of the demo.

### Consequences

**Good**

- Keyless, provisionless review: clone, install, run, and the canonical demo works.
- The failover path is exercised by default rather than described in prose.
- Deterministic reseed on boot makes an ephemeral filesystem (Render's free tier) a
  non-issue by design rather than by workaround.

**Bad — conceded plainly**

- SQLite is single-writer and would not survive real concurrent load. The failover path
  is a **degraded read path for continuity, not a scale path**, and claiming otherwise
  would be wrong.
- Genuinely OLTP data — sessions, messages, agent traces, outreach drafts — sits in
  SQLite, where Postgres belongs. That is not a warehouse workload by any reading.
- Two SQL dialects to keep in step, with no test asserting they return the same rows.
- No migration tooling: `schema.sql` with `IF NOT EXISTS`, which is fine for a
  reseed-on-boot demo and unacceptable for a database with state worth keeping.

**What changes for production:** Postgres for OLTP (sessions, messages, traces, drafts),
Databricks retained for transaction volume and for nightly precomputed value and leakage
scores served from a materialised table, SQLite either dropped or kept only for local
development.

### Alternatives considered

- **Postgres only.** Rejected *for this build* on the two forces above; **accepted for
  production**, as item one of the production list.
- **Postgres via Docker Compose only.** Rejected: a reviewer must run Docker and wait,
  and the port abstraction goes untested.
- **DuckDB as the local store.** Rejected: no better concurrency story, and it carries
  neither the warehouse narrative nor the one-command-review property.

---

## ADR-011 — Cognitive-load LLM routing, and an Anthropic adapter because the brief named Claude

**Status:** Accepted; **revised** after a provider-gate bug (below)

### Context

Billeasy's stack notes said *Preferred: Claude*. The inherited router had Gemini and
Groq and no Anthropic at all. Separately, the agent does two different jobs: structured
planning, which wants the strongest available reasoning, and a parallel fanout of short
WhatsApp drafts, which wants wall-clock latency. Hardcoding a model into each node makes
every provider change an edit in several places.

### Decision

Route by **kind of cognitive work**, not by node:

| Route | Order | Why |
| --- | --- | --- |
| `reasoning` (planner, critic, synthesizer) | Claude → Gemini → Groq → Mock | structured plans are where the strongest model earns its latency |
| `generation` (drafts, fanout bounded by a semaphore of 4) | Groq → Claude → Gemini → Mock | many short messages at once; wall-clock beats depth |
| `embed` (RAG) | Gemini → Mock | Anthropic publishes no embeddings endpoint |

Claude was added as one adapter behind the existing `LLMClient` port.
`ANTHROPIC_EFFORT` defaults to `low`: this is an interactive agent and depth trades
against latency the user feels.

### Consequences

**Good**

- Adding the preferred provider cost one adapter against an existing interface. That was
  the cheapest available test of whether the port abstraction was real (ADR-001), and it
  was.
- No node names a model, so a routing change is one edit in one file.
- The trace records which provider actually answered, so a fallback is observable.

**Bad — and this is the real cost of the decision**

Adding a provider to a system that names its providers in more than one place.
`agent/nodes/intent.py` gated its LLM intent classifier on `gemini or groq`. The
Anthropic adapter went in an hour earlier and that gate was never touched — so a
**Claude-only deployment would have had Claude leading every reasoning route while intent
classification silently fell back to heuristics.** No error, no log line, just a quieter
product. Found only because the security/documentation pass was pointed at the source
rather than the README (ADR-018).

**Revision:** the gate is now a generic check — *any live non-mock provider* — rather
than another hardcoded provider name, so the next adapter cannot reintroduce it.

Also bad: three providers means three rate-limit regimes, three failure modes and three
sets of JSON-mode quirks to keep working, and the fallback ordering is a judgement with
no benchmark behind it.

### Alternatives considered

- **A single provider.** Rejected: ignores an explicit brief preference and leaves no
  fallback when a free tier rate-limits mid-demo.
- **Hardcode a model per node.** Rejected: it is the bug above, generalised — every
  provider change becomes an edit in N places, and one of them gets missed.
- **An off-the-shelf LLM gateway.** Rejected: another dependency and another key in a
  build whose defining property is that it runs with none (ADR-012).

---

## ADR-012 — Ship a deterministic mock provider so the whole agent runs keyless

**Status:** Accepted

### Context

A reviewer should be able to run the canonical demo without obtaining a key, spending
money, or waiting on a free-tier signup. The test suite should pass offline. And a
reviewer who *does* run it keyless should not be shown obvious filler that makes the
product look worse than it is.

### Decision

`MockLLM` is the terminal tier of every route. It returns a canned plan for planner JSON
requests, a pass verdict for the critic, a templated ranked answer built from the actual
rendered candidate context, and templated drafts. The synthesizer substitutes a
**deterministic summary function** whenever the route resolves to mock, so a keyless
reviewer sees a real ranked answer computed from real scores rather than generic text.

### Consequences

**Good**

- Clone, install, run — the canonical demo works with an entirely empty environment. All
  six test files pass offline.
- It costs nothing to review, which is the difference between a reviewer running it and
  a reviewer reading about it.
- The keyless answer is still genuine output: the ranking, the scores and the citations
  are all real, only the prose is templated.

**Bad**

- **The mock flatters the planner.** A keyless reviewer sees perfect planning that
  reflects my few-shot prompt, not live model behaviour. Plan quality under a real model
  is the least-evaluated part of the system, and that is where the next day of work
  belongs.
- The critic always passes on the mock, so its replan path is exercised only by
  construction, not by observation.
- The deterministic summary is a function, not a model, and could easily be mistaken for
  one — which is why the README says so explicitly at the point where a reader would
  otherwise be misled.

### Alternatives considered

- **Require API keys.** Rejected: reviewer friction and cost, and the tests stop being
  runnable in a clean environment.
- **Record/replay fixtures captured from a real provider.** Rejected: fixtures go stale
  against the code, and it loses the "no keys at all" property that makes the build
  reviewable.
- **Fail closed with no LLM configured.** Rejected: there is then nothing to review.

---

## ADR-013 — React + Vite rather than Next.js

**Status:** Accepted

### Context

An authenticated internal tool for a single persona. No SEO surface, no public pages, no
server-rendering requirement, no marketing routes. The deployment budget is free tiers,
and the backend is already a FastAPI service that must exist regardless.

### Decision

React 18 + Vite + Tailwind, shipped as a static bundle on Vercel. Streaming via
`@microsoft/fetch-event-source`, chosen because it can set request headers — which is
what later made a header-only credential possible (ADR-018).

### Consequences

**Good**

- No server runtime to deploy, operate or pay for; the frontend is a static artifact on
  a CDN.
- Dev loop measured in milliseconds.
- The frontend is a pure client of a documented API, so the same API serves any other
  client without a private rendering path.
- Strict TypeScript with no `any` in `src/`; `tsc --noEmit` and `vite build` both pass.

**Bad**

- No server-side session, so the access token lives in `localStorage` — any XSS in the
  frontend yields the credential directly (ADR-018).
- Vite environment variables are read at **build time**, so changing `VITE_API_URL`
  requires a redeploy, not a restart.
- If per-user auth or server-held secrets are ever needed, a backend-for-frontend has to
  be introduced rather than already being there.
- No route-level code splitting out of the box.

### Alternatives considered

- **Next.js.** Rejected: a server runtime that buys nothing for an authenticated
  internal tool with no SEO surface, and costs a deployment target and a bill.
- **Server-rendered templates from FastAPI.** Rejected: the live trace pane, SSE
  streaming and D3 visuals want a real client application.

---

## ADR-014 — Seed data must genuinely compute its claimed signals

**Status:** Accepted

### Context

The easy version of this build seeds five hero counters with hardcoded scores so the
demo always looks good. It is faster, it is safer for a live demonstration, and it makes
the first hard reviewer question — *"why should I trust these numbers?"* — unanswerable.

### Decision

Written into the domain contract as a hard rule for every agent: **if a hero counter is
supposed to show a cash-share spike, its seeded transactions must actually produce that
number when the scorer runs.** Gateway Jetty's cash share moves 22.0% → 61.3% because
the rows say so, not because a fixture says so.

### Consequences

**Good**

- The ranking is falsifiable, and that falsification test is offered to the reviewer
  directly: change `weights.yaml` and watch the ranking move.
- It caught ADR-016. A fixture would have concealed the ranking bug entirely, because
  the demo output was correct while the reasoning underneath it was wrong.
- The hand-built hero is *beaten* by a randomly generated counter — Wadala Depot —
  Counter 8 at 57% against Gateway Jetty's 54%. A staged demo cannot produce that, and
  it is the single strongest piece of evidence that the ranking is computed.

**Bad**

- Considerably slower to build, and the constraint had to be enforced across seven
  concurrent agents.
- Every weight change can move the demo, so a re-tune requires re-verifying all five
  heroes — which is real work and is exactly how ADR-016's overfitting risk arises.
- "Genuinely computes" means internally consistent, not real. The world is still
  synthetic and modelled on my judgement of what a leak looks like.

### Alternatives considered

- **Hardcoded hero scores.** Rejected: unfalsifiable, and the first serious reviewer
  question ends the conversation.
- **Real data.** Not available, and none was needed — no Billeasy data was used.
- **Pure random noise with no engineered heroes.** Rejected: nothing demonstrable, and no
  stable anchor for the test suite to assert against.

---

## ADR-015 — Make the seeded network geographically coherent and counter names unique

**Status:** Accepted — taken *after* the defect was discovered, not designed in

### Context

This was not a plan; it was a repair. Sites, cities and operators were each drawn from a
correct list, independently. Every agent did its job. The dataset that emerged contained
**"Kashmere Gate ISBT"** — a Delhi bus terminal — sitting in **Kochi**, operated by
**MSRTC**, Maharashtra's undertaking. I only found it because a Mumbai query returned
Delhi-sounding names and my first hypothesis was that the city filter was broken. The
filter was fine. The world was broken.

The same class of defect produced two different counters both named **"Kurla Depot —
Counter 2"**, which would have quietly broken the knowledge base's name resolution — a
name that resolves to two records makes questions about either unanswerable.

### Decision

`CITY_PROFILE` in `db/seeders/faker_seed.py` scopes sites, operators and localities per
city, and a city simply omits the modes it does not run — Delhi has DTC buses and DMRC
metro and no ferries; Mumbai ferries sit under Maharashtra Maritime Board. Counter names
are drawn against a `used` set pre-seeded with the hero names, so a noise counter can
never shadow "Gateway Jetty — Counter 3".

### Consequences

**Good**

- The dataset survives being read by somebody who knows Indian transit, which is the
  audience.
- Name resolution in the knowledge base works, because a name identifies exactly one
  counter.
- The city filter's correctness became observable instead of confounded by incoherent
  data.

**Bad**

- `CITY_PROFILE` is hand-maintained, so adding a city is manual work and a wrong entry
  reintroduces the same class of defect silently.
- Uniqueness is enforced by retry-then-suffix, which can produce "Counter 9" at a site
  that realistically has eight.
- Restricting modes per city reduces variety in smaller cities, so the estate is less
  evenly distributed than a naive draw would give.

**Root cause, worth recording:** realism is a **cross-cutting property**. It belongs to
no single file, so a disjoint file-ownership split (ADR-002) structurally cannot assign
it, and no agent's brief said "make the world make sense". That is the orchestrator's
job, and it is only findable by looking at output rather than at code.

### Alternatives considered

- **Leave it.** Rejected: it breaks name resolution, and a reviewer who spots one absurd
  row discounts every other claim in the demo.
- **One global site list with a city label attached.** Rejected: that *is* the bug.
- **Fully synthetic names ("Counter 412").** Rejected: unrecognisable, and the manager
  types names — the product's entire follow-up flow depends on a name being sayable and
  unique.

---

## ADR-016 — Re-tune two propensity weight sets that won on free points

**Status:** Accepted, with a recorded overfitting risk

### Context

The heroes ranked correctly on leakage, so the demo looked right. Running every module
against every hero showed the reasoning underneath was wrong:

- **`MOD-ANALYTICS`** had four weights summing to 1.0 — `tpv_above_10l`, `txn_velocity`,
  `tenure_long`, `no_existing_module_bonus` — every one of which any large, tenured
  counter maxes out. It scored ~0.92 for *everyone* and beat reconciliation on a counter
  actively losing fares.
- **`MOD-WA-RECEIPT`** had the same shape: its actual trigger, `receipt_issuance_gap`,
  was weighted equally against three free points, so it won on counters with no receipt
  problem at all.

Only a sweep of all 8 modules × 5 counters exposed it. The headline demo was correct
throughout.

### Decision

Encode a domain rule rather than a fudge: **you do not sell a dashboard to a counter
that is bleeding — you fix the leak first.** `MOD-ANALYTICS` now carries
`settlement_mismatch_rate: -0.30` and `cash_share_spike: -0.25` against its positive
terms. `MOD-WA-RECEIPT`'s `receipt_issuance_gap` is raised to 0.45 so a module's own
trigger signal dominates it. Both justifications are written into `weights.yaml` as
comments beside the numbers, so the next person to tune reads the reasoning before the
values.

### Consequences

**Good**

- Both modules now respond to their own trigger rather than to counter size.
- The general rule — *a module's trigger must dominate its size and tenure terms* — is
  stated where a future tuner will encounter it.
- The sweep that found it (every module against every hero) is a repeatable check, not a
  one-off.

**Bad — the honest framing**

- **n = 5, and the person who chose the fix also chose the test.** This is tuning weights
  until the demo counters rank correctly, which is overfitting to five examples. The
  principle in the justification does not change the sample size.
- There are no ground-truth labels anywhere in this system, so the change is
  unfalsifiable in the strict sense.
- Negative weights make the propensity score non-monotone in counter quality. That is
  defensible for an analytics module and would be wrong if copied to another module by
  pattern-matching the shape.

**What should unsettle a reader:** the demo was right while the reasoning was wrong. That
is the failure class ADR-003's determinism cannot catch — plausible, silent and
arithmetically reproducible.

### Alternatives considered

- **Leave it; the demo passed.** Rejected: the recommendation itself was wrong, and the
  demo passing is what made it dangerous.
- **Remove the free-point features entirely.** Rejected: size, velocity and tenure are
  genuine signals for an analytics module — just not sufficient ones.
- **Train on outcomes instead of tuning.** Rejected: no labels exist. Recorded as the
  next step, behind the same `Scorer` interface and A/B'd against the heuristic.

---

## ADR-017 — Device uptime as a first-class column, plus a per-peak-window inference fallback

**Status:** Accepted; the inference fallback was **revised** after it failed on the exact
case it was written for

### Context

Two forces. First, real POS and AFC estates emit uptime telemetry, so inferring downtime
from holes in the transaction clock is modelling around missing data that is not actually
missing. Second, the original inference was correct code aimed at the wrong window: it
found days with off-peak sales but *zero* peak-hour sales. It could not detect the
scenario it was written for — CTR-0002, a depot counter that sells all morning and goes
dark at 17:00 — because the morning sales mean the day is not "dark". **A whole-day test
cannot see a half-day outage.**

### Decision

`counter_health.device_offline_minutes` is a first-class column, normalised 0 → 240
minutes so a full four-hour peak reads as 1.0, and it is used whenever present. The
inference remains as a fallback and now evaluates **per (day, peak window)**, judging
only the windows a counter actually trades in: a window served on fewer than half the
counter's active days is skipped entirely, because a morning-only jetty is not "down"
every evening — it is closed, and closed is not a leak.

### Consequences

**Good**

- The telemetry path is exact when the estate reports it, which is the realistic case.
- The fallback can now detect an evening-only outage, which is the case it exists for.
- The "only judge windows it trades in" rule removes a whole class of false positives on
  counters with genuine operating hours — previously every part-time counter looked
  permanently down.

**Bad**

- Two code paths for one signal, and they do not agree numerically. The column is minutes
  normalised against a 240-minute ceiling; the fallback is a ratio of dark slots to
  judged slots. The same counter can score differently depending on which fires, and
  nothing reconciles them.
- The fallback needs at least 4 active days, and the 0.5 "trades in this window" cutoff
  is an unvalidated constant.
- A field note mentioning "printer", "offline", "battery" or "network" floors the signal
  at 0.35 — a text signal mixed into a telemetry feature, which is a small contradiction
  of ADR-005's separation. It is tolerable only because `peak_hour_downtime` carries just
  0.08 of the leakage weight.

### Alternatives considered

- **Inference only.** Rejected: it was demonstrably wrong on its own scenario, and it
  pretends telemetry a real estate emits does not exist.
- **Column only.** Rejected: the fallback is what runs when the warehouse is unwired or a
  legacy terminal reports nothing.
- **Whole-day dark detection.** Rejected: this is the bug — it cannot see a half-day
  outage.

---

## ADR-018 — Shared-password gate for a demo, plus three fixes found by writing security docs from source

**Status:** Accepted for the demo; explicitly **not** a production posture

### Context

One reviewer persona, one deployment, one day. Per-user auth would have consumed a
meaningful share of the build and demonstrated nothing about the product. But *"it's a
demo"* is not a licence to be wrong about the controls that do exist — a control that is
present and broken is worse than one that is honestly absent.

### Decision

**The gate:** a single shared password used directly as the bearer token, compared with
`hmac.compare_digest`, enforced by a router-level `dependencies=[Depends(require_token)]`
rather than a per-handler decorator — so a new endpoint added to an existing router is
protected by construction. Only `/`, `/healthz`, `/status` and `/auth/verify` are open.

**The audit:** ask an agent to write the Security Considerations section **from the
source code**, with instructions to report anything it could not verify rather than
document it as true. Three real issues came back, all of them mine:

1. `POST /auth/verify` was **unthrottled**. Constant-time comparison stops a timing
   attack and does nothing about someone guessing at network speed. *Fixed:* 8 failures
   per client in a 300-second window returns `429` with `Retry-After`.
2. `allow_origins=settings.cors_origins or ["*"]` with `allow_credentials=True` — a
   combination the CORS specification forbids, sitting behind a fallback where **one
   empty config value would have opened an authenticated API to every origin**. *Fixed:*
   the configured list with no wildcard fallback, and `allow_credentials=bool(origins)`,
   so unset origins allow none rather than all.
3. The token was still accepted as a `?token=` query parameter — a leftover for browsers'
   native `EventSource`, which the shipped UI does not use (it streams with
   `fetch-event-source`, which sets headers). Query strings land in proxy logs, browser
   history and `Referer`. *Fixed:* header-only.

`backend/tests/test_security.py` fails if any of the three regress.

### Consequences

**Good**

- Three real vulnerabilities closed for the cost of one carefully-worded prompt.
- The generalisable technique: **documentation generated from source, with explicit
  permission to report rather than describe, is a cheap code review.** It must be pointed
  at the code and forbidden from trusting the existing docs — the same pass also found
  four places where the README described behaviour the code did not have, one of which
  was the live provider-gate bug in ADR-011.
- The gate's shape (router-level dependency) means the next endpoint is protected by
  default rather than by memory.

**Bad — stated plainly, because a reviewer will find these anyway**

- Every authenticated caller is the same principal. No JWT, no session, no expiry, no
  revocation, no RBAC; `/auth/verify` returns the password itself as the token.
- No row-level access control. Any caller can read any counter, any trace, any draft —
  not even scoped to the session they created.
- No general API rate limiting. Only `/auth/verify` is throttled; an authenticated caller
  can hammer `/chat/run` and burn the LLM budget.
- No audit log of who viewed which counter or approved which draft. `agent_traces`
  records what the agent did, not who asked it.
- No PII encryption at rest — supervisor phone numbers and field notes sit in plain
  SQLite. Gitignoring the file is not protection.
- The token lives in `localStorage` (ADR-013), so any XSS yields it directly.
- The throttle is in-memory and therefore per-process. Honest for a single-worker dyno;
  behind replicas it is not a rate limit and must move to Redis or the edge.
- DPDP consent is documented in the corpus and enforced nowhere. Acceptable only because
  nothing is ever sent (ADR-007).

**Documentation drift, unresolved:** the README's API table (§9) and environment-variable
table (§15.1) still describe the pre-fix behaviour — `?token=` accepted, and an empty
CORS list falling back to `*`. The code is correct on both counts; those two lines are
stale and should be corrected.

### Alternatives considered

- **No auth at all.** Rejected: a public deployment carrying counter data and supervisor
  phone numbers.
- **Full OIDC/JWT with row-level security.** Rejected for the day budget; it is items 1
  and 2 of the production list, not a disagreement about what is right.
- **Basic auth at the CDN edge.** Rejected: the gate then cannot be exercised by the API
  test suite, and a control that lives outside the repository cannot be reviewed with it.

---

## ADR-019 — Leakage is prioritisation, never accusation

**Status:** Accepted — a deliberate product-copy constraint

### Context

Every signal in the leakage scorer has an innocent explanation. A cash-share spike can be
a broken printer or a festival surge. A void-and-reissue pattern can be a supervisor
working around a queue. Peak-hour downtime can be a dead battery. The people on the
receiving end are transit staff and outlet owners, and the evidence against them is a
hand-tuned heuristic validated against five examples (ADR-016).

### Decision

A copy constraint applied everywhere the score surfaces — feature rationales, band
labels, the synthesized summary, and the WhatsApp drafts. Bands are
`clear / watch / elevated / severe`, not `suspicious / fraudulent`. Product copy reads
*"call the supervisor within 48h — elevated revenue leakage"*, never *"fraud detected"*.
A high score means **go look**, not *this supervisor is stealing*. Combined with ADR-007,
a person reads that framing before anyone outside the company does.

### Consequences

**Good**

- Cost nothing to implement and is defensible in a design review and in front of a
  partner.
- Keeps the product honest about what a heuristic with no ground truth can support.
- Makes the human approval step substantive rather than ceremonial — the manager is
  being asked to judge, and the copy tells them that.

**Bad**

- Softer language can under-communicate a genuine severe case. A manager who reads
  "elevated" on a real theft has been under-served by the vocabulary.
- There is no escalation vocabulary at all, so a *confirmed* case has nowhere to go
  inside the product — it leaves the system entirely.
- The constraint is enforced by prompt wording and hand-written copy, **not** by a
  validator like ADR-006. Nothing mechanically stops an LLM draft reaching for
  accusatory phrasing; the compliance validator checks numbers, not tone.

### Alternatives considered

- **A neutral risk score with no language guidance.** Rejected: the model fills the
  vacuum, generally with the most dramatic framing available.
- **Name it "fraud risk" explicitly.** Rejected: a tool that accuses transit staff on
  heuristic evidence gets somebody fired over a printer fault.
- **Hide the score; show only the recommended action.** Rejected: the transparency *is*
  the product — a manager who cannot see why a counter was flagged cannot judge whether
  to act on it.

---

## ADR-020 — Hand-written async DAG rather than a runtime graph framework

**Status:** Accepted

### Context

LangGraph is already a dependency of this project. The node sequence is fixed, and the
SSE stream needs each event on the wire the instant its node produces it — the trace pane
is the product's main demonstration of its own reasoning, and buffered events destroy it.

### Decision

`run_agent` in `agent/graph.py` is a plain async generator that calls pure node functions
and drains typed `TraceEvent`s to the caller between every step. LangGraph is retained as
a dependency and the node functions are kept pure, so the same nodes could be hosted in a
`StateGraph` if a richer DAG is ever needed.

### Consequences

**Good**

- Exact control over streaming order and disconnection: the generator checks
  `request.is_disconnected()` between events, so closing the tab stops the run rather
  than burning tokens on nobody.
- No framework abstraction between a bug and its cause.
- Nodes are pure functions, so each is testable in isolation and the migration path stays
  open.

**Bad**

- No framework checkpointing, persistence or resumption — a run that dies mid-flight is
  gone, and only the trace of what completed survives.
- Conditional branching is hand-written `if`/`else` over the six intent routes and will
  not scale gracefully past that.
- Carrying LangGraph as an effectively unused dependency is dead weight a reader will
  reasonably ask about.

### Alternatives considered

- **LangGraph `StateGraph`.** Rejected for streaming control over a sequence that is
  fixed anyway. Deliberately kept as the migration path rather than removed.
- **A task queue with a worker pool.** Rejected: the run is interactive and completes in
  seconds. It is the right answer for draft generation at scale, and that is where it is
  proposed.

---

## ADR-021 — Two-stage filter relaxation when a counter query returns nothing

**Status:** Accepted, with an unresolved transparency gap

### Context

The planner writes structured filters from natural language and will sometimes
over-constrain. A city, plus a counter type, plus a TPV floor, plus a settlement cycle
can legitimately match zero counters, and an empty result gives the Area Manager nothing
to act on and nothing to learn from.

### Decision

`tools/query_counters.py` retries on an empty result: first with the relaxable filters
cleared, then with only `exclude_modules` and a limit of 80.

### Consequences

**Good**

- The manager gets a usable answer rather than an empty list.
- The agent recovers from a planner over-constraint without spending a critic replan
  round trip.

**Bad — and this one is real**

- **The relaxation is silent.** A manager who asked for anchor counters in Kochi with a
  mismatch above 2% can be handed a list satisfying none of those constraints, with
  nothing indicating a filter was dropped. The tool result carries no relaxation flag, so
  nothing downstream — the summary, the drafts, or the UI — says the answer is to a
  different question than the one asked. That is a trust defect in a product whose main
  claim is transparency, and it should carry a flag on the result.

### Alternatives considered

- **Return the empty result.** Rejected: unhelpful for an open-ended assistant, and it
  pushes the manager into guessing which filter was too tight.
- **Force a critic replan.** Rejected: a full round trip to solve what is usually an
  over-tight numeric floor.
- **Relax one filter at a time, reporting which.** More explainable and more expensive.
  This is the right fix for the transparency gap above and was not done.

---

## ADR-022 — The leakage scorer imports the propensity module's feature builders

**Status:** Accepted; the refactor it implies is outstanding

### Context

`cash_share_spike`, `settlement_mismatch_rate`, `void_reissue_rate`,
`receipt_issuance_gap` and four others are needed by both the propensity scorer and the
leakage scorer. Two implementations of "what counts as a cash-share spike" would drift,
and the two scorers would then report different measurements for the same counter — which
would destroy the audit story that justifies ADR-003 and ADR-004.

### Decision

`scoring/leakage.py` imports the private builders (`_cash_share_spike`,
`_settlement_mismatch_rate`, …) and the shared `_RATIONALES` dictionary directly from
`scoring/propensity.py`, which is declared in the module docstring as the single source
of truth for feature math.

### Consequences

**Good**

- The two scorers cannot disagree about a measurement.
- A rationale string is written once and appears identically in a propensity breakdown
  and a leakage breakdown.
- A threshold change propagates to both by construction, not by discipline.

**Bad**

- It is a cross-module import of underscore-prefixed private names — precisely the
  coupling the leading underscore exists to discourage. Nothing prevents a refactor of
  `propensity.py` from silently breaking `leakage.py`, and there is no test asserting the
  shared surface.
- It makes `propensity.py` implicitly the lower-level module, which its name does not
  communicate.

### Alternatives considered

- **Duplicate the math in each scorer.** Rejected: guaranteed drift, and two different
  mismatch rates for one counter would be indefensible in front of an Area Manager.
- **A shared `features.py` that both import from as a public API.** The correct answer.
  Not done, and recorded here as the outstanding refactor.

---

## ADR-023 — State modelling conventions as conventions, never as regulation

**Status:** Accepted; one residual naming risk

### Context

The agent cites a retrieval corpus covering GST e-invoicing, RBI payment-aggregator
rules, settlement norms, MDR, NCMC and DPDP. Several thresholds this product uses to
*prospect* look superficially like statutory thresholds. An agent that cites documents
must not launder a product heuristic into a regulation — a merchant told "the law
requires this at ₹5 lakh" has been misinformed by a system that sounded authoritative.

### Decision

The corpus labels every such figure **`[product convention]`** and states the rule at the
top of the document: *never present a product convention to a partner as law.* The
worked example is explicit:

> `gst_threshold_crossed` fires at **monthly TPV ≥ ₹5,00,000** (≈ ₹60 lakh annualised).
> That is a *prospecting* trigger for `MOD-BILLING` — a counter at that volume is well
> past the GST **registration** thresholds and should be issuing compliant bills. **It is
> not the ₹5 crore e-invoicing threshold and must never be described to a merchant as
> one.**

The corpus also carries a standing instruction that figures are representative and must
be confirmed against the current CBIC notification, RBI circular or NPCI operating
circular before any commitment is made.

### Consequences

**Good**

- The distinction is stated in the retrieved text itself, so it travels with the citation
  rather than living in a developer's head.
- It sets a reusable pattern: any future threshold added to the scorers gets a convention
  label or a statutory citation, not silence.

**Bad**

- Enforced by corpus wording and retrieval quality, not by a validator. Retrieval is
  BM25-only by default (Chroma exceeds the free tier's memory), so a question can land in
  the wrong document and miss the label entirely.
- **Residual naming risk:** the feature is called `gst_threshold_crossed`, and the domain
  contract even annotated it "(e-invoice mandate band)". The name implies a statutory
  threshold that the corpus then has to spend a paragraph disclaiming. A feature named
  `gst_billing_prospect_band` would carry the distinction in the identifier and need no
  disclaimer. The label is a patch over a naming error.

### Alternatives considered

- **Cite the real statutory threshold (₹5 crore AATO) as the trigger.** Rejected: almost
  no counter in this network reaches it, so the feature would never fire and the module
  would never be recommended — the trigger is a commercial one and should be honest about
  that.
- **Say nothing and let the number stand.** Rejected: the agent cites documents, and a
  cited convention presented as a rule is worse than an uncited one.
- **Rename the feature.** The correct fix. Not done, because the name is pinned by the
  domain contract (ADR-002) and appears in the weights file, the scorers and the frontend
  types; recorded here as outstanding.

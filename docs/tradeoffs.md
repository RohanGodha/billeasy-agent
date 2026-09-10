# Trade-offs and limitations

The long version of README §10. Nothing here is softened; where this document differs
from the README it is by being **more** specific.

**The frame:** Counter Copilot is a **demo-grade system running on synthetic data**. It
is production-*shaped* — hexagonal ports, typed tools, failover, an audit trail — and it
is not production-*ready*. The gap between those two words is what this document is
about.

---

## 1. The things I did not verify

### The UI is build-verified, not eyeball-verified

`npx tsc --noEmit` passes with zero `any` in `src/`. `npm run build` produces a clean
production bundle. The dev server serves. Every API payload the components consume was
exercised over HTTP. **No screenshot was taken in the final pass, and no browser
automation was available in the build environment.**

So: the components compile, and they are fed correct data. Whether the three-pane
workspace, the score-breakdown chart, the D3 pipeline visual and the mobile bottom
navigation actually *look* right on a screen is unverified. Treat every claim about the
UI's appearance in any document in this repo as unverified.

### There is no performance measurement

The timing figures in [`execution-flow.md`](execution-flow.md) are indicative numbers
from local runs. There is no benchmark harness, no load test, and no P95 measurement
anywhere in the repo. Do not read them as an SLO.

### There is no eval harness

*Built since: `backend/evals/` is a 33-case golden set with a runner that grades the
planner's *plan* on 8 independent dimensions and writes a provider-labelled report. The
honest caveat stands for keyless runs — the mock mirrors the prompt, so a green mock
score does not prove a real model plans well. The next step is running it against one
free key.*

Eight backend test suites pass keyless against the mock LLM. They assert real behaviour —
filter correctness, that Gateway Jetty surfaces through scoring rather than a fixture,
that the metro cluster's top recommendation is `MOD-ETICKET`, that `leakage_risk` is a
valid float with a valid band, that every draft passes the compliance validator, that a
named counter resolves to its own record, and now that the action queue stays ordered.
What they do **not** assert is *plan quality* or *draft quality* under a real model —
the eval harness scores plan quality but against the mock in a keyless environment.

---

## 2. The scoring is judgement, not learning

**There are no ground-truth labels anywhere in this domain, and there is no way to
manufacture them from synthetic data.** No counter in this dataset has a confirmed
leakage outcome. So every weight in `weights.yaml` — the leakage weights, the ~25
propensity features, the per-module weightings, the band-normalisation cut points — is
hand-tuned domain judgement.

That has three specific consequences worth stating plainly:

1. **The weights were tuned until five hero counters ranked correctly.** That is n=5,
   and the person who chose the fix also chose the test. The two changes made were
   defensible on domain grounds — `MOD-ANALYTICS` and `MOD-WA-RECEIPT` were winning on
   "free points" that any large tenured counter maxes out, rather than on their own
   trigger signal, so analytics now carries *negative* weights on mismatch and cash
   spike, on the rule that you don't sell a dashboard to a counter that's bleeding. But
   the honest framing is still: fitted to five examples.
2. **The relative ordering of the leakage weights is a claim, not a finding.** Putting
   `settlement_mismatch_rate` at 0.27 above `cash_share_spike` at 0.23 says measured
   money that didn't arrive beats circumstantial evidence. That's a reasonable prior. It
   is not a measured effect size.
3. **`field_note_stress_signal` is weighted at 0.03 deliberately**, so a complaint
   corroborates evidence rather than creating it. That's the design's central bet — that
   the counter worth finding is the one leaking *without* having complained — and it is
   untested against reality.

The right next step is a trained model behind the same `Scorer` interface, A/B'd against
this heuristic. Not more hand-tuning.

---

## 3. Leakage risk is prioritisation, not accusation

A high leakage score means **look here**. It does not mean a supervisor is stealing.

Several of the signals have entirely innocent explanations: a broken receipt printer
produces a receipt-issuance gap; a festival cash surge produces a cash-share spike; a
genuine queue at a jetty produces void-and-reissue activity; a network outage produces
peak-hour downtime. The scorer cannot distinguish those from the fraud case, and it does
not try to.

Every user-facing string is therefore *"call the supervisor"*, never *"fraud
detected"*. This was a deliberate constraint on the product language, because a tool
that quietly accuses transit staff on heuristic evidence is a tool that gets someone
fired for a printer fault.

**The residual risk that stays:** a ranked list is itself an accusation-shaped artifact,
however carefully it's worded. Anyone deploying this against real counters needs a human
review step and an appeals path, and neither of those is in this build.

---

## 4. Retrieval is weaker than the architecture suggests

The hybrid retriever is real — BM25 plus Chroma dense retrieval, fused with RRF at
K=60, re-ranked with MMR at λ=0.7. But **Chroma exceeds Render's free-tier memory
budget, so the deployed default is BM25-only**, lexical, no dense leg. RRF and MMR still
run, over one ranking.

Retrieval quality is visibly worse in that mode. A question about NCMC at an AFC gate
can land in the chargebacks FAQ. The citations remain honest — it tells you which
document it used — but the document can be the wrong one. This is the subsystem most
likely to embarrass the product in a live demo, and it is why the demo script tells you
to call it out yourself rather than hope nobody asks.

---

## 5. The mock LLM flatters the whole system

The deterministic mock provider means the entire agent runs with zero API keys, which is
a genuine reviewability win. It is also a distortion:

- **Canned plans.** A keyless reviewer sees perfect planning that reflects the few-shot
  prompt, not live model behaviour. Plan quality under a real model is untested.
- **Canned summaries.** The synthesizer explicitly detects a mock route (or a
  suspiciously short response) and substitutes `_fallback_summary`, a deterministic
  data-grounded summary built from the real candidates. That's honest — it never shows
  generic filler — but it means the summary you see keyless is code, not a model.
- **Canned drafts.** They pass the compliance validator, which proves the validator
  runs, not that it catches a real model's real hallucination. The validator is
  independently unit-tested, but the end-to-end proof is weaker than it looks.

---

## 6. The critic is a heuristic with one job

`nodes/critic.py` is rule-based, not an LLM call. That was a deliberate saving of five
LLM round trips per run, and it makes the run cheaper and faster.

It catches exactly one failure mode: `query_counters` returning zero rows. Recovery is
blunt — strip the numeric thresholds and the city filter, raise the limit, retry once.

What it **cannot** catch: a plan that filtered the wrong city, a `target_module` that
doesn't match the ask, a shortlist that is technically non-empty but irrelevant, a
propensity result that is uniformly implausible, or a synthesized summary that overstates
its own evidence. Every one of those would sail through as `verdict: pass`.

Upgrading to an LLM critic for the hard cases is a contained change and it's on the
backlog. Calling the current one "a critic in the loop" is accurate but generous.

---

## 7. Auth, tenancy and data handling

- **Single-tenant, shared-password.** One `APP_PASSWORD`, constant-time compared, sent
  as `X-Access-Token`. There are no user accounts, no roles, and no per-manager data
  isolation. Every session can see every counter.
- **No rate limiting on the API.** Nothing stops a caller from running the pipeline in a
  loop.
- **No PII redaction on traces or logs.** `agent_traces` stores full event payloads
  including candidate records and draft text. With synthetic data that is harmless. With
  real merchant data it would not be.
  *(2026-09-10: the free-text surfaces are now masked pre-persistence — README §7.13,
  `app/security/pii.py` — so a trace holds counters and costs, not raw identifiers.
  `agent_traces` retaining full *candidate and draft* payloads remains true; those carry no
  raw identifiers after masking.)*
- **`agent_traces` grows unbounded.** There is no TTL or retention job.
- **CORS** is driven by `APP_CORS_ORIGINS` and should be pinned to the exact deployed
  origin in production rather than left broad.

---

## 8. The data is synthetic, and its realism is hand-maintained

500 counters across 14 cities, ~15,000 transactions, deterministic under
`Faker.seed(7)`. Modelled on real Indian transit and retail — real terminal names, real
operators, each city carrying only the transit modes it actually runs — but **entirely
invented**. No Billeasy data was used, and none is required to run this.

Two things about that realism are worth knowing:

- It is a **cross-cutting property that nothing owns**. An earlier pass produced a Delhi
  bus terminal sitting in Kochi under a Maharashtra operator, and two different counters
  sharing a name — each field drawn correctly from a correct list, independently. That
  class of bug is only findable by looking at output, and there is no test that would
  catch a new instance of it.
- The **hero counters genuinely compute**. Their signals are arithmetic over seeded
  transaction rows, not hardcoded scores, which is why changing `weights.yaml` changes
  the ranking. That is the check to run if you suspect the demo is rigged — and it is
  also the reason the demo is fragile to weight changes.

---

## 9. Modelling conventions are not regulations

The knowledge base flags explicitly where a threshold is this product's own heuristic
rather than statute. The clearest case: the **₹5 lakh TPV prospecting trigger is not the
₹5 crore e-invoicing mandate**. They are different numbers doing different jobs, and an
agent that cites documents must not launder a convention into a regulation.

This is stated because the failure would be quiet and expensive: a manager repeating a
"threshold" to a merchant as though it came from the GST rules.

---

## 10. What was deliberately not built

| Skipped | Why | What production would need |
| --- | --- | --- |
| Trained leakage / propensity model | No labels exist; explainability mattered more than a few points of AUROC | Gradient-boosted scorer behind the same `Scorer` interface, A/B'd against the heuristic, with an offline labelling loop |
| Real WhatsApp send | Requires a Meta Cloud API business account and approved templates | `MessageChannel` port with adapters, plus idempotency, rate limiting, opt-in and consent tracking |
| Inbound reply handling | Out of scope for a one-way drafting demo | Classify supervisor replies, thread them to the counter, surface the next step |
| Multi-tenant auth / SSO | Single-manager demo | JWT + refresh, per-tenant isolation, row-level security in the warehouse |
| Distributed tracing (OTLP) | Free tier has no backend for it | Same `TraceEvent` payload, additional exporter to a hosted collector |
| Vector search inside Databricks | Would remove the local Chroma dependency and its memory cost | Move the dense leg into the warehouse |
| Background re-embedding | Unnecessary at 500 counters | Scheduled job to refresh field-note vectors |
| Tool-result caching | Doubtful at 500 counters — a scatter/gather over SQLite is cheap, and the faces change during the day | *(Shipped as a keyless memoiser, `tool_cache` + `tool_cache_ttl_seconds`; the productive part is the discipline it forced: a cache key over raw tool+args that can never touch a write or generative path.)* |
| Seasonal per-counter baselines | Leakage is currently a trailing-window comparison | Proper seasonal baselines to cut festival-cash false positives |
| One-shot regeneration before redaction | Conservative default was simpler and safer | Regenerate once with the offending figure removed, then redact only if it recurs |
| Per-manager preferences | Single-manager demo | Preference table: default tone, default language, default review cadence |

---

## 11. Operational limits of the free tier

- **Render free tier:** ~50 s cold start, 512 MB RAM, sleeps after 15 minutes idle. A
  self-ping and an external cron mitigate it; they do not remove it. The 512 MB ceiling
  is also why Chroma is optional.
- **Ephemeral filesystem:** the deployed backend reseeds deterministically on boot. Any
  outreach batch persisted in a previous instance is gone.
- **Databricks Free Edition:** serverless warehouse cold start is ~30 s, well past the
  5 s timeout, so the trace will read `sqlite` until it warms. That is the failover
  working, and it is visible rather than hidden — but it does mean the "live warehouse"
  claim is often not what actually served the demo.
- **LLM free tiers:** Groq and Gemini both have daily caps. The draft fanout is bounded
  at 4 concurrent for exactly that reason. Exhaust the quota and the router silently
  degrades to the mock, with `fallback_reason` recording why.
- **No real-time streaming reads.** Every warehouse read is batch.

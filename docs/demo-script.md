# Demo script — Counter Copilot

*Every counter, accounted for.*

Four scenarios, in order, one session. Target length **7 minutes**; scenarios A and B are
the spine, C and D are the proof it reasons rather than pattern-matches.

The persona throughout is **Rohan, Area Partner Manager — Mumbai West**. He owns a few
hundred counters: retail POS outlets, ferry jetties, bus depots, metro ticket counters.
Every morning he asks the same question — *which counters, and what do I say?*

> **Say this once, early, and mean it:** the network is **synthetic** — 500 counters,
> ~15,000 transactions, deterministically seeded with `Faker.seed(7)`, modelled on real
> Indian transit and retail but invented. No Billeasy data was used or is needed.

---

## Before you record

1. **Warm the backend.** Hit `/healthz` on the deployed Render service once — free-tier
   cold start is ~50 s. Locally, `uvicorn app.main:app --port 8000` and wait for the
   deterministic seed to finish on first boot.
2. **Warm the indexes.** `cd backend && $env:PYTHONPATH="." && python tests/test_agent_e2e.py`
   once. It builds the BM25 index and exercises the full pipeline, so the first
   on-camera query isn't the one that pays for initialisation.
3. **Check which providers are live.** `GET /status`, or read the top bar. Decide before
   recording whether you are demoing keyless (mock LLM, ~1 s runs, canned plans) or with
   real keys (~5 s runs, live planning). Say which one on camera — see the caveat in
   scenario A.
4. **Optional — make "Send on WhatsApp" open a real chat.** Copy
   `frontend/.env.example` to `frontend/.env.local` and map a hero counter to a number
   you control:
   `VITE_DEMO_PHONES={"Gateway Jetty":"91XXXXXXXXXX"}`. `.env.local` is gitignored.
5. Browser at 100% zoom, notifications off, 1080p. Sign in with password `shared`.

---

## 0:00–0:50 — Frame the problem

**Show:** the login screen, then the empty three-pane workspace.

> "Billeasy runs the digital payment and ticketing rail for offline India — retail POS
> outlets and government mass transit: ferry jetties, bus depots, metro stations. Money
> enters at the physical edge, Billeasy captures it, issues a GST bill or an e-ticket,
> and settles T+1.
>
> The edge is where it breaks. Cash quietly bypasses the digital rail. A ticket gets
> issued, voided, and reissued — the cash goes in a pocket. A terminal sits dark through
> the evening peak. What was captured doesn't match what was settled.
>
> I'm Rohan. I'm an Area Partner Manager and I own a few hundred of these counters. A
> dashboard tells me what happened last month. A support queue only tells me about the
> counters that complained — which is structurally the wrong set, because the counter
> quietly leaking money has no reason to call me.
>
> Counter Copilot is one chat box that answers both halves of my morning: which
> counters, and what do I say."

---

## Scenario A — the canonical ask (0:50–3:40)

**Type:**

```
Find ferry and bus counters in Mumbai leaking digital ticket revenue this month and draft WhatsApp nudges for the depot supervisors.
```

Let the trace populate. Narrate against it as it goes.

**Intent → Plan.**
> "First an intent gate — this is a task, so it runs the pipeline. A capability question
> or a policy question would never get this far, and you'll see that in scenario D.
>
> The planner emits a typed JSON plan: intent, `target_module` — it picked
> `MOD-RECON`, Settlement & Fare Reconciliation — the city filter, the language, and
> five ordered steps. That's the reasoning route, and with an Anthropic key set it's
> Claude, because a structured plan is where the strongest model earns its latency."

**Tool calls.**
> "Five typed tools, in order: `query_counters`, `compute_counter_value`,
> `predict_module_propensity`, `recommend_modules`, `search_field_notes`. Every result
> is tagged with the data source it came from — `databricks` or `sqlite` — because
> there's a real failover behind that port and I want to know which one served me."

**Critic.**
> "After each tool there's an explicit verdict. It's rule-based, not an LLM call — five
> LLM round trips removed from the hot path. It catches one failure mode properly: if
> the filter returns nothing, it strips the thresholds and retries once. That cap is why
> it can't loop."

**Candidates.**
> "Now the ranking. Top of the queue is **Wadala Depot — Counter 8** at **0.57 leakage
> risk — elevated**. Second is **Gateway Jetty — Counter 3** at **0.54**.
>
> I want to point at that order deliberately. Gateway Jetty is the counter I *hand-built*
> for this demo. It doesn't win. It's beaten by a randomly generated counter that happened
> to get a worse leakage profile from the seeder. I could have tuned that away and had my
> showcase counter sit at number one — I'd rather you see that the ranking is actually
> computed. The heroes are engineered to be findable, not to win."

Open the drawer on Gateway Jetty. Point at the leakage breakdown.

> "This is the part I'd defend in a review. That 0.54 isn't a model output I can't
> explain — the weights sum to 1.0 over features that are each between 0 and 1, so 0.54
> literally reads as *54% of the maximum leakage evidence we could have seen*.
>
> Top driver: `void_reissue_rate`, contributing 0.21. Tickets issued, voided, reissued —
> the classic cash-pocketing pattern. Second: `cash_share_spike` at 0.187 — this
> counter's cash share moved from 22% to 61% against its own baseline. Third:
> `settlement_mismatch_rate` — what was captured doesn't reconcile with what was
> settled.
>
> And the language matters. It says *call the supervisor within 48 hours*. It does not
> say *fraud detected*. Every one of those signals has an innocent explanation — a dead
> printer, a festival cash surge. This is prioritisation, not accusation."

Scroll to the WhatsApp draft.

> "Ten drafts, generated in parallel — that's the generation route, Groq first, because
> it's many short messages at once and wall-clock beats depth.
>
> Then the bit I actually care about: a compliance validator pulls every number out of
> the draft and checks it against the source data. Anything the data doesn't support
> gets replaced with a dash before I ever see it. It assumes the model will eventually
> invent a figure, and mechanically refuses to let that reach a partner. The drawer
> tells me exactly which numbers were stripped, if any."

Click **Send on WhatsApp**.

> "It opens WhatsApp with the message pre-filled. I read it, I edit it, I send it. The
> agent drafts; a person sends. That's deliberate."

**If you are demoing keyless, say so here:**
> "Everything you've just watched ran with **zero API keys** — there's a deterministic
> mock provider behind the same port, which is how you can review this without paying
> for anything. The honest caveat: the mock returns canned plans, so what you saw was my
> few-shot prompt, not live planning. With a real key the plan is genuinely generated,
> and that's where I'd spend the next day building evals."

---

## Scenario B — stateful refinement (3:40–4:50)

**Same session. Type:**

```
Now only Kochi, and make it firmer.
```

> "I don't restate the task. The intent gate sees a refinement with history behind it,
> routes it as a follow-up, and the planner rewrites it into a standalone task using the
> previous turn before it plans anything.
>
> Two things changed: the city filter is now Kochi, and the tone is firmer. Watch —
> Kochi's counters are Kochi's counters. Water Metro ferry jetties, KSRTC bus, Kochi
> Metro Rail. The seed data is geographically coherent: each city only has the transit
> modes it actually runs, under the operator that actually runs them. That sounds like a
> detail. It isn't — the first pass of this dataset had a Delhi terminal sitting in
> Kochi under a Maharashtra operator, and I only caught it because the output looked
> wrong.
>
> The drafts regenerate at the new tone, and every one of them goes through the same
> compliance validator."

---

## Scenario C — reasoning, not hardcoding (4:50–6:00)

**New ask:**

```
Which retail outlets crossed the GST e-invoice threshold but aren't issuing compliant bills? Draft in Hindi.
```

> "Nothing here says which module to sell. Watch the plan: `target_module` comes back as
> **`MOD-BILLING`** — Digital Billing & GST e-Invoice — not the reconciliation module it
> defaulted to in scenario A. And `language` is **Hindi**, so the drafts come out in
> Devanagari.
>
> Note the intent routing too. This question names GST — a compliance term that would
> normally route to the knowledge base. But it asks about a *set of outlets*, so it's a
> pipeline run, not a policy lookup. That precedence is explicit in the code.
>
> The signal doing the work here is the **receipt-issuance gap**. In the transaction
> table, a null instrument means no GST bill and no e-ticket was issued. Expect
> **Shree Provision Stores — Pune** near the top: past the ₹5 lakh band with a 46%
> receipt gap."

**Say the honest caveat, on camera:**
> "One thing I want to flag rather than let you assume. That ₹5 lakh trigger is *this
> product's prospecting heuristic*. It is **not** the statutory ₹5 crore e-invoicing
> mandate. The knowledge base says so explicitly, because an agent that cites documents
> must not launder a convention into a regulation."

---

## Scenario D — knowledge, not counters (6:00–6:40)

**Ask:**

```
What is NCMC and how does it work at an AFC gate?
```

> "Different route entirely. The intent gate classifies this as a knowledge question, and
> it short-circuits — no planner, no tools, no counters scored, no drafts. It answers
> from the reference corpus with citations, and the candidate pane stays empty. A
> question about a payment standard shouldn't cost five tool calls."

**And immediately be honest about it:**
> "This is also the weakest thing in the build, so let me point at it rather than hope
> you don't. Chroma exceeds Render's free-tier memory, so the deployed default is
> **BM25 only** — lexical, no dense retrieval. Ask about NCMC at an AFC gate and it can
> land in the chargebacks FAQ. It cites honestly; it just retrieves imperfectly. Install
> `requirements-rag.txt` locally and you get the full dense-plus-lexical hybrid, fused
> with RRF and re-ranked with MMR."

Optionally show the guardrail in the same breath — *"write a poem about Mumbai rain"* is
declined, and *"what modules can you recommend?"* is answered as a capability question
without running the pipeline.

---

## 6:40–7:00 — Close on the trade-offs

**Show:** `/trace/{session_id}`.

> "Every event you watched is persisted and replayable. That's the audit trail.
>
> Three things I'd want on the record. The scoring is **heuristic** — there are no
> ground-truth leakage labels, so those weights are hand-tuned domain judgement.
> Transparent and tunable, but judgement; change `weights.yaml` and the ranking changes,
> which is the check to run if you think the demo is rigged. The data is **synthetic**.
> And the UI is **build-verified, not eyeball-verified** — types check and the
> production build passes, but I took no screenshot in the final pass and I'm not going
> to tell you it looks right when what I verified is that it compiles and is fed correct
> data.
>
> That's Counter Copilot. Every counter, accounted for."

---

## Copy-paste queries

1. `Find ferry and bus counters in Mumbai leaking digital ticket revenue this month and draft WhatsApp nudges for the depot supervisors.`
2. `Now only Kochi, and make it firmer.` *(same session)*
3. `Which retail outlets crossed the GST e-invoice threshold but aren't issuing compliant bills? Draft in Hindi.`
4. `What is NCMC and how does it work at an AFC gate?`
5. `Write a poem about Mumbai rain.` *(guardrail — optional)*
6. `What modules can you recommend?` *(capability question — optional)*

## The five hero counters, for reference

| id | counter | engineered signal | surfaces |
| --- | --- | --- | --- |
| `CTR-0001` | Gateway Jetty — Counter 3 (ferry, Mumbai) | cash share 22.0% → 61.3%, void/reissue 20%, mismatch 5.7% | `MOD-RECON` |
| `CTR-0002` | BEST Depot — Wadala Counter 1 (bus, Mumbai) | 240 min dark across the 17:00–21:00 peak, 39% receipt gap | `MOD-OFFLINE` |
| `CTR-0003` | Sahakari Bhandar — Dadar (retail, Mumbai) | digital share 68% → 91%, ₹18L TPV, no loyalty module live | `MOD-LOYALTY` |
| `CTR-0004` | Metro Line-1 Andheri — TVM Cluster (metro, Mumbai) | NCMC share only 8% at high velocity | `MOD-ETICKET` |
| `CTR-0005` | Shree Provision Stores — Pune (retail) | past the ₹5L band with a 46% receipt-issuance gap | `MOD-BILLING` |

They reach the top **by computing real signals** off seeded rows — nothing is hardcoded.

---

## Contingencies

| Symptom | Cause | What to do |
| --- | --- | --- |
| Drafts show `llm_route: mock` when you expected Groq | Quota exhausted or key unset | Check `/status`. Either wait, or re-frame the segment as the keyless demo — it's a feature, not a stumble. |
| First query is slow | Render cold start (~50 s) or first-boot seed | Run one throwaway query before recording. |
| A tool result reads `sqlite` when you promised Databricks | Warehouse cold-started past the 5 s timeout; the 60 s circuit breaker tripped | Say it out loud — the failover working is a better demo than the failover not being needed. |
| "Not on WhatsApp" when clicking send | The counter isn't in `VITE_DEMO_PHONES`, or the number isn't a registered WhatsApp account | Map a hero counter to your own number in `frontend/.env.local`. |
| Scenario D answers from the wrong FAQ | BM25-only retrieval | Don't hide it — it's in the trade-offs and calling it yourself is stronger than being caught. |

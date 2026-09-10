# Security & Data-Protection Policies

How Counter Copilot treats data on the way through the agent, under India's DPDP Act and the
partner's security posture. This is the *policy* corpus; enforcement lives in code — prompts,
traces, and stored messages are masked by the PII guard before any LLM or persistence step.

## The PII guard (in force)
- ANY free text entering the agent is masked at two chokepoints: the chat boundary (before it
  is persisted, titled, or built into state) and the agent entry gate (so direct callers get
  the same shield). Placeholders `[GSTIN]`, `[PAN]`, `[AADHAAR]`, `[PHONE]`, `[EMAIL]` replace
  the matched identifiers.
- Masked before: LLM prompts, knowledge-base retrieval, session titles, the messages thread,
  and every row in `agent_traces`. Masking is idempotent — a masked trace replayed never
  re-exposes a number.
- What it covers: GSTIN, PAN, Aadhaar, Indian mobile numbers, emails. Business open secrets
  (counter name, city, operator) are NOT masked; blanking them would break every answer.
- What it does NOT claim: a full DLP sweep. It is a DPDP-identifier guard, not a redaction
  system for arbitrary secrets — a merchant's free-text invoice notes would still be visible
  in a trace.

## Consent & notice (DPDP)
- A counter that processes customer personal data must show a concise notice and take consent
  where consent is the legal ground. Billeasy is the data fiduciary; counters are controllers
  of their own records.
- Counter Copilot does NOT build, store, or export a customer PII database. It scores counters,
  generates outreach drafts, and answers from reference documents. PII travels only as a
  *query* (e.g. "find counters of merchant X") and is masked before it reaches a provider.

## Data retention & lifecycle
- `messages` (the session thread) powers follow-up decoding; `reset` clears the thread while
  keeping the trace for auditability.
- `agent_traces` retains the run with masked prompts so a security review can replay *what*
  ran but never the raw identifiers.
- `tool_cache` stores deterministic results (no PII is cached, only counter aggregates and
  scores for non-PII inputs).

## The security-audit workflow
For "audit our data handling / what do we do with PII / are prompts logged in plaintext /
SOC2-style questions", Counter Copilot answers from THIS corpus: it walks the partner through
what is masked, where traces go, and what survives erasure. It does not stage a real audit —
it is the documented posture your auditor starts from. Real evidence (a SOC 2 report, DPDP
breach register) is an ops-desk deliverable, not an agent output.

## Standing rules
- Never paste a customer's PAN/Aadhaar/bank account into a prompt to probe the agent — it is
  masked; use mock values like `ABCDE1234F` (which is also a valid PAN shape, so mask it or be
  aware the placeholder appears).
- Never ask the agent to "send" anything to a regulator — it has no send path by design.
- Escalations (fraud, breach, chargeback surge) go to the security ops desk with the counter
  id and batch date, never to the counter operator.
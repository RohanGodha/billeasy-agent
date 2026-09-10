"""Structured capabilities + 50 real FAQs.

Single source consumed by:
  - the FAQ node (grounding text),
  - the /meta/capabilities + /meta/faqs API,
  - the frontend "Guide" panel (what the agent does, modules, examples, FAQs).
"""
from __future__ import annotations

CAPABILITIES: list[dict[str, str]] = [
    {"title": "Find counters", "desc": "Search the network by city, counter type (retail/ferry/bus/metro), tier, monthly TPV, daily transactions, settlement cycle, or live modules."},
    {"title": "Score counter value", "desc": "Rank counters by an explainable value score (monthly TPV, digital share, tenure, transaction velocity)."},
    {"title": "Detect revenue leakage", "desc": "Flag cash-share spikes, void-and-reissue patterns, settlement mismatches and payout backlogs before they become a write-off."},
    {"title": "Predict module fit", "desc": "Estimate each counter's propensity to adopt a Billeasy module, with the top driving signals shown."},
    {"title": "Recommend modules", "desc": "Suggest the best-fit, eligibility-checked Billeasy module for each counter — recon, e-ticketing, billing and more."},
    {"title": "Draft supervisor nudges", "desc": "Generate a personalised, compliance-checked WhatsApp message per counter for the supervisor or outlet owner."},
    {"title": "Refine conversationally", "desc": "Follow-ups like 'now only the jetties' or 'make it warmer' build on the previous result."},
    {"title": "Multilingual drafts", "desc": "Write nudges in Hindi, Marathi, Tamil and more — English by default. Depot supervisors read what they're comfortable with."},
    {"title": "Explain every score", "desc": "Show the top contributing signals so you know exactly why a counter surfaced."},
    {"title": "Show its reasoning", "desc": "Stream the full plan -> tools -> critic -> synthesis trace, replayable per session."},
]

MODULES: list[dict[str, str]] = [
    {"id": "MOD-BILLING", "name": "Digital Billing & GST e-Invoice", "category": "billing"},
    {"id": "MOD-ETICKET", "name": "Transit e-Ticketing (QR + NCMC)", "category": "ticketing"},
    {"id": "MOD-QR", "name": "Dynamic QR Collect", "category": "payments"},
    {"id": "MOD-RECON", "name": "Settlement & Fare Reconciliation", "category": "reconciliation"},
    {"id": "MOD-OFFLINE", "name": "Offline-First Sync Kit", "category": "payments"},
    {"id": "MOD-LOYALTY", "name": "Loyalty & Rewards", "category": "loyalty"},
    {"id": "MOD-WA-RECEIPT", "name": "WhatsApp Receipts & Engagement", "category": "engagement"},
    {"id": "MOD-ANALYTICS", "name": "Counter Analytics", "category": "analytics"},
]

EXAMPLE_PROMPTS: list[str] = [
    "Find ferry and bus counters in Mumbai leaking digital ticket revenue this month and draft WhatsApp nudges for the depot supervisors.",
    "Which retail outlets crossed the GST e-invoice threshold but aren't issuing compliant bills?",
    "Show anchor counters with settlement mismatches above 2% and recommend the right Billeasy module.",
    "Which metro counters have low NCMC share and should move to Transit e-Ticketing?",
    "Bus depot counters with peak-hour device downtime — draft the nudges in Marathi.",
    "Retail outlets with pending settlement piling up — who do I call first?",
]

DOMAIN = {
    "name": "Offline Payments & Transit Ticketing — Counter Revenue Assurance",
    "persona": "Counter Copilot, assistant to Rohan, Area Partner Manager at Billeasy — Mumbai West",
    "scope": "Counter targeting, revenue-leakage and settlement detection, Billeasy module recommendation, and supervisor outreach drafting.",
    "out_of_scope": "General knowledge, coding, other industries, legal/tax rulings, and actually sending messages or moving money.",
}

# --- 50 FAQs (grouped) ---
FAQS: list[dict[str, str]] = [
    # Capability
    {"q": "What can you do?", "a": "I find counters that are leaking revenue or drifting out of compliance, score them, recommend the right Billeasy module, and draft compliance-checked WhatsApp nudges — with full reasoning shown.", "category": "Capabilities"},
    {"q": "List the things you can help me with.", "a": "Find counters; score network value; detect revenue leakage; predict module propensity; recommend modules; draft supervisor WhatsApp nudges; refine results conversationally; write multilingual drafts; explain every score; and show my step-by-step reasoning.", "category": "Capabilities"},
    {"q": "How do I ask for counters?", "a": "Ask in plain language, e.g. 'Find ferry counters in Mumbai with a cash-share spike'. I infer the filters and the target module.", "category": "Capabilities"},
    {"q": "Can you refine a result?", "a": "Yes. After a search, say 'now only the jetties', 'top 5 only', 'make it warmer', or 'exclude counters already on recon' and I'll rebuild on the previous result.", "category": "Capabilities"},
    {"q": "Can you draft the message for me?", "a": "Yes — every candidate counter gets a personalised WhatsApp draft grounded in its real signals, ready for you to edit and approve.", "category": "Capabilities"},
    {"q": "Do you send the WhatsApp messages?", "a": "No. I produce drafts for your review and approval. Actual sending needs the WhatsApp Business API integration, which is out of scope for this build.", "category": "Capabilities"},
    {"q": "Can you write in Hindi or Marathi?", "a": "Yes. Add 'in Hindi' (or Marathi, Tamil, etc.) and I'll write the whole nudge in that language. English is the default.", "category": "Capabilities"},
    {"q": "Can you handle multiple modules at once?", "a": "I focus a run on one target module for clarity. Ask a follow-up for a different module and I'll re-run the network.", "category": "Capabilities"},
    {"q": "Can you compare two modules for a counter?", "a": "I recommend the single best-fit module per counter by propensity. Side-by-side module comparison is on the roadmap.", "category": "Capabilities"},
    {"q": "How many counters do you return?", "a": "The top 10 by combined value + propensity, by default. Ask 'top 5' or 'top 20' to change it.", "category": "Capabilities"},

    # Modules
    {"q": "Which modules can you recommend?", "a": "Digital Billing & GST e-Invoice, Transit e-Ticketing (QR + NCMC), Dynamic QR Collect, Settlement & Fare Reconciliation, Offline-First Sync Kit, Loyalty & Rewards, WhatsApp Receipts & Engagement, and Counter Analytics.", "category": "Modules"},
    {"q": "Which module fixes revenue leakage?", "a": "Settlement & Fare Reconciliation (MOD-RECON). It matches captured collections against settled payouts daily and flags voids, reissues and mismatches at the counter level.", "category": "Modules"},
    {"q": "A counter keeps going offline at peak hour — what do I pitch?", "a": "The Offline-First Sync Kit. It queues transactions locally when the network drops and syncs on reconnect, so peak-hour fares still get recorded and settled.", "category": "Modules"},
    {"q": "What suits a retail outlet that crossed the GST threshold?", "a": "Digital Billing & GST e-Invoice — IRN generation, dynamic QR on B2C bills, HSN mapping and credit notes, so the outlet stops issuing kacha bills.", "category": "Modules"},
    {"q": "When should a transit counter move to e-Ticketing?", "a": "When paper or manual tickets still dominate, or NCMC share is low despite AFC-gate infrastructure. Transit e-Ticketing covers QR tickets and NCMC card acceptance.", "category": "Modules"},
    {"q": "What is Dynamic QR Collect for?", "a": "Cash-heavy counters with little or no digital acceptance. A per-transaction dynamic QR pulls collections onto the digital rail with zero MDR on UPI.", "category": "Modules"},
    {"q": "Who should get Loyalty & Rewards?", "a": "High-velocity retail outlets with repeat footfall, healthy digital share and no loyalty module live — typically flagship-tier neighbourhood stores.", "category": "Modules"},
    {"q": "How do you check module eligibility?", "a": "Each module has rules — minimum monthly TPV, a daily-transaction band, counter type, merchant KYC status and minimum tenure. I filter candidates against them before recommending.", "category": "Modules"},
    {"q": "What is the take rate on a module?", "a": "It's the per-transaction commission Billeasy earns, from 0.3% on WhatsApp Receipts to 1.2% on Transit e-Ticketing. Each module card shows its own rate.", "category": "Modules"},
    {"q": "Which modules are transit-only?", "a": "Transit e-Ticketing and Settlement & Fare Reconciliation are transit-first. Billing, Loyalty and WhatsApp Receipts are retail-first. QR Collect, Offline Sync and Analytics suit both.", "category": "Modules"},

    # Scoring
    {"q": "How is the value score calculated?", "a": "A transparent weighted model over monthly TPV, digital share of TPV, counter tenure and transaction velocity — z-scored against the counters in the candidate pool.", "category": "Scoring"},
    {"q": "What is the propensity score?", "a": "A per-module likelihood (0–100%) that a counter adopts the recommended module, built from behavioural signals such as cash-share spike, receipt gap or device downtime, with the top drivers shown.", "category": "Scoring"},
    {"q": "What is the composite score?", "a": "A blend of value and propensity. For growth modules it's 40% value / 60% propensity; for remediation modules like Reconciliation and Offline Sync, propensity dominates (80%) because urgency beats counter size.", "category": "Scoring"},
    {"q": "What is the leakage risk flag?", "a": "It marks counters whose field notes and transaction pattern point at revenue slipping off the digital rail — cash-share spikes, void-reissue clusters, settlement mismatches or payout complaints.", "category": "Scoring"},
    {"q": "Why was a counter ranked highly?", "a": "Open its card — I show the top contributing signals (e.g. cash share jumped versus baseline, 240 minutes of peak-hour downtime, receipt-issuance gap) with their weights.", "category": "Scoring"},
    {"q": "Is the scoring a black box?", "a": "No. Weights live in a config file and every recommendation lists its top signals — built for fintech auditability.", "category": "Scoring"},
    {"q": "Do you use a trained ML model?", "a": "This build uses transparent weighted/heuristic models for explainability. A trained model can be swapped in behind the same interface.", "category": "Scoring"},
    {"q": "What is the estimated opportunity on a candidate?", "a": "An indicative annual take-rate value: the counter's monthly TPV at the recommended module's take rate, annualised. It's for prioritisation, not a commercial quote.", "category": "Scoring"},

    # Data
    {"q": "What data do you use?", "a": "Counter profiles, transactions across UPI/card/cash/NCMC/wallet, settlement and payout records, live module holdings, and field-visit notes.", "category": "Data"},
    {"q": "Where does the data live?", "a": "Primary source is a Databricks Delta warehouse with an automatic SQLite fallback. Every result shows which source served it.", "category": "Data"},
    {"q": "Is this real counter data?", "a": "No — it's synthetic demo data (≈500 counters plus a few hand-crafted hero counters). No real merchant or passenger PII.", "category": "Data"},
    {"q": "How fresh is the data?", "a": "In this build it's seeded at startup. A production deployment would read live settlement and counter-health tables.", "category": "Data"},
    {"q": "Can I see a counter's full profile?", "a": "Yes — click any candidate to open Counter 360: profile, live modules, recent transactions, field notes, score breakdown, and the draft nudge.", "category": "Data"},
    {"q": "What is TPV?", "a": "Total Payment Volume — the rupee value a counter processes in a month across all channels. It drives tier bands, module eligibility and the GST e-invoice threshold check.", "category": "Data"},
    {"q": "What do the counter tiers mean?", "a": "Network-size bands by monthly TPV: nano (₹50k–₹2L), standard (₹2L–₹8L), flagship (₹8L–₹25L), anchor (₹25L–₹1.2Cr).", "category": "Data"},

    # Compliance / trust
    {"q": "Will the messages contain wrong numbers?", "a": "No. A numeric-grounding validator strips any figure not present in the counter's real data — no fabricated settlement amounts, TPV or take rates.", "category": "Compliance"},
    {"q": "What does the 'compliance ok' badge mean?", "a": "It confirms every number in the draft is grounded in source data. If something was stripped, you'll see a 'redacted' note.", "category": "Compliance"},
    {"q": "Can I edit a draft before approving?", "a": "Yes — edit inline in the WhatsApp preview, then Approve & queue.", "category": "Compliance"},
    {"q": "Is there an audit trail?", "a": "Yes — every agent step is saved and replayable per session, which is what a settlement or partner dispute review needs.", "category": "Compliance"},
    {"q": "Do you make settlement or payout decisions?", "a": "No. I surface leakage and compliance signals and draft outreach. Actual settlement, holds and payouts stay with Billeasy's payments systems and ops team.", "category": "Compliance"},
    {"q": "What is the GST e-invoice threshold you check?", "a": "I flag counters whose monthly TPV crosses the ₹5,00,000 band used here as the e-invoice mandate proxy, then check whether digital bills are actually being issued.", "category": "Compliance"},
    {"q": "Can I message any counter supervisor?", "a": "Only partners with a valid consent record. Under the DPDP Act, outreach to a merchant contact needs a lawful basis — I draft, you and the consent register decide who receives it.", "category": "Compliance"},

    # Revenue assurance
    {"q": "What counts as revenue leakage?", "a": "Value collected at the counter that never reaches the digital rail or the authority's revenue account — cash bypass, voided-and-reissued tickets, unbilled sales, and fares lost to device downtime.", "category": "Revenue assurance"},
    {"q": "How do you spot a cash-share spike?", "a": "I compare the counter's recent cash share of TPV against its own baseline. A sharp jump with flat or falling digital share is the classic fare-leakage fingerprint.", "category": "Revenue assurance"},
    {"q": "What is void-and-reissue fraud?", "a": "A ticket is issued, voided, the cash pocketed, then a fresh ticket issued for the next passenger. It shows up as an abnormal void-reissue rate against the counter's own history.", "category": "Revenue assurance"},
    {"q": "What is a settlement mismatch?", "a": "Captured value and settled value disagree beyond tolerance — from refunds and chargebacks, failed captures, offline transactions that never synced, or fees applied at a different rate.", "category": "Revenue assurance"},
    {"q": "What should I do with an escalated counter?", "a": "Call the supervisor within 48 hours before you pitch anything. Confirm the device and settlement position first — a partner with a stuck payout won't hear a module pitch.", "category": "Revenue assurance"},
    {"q": "How do you read field notes?", "a": "A rule-based sentiment pass over field-visit notes and support tickets labels each counter positive, neutral or negative, and escalates ones mentioning device, payout or reconciliation trouble.", "category": "Revenue assurance"},

    # Workflow / UI
    {"q": "What is the 'Agent reasoning' panel?", "a": "It streams my live plan, each tool call, the critic's checks, and the synthesis — collapsed by default; click 'Show' to expand.", "category": "Using the app"},
    {"q": "What's in the right-hand panel?", "a": "The ranked candidate counters. Click one for Counter 360 and its WhatsApp draft.", "category": "Using the app"},
    {"q": "How do I start a fresh topic?", "a": "Click 'New conversation' in the left sidebar. Past sessions are listed there too.", "category": "Using the app"},
    {"q": "Can I continue an old conversation?", "a": "Yes — pick it from the sidebar; follow-ups use that session's context.", "category": "Using the app"},
    {"q": "How do I reset a session (help, reset, cancel)?", "a": "Just type one of them. \u201chelp\u201d lists what I can do, \u201creset\u201d clears the session's conversation memory so the next message starts fresh (past runs and drafts stay saved), and \u201ccancel\u201d stops a misbehaving run.", "category": "Using the app"},
    {"q": "Why did I get no counters?", "a": "The filters were too tight or nothing matched. Try a different city, a lower TPV threshold, or drop the counter-type filter.", "category": "Using the app"},
    {"q": "What do the score colours mean?", "a": "Green ≥75 (strong), blue 55–74 (good), amber below 55 (marginal) — for the composite score ring.", "category": "Using the app"},
    {"q": "Can I export the list?", "a": "Export to CSV/XLSX is on the roadmap; for now you can approve drafts and review them per session.", "category": "Using the app"},

    # Scope / meta
    {"q": "Who are you?", "a": "I'm Counter Copilot, an AI assistant for a Billeasy Area Partner Manager — focused on counter revenue assurance, settlement health and partner outreach. Every counter, accounted for.", "category": "About"},
    {"q": "Can you answer general questions?", "a": "I stay within Billeasy's counter network and Indian payments context. For anything else I'll point you back to what I do best: finding counters and drafting nudges.", "category": "About"},
    {"q": "What can't you do?", "a": "Send messages, release or hold settlements, give legal or tax rulings, or work outside offline payments and transit ticketing.", "category": "About"},
    {"q": "Which LLMs power you?", "a": "Reasoning runs on Gemini; high-volume drafting on Groq Llama 3.3; with a deterministic offline fallback. Embeddings use Gemini.", "category": "About"},
    {"q": "How does RAG work here?", "a": "Hybrid retrieval over field-visit notes — dense embeddings plus BM25, fused and diversity-re-ranked, with citations.", "category": "About"},
    {"q": "Is my conversation saved?", "a": "Yes, per session, so you can revisit it and so follow-ups have context. It's single-manager demo storage.", "category": "About"},
    {"q": "How fast are you?", "a": "A full run typically completes in a few seconds; the plan streams within about a second.", "category": "About"},
    {"q": "What happens if the warehouse is down?", "a": "I automatically fall back to a local copy, so the demo never breaks — the trace shows 'sqlite(failover)'.", "category": "About"},
    {"q": "Can you handle another area or another network?", "a": "The design is multi-tenant-ready; this build is configured for Rohan's Mumbai West territory with synthetic data.", "category": "About"},
]


def faq_knowledge_text() -> str:
    """Compact grounding text for the FAQ node."""
    lines = [
        f"DOMAIN: {DOMAIN['name']} — {DOMAIN['scope']}",
        f"PERSONA: {DOMAIN['persona']}",
        f"OUT OF SCOPE: {DOMAIN['out_of_scope']}",
        "",
        "MODULES: " + ", ".join(m["name"] for m in MODULES),
        "",
        "CAPABILITIES:",
    ]
    lines += [f"- {c['title']}: {c['desc']}" for c in CAPABILITIES]
    lines += ["", "FAQs:"]
    lines += [f"Q: {f['q']}\nA: {f['a']}" for f in FAQS]
    return "\n".join(lines)

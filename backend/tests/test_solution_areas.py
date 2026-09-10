"""Solution-area enforcement tests: PII guard, reconciliation triage,
invoice-layout validation, ERP mapping, telemetry synthesis and the new KB corpora.

Runs keyless against the deterministic mock LLM and the seeded counter network.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

_RAW = (
    "Reach Rohan at +919876543210 or rohan.billeasy@example.in. GSTIN 27ABCDE1234F1Z5, "
    "PAN ABCDE1234F, Aadhaar 1234 5678 9012."
)

_PHONE = "9876543210"


async def run() -> int:
    from app.agent import AgentState, run_agent
    from app.agent.nodes.intent import _heuristic
    from app.db.sqlite_engine import bootstrap
    from app.knowledge_base import get_knowledge_base
    from app.security import mask_pii
    from app.tools.analyze_telemetry import AnalyzeTelemetryIn, analyze_telemetry
    from app.tools.diagnose_reconciliation import DiagnoseReconciliationIn, diagnose_reconciliation
    from app.tools.generate_erp_mapping import GenerateErpMappingIn, generate_erp_mapping
    from app.tools.validate_invoice_layout import ValidateInvoiceLayoutIn, validate_invoice_layout

    bootstrap()
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        status = "ok" if cond else "FAIL"
        print(f"  [{status}] {name}{(' - ' + detail) if detail else ''}")
        if not cond:
            failures.append(name)

    # ---- 1. PII guard ---------------------------------------------------
    masked = mask_pii(_RAW)
    check("pii: phone masked", _PHONE not in masked, masked)
    check("pii: +91 phone masked", "+919876543210" not in masked)
    check("pii: email masked", "rohan.billeasy@example.in" not in masked)
    check("pii: gstin masked", "27ABCDE1234F1Z5" not in masked)
    check("pii: standalone pan masked", "ABCDE1234F" not in masked)
    check("pii: aadhaar masked", "1234 5678 9012" not in masked)
    for placeholder in ("[GSTIN]", "[PAN]", "[AADHAAR]", "[PHONE]", "[EMAIL]"):
        check(f"pii: placeholder {placeholder} present", placeholder in masked)
    check("pii: idempotent", mask_pii(masked) == masked, mask_pii(masked))
    check("pii: 91-prefixed mobile labelled [PHONE]", "[PHONE]" in mask_pii("call 919876543210 now"),
          mask_pii("call 919876543210 now"))
    check("pii: +91 mobile labelled [PHONE]", "[PHONE]" in mask_pii("reach +91 98765 43210"),
          mask_pii("reach +91 98765 43210"))
    check("pii: spaced aadhaar handled", "[AADHAAR]" in mask_pii("aadhaar 1234 5678 9012"),
          mask_pii("aadhaar 1234 5678 9012"))
    check("pii: empty safe", mask_pii("") == "" and mask_pii(None) == "")
    check("pii: non-pii preserved", mask_pii("Mumbai flagship counters") == "Mumbai flagship counters")

    # The agent entry gate masks a direct AgentState caller before any node runs.
    trail: list[str] = []
    state = AgentState(
        session_id="pii-test",
        manager_query=f"find ferry counters in Mumbai with a settlement mismatch, talk to {_PHONE}",
        manager_name="Rohan",
        history=[],
    )
    async for ev in run_agent(state):
        trail.append(ev.model_dump_json())
    leaked = _PHONE in " ".join(trail) or _PHONE in (state.final_summary or "")
    check("pii: run_agent masks direct state (no phone in stream/summary)", not leaked, state.final_summary or "")

    # ---- 2. Reconciliation triage --------------------------------------
    d = await diagnose_reconciliation(DiagnoseReconciliationIn(counter_id="CTR-0001"))
    check("recon: leaking counter classified as merchant_void_reissue",
          d.verdict.verdict == "merchant_void_reissue", d.verdict.verdict)
    check("recon: mismatch above 2% band", d.verdict.mismatch_rate > 0.02, str(d.verdict.mismatch_rate))
    check("recon: void-reissue count corroborates", d.verdict.void_reissue_count >= 3,
          str(d.verdict.void_reissue_count))
    check("recon: next steps present", len(d.verdict.next_steps) >= 2, str(d.verdict.next_steps))

    # ---- 3. Invoice-layout validation ----------------------------------
    good = await validate_invoice_layout(ValidateInvoiceLayoutIn(invoice_text=(
        "Tax Invoice GSTIN 27ABCDE1234F1Z5 HSN 490110 Total Rs 500 "
        "IRN abcdefghijklmnopqrstuvwxyz1234567890"
    )))
    check("invoice: well-formed tax invoice passes", good.ok,
          str([i.code for i in good.issues]))
    bad = await validate_invoice_layout(ValidateInvoiceLayoutIn(
        invoice_text="Tax Invoice total Rs 500",
    ))
    check("invoice: bare self-claim fails with errors", not bad.ok,
          str([i.code for i in bad.issues]))
    codes = {i.code for i in bad.issues}
    check("invoice: missing-gstin flagged", "missing_gstin" in codes, str(codes))
    check("invoice: self-claim-unsupported flagged", "self_claim_unsupported" in codes, str(codes))
    warned = await validate_invoice_layout(ValidateInvoiceLayoutIn(invoice_text=(
        "Tax Invoice GSTIN 27ABCDE1234F1Z5 HSN 490110 Total Rs 500"
    )))
    wcodes = {i.code for i in warned.issues}
    check("invoice: missing IRN is a warning, not a failure", warned.ok and "irn_absent" in wcodes,
          str(wcodes))

    # ---- 4. ERP mapping -------------------------------------------------
    e = await generate_erp_mapping(GenerateErpMappingIn(
        categories=["sales", "settlement_payout", "mdr_fee", "stocks"], target="tally",
    ))
    check("erp: known categories mapped", {r.category for r in e.mapping} == {"sales", "settlement_payout", "mdr_fee"},
          str([r.category for r in e.mapping]))
    check("erp: unknown category reported unmapped", e.unmapped == ["stocks"], str(e.unmapped))
    check("erp: no write-path claims",
          any("no live erp" in n.lower() for n in e.notes), str(e.notes))
    bad2 = await generate_erp_mapping(GenerateErpMappingIn(categories=["sales"], target="sap"))
    check("erp: unknown target -> all unmapped + guidance",
          bad2.unmapped == ["sales"] and any("unknown target" in n.lower() for n in bad2.notes),
          str(bad2.notes))

    # ---- 5. Telemetry synthesis ----------------------------------------
    t = await analyze_telemetry(AnalyzeTelemetryIn())
    check("telemetry: clusters returned", len(t.clusters) >= 1, str(t.clusters[:2]))
    check("telemetry: sorted by lag desc",
          all(t.clusters[i].lag_score >= t.clusters[i + 1].lag_score for i in range(len(t.clusters) - 1)),
          str([c.lag_score for c in t.clusters[:4]]))
    check("telemetry: scope label applied", t.scope == "all", t.scope)
    check("telemetry: offline minutes present on clusters", any(c.total_offline_minutes > 0 for c in t.clusters))
    t2 = await analyze_telemetry(AnalyzeTelemetryIn(cities=["Mumbai"]))
    check("telemetry: city filter narrows", t2.scope == "cities=mumbai" and all(c.city == "Mumbai" for c in t2.clusters),
          t2.scope)

    # ---- 6. New KB corpora + intent routing ----------------------------
    kb = get_knowledge_base()
    labels = [s["source"] for s in kb.sources()]
    check("kb: eight corpora loaded", len(labels) == 8, str(labels))

    r = await kb.ask("How do I integrate Counter Copilot with our ERP and what endpoints exist?")
    check("kb: api_guide grounds the integration answer",
          any("API" in s for s in r["sources"]), str(r["sources"]))
    check("kb: api answer non-empty", len(r["answer"]) > 10, r["answer"][:70])

    r = await kb.ask("What does the security posture do with customer PII and where do prompts get logged?")
    check("kb: security corpus grounds the policy answer",
          any("Security" in s for s in r["sources"]), str(r["sources"]))

    r = await kb.ask("A customer says they paid but the payout is missing - what class of failure is this?")
    check("kb: gateway corpus grounded", len(r["answer"]) > 10, str(r["sources"])[:120])

    r = await kb.ask("Which ERP targets does the category mapper support?")
    check("kb: erp corpus grounded",
          any("ERP" in s for s in r["sources"]), str(r["sources"]))

    routes = {
        "which ERP can we map to for accounting": "knowledge",
        "how do I use the API endpoints for integration": "knowledge",
        "what is our security posture for customer PII": "knowledge",
        "when does the GST e-invoicing band apply": "knowledge",
        "find counters with settlement mismatches and draft warnings": "task",
        "show me the counters struggling with gateway errors": "task",
    }
    for q, expected in routes.items():
        got = _heuristic(q, False)
        check(f"route '{q[:42]}' -> {expected}", got == expected, f"got {got}")

    if failures:
        print(f"\nSolution-areas test FAILED: {failures}")
        return 1
    print("\nSolution-areas test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))

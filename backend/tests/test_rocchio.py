"""Rocchio-style feedback retrieval — the next question re-weights itself on the terms
our *own last grounded answer* emphasised.

We have no scored index and no per-document relevance labels, so the textbook Rocchio
formula does not apply directly. But BM25 scales each token's contribution by its query
frequency, so repeating a feedback term in the next query multiplies its score — a keyless
analogue of relevance feedback. This test pins the mechanism and the term-extraction rules,
not a fragile golden ranking.
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

GST_PRIOR_ANSWER = (
    "GST e-invoicing: businesses above the turnover threshold must generate an e-invoice "
    "(einvoice) and obtain an IRN from the GST system before the invoice is issued at the "
    "counter; GST rates apply per HSN code, e.g. transport services. Use the HSN / SAC "
    "code tables before billing."
)

# A follow-up with nothing to do with GST on the face of it (settlement timing); the
# control order must NOT already be GST-led, so the re-weighting is visibly the cause.
SETTLEMENT_QUERY = "when does money from a transaction land in the account"


async def run() -> int:
    from app.knowledge_base import get_knowledge_base

    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(f"  [{'ok' if cond else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
        if not cond:
            failures.append(name)

    kb = get_knowledge_base()

    # --- 1. Term extraction rules ----------------------------------------------
    terms = kb.feedback_terms(GST_PRIOR_ANSWER, SETTLEMENT_QUERY)
    check("feedback terms are capped", len(terms) <= 4, f"{terms}")
    check(
        "feedback terms carry topic signal (gst/hsn surface favourites)",
        any(t in {"gst", "hsn", "irn", "code"} for t in terms),
        f"{terms}",
    )
    excl = kb.feedback_terms("npci upi upi upi aggregator", "upi")
    check("terms already in the query are not re-used as feedback", "upi" not in excl, f"{excl}")
    check("query-unseen related terms still surface", "npci" in excl, f"{excl}")

    # --- 2. Re-weighting changes the ranking deterministically ------------------
    def gst_domain(heading: str) -> bool:
        return any(x in heading for x in ("GST", "HSN", "IRN"))

    control = kb.search(SETTLEMENT_QUERY, k=5)
    control_heads = [h["heading_path"] for h in control]
    check(
        "control ranking is not already GST-led",
        not any(gst_domain(h) for h in control_heads[:3]),
        "/".join(h[:30] for h in control_heads),
    )

    expanded = kb.search(
        SETTLEMENT_QUERY,
        k=5,
        expand_terms=kb.feedback_terms(GST_PRIOR_ANSWER, SETTLEMENT_QUERY),
    )
    expanded_heads = [h["heading_path"] for h in expanded]
    check(
        "feedback moves the previously-relevant topic above unrelated matches",
        gst_domain(expanded_heads[0]) and sum(1 for h in expanded_heads[:3] if gst_domain(h)) >= 2,
        "/".join(h[:30] for h in expanded_heads),
    )
    check(
        "feedback lifts overall score of the re-weighted topic",
        expanded[0]["score"] > control[0]["score"],
        f"{expanded[0]['score']:.3f} vs {control[0]['score']:.3f}",
    )

    # --- 3. The expansion is bounded (does not crush a related follow-up) -------
    mdr_terms = kb.feedback_terms(
        "MDR is the interchange the card network charges; zero MDR applies to smaller UPI "
        "transactions and RuPay cards at every counter's tap reader.",
        "merchant discount rate",
    )
    mdr_control = kb.search("merchant discount rate", k=3)
    mdr_expanded = kb.search("merchant discount rate", k=3, expand_terms=mdr_terms)
    check(
        "re-weighting aligns with (not against) a genuinely related follow-up",
        mdr_expanded[0]["heading_path"] == mdr_control[0]["heading_path"],
        f"{mdr_control[0]['heading_path'][:40]} / {mdr_expanded[0]['heading_path'][:40]}",
    )

    if failures:
        print(f"\nRocchio test FAILED: {failures}")
        return 1
    print("\nRocchio tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))

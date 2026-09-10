"""Reconciliation triage — classifies a single counter's collection-vs-settlement gap.

Gateway outages and bank shortfalls land differently: a customer-facing timeout leaves
money captured but never settled (a *settlement shortfall*), while ticket counter staff
recycling cash repeatedly void-and-reissue tickets (a *merchant void/reissue* pattern).
Both show up in the transaction ledger aggregates as a mismatch between what the counter
collected and what Billeasy paid out.

This tool reuses the same ledger aggregation as `get_counter_transactions` and then
labels the gap with a deterministic verdict, a confidence sub-label, and next steps that
point the partner at the right *kind* of failure. It cannot see gateway error codes (the
ledger does not carry them), so it never claims the specific provider — it says which
check to run, which the gateway_error_codes corpus document then answers for the partner.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.application.tool_registry import tool
from app.tools.get_counter_transactions import GetCounterTransactionsIn, get_counter_transactions

# A gap above this share of collections is "a mismatch", mirroring the leakage scoring
# heuristic (test_smoke asserts a leaking counter exceeds 0.02).
_MISMATCH_THRESHOLD = 0.02
# Fewer than this many void-reissues in the window: not a merchant recycling pattern.
_VOID_LOW = 3


class DiagnoseReconciliationIn(BaseModel):
    counter_id: str
    months: int = Field(default=6, ge=1, le=24)


class ReconVerdict(BaseModel):
    verdict: str
    confidence: str
    mismatch_rate: float
    collected: float
    settled: float
    void_reissue_count: int
    refund_total: float
    cash_share: float
    next_steps: list[str]


class DiagnoseReconciliationOut(BaseModel):
    counter_id: str
    months: int
    verdict: ReconVerdict


@tool(
    name="diagnose_reconciliation",
    description=(
        "Triage ONE counter's collection-vs-settlement gap. Returns a deterministic verdict "
        "(merchant_void_reissue | settlement_shortfall | within_band), the mismatch rate, the "
        "void-and-reissue count, refund total and cash share from the transaction ledger, plus "
        "next steps naming which failure mode to check (gateway timeouts vs bank shortfall vs "
        "void/reissue recycling). Use for 'why doesn't X match', 'where did the money go' and "
        "settlement-mismatch follow-ups."
    ),
    input_model=DiagnoseReconciliationIn,
    output_model=DiagnoseReconciliationOut,
)
async def diagnose_reconciliation(
    args: DiagnoseReconciliationIn,
) -> DiagnoseReconciliationOut:
    agg = (await get_counter_transactions(
        GetCounterTransactionsIn(counter_id=args.counter_id, months=args.months)
    )).aggregates

    collected = agg.total_collected
    settled = agg.total_settled
    if collected > 0:
        mismatch_rate = abs(collected - settled) / collected
    else:
        mismatch_rate = 0.0

    if mismatch_rate > _MISMATCH_THRESHOLD and agg.void_reissue_count >= _VOID_LOW:
        verdict = "merchant_void_reissue"
        confidence = "high" if agg.void_reissue_count >= 3 * _VOID_LOW else "medium"
        next_steps = [
            "Pull the counter's ticket history and look for the same-amount sale → void → reissue loop.",
            "Cross-check handheld sync logs for the period before checking the gateway: this pattern is staff-side cash recycling, not a provider outage.",
            "If the loop is confirmed, the fix is a refund-policy nudge to the supervisor (see field_ops_faqs), not a module swap.",
        ]
    elif mismatch_rate > _MISMATCH_THRESHOLD:
        verdict = "settlement_shortfall"
        confidence = "medium"
        next_steps = [
            "Check whether the shortfall matches the counter's pending settlement batch (money captured, payout not yet released).",
            "If a whole day+ is missing, treat it as a settlement/railing failure: consult gateway_error_codes for capture-vs-payout error classes.",
            "Otherwise start from gateway timeout / bank decline routing before suspecting the counter operator.",
        ]
    else:
        verdict = "within_band"
        confidence = "high"
        next_steps = [
            "Collections and payouts track within the 2% band — keep the standard monitoring window, no escalation.",
            f"Watch the cash share ({agg.cash_share:.1%} of collections); a sharp rise is the earliest leakage signal.",
        ]

    return DiagnoseReconciliationOut(
        counter_id=args.counter_id,
        months=args.months,
        verdict=ReconVerdict(
            verdict=verdict,
            confidence=confidence,
            mismatch_rate=round(mismatch_rate, 4),
            collected=round(collected, 2),
            settled=round(settled, 2),
            void_reissue_count=agg.void_reissue_count,
            refund_total=round(agg.refund_total, 2),
            cash_share=round(agg.cash_share, 4),
            next_steps=next_steps,
        ),
    )

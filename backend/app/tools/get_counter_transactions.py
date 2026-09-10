from __future__ import annotations

from collections import defaultdict
from typing import Any

from pydantic import BaseModel, Field

from app.application.tool_registry import tool
from app.infrastructure.datasource import get_datasource

# Money the counter took in from a passenger or shopper.
_COLLECTION_CATEGORIES = {"ticket_sale", "retail_bill", "topup"}
# Money Billeasy paid out to the merchant / transit authority.
_PAYOUT_CATEGORIES = {"settlement_payout"}
# Everything that is not physical cash rides the digital rail.
_CASH_CHANNEL = "cash"


class GetCounterTransactionsIn(BaseModel):
    counter_id: str
    months: int = Field(default=6, ge=1, le=24)


class TxnAggregates(BaseModel):
    total_collected: float = 0.0
    total_settled: float = 0.0
    cash_share: float = 0.0
    digital_share: float = 0.0
    channel_split: dict[str, float] = {}
    largest_ticket: float = 0.0
    void_reissue_count: int = 0
    refund_total: float = 0.0
    txn_count: int = 0


class GetCounterTransactionsOut(BaseModel):
    source: str
    counter_id: str
    months: int
    aggregates: TxnAggregates
    transactions: list[dict[str, Any]]
    latency_ms: int


@tool(
    name="get_counter_transactions",
    description=(
        "Return recent transactions for one counter with revenue-assurance aggregates: total ₹ "
        "collected, total ₹ settled out, cash vs digital share of collections, per-channel split "
        "(upi/card/cash/ncmc/wallet/netbanking), largest single ticket, void-and-reissue count "
        "and refund total. Used as input to leakage scoring."
    ),
    input_model=GetCounterTransactionsIn,
    output_model=GetCounterTransactionsOut,
)
async def get_counter_transactions(args: GetCounterTransactionsIn) -> GetCounterTransactionsOut:
    ds = get_datasource()
    res = await ds.get_transactions(args.counter_id, args.months)
    txns: list[dict[str, Any]] = res.data or []

    channel_totals: dict[str, float] = defaultdict(float)
    total_collected = 0.0
    total_settled = 0.0
    cash_collected = 0.0
    largest_ticket = 0.0
    void_reissue_count = 0
    refund_total = 0.0
    for t in txns:
        amt = float(t["amount"])
        cat = t.get("category") or "other"
        channel = t.get("channel") or "other"
        if cat in _COLLECTION_CATEGORIES:
            total_collected += amt
            channel_totals[channel] += amt
            if channel == _CASH_CHANNEL:
                cash_collected += amt
            if amt > largest_ticket:
                largest_ticket = amt
        elif cat in _PAYOUT_CATEGORIES:
            total_settled += abs(amt)
        elif cat == "void_reissue":
            void_reissue_count += 1
        elif cat == "refund":
            refund_total += abs(amt)

    cash_share = (cash_collected / total_collected) if total_collected > 0 else 0.0

    agg = TxnAggregates(
        total_collected=round(total_collected, 2),
        total_settled=round(total_settled, 2),
        cash_share=round(cash_share, 4),
        digital_share=round(1.0 - cash_share, 4) if total_collected > 0 else 0.0,
        channel_split={k: round(v, 2) for k, v in channel_totals.items()},
        largest_ticket=round(largest_ticket, 2),
        void_reissue_count=void_reissue_count,
        refund_total=round(refund_total, 2),
        txn_count=len(txns),
    )
    return GetCounterTransactionsOut(
        source=res.source,
        counter_id=args.counter_id,
        months=args.months,
        aggregates=agg,
        transactions=txns,
        latency_ms=res.latency_ms,
    )

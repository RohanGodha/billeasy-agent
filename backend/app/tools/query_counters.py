from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.application.tool_registry import tool
from app.domain import CounterFilters
from app.infrastructure.datasource import get_datasource


class QueryCountersIn(BaseModel):
    cities: list[str] | None = Field(default=None, description="City filter, e.g. ['Mumbai'].")
    tiers: list[str] | None = Field(default=None, description="['nano','standard','flagship','anchor'].")
    counter_types: list[str] | None = Field(
        default=None,
        description="['retail','ferry','bus','metro'] — ferry/bus/metro are transit ticketing counters.",
    )
    min_tpv: float | None = Field(default=None, description="Minimum monthly TPV in ₹.")
    max_tpv: float | None = Field(default=None, description="Maximum monthly TPV in ₹.")
    min_pending_settlement: float | None = Field(
        default=None,
        description="Minimum ₹ awaiting payout — use to surface settlement backlogs.",
    )
    min_daily_txns: int | None = Field(default=None, description="Minimum average daily transactions.")
    max_daily_txns: int | None = Field(default=None, description="Maximum average daily transactions.")
    settlement_cycles: list[str] | None = Field(default=None, description="['T+1','T+2','weekly'].")
    exclude_modules: list[str] | None = Field(
        default=None,
        description="Skip counters that already run any of these Billeasy module IDs.",
    )
    limit: int = Field(default=200, ge=1, le=1000)

    @field_validator("cities", "tiers", "counter_types", "settlement_cycles", "exclude_modules", mode="before")
    @classmethod
    def _wrap_scalar(cls, v: Any) -> Any:
        if isinstance(v, str):
            return [v]
        return v


class QueryCountersOut(BaseModel):
    source: str
    rows: int
    counters: list[dict[str, Any]]
    latency_ms: int
    # Which filters were dropped to avoid returning nothing, and a sentence the UI can
    # show. Relaxation used to be silent: a manager asking about Kochi ferry counters
    # could be answered about the whole network with no indication the question had
    # changed. In a tool whose value is trust, that is not an acceptable default.
    relaxed_filters: list[str] = Field(default_factory=list)
    relaxation_note: str | None = None


# Filters dropped first when a strict plan returns nobody, in order of selectivity.
_RELAXABLE = ("min_tpv", "max_tpv", "min_daily_txns", "max_daily_txns", "settlement_cycles")

# Human labels for the relaxation note, so a manager sees "the city filter" not "cities".
_FILTER_LABEL = {
    "cities": "the city filter",
    "tiers": "the tier filter",
    "counter_types": "the counter-type filter",
    "settlement_cycles": "the settlement-cycle filter",
    "min_tpv": "the minimum-TPV filter",
    "max_tpv": "the maximum-TPV filter",
    "min_pending_settlement": "the minimum-pending-settlement filter",
    "min_daily_txns": "the minimum-daily-transactions filter",
    "max_daily_txns": "the maximum-daily-transactions filter",
}


@tool(
    name="query_counters",
    description=(
        "Search the Billeasy counter network with structured filters (city, tier, counter type, "
        "monthly TPV, pending settlement, daily transaction volume, settlement cycle). Returns "
        "enriched counter rows including pending_settlement, avg_daily_txns and digital_share."
    ),
    input_model=QueryCountersIn,
    output_model=QueryCountersOut,
)
async def query_counters(args: QueryCountersIn) -> QueryCountersOut:
    ds = get_datasource()
    raw = args.model_dump()
    for key in ("min_tpv", "max_tpv", "min_pending_settlement", "min_daily_txns", "max_daily_txns"):
        if key in raw and raw[key] == 0:
            raw[key] = None

    res = await ds.find_counters(CounterFilters(**raw))
    dropped: list[str] = []

    if res.rows == 0:
        # Stage 1 — drop the numeric thresholds, keep the categorical intent
        # (city, counter type, tier) that the manager actually asked about.
        dropped = [k for k in _RELAXABLE if raw.get(k) is not None]
        relaxed = {**raw, **dict.fromkeys(_RELAXABLE)}
        res = await ds.find_counters(CounterFilters(**relaxed))

    if res.rows == 0:
        # Stage 2 — last resort: only the module exclusion survives. This changes the
        # question, so it must be reported loudly rather than quietly widened.
        dropped = [
            k for k in ("cities", "tiers", "counter_types", "settlement_cycles", *_RELAXABLE)
            if raw.get(k) is not None
        ]
        minimal = {"exclude_modules": raw.get("exclude_modules"), "limit": raw.get("limit") or 80}
        res = await ds.find_counters(CounterFilters(**minimal))

    note = None
    if dropped and res.rows:
        pretty = ", ".join(_FILTER_LABEL.get(k, k) for k in dropped)
        note = (
            f"No counters matched every filter, so this result ignores {pretty}. "
            "Treat it as a wider sweep than you asked for."
        )

    return QueryCountersOut(
        source=res.source,
        rows=res.rows,
        counters=res.data or [],
        latency_ms=res.latency_ms,
        relaxed_filters=dropped,
        relaxation_note=note,
    )

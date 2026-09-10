from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.application.tool_registry import tool
from app.domain import ScoreBreakdown
from app.infrastructure.datasource import get_datasource
from app.scoring.value import compute_value


class ComputeValueIn(BaseModel):
    counter_ids: list[str] = Field(default_factory=list)
    months: int = Field(default=6, ge=1, le=24)

    @field_validator("counter_ids", mode="before")
    @classmethod
    def _wrap_scalar(cls, v: object) -> object:
        return [v] if isinstance(v, str) else v


class CounterValue(BaseModel):
    counter_id: str
    value_score: float
    breakdown: list[ScoreBreakdown]


class ComputeValueOut(BaseModel):
    source: str
    counters: list[CounterValue]
    latency_ms: int


@tool(
    name="compute_counter_value",
    description=(
        "Compute an explainable network-value score (0-1) per counter ID, based on monthly TPV, "
        "digital share of TPV, tenure on the Billeasy rail and transaction velocity, z-scored "
        "against the candidate population. Returns top contributing features."
    ),
    input_model=ComputeValueIn,
    output_model=ComputeValueOut,
)
async def compute_counter_value(args: ComputeValueIn) -> ComputeValueOut:
    import time
    started = time.perf_counter()
    ds = get_datasource()

    # Bulk-fetch counters + transactions in 2 queries (instead of 2N).
    counters_map = await ds.get_counters_bulk(args.counter_ids)
    txns_map = await ds.get_transactions_bulk(args.counter_ids, args.months)

    population: list[dict[str, Any]] = []
    velocity_map: dict[str, int] = {}
    for cid, counter in counters_map.items():
        velocity_map[cid] = len(txns_map.get(cid, []))
        counter["_txn_velocity"] = velocity_map[cid]
        population.append(counter)

    out: list[CounterValue] = []
    for cid, counter in counters_map.items():
        score, breakdown = compute_value(counter, population, txn_count_6m=velocity_map.get(cid, 0))
        out.append(CounterValue(counter_id=cid, value_score=score, breakdown=breakdown))

    out.sort(key=lambda c: c.value_score, reverse=True)
    return ComputeValueOut(
        source=getattr(ds, "name", "sqlite"),
        counters=out,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )

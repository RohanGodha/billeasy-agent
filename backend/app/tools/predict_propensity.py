from __future__ import annotations

import asyncio
import time

from pydantic import BaseModel, Field, field_validator

from app.application.tool_registry import tool
from app.domain import ScoreBreakdown
from app.infrastructure.datasource import get_datasource
from app.scoring.propensity import predict_propensity

_DEFAULT_MODULE = "MOD-RECON"


class PredictPropensityIn(BaseModel):
    counter_ids: list[str] = Field(default_factory=list)
    module_id: str = _DEFAULT_MODULE

    @field_validator("module_id", mode="before")
    @classmethod
    def _default_module(cls, v: object) -> object:
        return v if isinstance(v, str) and v.strip() else _DEFAULT_MODULE

    @field_validator("counter_ids", mode="before")
    @classmethod
    def _wrap_scalar(cls, v: object) -> object:
        return [v] if isinstance(v, str) else v


class CounterPropensity(BaseModel):
    counter_id: str
    module_id: str
    propensity_score: float
    breakdown: list[ScoreBreakdown]


class PredictPropensityOut(BaseModel):
    source: str
    module_id: str
    counters: list[CounterPropensity]
    latency_ms: int


@tool(
    name="predict_module_propensity",
    description=(
        "Predict the propensity (0-1) of each counter to adopt a specific Billeasy module. "
        "Weighted logistic over module-specific settlement, leakage and device signals "
        "(cash-share spike, void/reissue rate, settlement mismatch, receipt-issuance gap, "
        "peak-hour downtime); returns top driving features for explainability."
    ),
    input_model=PredictPropensityIn,
    output_model=PredictPropensityOut,
)
async def predict_module_propensity(args: PredictPropensityIn) -> PredictPropensityOut:
    started = time.perf_counter()
    ds = get_datasource()

    # Bulk-fetch everything in 4 queries (instead of 4N).
    counters_map, txns_map, holdings_map, field_notes_map = await asyncio.gather(
        ds.get_counters_bulk(args.counter_ids),
        ds.get_transactions_bulk(args.counter_ids, 6),
        ds.get_holdings_bulk(args.counter_ids),
        ds.get_field_notes_bulk(args.counter_ids),
    )

    out: list[CounterPropensity] = []
    for cid in args.counter_ids:
        counter = counters_map.get(cid)
        if not counter:
            continue
        score, breakdown = predict_propensity(
            counter=counter,
            txns=txns_map.get(cid, []),
            holdings=holdings_map.get(cid, []),
            field_notes=field_notes_map.get(cid, []),
            module_id=args.module_id,
        )
        out.append(
            CounterPropensity(
                counter_id=cid,
                module_id=args.module_id,
                propensity_score=score,
                breakdown=breakdown,
            )
        )

    out.sort(key=lambda c: c.propensity_score, reverse=True)
    return PredictPropensityOut(
        source=getattr(ds, "name", "sqlite"),
        module_id=args.module_id,
        counters=out,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )

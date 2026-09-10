from __future__ import annotations

import asyncio
import time
from datetime import date
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.application.tool_registry import tool
from app.infrastructure.datasource import get_datasource
from app.scoring.propensity import predict_propensity

# Every Billeasy SaaS module category an Area Partner Manager can actually pitch.
_RECOMMENDABLE_CATEGORIES = {
    "billing",
    "ticketing",
    "payments",
    "reconciliation",
    "loyalty",
    "engagement",
    "analytics",
}


class RecommendIn(BaseModel):
    counter_ids: list[str] = Field(default_factory=list)
    candidate_module_ids: list[str] | None = None
    top_k: int = Field(default=1, ge=1, le=8)

    @field_validator("counter_ids", "candidate_module_ids", mode="before")
    @classmethod
    def _wrap_scalar(cls, v: object) -> object:
        return [v] if isinstance(v, str) else v


class Recommendation(BaseModel):
    counter_id: str
    module_id: str
    module_name: str
    propensity_score: float
    eligible: bool
    reasons: list[str]


class RecommendOut(BaseModel):
    source: str
    recommendations: list[Recommendation]
    latency_ms: int


def _months_onboarded(onboarded_date: Any) -> float:
    """Months live on the Billeasy rail; 0 when the onboarding date is unparseable."""
    if not isinstance(onboarded_date, str):
        return 0.0
    try:
        started = date.fromisoformat(onboarded_date[:10])
    except ValueError:
        return 0.0
    today = date.today()
    return max(0.0, (today - started).days / 30.44)


def _threshold(module: dict[str, Any], elig: dict[str, Any], key: str) -> Any:
    """Eligibility JSON overrides the module's catalog column."""
    override = elig.get(key)
    return module.get(key) if override is None else override


def _eligibility_ok(counter: dict[str, Any], module: dict[str, Any]) -> tuple[bool, list[str]]:
    elig: dict[str, Any] = module.get("eligibility") or {}
    reasons: list[str] = []
    tpv = float(counter.get("monthly_tpv") or 0)
    daily_txns = float(counter.get("avg_daily_txns") or 0)

    if (min_tpv := _threshold(module, elig, "min_monthly_tpv")) is not None and tpv < float(min_tpv):
        reasons.append(f"monthly TPV ₹{tpv:,.0f} below min_monthly_tpv ₹{float(min_tpv):,.0f}")
    if (min_txns := _threshold(module, elig, "min_daily_txns")) is not None and daily_txns < float(min_txns):
        reasons.append(f"avg daily txns {daily_txns:.0f} below min_daily_txns {float(min_txns):.0f}")
    if (max_txns := _threshold(module, elig, "max_daily_txns")) is not None and daily_txns > float(max_txns):
        reasons.append(f"avg daily txns {daily_txns:.0f} above max_daily_txns {float(max_txns):.0f}")
    if isinstance(elig.get("counter_type"), list) and counter.get("counter_type") not in elig["counter_type"]:
        reasons.append(f"counter_type {counter.get('counter_type')} not in {elig['counter_type']}")
    if (min_tenure := elig.get("min_tenure_months")) is not None:
        tenure = _months_onboarded(counter.get("onboarded_date"))
        if tenure < float(min_tenure):
            reasons.append(f"onboarded {tenure:.0f} months ago, below min_tenure_months {float(min_tenure):.0f}")
    if elig.get("kyc") == "verified" and counter.get("kyc_status") != "verified":
        reasons.append("merchant KYC not verified")
    if isinstance(elig.get("settlement_cycle"), list):
        if counter.get("settlement_cycle") not in elig["settlement_cycle"]:
            reasons.append(f"settlement_cycle {counter.get('settlement_cycle')} not in {elig['settlement_cycle']}")
    return (len(reasons) == 0), reasons


@tool(
    name="recommend_modules",
    description=(
        "For each counter, recommend the best-fit Billeasy module among an optional candidate "
        "list (defaults to the full module catalog), skipping modules the counter already runs, "
        "ranking by adoption propensity and checking eligibility (monthly TPV floor, daily-txn "
        "band, counter type, tenure and merchant KYC)."
    ),
    input_model=RecommendIn,
    output_model=RecommendOut,
)
async def recommend_modules(args: RecommendIn) -> RecommendOut:
    started = time.perf_counter()
    ds = get_datasource()
    mod_res = await ds.get_modules()
    modules: list[dict[str, Any]] = mod_res.data or []
    if args.candidate_module_ids:
        modules = [m for m in modules if m["id"] in args.candidate_module_ids]
    # Exclude non-actionable categories
    modules = [m for m in modules if m["category"] in _RECOMMENDABLE_CATEGORIES]

    counters_map, txns_map, holdings_map, field_notes_map = await asyncio.gather(
        ds.get_counters_bulk(args.counter_ids),
        ds.get_transactions_bulk(args.counter_ids, 6),
        ds.get_holdings_bulk(args.counter_ids),
        ds.get_field_notes_bulk(args.counter_ids),
    )

    recs: list[Recommendation] = []
    for cid in args.counter_ids:
        counter = counters_map.get(cid)
        if not counter:
            continue
        hr = holdings_map.get(cid, [])
        tr = txns_map.get(cid, [])
        fn = field_notes_map.get(cid, [])
        candidates: list[Recommendation] = []
        for mod in modules:
            # Skip modules the counter already runs (live)
            if any(h["module_id"] == mod["id"] for h in hr):
                continue
            score, _ = predict_propensity(counter, tr, hr, fn, mod["id"])
            eligible, reasons = _eligibility_ok(counter, mod)
            candidates.append(
                Recommendation(
                    counter_id=cid,
                    module_id=mod["id"],
                    module_name=mod["name"],
                    propensity_score=score,
                    eligible=eligible,
                    reasons=reasons or ["meets all eligibility rules"],
                )
            )
        _ = fn  # field notes reserved for future reason-codes
        candidates.sort(key=lambda r: (r.eligible, r.propensity_score), reverse=True)
        recs.extend(candidates[: args.top_k])

    return RecommendOut(
        source=mod_res.source,
        recommendations=recs,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )

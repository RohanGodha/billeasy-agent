"""Telemetry synthesizer — city-level bottleneck clusters from the device estate.

ZOOM-OUT counterpart to the per-counter pipeline. Where `query_counters` shortlists the
network and the per-counter transactions tool audits one counter, this tool aggregates
the whole estate into bottleneck clusters per city, from fields the counters table
already carries: `device_offline_minutes` (peak-window downtime), `pending_settlement`
(money captured but not yet paid out — the auto-reconciliation lag proxy) and
`avg_daily_txns` (velocity).

It is snapshot-only and deliberately time-boxed: the demo warehouse is an immutable seed,
so it can never claim "since 09:00" trends. Each cluster gets a plain unnormalised lag
score (offline-minutes weight + pending-payout weight + velocity weight), and a city is
flagged as a bottleneck when its average offline minutes or average pending settlement
clears the same roughness thresholds the leakage scorer uses. Deterministic and keyless.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.application.tool_registry import tool
from app.domain import CounterFilters
from app.infrastructure.datasource import get_datasource

# Weighting for the composite lag score. Units are rough on purpose: offline minutes and
# pending ₹ are different scales, so the weights are tuned against the demo seed.
_W_OFFLINE = 1.0
# pending settlement normalised against a 1L unit to sit near the offline-minutes scale.
_W_PENDING = 1.0 / 100_000.0
_W_VELOCITY = 1.0 / 200.0

# Roughness thresholds (avg per counter in a city) to label a cluster a bottleneck.
_AVG_OFFLINE_MIN = 30.0
_AVG_PENDING = 250_000.0


class TelemetryCluster(BaseModel):
    city: str
    counter_count: int
    total_offline_minutes: float
    avg_offline_minutes: float
    total_pending_settlement: float
    avg_pending_settlement: float
    avg_daily_txns: float
    lag_score: float
    bottleneck: bool


class AnalyzeTelemetryIn(BaseModel):
    cities: list[str] | None = Field(
        default=None,
        description="Restrict the sweep to these cities. Omit for the whole estate.",
    )


class AnalyzeTelemetryOut(BaseModel):
    scope: str
    clusters: list[TelemetryCluster]
    source: str


@tool(
    name="analyze_telemetry",
    description=(
        "Aggregate the counter estate into per-city bottleneck clusters from device telemetry: "
        "peak-window offline minutes, pending settlement (money captured not yet paid out) and "
        "ticket velocity. Returns clusters sorted by lag score with a bottleneck flag and a "
        "snapshot-scope note. Use for 'which city is struggling', 'where is the network down', "
        "'where should ops camp next'."
    ),
    input_model=AnalyzeTelemetryIn,
    output_model=AnalyzeTelemetryOut,
)
async def analyze_telemetry(args: AnalyzeTelemetryIn) -> AnalyzeTelemetryOut:
    ds = get_datasource()
    res = await ds.find_counters(CounterFilters())
    counters = res.data or []
    if not counters:
        return AnalyzeTelemetryOut(scope="all", clusters=[], source="counter_health")

    want = {c.lower() for c in (args.cities or [])}
    if want:
        counters = [c for c in counters if (c.get("city") or "").lower() in want]

    agg: dict[str, dict] = {}
    for c in counters:
        city = c.get("city") or "unknown"
        bucket = agg.setdefault(city, {
            "count": 0, "offline": 0.0, "pending": 0.0,
            "txns": 0.0, "txns_set": 0,
        })
        bucket["count"] += 1
        bucket["offline"] += float(c.get("device_offline_minutes") or 0.0)
        bucket["pending"] += float(c.get("pending_settlement") or 0.0)
        txns = c.get("avg_daily_txns")
        if isinstance(txns, (int, float)):
            bucket["txns"] += float(txns)
            bucket["txns_set"] += 1

    clusters: list[TelemetryCluster] = []
    for city, b in agg.items():
        n = b["count"]
        avg_offline = b["offline"] / n
        avg_pending = b["pending"] / n
        avg_txns = (b["txns"] / b["txns_set"]) if b["txns_set"] else 0.0
        lag = (_W_OFFLINE * b["offline"] + _W_PENDING * b["pending"] + _W_VELOCITY * b["txns"])
        bottleneck = avg_offline >= _AVG_OFFLINE_MIN or avg_pending >= _AVG_PENDING
        clusters.append(TelemetryCluster(
            city=city,
            counter_count=n,
            total_offline_minutes=round(b["offline"], 1),
            avg_offline_minutes=round(avg_offline, 1),
            total_pending_settlement=round(b["pending"], 2),
            avg_pending_settlement=round(avg_pending, 2),
            avg_daily_txns=round(avg_txns, 1),
            lag_score=round(lag, 2),
            bottleneck=bottleneck,
        ))

    clusters.sort(key=lambda c: c.lag_score, reverse=True)

    scope_label = "cities=" + ",".join(sorted(want)) if want else "all"
    return AnalyzeTelemetryOut(
        scope=scope_label,
        clusters=clusters,
        source="counter_health",
    )

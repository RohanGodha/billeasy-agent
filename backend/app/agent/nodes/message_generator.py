"""MessageGenerator node — parallel WhatsApp nudges to counter supervisors,
grounded in the counter's real signals and compliance-checked."""
from __future__ import annotations

import asyncio
from typing import Any

from app.agent.state import AgentState, DraftRecord, TraceEvent
from app.application.tool_registry import invoke_tool
from app.domain import ScoreBreakdown
from app.infrastructure.datasource import get_datasource

_MAX_CONCURRENCY = 4


async def _draft_for(state: AgentState, candidate) -> DraftRecord | None:
    feats = [ScoreBreakdown(**f) for f in candidate.top_features[:3] if isinstance(f, dict)]
    envelope = await invoke_tool(
        "generate_whatsapp_message",
        {
            "counter_id": candidate.counter_id,
            "module_id": candidate.recommended_module_id,
            "tone": (state.plan.tone if state.plan else "professional"),
            "language": (state.plan.language if state.plan else "English"),
            "top_features": [f.model_dump() for f in feats],
            "manager_name": state.manager_name,
        },
    )
    if not envelope["ok"]:
        return None
    data = envelope["data"]
    rec = DraftRecord(
        counter_id=candidate.counter_id,
        module_id=candidate.recommended_module_id,
        message=data.get("message", ""),
        compliance=data.get("compliance", {}),
        llm_route=data.get("llm_route", ""),
    )
    state.emit(TraceEvent(
        event="draft",
        data={
            "counter_id": rec.counter_id,
            "module_id": rec.module_id,
            "message": rec.message,
            "compliance": rec.compliance,
            "llm_route": data.get("llm_route"),
            "fallback_reason": data.get("fallback_reason", ""),
        },
        llm_route=data.get("llm_route"),
        latency_ms=data.get("latency_ms"),
    ))
    return rec


async def _consented_ids(state: AgentState) -> tuple[set[str], list[dict[str, Any]]]:
    """DPDP consent gate: only counters that opted into outreach may be drafted.

    Reads consent straight from the datasource (the counter row is authoritative, not
    the recommendation), and fails closed — a candidate with no consent record on file
    is treated as opted out. Returns (consented ids, skipped candidate summaries).
    """
    ids = [c.counter_id for c in state.candidates]
    consented: set[str] = set()
    skipped: list[dict[str, Any]] = []
    try:
        ds = get_datasource()
        recs = await ds.get_counters_bulk(ids)
    except Exception:  # noqa: BLE001 — a consent lookup must never crash the node
        recs = {}

    for c in state.candidates:
        if bool(recs.get(c.counter_id, {}).get("consent_ok")):
            consented.add(c.counter_id)
        else:
            skipped.append(
                {
                    "counter_id": c.counter_id,
                    "name": c.name,
                    "module_id": c.recommended_module_id,
                    "composite_score": c.composite_score,
                    "reason": "no DPDP consent on file" if c.counter_id in recs else "consent record unavailable",
                }
            )
    return consented, skipped


async def run_message_generator(state: AgentState) -> AgentState:
    if not state.candidates:
        state.emit(TraceEvent(event="info", data={"msg": "no candidates → skipping drafts"}))
        return state

    consented, skipped = await _consented_ids(state)
    if skipped:
        state.emit(TraceEvent(
            event="info",
            data={
                "msg": f"drafts blocked for {len(skipped)} candidate(s) without DPDP consent",
                "skipped": skipped,
            },
        ))

    open_candidates = [c for c in state.candidates if c.counter_id in consented]
    if not open_candidates:
        state.emit(TraceEvent(event="info", data={"msg": "no consented candidates → skipping drafts"}))
        return state

    sem = asyncio.Semaphore(_MAX_CONCURRENCY)

    async def _bounded(c):
        async with sem:
            return await _draft_for(state, c)

    results = await asyncio.gather(*[_bounded(c) for c in open_candidates])
    state.drafts = [r for r in results if r is not None]
    return state

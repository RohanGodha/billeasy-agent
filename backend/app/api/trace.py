"""Replay the agent's reasoning trace for one session."""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from app.auth.middleware import require_token
from app.db.sqlite_engine import get_async_conn

router = APIRouter(prefix="/trace", tags=["trace"], dependencies=[Depends(require_token)])


@router.get("/{session_id}", summary="Full plan -> tool -> critic -> synthesis trace for a session")
async def get_trace(session_id: str) -> dict:
    async with get_async_conn() as conn:
        cur = await conn.execute(
            "SELECT * FROM agent_traces WHERE session_id = ? ORDER BY ts ASC",
            (session_id,),
        )
        events = [dict(r) for r in await cur.fetchall()]
        cur = await conn.execute(
            "SELECT * FROM messages WHERE session_id = ? ORDER BY ts ASC",
            (session_id,),
        )
        messages = [dict(r) for r in await cur.fetchall()]
        cur = await conn.execute(
            "SELECT * FROM outreach_drafts WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        )
        drafts = [dict(r) for r in await cur.fetchall()]
    if not events and not messages:
        raise HTTPException(status_code=404, detail="No trace for that session")
    # Pretty-parse JSON fields
    for e in events:
        for k in ("input_json", "output_json"):
            if e.get(k):
                try:
                    e[k.replace("_json", "")] = json.loads(e[k])
                except Exception:  # noqa: BLE001
                    pass
    telemetry = {
        "llm_calls": sum(1 for e in events if e.get("llm_route")),
        "by_route": {
            route: sum(1 for e in events if e.get("llm_route") == route)
            for route in sorted({e["llm_route"] for e in events if e.get("llm_route")})
        },
        "routes": sorted({e.get("llm_route") for e in events} - {None}),
        "fallback_count": sum(1 for e in events if e.get("fallback_reason")),
        "fallback_reasons": sorted(
            {e["fallback_reason"] for e in events if e.get("fallback_reason")}
        ),
    }
    return {"events": events, "messages": messages, "drafts": drafts, "telemetry": telemetry}

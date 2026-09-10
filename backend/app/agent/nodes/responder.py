"""Responder node — persists drafts, emits the final SSE envelope, writes traces."""
from __future__ import annotations

import json

from app.agent.state import AgentState, TraceEvent
from app.application.tool_registry import invoke_tool
from app.db.sqlite_engine import get_async_conn


async def run_responder(state: AgentState) -> AgentState:
    # Defensively ensure the session row exists *before* writing any FK-dependent rows.
    async with get_async_conn() as conn:
        await conn.execute(
            "INSERT OR IGNORE INTO sessions (id, title) VALUES (?, ?)",
            (state.session_id, (state.manager_query[:60] + "...") if len(state.manager_query) > 63 else state.manager_query),
        )
        await conn.commit()

    # Persist outreach drafts (their FK now resolves)
    if state.drafts:
        await invoke_tool(
            "create_outreach_batch",
            {
                "session_id": state.session_id,
                "channel": "whatsapp",
                "drafts": [
                    {
                        "counter_id": d.counter_id,
                        "module_id": d.module_id,
                        "message": d.message,
                        "score": next((c.composite_score for c in state.candidates if c.counter_id == d.counter_id), None),
                        "compliance": d.compliance,
                    }
                    for d in state.drafts
                ],
            },
        )

    # Persist all events into agent_traces
    async with get_async_conn() as conn:
        for ev in state.archive:
            await conn.execute(
                """
                INSERT INTO agent_traces (id, session_id, node, input_json, output_json, llm_route, fallback_reason, source, latency_ms)
                VALUES (lower(hex(randomblob(8))), ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    state.session_id,
                    ev.event,
                    None,
                    json.dumps(ev.data, default=str),
                    ev.llm_route,
                    ev.fallback_reason,
                    ev.data.get("source"),
                    ev.latency_ms,
                ),
            )
        # also persist the final assistant message
        await conn.execute(
            """
            INSERT INTO messages (id, session_id, role, content, payload_json)
            VALUES (lower(hex(randomblob(8))), ?, 'assistant', ?, ?)
            """,
            (
                state.session_id,
                state.final_summary or "",
                json.dumps(
                    {
                        "candidates": [c.model_dump() for c in state.candidates],
                        "drafts": [d.model_dump() for d in state.drafts],
                    },
                    default=str,
                ),
            ),
        )
        await conn.commit()

    state.emit(TraceEvent(
        event="final",
        data={
            "summary": state.final_summary,
            "candidates": [c.model_dump() for c in state.candidates],
            "drafts": [d.model_dump() for d in state.drafts],
        },
    ))
    return state

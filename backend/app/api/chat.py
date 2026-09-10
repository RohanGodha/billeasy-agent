"""SSE-streamed chat endpoint. Drives the entire agent run."""
from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, Depends, Request
from pydantic import AliasChoices, BaseModel, Field, field_validator
from sse_starlette.sse import EventSourceResponse

from app.agent import AgentState, run_agent
from app.auth.middleware import require_token
from app.db.sqlite_engine import get_async_conn
from app.security import mask_pii

router = APIRouter(prefix="/chat", tags=["chat"], dependencies=[Depends(require_token)])


class ChatStreamIn(BaseModel):
    """One turn from the Area Partner Manager."""

    session_id: str | None = None
    manager_query: str = Field(
        validation_alias=AliasChoices("manager_query", "query"),
        description="Plain-language ask, e.g. 'find ferry counters in Mumbai leaking ticket revenue'.",
    )
    manager_name: str = Field(
        default="Rohan",
        validation_alias=AliasChoices("manager_name", "manager"),
        description="First name of the Area Partner Manager; used to sign outreach drafts.",
    )

    @field_validator("manager_query", mode="before")
    @classmethod
    def _clean_query(cls, v: object) -> str:
        s = (v if isinstance(v, str) else "").strip()
        if not s:
            raise ValueError("manager_query must not be empty")
        return s[:2000]


async def _ensure_session(session_id: str | None, query: str) -> str:
    if session_id:
        return session_id
    sid = str(uuid.uuid4())
    async with get_async_conn() as conn:
        await conn.execute(
            "INSERT INTO sessions (id, title) VALUES (?, ?)",
            (sid, _title_from_query(query)),
        )
        await conn.commit()
    return sid


def _title_from_query(q: str) -> str:
    q = q.strip().rstrip("?.! ")
    return (q[:60] + "...") if len(q) > 63 else q


async def _persist_user_msg(session_id: str, content: str) -> None:
    async with get_async_conn() as conn:
        await conn.execute(
            "INSERT INTO messages (id, session_id, role, content) VALUES (lower(hex(randomblob(8))), ?, 'user', ?)",
            (session_id, content),
        )
        await conn.execute("UPDATE sessions SET updated_at = datetime('now') WHERE id = ?", (session_id,))
        await conn.commit()


async def _load_history(session_id: str, limit: int = 8) -> list[dict[str, str]]:
    """Recent prior turns for this session (excludes the just-inserted user msg via caller order)."""
    async with get_async_conn() as conn:
        cur = await conn.execute(
            "SELECT role, content FROM messages WHERE session_id = ? ORDER BY ts ASC",
            (session_id,),
        )
        rows = [dict(r) for r in await cur.fetchall()]
    turns = [{"role": r["role"], "content": r["content"]} for r in rows if r["role"] in ("user", "assistant")]
    return turns[-limit:]


@router.post(
    "/stream",
    summary="Run the Counter Copilot agent and stream its reasoning over SSE",
    description=(
        "Streams plan / tool_call / tool_result / critic / candidate / draft / final events as the "
        "agent queries the counter network, scores leakage risk, recommends a Billeasy module and "
        "drafts WhatsApp nudges for counter supervisors."
    ),
)
async def chat_stream(req: ChatStreamIn, request: Request) -> EventSourceResponse:
    # DPDP gate: the query is masked before it is stored, titled, or built into state, so
    # the messages thread, session title, every LLM prompt and the agent trace never see
    # raw PAN/Aadhaar/GSTIN/mobile/email. Re-masking later (graph.py) is a no-op.
    query = mask_pii(req.manager_query)
    session_id = await _ensure_session(req.session_id, query)
    history = await _load_history(session_id)  # before inserting the new message
    await _persist_user_msg(session_id, query)

    state = AgentState(
        session_id=session_id,
        manager_query=query,
        manager_name=req.manager_name,
        history=history,
    )

    async def event_gen() -> AsyncIterator[dict]:
        yield {"event": "info", "data": json.dumps({"session_id": session_id})}
        try:
            async for ev in run_agent(state):
                if await request.is_disconnected():
                    break
                yield {"event": ev.event, "data": ev.model_dump_json()}
                # tiny throttle so the UI can paint between events
                await asyncio.sleep(0.005)
        except Exception as e:  # noqa: BLE001
            yield {"event": "error", "data": json.dumps({"error": f"{type(e).__name__}: {e}"})}

    return EventSourceResponse(event_gen(), ping=15)


# ---- non-streaming convenience for tests ----

@router.post(
    "/run",
    summary="Run the agent to completion and return candidates, drafts and the full trace",
)
async def chat_run(req: ChatStreamIn) -> dict:
    query = mask_pii(req.manager_query)
    session_id = await _ensure_session(req.session_id, query)
    history = await _load_history(session_id)
    await _persist_user_msg(session_id, query)
    state = AgentState(
        session_id=session_id,
        manager_query=query,
        manager_name=req.manager_name,
        history=history,
    )
    events = []
    async for ev in run_agent(state):
        events.append(ev.model_dump())
    return {
        "session_id": session_id,
        "summary": state.final_summary,
        "candidates": [c.model_dump() for c in state.candidates],
        "drafts": [d.model_dump() for d in state.drafts],
        "events": events,
    }

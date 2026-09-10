"""Chat sessions — one working thread per Area Partner Manager conversation."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.auth.middleware import require_token
from app.db.sqlite_engine import get_async_conn

router = APIRouter(prefix="/sessions", tags=["sessions"], dependencies=[Depends(require_token)])


class SessionRow(BaseModel):
    id: str
    title: str | None = None
    created_at: str
    updated_at: str


class CreateSessionIn(BaseModel):
    title: str | None = None


@router.post("", response_model=SessionRow, summary="Start a new Counter Copilot session")
async def create_session(body: CreateSessionIn) -> SessionRow:
    sid = str(uuid.uuid4())
    async with get_async_conn() as conn:
        await conn.execute(
            "INSERT INTO sessions (id, title) VALUES (?, ?)",
            (sid, body.title or "New session"),
        )
        await conn.commit()
        cur = await conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,))
        row = await cur.fetchone()
    assert row is not None
    return SessionRow(**dict(row))


@router.get("", response_model=list[SessionRow], summary="List recent sessions, newest first")
async def list_sessions() -> list[SessionRow]:
    async with get_async_conn() as conn:
        cur = await conn.execute(
            "SELECT * FROM sessions ORDER BY updated_at DESC LIMIT 50"
        )
        rows = [dict(r) for r in await cur.fetchall()]
    return [SessionRow(**r) for r in rows]

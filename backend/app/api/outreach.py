"""Outreach drafts — the WhatsApp nudges the agent writes for counter supervisors."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth.middleware import require_token
from app.db.sqlite_engine import get_async_conn

router = APIRouter(prefix="/outreach", tags=["outreach"], dependencies=[Depends(require_token)])


class ApproveIn(BaseModel):
    draft_ids: list[str]


@router.get("/{session_id}", summary="List every WhatsApp draft produced in a session")
async def list_drafts(session_id: str) -> dict:
    async with get_async_conn() as conn:
        cur = await conn.execute(
            "SELECT * FROM outreach_drafts WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,),
        )
        rows = [dict(r) for r in await cur.fetchall()]
    return {"drafts": rows}


@router.post("/approve", summary="Approve drafts for sending to counter supervisors")
async def approve(body: ApproveIn) -> dict:
    if not body.draft_ids:
        raise HTTPException(status_code=400, detail="draft_ids cannot be empty")
    async with get_async_conn() as conn:
        placeholders = ",".join(["?"] * len(body.draft_ids))
        await conn.execute(
            f"UPDATE outreach_drafts SET status='approved' WHERE id IN ({placeholders})",
            tuple(body.draft_ids),
        )
        await conn.commit()
    return {"approved": len(body.draft_ids)}


class UpdateDraftIn(BaseModel):
    message: str


@router.patch("/{draft_id}", summary="Edit a draft before it goes to the supervisor")
async def update_draft(draft_id: str, body: UpdateDraftIn) -> dict:
    async with get_async_conn() as conn:
        cur = await conn.execute("SELECT id FROM outreach_drafts WHERE id = ?", (draft_id,))
        row = await cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="draft not found")
        await conn.execute(
            "UPDATE outreach_drafts SET message = ? WHERE id = ?",
            (body.message, draft_id),
        )
        await conn.commit()
    return {"ok": True, "id": draft_id}

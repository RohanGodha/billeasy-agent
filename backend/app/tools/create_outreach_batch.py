from __future__ import annotations

import json
import time
import uuid

from pydantic import BaseModel

from app.application.tool_registry import tool
from app.db.sqlite_engine import get_async_conn


class DraftIn(BaseModel):
    counter_id: str
    module_id: str
    message: str
    score: float | None = None
    compliance: dict | None = None


class CreateOutreachIn(BaseModel):
    session_id: str
    channel: str = "whatsapp"
    drafts: list[DraftIn]


class CreateOutreachOut(BaseModel):
    session_id: str
    created: int
    ids: list[str]
    latency_ms: int


@tool(
    name="create_outreach_batch",
    description=(
        "Persist a batch of counter outreach drafts against a session. The Area Partner Manager "
        "reviews/approves these via the UI; this is the only write-path to the campaigns store."
    ),
    input_model=CreateOutreachIn,
    output_model=CreateOutreachOut,
)
async def create_outreach_batch(args: CreateOutreachIn) -> CreateOutreachOut:
    started = time.perf_counter()
    ids: list[str] = []
    async with get_async_conn() as conn:
        for d in args.drafts:
            draft_id = str(uuid.uuid4())
            ids.append(draft_id)
            await conn.execute(
                """
                INSERT INTO outreach_drafts
                  (id, session_id, counter_id, module_id, channel, message, score, compliance_json, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'draft')
                """,
                (
                    draft_id,
                    args.session_id,
                    d.counter_id,
                    d.module_id,
                    args.channel,
                    d.message,
                    d.score,
                    json.dumps(d.compliance or {}),
                ),
            )
        await conn.commit()
    return CreateOutreachOut(
        session_id=args.session_id,
        created=len(ids),
        ids=ids,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )

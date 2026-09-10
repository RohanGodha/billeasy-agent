from __future__ import annotations

from fastapi import APIRouter

from app.infrastructure.datasource import get_datasource
from app.infrastructure.llm import get_llm_router

router = APIRouter(tags=["health"])


@router.get("/healthz", summary="Liveness probe")
async def healthz() -> dict:
    return {"ok": True, "service": "counter-copilot"}


@router.get("/status", summary="Live datasource and LLM provider status")
async def status() -> dict:
    ds = get_datasource()
    llm = get_llm_router()
    return {
        "datasource_active": getattr(ds, "name", "unknown"),
        "datasource_healthy": await ds.health(),
        "llm_providers": llm.status(),
    }

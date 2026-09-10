"""Knowledge-base endpoints — NLP query over the Billeasy reference documents:
payments & GST compliance, counter performance methodology, and field-ops FAQs.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, field_validator

from app.auth.middleware import require_token
from app.knowledge_base import get_knowledge_base

router = APIRouter(prefix="/knowledge", tags=["knowledge"], dependencies=[Depends(require_token)])


class AskIn(BaseModel):
    query: str

    @field_validator("query", mode="before")
    @classmethod
    def _clean(cls, v: object) -> str:
        s = (v if isinstance(v, str) else "").strip()
        if not s:
            raise ValueError("query must not be empty")
        return s[:500]


@router.post("/ask", summary="Ask a payments, settlement, GST or counter-history question")
async def ask(body: AskIn) -> dict:
    return await get_knowledge_base().ask(body.query)


@router.get("/sources", summary="Indexed reference documents and suggested questions")
async def sources() -> dict:
    kb = get_knowledge_base()
    return {
        "sources": kb.sources(),
        "suggestions": [
            "What is the GST e-invoice turnover threshold and the B2C dynamic-QR mandate?",
            "How does T+1 settlement work, and when is a payout considered delayed?",
            "Is MDR charged on UPI and RuPay debit transactions?",
            "What are the RBI nodal and escrow account rules for a payment aggregator?",
            "Explain merchant KYC and re-KYC for a new transit counter.",
            "Gateway Jetty — Counter 3: settlement history and open field notes.",
        ],
    }

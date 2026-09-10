from __future__ import annotations

import time
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.application.tool_registry import tool
from app.infrastructure.rag import get_retriever


class SearchFieldNotesIn(BaseModel):
    query: str = ""
    k: int = Field(default=5, ge=1, le=50)
    counter_id: str | None = None

    @field_validator("counter_id", mode="before")
    @classmethod
    def _only_string(cls, v: Any) -> Any:
        return v if isinstance(v, str) else None


class SearchFieldNotesOut(BaseModel):
    source: str = "bm25"
    matches: list[dict[str, Any]]
    latency_ms: int


@tool(
    name="search_field_notes",
    description=(
        "Search field-visit notes and support tickets for a counter using hybrid retrieval "
        "(dense + BM25 with MMR diversity re-rank). Surfaces device downtime, payout queries, "
        "reconciliation disputes and supervisor complaints. Returns ranked, cited snippets with "
        "citation IDs that downstream nodes must reference."
    ),
    input_model=SearchFieldNotesIn,
    output_model=SearchFieldNotesOut,
)
async def search_field_notes(args: SearchFieldNotesIn) -> SearchFieldNotesOut:
    started = time.perf_counter()
    retriever = get_retriever()
    matches = await retriever.search(args.query, k=args.k, counter_id=args.counter_id)
    return SearchFieldNotesOut(
        source=retriever.mode,
        matches=matches,
        latency_ms=int((time.perf_counter() - started) * 1000),
    )

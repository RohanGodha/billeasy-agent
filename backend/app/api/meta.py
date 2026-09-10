"""Meta endpoints — capabilities, Billeasy modules, example prompts, FAQs, domain + live status.

Powers the frontend "Guide" panel so the Area Partner Manager can see exactly what the
agent does, which domain it operates in, and browse the full FAQ set.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.agent.knowledge import CAPABILITIES, DOMAIN, EXAMPLE_PROMPTS, FAQS, MODULES
from app.auth.middleware import require_token
from app.infrastructure.datasource import get_datasource
from app.infrastructure.llm import get_llm_router

router = APIRouter(prefix="/meta", tags=["meta"], dependencies=[Depends(require_token)])


@router.get(
    "/capabilities",
    summary="What Counter Copilot can do, the modules it recommends, and live component status",
)
async def capabilities() -> dict:
    ds = get_datasource()
    llm = get_llm_router()
    providers = llm.status()
    active = [k for k, v in providers.items() if v and k != "mock"]

    # Report what is actually loaded, never a hardcoded label. Chroma is optional (it
    # exceeds the free tier's memory), so a deployment that says "hybrid" while running
    # lexical-only retrieval is lying to the person evaluating it.
    from app.infrastructure.rag.hybrid_retriever import get_retriever

    retrieval_mode = get_retriever().mode
    rag_label = (
        "hybrid (dense + BM25)" if retrieval_mode == "chroma+bm25" else "BM25 (lexical only)"
    )

    return {
        "domain": DOMAIN,
        "capabilities": CAPABILITIES,
        "modules": MODULES,
        "example_prompts": EXAMPLE_PROMPTS,
        "faq_count": len(FAQS),
        # True when no LLM key is configured: the agent still runs end to end, but the
        # planner and the summary are deterministic rather than model-written. Surfaced
        # so the UI can say so plainly instead of looking mysteriously capable.
        "demo_mode": not active,
        "status": {
            "datasource": getattr(ds, "name", "unknown"),
            "llm": (" + ".join(active)) if active else "deterministic planner (no LLM key)",
            "rag": rag_label,
        },
    }


@router.get("/faqs", summary="Area Partner Manager FAQs, grouped by category")
async def faqs() -> dict:
    grouped: dict[str, list[dict[str, str]]] = {}
    for f in FAQS:
        grouped.setdefault(f["category"], []).append({"q": f["q"], "a": f["a"]})
    return {"count": len(FAQS), "categories": grouped}

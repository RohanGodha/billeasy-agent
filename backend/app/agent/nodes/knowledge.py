"""Knowledge node — answers payments/compliance/counter questions from the reference KB.

If the question is answerable from the markdown knowledge base (payments compliance,
counter performance methodology, field-ops FAQs) or a named counter's records, the answer
is grounded in them. Otherwise it falls back to a full LLM call for a general Indian
payments / transit-ticketing answer.
"""
from __future__ import annotations

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.state import AgentState, TraceEvent
from app.infrastructure.llm import LLMMessage, get_llm_router
from app.knowledge_base import get_knowledge_base
from app.observability import get_logger

logger = get_logger(__name__)


async def run_knowledge(state: AgentState) -> AgentState:
    kb = get_knowledge_base()
    # Rocchio feedback: reuse the terms our last grounded answer emphasised so a
    # follow-up that re-asks a topic re-finds the sections that answered it before.
    prior = " ".join(h["content"] for h in state.history[-6:] if h["role"] == "assistant")
    feedback = kb.feedback_terms(prior, state.manager_query)
    result = await kb.ask(state.manager_query, expand_terms=feedback or None)
    sources = result.get("sources") or []
    route = result.get("llm_route")

    if sources:
        state.final_summary = result["answer"]
    else:
        # Not in the knowledge base — do a full LLM call for a general payments answer.
        router = get_llm_router()
        try:
            resp = await router.complete(
                kind="reasoning",
                messages=[
                    LLMMessage(role="system", content=SYSTEM_PROMPT),
                    LLMMessage(role="user", content=state.manager_query),
                ],
                temperature=0.3,
                max_tokens=320,
            )
            text = resp.text.strip()
            state.final_summary = text or result["answer"]
            route = resp.meta.get("route_used", resp.provider)
        except Exception as e:  # noqa: BLE001
            logger.warning("Knowledge fallback LLM failed (%s).", e.__class__.__name__)
            state.final_summary = result["answer"]

    state.emit(TraceEvent(
        event="synth",
        data={
            "summary": state.final_summary,
            "candidate_count": 0,
            "mode": "knowledge",
            "kb_sources": sources,
        },
        llm_route=route,
        fallback_reason=None,
    ))
    return state

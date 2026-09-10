"""FAQ node — answers capability/module/process questions, grounded in the KB."""
from __future__ import annotations

from app.agent.knowledge import FAQ_KNOWLEDGE_BASE
from app.agent.prompts import FAQ_PROMPT, SYSTEM_PROMPT
from app.agent.state import AgentState, TraceEvent
from app.infrastructure.llm import LLMMessage, get_llm_router


async def run_faq(state: AgentState) -> AgentState:
    router = get_llm_router()
    resp = await router.complete(
        kind="reasoning",
        messages=[
            LLMMessage(role="system", content=SYSTEM_PROMPT + "\n\n" + FAQ_PROMPT.format(kb=FAQ_KNOWLEDGE_BASE)),
            LLMMessage(role="user", content=state.manager_query),
        ],
        temperature=0.2,
        max_tokens=260,
    )
    text = resp.text.strip()
    if len(text) < 15:
        text = (
            "I help you find counters that are leaking revenue or drifting out of compliance, score "
            "them, recommend the right Billeasy module, and draft compliance-checked WhatsApp nudges. "
            "Try: \"Find ferry and bus counters in Mumbai leaking digital ticket revenue and draft "
            "nudges for the supervisors.\""
        )
    state.final_summary = text
    state.emit(TraceEvent(
        event="synth",
        data={"summary": state.final_summary, "candidate_count": 0, "mode": "faq"},
        llm_route=resp.meta.get("route_used", resp.provider),
        latency_ms=resp.latency_ms,
        fallback_reason=resp.meta.get("fallback_reason"),
    ))
    return state

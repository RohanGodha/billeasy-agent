"""Planner node — turns the Area Manager's natural-language ask into a typed Plan."""
from __future__ import annotations

from typing import Any

from app.agent.prompts import FOLLOW_UP_PROMPT, planner_prompt
from app.agent.state import AgentState, Plan, PlanStep, TraceEvent
from app.infrastructure.llm import LLMMessage, get_llm_router
from app.observability import get_logger

logger = get_logger(__name__)

_VALID_MODULES = {
    "MOD-BILLING", "MOD-ETICKET", "MOD-QR", "MOD-RECON",
    "MOD-OFFLINE", "MOD-LOYALTY", "MOD-WA-RECEIPT", "MOD-ANALYTICS",
}

# Settlement & Fare Reconciliation is the default target: revenue leakage is the
# Area Manager's daily question, and every counter type is eligible for it.
_DEFAULT_MODULE = "MOD-RECON"


def _load_system() -> str:
    return planner_prompt()


async def _rewrite_follow_up(state: AgentState) -> str:
    """Expand a refinement into a standalone task using conversation history."""
    router = get_llm_router()
    prev_user = next((h["content"] for h in reversed(state.history) if h["role"] == "user"), "")
    prev_assistant = next((h["content"] for h in reversed(state.history) if h["role"] == "assistant"), "")
    try:
        resp = await router.complete(
            kind="reasoning",
            messages=[
                LLMMessage(role="system", content=FOLLOW_UP_PROMPT),
                LLMMessage(role="user", content=(
                    f"Previous: '{prev_user}'\n"
                    f"(assistant replied: {prev_assistant[:160]})\n"
                    f"New: '{state.manager_query}'"
                )),
            ],
            temperature=0.0,
            max_tokens=160,
            json_mode=True,
        )
        rewritten = (resp.json_data or {}).get("rewritten", "").strip()
        if rewritten:
            return rewritten
    except Exception:  # noqa: BLE001
        pass
    # Fallback: concatenate previous task + new refinement
    return f"{prev_user} ({state.manager_query})" if prev_user else state.manager_query


def _coerce_plan(raw: dict[str, Any]) -> Plan:
    steps: list[PlanStep] = []
    for s in raw.get("steps", []) or []:
        try:
            steps.append(PlanStep(**s))
        except Exception:  # noqa: BLE001
            continue

    # city_filter can arrive as a list, a string, or null — normalise to list.
    raw_cf = raw.get("city_filter")
    if isinstance(raw_cf, str):
        cf: list[str] | None = [raw_cf]
    elif isinstance(raw_cf, list):
        cf = [str(c) for c in raw_cf if c]
        cf = cf if cf else None
    else:
        cf = None

    # Default to reconciliation when the planner leaves the module unset, so
    # downstream scoring/recommendation always has a concrete target.
    target = raw.get("target_module")
    if not (isinstance(target, str) and target.strip() in _VALID_MODULES):
        target = _DEFAULT_MODULE

    return Plan(
        intent=raw.get("intent", "find_counters_leaking_revenue"),
        target_module=target,
        city_filter=cf,
        tone=raw.get("tone", "professional"),
        language=raw.get("language", "English") or "English",
        steps=steps,
    )


def _default_plan(target_module: str = _DEFAULT_MODULE) -> Plan:
    """Hard fallback so the agent always has a runnable plan."""
    return Plan(
        intent="find_counters_leaking_revenue_and_outreach",
        target_module=target_module,
        tone="professional",
        steps=[
            PlanStep(step=1, tool="query_counters",
                     args={"min_tpv": 200000, "limit": 120, "exclude_modules": [target_module]},
                     expected="Shortlist of counters."),
            PlanStep(step=2, tool="compute_counter_value",
                     args={"counter_ids": "$step1.ids"},
                     expected="Value score per counter."),
            PlanStep(step=3, tool="predict_module_propensity",
                     args={"counter_ids": "$step1.ids", "module_id": target_module},
                     expected="Propensity per candidate counter."),
            PlanStep(step=4, tool="recommend_modules",
                     args={"counter_ids": "$step3.top_k",
                           "candidate_module_ids": [target_module], "top_k": 1},
                     expected="Best-fit Billeasy module per counter."),
            PlanStep(step=5, tool="search_field_notes",
                     args={"query": "settlement mismatch cash collection", "k": 5},
                     expected="RAG snippets for grounding."),
        ],
    )


async def run_planner(state: AgentState) -> AgentState:
    router = get_llm_router()
    sys_prompt = _load_system()

    # Follow-up: rewrite into a standalone task using history before planning.
    if state.intent == "follow_up" and state.history:
        rewritten = await _rewrite_follow_up(state)
        state.rewritten_query = rewritten
        state.emit(TraceEvent(event="info", data={"node": "follow_up", "rewritten": rewritten}))
        user_msg = rewritten.strip()
    else:
        user_msg = state.manager_query.strip()

    if not user_msg:
        state.plan = _default_plan()
        state.emit(TraceEvent(event="plan", data={"plan": state.plan.model_dump(), "source": "default"}))
        return state

    resp = await router.complete(
        kind="reasoning",
        messages=[
            LLMMessage(role="system", content=sys_prompt),
            LLMMessage(role="user", content=user_msg),
        ],
        temperature=0.2,
        max_tokens=900,
        json_mode=True,
    )
    raw = resp.json_data
    if not isinstance(raw, dict):
        logger.warning("Planner returned non-JSON; using default plan.")
        plan = _default_plan()
    else:
        plan = _coerce_plan(raw)
        if not plan.steps:
            plan = _default_plan(plan.target_module or _DEFAULT_MODULE)
    state.plan = plan
    state.emit(TraceEvent(
        event="plan",
        data={"plan": plan.model_dump(), "intent": plan.intent, "target_module": plan.target_module, "language": plan.language},
        llm_route=resp.meta.get("route_used", resp.provider),
        latency_ms=resp.latency_ms,
        fallback_reason=resp.meta.get("fallback_reason"),
    ))
    return state

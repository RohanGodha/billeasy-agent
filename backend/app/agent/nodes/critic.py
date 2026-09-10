"""Critic node — checks the latest tool call and decides pass/fail/replan.

The original critic caught exactly one failure mode: an empty result set. That let a
*plausible-but-wrong* step through — a sweep that ignored the requested city filters, or
a scoring stage that returned zero rows — and the Area Manager read the summary as
authoritative. The heuristics here are deliberately deterministic and cheap: the critic
shares no code path with the scoring that could mask its own mistakes.
"""
from __future__ import annotations

from app.agent.state import AgentState, TraceEvent

# Tools whose output shape is a list of result rows.
_ROWS_TOOLS = {
    "compute_counter_value": "counters",
    "predict_module_propensity": "counters",
    "recommend_modules": "recommendations",
}


def _requested_cities(state: AgentState, last) -> set[str]:
    """Cities the plan asked for, whether from the step args or the plan-level filter."""
    cities: list[str] = []
    step_cities = (last.args or {}).get("cities")
    if isinstance(step_cities, list):
        cities = [str(c) for c in step_cities if c]
    if not cities and state.plan and state.plan.city_filter:
        cities = [str(c) for c in state.plan.city_filter if c]
    return {c.lower() for c in cities}


async def run_critic(state: AgentState) -> AgentState:
    if not state.tool_calls:
        return state
    last = state.tool_calls[-1]

    verdict = "pass"
    replan = False
    notes = "Tool returned successfully."

    if not last.ok:
        verdict = "fail"
        replan = True
        notes = f"{last.tool} failed: {last.error}"
    elif isinstance(last.output, dict) and last.tool == "query_counters":
        counters: list = last.output.get("counters", []) or []
        relaxed: list = last.output.get("relaxed_filters", []) or []
        wanted = _requested_cities(state, last)
        if len(counters) == 0:
            verdict = "fail"
            replan = True
            notes = "No counters matched the filters; loosen criteria."
        elif wanted and "cities" in relaxed:
            # The tool already dropped the city filter to return *something*. Verdict
            # passes but the note must say so loudly: the answer is a wider sweep than
            # the Area Manager asked for and must not be presented as scoped.
            verdict = "pass"
            replan = False
            notes = (
                f"Returned {len(counters)} counters after dropping city filters "
                f"({sorted(wanted)}). This is a wider sweep than requested."
            )
        elif wanted and not any(((c.get("city") or "").lower()) in wanted for c in counters):
            # No relaxation happened and still not one counter landed in the requested
            # city — the filters and the data disagree. Don't replan (re-running cannot
            # change geography); flag it so the summary cannot overclaim coverage.
            verdict = "fail"
            replan = False
            notes = (
                f"No counter landed in the requested city set {sorted(wanted)}. "
                "Filters and data disagree — review before outreach."
            )
    elif isinstance(last.output, dict) and last.tool in _ROWS_TOOLS:
        rows_key = _ROWS_TOOLS[last.tool]
        rows: list = last.output.get(rows_key, []) or []
        if len(rows) == 0:
            verdict = "fail"
            replan = False
            notes = f"{last.tool} returned no rows; candidates will be thin."
    elif isinstance(last.output, dict) and last.tool == "search_field_notes" and not (last.output.get("matches") or []):
        notes = "No field-note matches; drafts will ground only on counter/module context."

    state.emit(TraceEvent(
        event="critic",
        data={"step": last.step, "tool": last.tool, "verdict": verdict, "replan": replan, "notes": notes},
    ))
    if verdict == "fail" and replan and state.replans < 1:
        state.replans += 1
        # naive recovery: relax filters and retry once
        if last.tool == "query_counters" and state.plan:
            step = state.plan.steps[state.cursor]
            step.args = {
                k: v for k, v in step.args.items()
                if k not in {"min_tpv", "min_pending_settlement", "min_daily_txns", "cities"}
            }
            step.args["limit"] = 200
            step.done = False
            # Pop the failed record so it re-runs cleanly
            state.tool_calls.pop()
            state.emit(TraceEvent(event="info", data={"action": "replan", "tool": last.tool, "new_args": step.args}))
            return state
    state.cursor += 1
    return state

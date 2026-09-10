"""Tool executor — resolves placeholders, dispatches, records the result."""
from __future__ import annotations

from typing import Any

from app.agent.state import AgentState, ToolCallRecord, TraceEvent
from app.application.tool_registry import invoke_tool


def _resolve_placeholders(state: AgentState, args: dict[str, Any]) -> dict[str, Any]:
    """Replace `$stepN.ids` / `$stepN.top_k` references with real values."""
    resolved: dict[str, Any] = {}
    for key, value in args.items():
        if isinstance(value, str) and value.startswith("$step"):
            resolved[key] = _resolve_one(state, value)
        elif isinstance(value, list):
            resolved[key] = [
                (_resolve_one(state, v) if isinstance(v, str) and v.startswith("$step") else v)
                for v in value
            ]
        else:
            resolved[key] = value
    return resolved


def _resolve_one(state: AgentState, ref: str) -> Any:
    """ref like '$step1.ids' or '$step2.top_k' """
    try:
        body = ref[5:]  # strip "$step"
        n_str, _, attr = body.partition(".")
        n = int(n_str)
    except ValueError:
        return ref
    tc = next((t for t in state.tool_calls if t.step == n and t.ok), None)
    if tc is None:
        return []
    out = tc.output or {}
    if attr == "ids":
        if tc.tool == "query_counters":
            return [c["id"] for c in out.get("counters", [])]
        if tc.tool == "compute_counter_value":
            return [c["counter_id"] for c in out.get("counters", [])]
    if attr == "top_k":
        # Pass a *wide* shortlist into the next scoring stage so the final
        # composite ranking (value + propensity) is meaningful. If we capped at
        # 10 here, a high-propensity / moderate-value counter (e.g. a nano-tier
        # jetty with a severe cash-share spike) would be filtered out before
        # propensity is ever computed. The synthesizer trims to the real top-K.
        k = 40
        if tc.tool == "compute_counter_value":
            return [c["counter_id"] for c in out.get("counters", [])[:k]]
        if tc.tool == "predict_module_propensity":
            return [c["counter_id"] for c in out.get("counters", [])[:k]]
    return out


def _latest_counter_ids(state: AgentState, limit: int = 80) -> list[str]:
    """Most recent counter id list from query_counters / compute_counter_value."""
    for tc in reversed(state.tool_calls):
        if not tc.ok or not isinstance(tc.output, dict):
            continue
        if tc.tool == "query_counters":
            return [c["id"] for c in tc.output.get("counters", [])][:limit]
        if tc.tool == "compute_counter_value":
            return [c["counter_id"] for c in tc.output.get("counters", [])][:limit]
    return []


async def execute_step(state: AgentState, step_index: int) -> AgentState:
    if not state.plan or step_index >= len(state.plan.steps):
        return state
    step = state.plan.steps[step_index]
    args = _resolve_placeholders(state, step.args)

    # Apply the plan-level city filter if the step didn't carry it explicitly.
    if step.tool == "query_counters" and state.plan.city_filter:
        existing = args.get("cities")
        if not existing or not isinstance(existing, list) or len(existing) == 0:
            args["cities"] = state.plan.city_filter

    # Backfill counter_ids from the latest shortlist when a placeholder resolves empty.
    if step.tool in {"compute_counter_value", "predict_module_propensity", "recommend_modules"}:
        cids = args.get("counter_ids")
        if not cids or not isinstance(cids, list) or len(cids) == 0:
            args["counter_ids"] = _latest_counter_ids(state)

    state.emit(TraceEvent(event="tool_call", data={"step": step.step, "tool": step.tool, "args": args}))

    envelope = await invoke_tool(step.tool, args)
    record = ToolCallRecord(
        step=step.step,
        tool=step.tool,
        args=args,
        ok=envelope["ok"],
        source=(envelope.get("data") or {}).get("source") if envelope["ok"] else None,
        latency_ms=envelope["latency_ms"],
        output=envelope.get("data"),
        error=envelope.get("error"),
    )
    state.tool_calls.append(record)
    step.done = record.ok

    # Build a compact result payload for SSE
    summary: dict[str, Any] = {
        "step": step.step,
        "tool": step.tool,
        "ok": record.ok,
        "source": record.source,
        "latency_ms": record.latency_ms,
    }
    if record.ok and isinstance(record.output, dict):
        if "counters" in record.output and isinstance(record.output["counters"], list):
            summary["rows"] = len(record.output["counters"])
        elif "recommendations" in record.output:
            summary["rows"] = len(record.output["recommendations"])
        elif "matches" in record.output:
            summary["rows"] = len(record.output["matches"])
    if not record.ok:
        summary["error"] = record.error

    state.emit(TraceEvent(
        event="tool_result",
        data=summary,
        latency_ms=record.latency_ms,
    ))
    return state

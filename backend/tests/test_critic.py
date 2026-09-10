"""Critic hard-case heuristics — the critic now catches plausible-but-wrong steps.

The original critic flagged exactly one thing: an empty result set. These tests pin the
new deterministic checks — a city filter officially ignored because the tool relaxed it,
a result set that contradicts the plan's requested cities with no relaxation at all,
and an empty scoring/recall stage — so a wrong-looking or thin run is *described* in the
trace and cannot be presented as scoped and complete.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


async def run() -> int:
    from app.agent.nodes.critic import run_critic
    from app.agent.state import AgentState, Plan, PlanStep, ToolCallRecord

    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(f"  [{'ok' if cond else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
        if not cond:
            failures.append(name)

    def critic_event(state: AgentState) -> dict:
        ev = [e for e in state.archive if e.event == "critic"][-1]
        return ev.data

    # --- 1. City filters dropped by relaxation must be reported loudly ---------
    state = AgentState(
        plan=Plan(steps=[PlanStep(step=1, tool="query_counters", args={"cities": ["Mumbai"]})]),
    )
    state.tool_calls.append(ToolCallRecord(
        step=1, tool="query_counters", args={"cities": ["Mumbai"]}, ok=True,
        output={
            "counters": [{"id": "CTR-1", "city": "Pune"}],
            "relaxed_filters": ["cities"],
        },
    ))
    await run_critic(state)
    ev = critic_event(state)
    check(
        "relaxed city filter is pass-with-loud-note (not silently accepted)",
        ev["verdict"] == "pass" and "wider sweep" in ev["notes"],
        f"verdict={ev['verdict']} notes={ev['notes'][:80]}",
    )

    # --- 2. City contradiction with NO relaxation is a hard fail ---------------
    state = AgentState(
        plan=Plan(steps=[PlanStep(step=1, tool="query_counters", args={"cities": ["Mumbai"]})]),
    )
    state.tool_calls.append(ToolCallRecord(
        step=1, tool="query_counters", args={"cities": ["Mumbai"]}, ok=True,
        output={
            "counters": [{"id": "CTR-2", "city": "Kochi"}],
            "relaxed_filters": [],
        },
    ))
    await run_critic(state)
    ev = critic_event(state)
    check(
        "unrelaxed city contradiction is a fail",
        ev["verdict"] == "fail" and ev["replan"] is False and "No counter landed" in ev["notes"],
        f"verdict={ev['verdict']} replan={ev['replan']}",
    )

    # --- 3. Plan-level city filter is honoured when the step carries none ------
    state = AgentState(
        plan=Plan(city_filter=["Kolkata"], steps=[PlanStep(step=1, tool="query_counters", args={})]),
    )
    state.tool_calls.append(ToolCallRecord(
        step=1, tool="query_counters", args={"cities": ["Kolkata"]}, ok=True,
        output={
            "counters": [{"id": "CTR-3", "city": "Delhi"}],
            "relaxed_filters": [],
        },
    ))
    await run_critic(state)
    ev = critic_event(state)
    check(
        "plan-level city filter feeds the contradiction check",
        ev["verdict"] == "fail" and "kolkata" in ev["notes"] and "requested city set" in ev["notes"],
        ev["notes"][:70],
    )

    # --- 4. In-scope results pass normally --------------------------------------
    state = AgentState(plan=Plan(steps=[PlanStep(step=1, tool="query_counters", args={})]))
    state.tool_calls.append(ToolCallRecord(
        step=1, tool="query_counters", args={}, ok=True,
        output={"counters": [{"id": "CTR-4", "city": "Mumbai"}], "relaxed_filters": []},
    ))
    await run_critic(state)
    ev = critic_event(state)
    check("in-scope results pass", ev["verdict"] == "pass", f"verdict={ev['verdict']}")

    # --- 5. Empty scoring/recall stages are flagged, not silently accepted ------
    for tool, key in [("compute_counter_value", "counters"), ("recommend_modules", "recommendations")]:
        s = AgentState(plan=Plan(steps=[PlanStep(step=1, tool=tool, args={})]))
        s.tool_calls.append(ToolCallRecord(step=1, tool=tool, args={}, ok=True, output={key: []}))
        await run_critic(s)
        ev = critic_event(s)
        check(
            f"{tool} returning zero rows is flagged",
            ev["verdict"] == "fail" and ev["replan"] is False,
            f"verdict={ev['verdict']}",
        )

    # --- 6. Empty search_field_notes is a note, not a fail (drafts still grounded) --
    state = AgentState(plan=Plan(steps=[PlanStep(step=1, tool="search_field_notes", args={})]))
    state.tool_calls.append(ToolCallRecord(step=1, tool="search_field_notes", args={}, ok=True, output={"matches": []}))
    await run_critic(state)
    ev = critic_event(state)
    check(
        "empty field-notes search is pass-with-note",
        ev["verdict"] == "pass" and "No field-note matches" in ev["notes"],
        f"verdict={ev['verdict']}",
    )

    # --- 7. The existing empty-resultate replan recovery still works ------------
    state = AgentState(
        plan=Plan(steps=[PlanStep(step=1, tool="query_counters", args={"cities": ["Mumbai"]}, done=False)]),
    )
    state.tool_calls.append(ToolCallRecord(
        step=1, tool="query_counters", args={"cities": ["Mumbai"]}, ok=True,
        output={"counters": [], "relaxed_filters": []},
    ))
    await run_critic(state)
    check(
        "empty result still triggers the relax-and-retry replan",
        state.replans == 1 and len(state.tool_calls) == 0,
        f"replans={state.replans} calls={len(state.tool_calls)}",
    )

    if failures:
        print(f"\nCritic test FAILED: {failures}")
        return 1
    print("\nCritic tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))

"""Full agent run — Planner → Tools → Critic → Synthesizer → MessageGen → Responder.

Runs against the deterministic mock LLM and the seeded SQLite network, so it needs no
API keys. The assertions check that the demo claim actually holds: a plain-language
leakage question has to surface the leaking ferry counter through real scoring, with a
grounded, compliance-checked draft.
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
    from app.agent import AgentState, run_agent
    from app.db.sqlite_engine import bootstrap

    bootstrap()
    state = AgentState(
        manager_query=(
            "Find ferry and bus counters in Mumbai leaking digital ticket revenue "
            "this month and draft WhatsApp nudges for the depot supervisors."
        ),
    )
    print(f">>> Session id: {state.session_id}")
    event_counts: dict[str, int] = {}
    async for ev in run_agent(state):
        event_counts[ev.event] = event_counts.get(ev.event, 0) + 1
        if ev.event in ("plan", "tool_result", "critic", "synth", "final"):
            print(f"  [{ev.event}] keys={list(ev.data.keys())[:6]}")

    print(f"\n>>> Event counts: {event_counts}")
    print(f">>> Plan steps: {len(state.plan.steps) if state.plan else 0}")
    print(f">>> Target module: {state.plan.target_module if state.plan else None}")
    print(f">>> Tool calls: {len(state.tool_calls)}")
    print(f">>> Candidates: {len(state.candidates)}")
    print(f">>> Drafts:     {len(state.drafts)}")
    print(f">>> Summary ({len(state.final_summary)} chars):")
    print("    " + state.final_summary[:240].replace("\n", " "))

    print("\n>>> Top 3 candidates:")
    for c in state.candidates[:3]:
        print(
            f"  - {c.name[:34]:34s} comp={c.composite_score:.2f} "
            f"leak={c.leakage_risk:.2f} ({c.leakage_band}) -> {c.recommended_module_name}"
        )
        print(f"      next: {c.next_action}")

    print("\n>>> Sample draft (first):")
    if state.drafts:
        print(f"    {state.drafts[0].message[:280]}")
        print(f"    compliance.ok = {state.drafts[0].compliance.get('ok')}")

    # --- assertions -------------------------------------------------------
    assert state.plan is not None, "Plan was not produced"
    assert len(state.tool_calls) >= 4, f"Expected >=4 tool calls, got {len(state.tool_calls)}"
    assert len(state.candidates) >= 1, "No candidates produced"
    assert len(state.drafts) >= 1, "No drafts produced"

    # leakage_risk is a real 0-1 severity, not a flag
    for c in state.candidates:
        assert isinstance(c.leakage_risk, float), f"leakage_risk not a float: {c.leakage_risk!r}"
        assert 0.0 <= c.leakage_risk <= 1.0, f"leakage_risk out of range: {c.leakage_risk}"
        assert c.leakage_band in {"clear", "watch", "elevated", "severe"}, c.leakage_band

    # The leaking ferry counter must surface for a leakage question, by scoring.
    ids = {c.counter_id for c in state.candidates}
    assert "CTR-0001" in ids, f"Gateway Jetty (CTR-0001) not surfaced; got {sorted(ids)[:8]}"

    # DPDP consent gate: CTR-0001 was seeded without outreach consent, so even though
    # it is the top scoring leak, it must never receive a draft. Only opted-in counters
    # may be drafted.
    draft_ids = {d.counter_id for d in state.drafts}
    assert "CTR-0001" not in draft_ids, "No-consent counter must not receive a draft"
    assert len(draft_ids) >= 1, "Expected at least one consented counter to be drafted"

    # Every draft has to pass the numeric-grounding validator.
    for d in state.drafts:
        assert d.compliance.get("ok") is True, f"Draft failed compliance: {d.compliance}"
        assert d.compliance.get("dpdp_consent_ok") is True, f"Draft missing consent marker: {d.compliance}"
        assert d.message.strip(), "Empty draft message"

    print("\nAgent E2E test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))

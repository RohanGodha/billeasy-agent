"""Global control commands — help / reset / cancel — must be recognised without any
LLM provider and must never be fumbled into a task plan. A real ask that merely
*contains* the word ("help me find counters leaking revenue") is not a command.
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

CANONICAL = "find counters in Mumbai with monthly TPV above 50 lakh, flag significant revenue leakage, and draft a WhatsApp nudge for each counter supervisor"


async def run() -> int:
    from fastapi.testclient import TestClient

    from app.agent.nodes.intent import classify_intent
    from app.agent.state import AgentState
    from app.db.sqlite_engine import bootstrap
    from app.main import app

    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(f"  [{'ok' if cond else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
        if not cond:
            failures.append(name)

    bootstrap()

    budget = "shared"

    client = TestClient(app)
    auth = {"X-Access-Token": budget}

    # --- 1. Deterministic heuristic routing, no provider needed ---------------
    for cmd in ["help", "Help!", "back", "go back", "cancel", "stop", "reset",
                "restart", "start over", "start again",
                "clear session", "clear the conversation", "clear chat history",
                "help.", "  reset  "]:
        st = AgentState(manager_query=cmd)
        await classify_intent(st)
        check(f"'{cmd}' -> command", st.intent == "command", st.intent)
    for ask in ["help me find counters leaking revenue in Goa",
                "can you recheck the settlement from yesterday",
                "give me 5 counters in Pune"]:
        st = AgentState(manager_query=ask)
        await classify_intent(st)
        check(f"'{ask[:34]}...' is NOT a command", st.intent != "command", st.intent)

    def stream_sid(query: str, session_id: str | None = None) -> str | None:
        body: dict = {"manager_query": query}
        if session_id:
            body["session_id"] = session_id
        r = client.post("/chat/run", json=body, headers=auth)
        assert r.status_code == 200, f"{r.status_code}: {r.text[:200]}"
        return r.json().get("session_id")

    # --- 2. help runs a full keyless response ---------------------------------
    help_id = stream_sid("help")
    check("help request returns a session_id", bool(help_id), str(help_id))
    if help_id:
        trace = client.get(f"/trace/{help_id}", headers=auth).json()
        summary = " ".join(m["content"] for m in trace["messages"] if m["role"] == "assistant")
        check("help reply documents the commands", "Commands" in summary or "help" in summary.lower(), summary[:80])

    # --- 3. a full canonical run, then reset clears only the memory -------------
    run_id = stream_sid(CANONICAL)
    check("canonical run returns a session_id", bool(run_id), str(run_id))
    if not run_id:
        failures.append("no canonical session")
        return 1
    trace_before = client.get(f"/trace/{run_id}", headers=auth).json()
    user_msgs_before = [m["content"] for m in trace_before["messages"] if m["role"] == "user"]
    check("run persists user message", len(user_msgs_before) == 1, str(len(user_msgs_before)))
    check("run leaves a trace", len(trace_before["events"]) > 3, str(len(trace_before["events"])))

    reset_id = stream_sid("reset", session_id=run_id)
    check("reset returns the same session_id", reset_id == run_id, str(reset_id))
    if reset_id == run_id:
        trace_after = client.get(f"/trace/{run_id}", headers=auth).json()
        msgs_after = trace_after["messages"]
        user_msgs_after = [m for m in msgs_after if m["role"] == "user"]
        assis_msgs_after = [m for m in msgs_after if m["role"] == "assistant"]
        check(
            "reset cleared all user messages from the session memory",
            len(user_msgs_after) == 0,
            str(len(user_msgs_after)),
        )
        check(
            "reset left exactly one assistant reply",
            len(assis_msgs_after) == 1 and "cleared this session's conversation memory" in assis_msgs_after[0]["content"],
            f"{len(assis_msgs_after)}",
        )
        check(
            "past run content did not leak into the cleared memory",
            not any("ferry" in m["content"].lower() for m in msgs_after),
        )
        check("original trace events survived the reset", len(trace_after["events"]) >= len(trace_before["events"]))

    if failures:
        print(f"\nCommands test FAILED: {failures}")
        return 1
    print("\nCommands tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))

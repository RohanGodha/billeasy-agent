"""Router telemetry — GET /trace must report which model answered every LLM call in a
session and when the router had to fall back to the mock. The frontend's trace pane and
any ops dashboard read this aggregation; without it, a silent fallback to mock is
invisible, which would make a real provider's absence look like a normal run.
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

CANONICAL = (
    "Find ferry and bus counters in Mumbai leaking digital ticket revenue this month "
    "and draft WhatsApp nudges for the depot supervisors."
)


async def run() -> int:
    from app.db.sqlite_engine import bootstrap
    from app.main import app

    bootstrap()
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(f"  [{'ok' if cond else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
        if not cond:
            failures.append(name)

    from fastapi.testclient import TestClient

    client = TestClient(app)
    auth = {"X-Access-Token": "shared"}

    r = client.post("/chat/run", json={"manager_query": CANONICAL}, headers=auth)
    check("run completes", r.status_code == 200, f"got {r.status_code}")
    sid = r.json()["session_id"]
    trace = client.get(f"/trace/{sid}", headers=auth).json()
    telemetry = trace["telemetry"]

    check("telemetry aggregates llm calls", telemetry["llm_calls"] >= 4, str(telemetry["llm_calls"]))
    check(
        "every llm event attributes its route",
        sum(telemetry["by_route"].values()) == telemetry["llm_calls"],
        f"road={telemetry['by_route']}",
    )
    check(
        "keyless run routes everything through mock",
        set(telemetry["routes"]) <= {"mock"},
        str(telemetry["routes"]),
    )
    check(
        "planner + synthesizer events carry a route on the trace",
        any(e["node"] == "plan" and e["llm_route"] for e in trace["events"])
        and any(e["node"] == "synth" and e["llm_route"] for e in trace["events"]),
    )
    check(
        "no fallback recorded when no provider was configured",
        telemetry["fallback_count"] == 0 and telemetry["fallback_reasons"] == [],
        f"{telemetry['fallback_count']} / {telemetry['fallback_reasons']}",
    )

    # The column itself must exist on the alive DB (schema + migration both correct).
    import sqlite3

    from app.settings import get_settings

    conn = sqlite3.connect(get_settings().sqlite_abs_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(agent_traces)")}
    finally:
        conn.close()
    check("agent_traces has a fallback_reason column", "fallback_reason" in cols)

    if failures:
        print(f"\nTelemetry test FAILED: {failures}")
        return 1
    print("\nTelemetry tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))

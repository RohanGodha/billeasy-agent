"""FR-32 — a session resumed from disk rejoins the same thread.

The guarantee: conversation state lives in SQLite, not in process memory, so a browser
restart or a backend reload must pick up where the conversation left off. This test proves
each link in that chain for real:

  1. a run persists its session + messages to the on-disk DB (checked with an independent
     sqlite3 connection, not the app's own handles);
  2. a *fresh* FastAPI client (simulating a restart) resumes the same session_id instead
     of minting a new one;
  3. the resumed turn is read as a follow-up — the planner rewrites it against the
     persisted history, which only works if history loaded off disk.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3
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
FOLLOW_UP = "of the counters you found, which had the strongest leakage signal?"


async def run() -> int:
    from fastapi.testclient import TestClient

    from app.db.sqlite_engine import bootstrap
    from app.main import app
    from app.settings import get_settings

    bootstrap()
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(f"  [{'ok' if cond else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
        if not cond:
            failures.append(name)

    auth = {"X-Access-Token": "shared"}
    db_path = get_settings().sqlite_abs_path

    def on_disk(query: str) -> list[tuple[str, str]]:
        """Read the thread this session has on disk via an airtight-foreign connection."""
        conn = sqlite3.connect(db_path)
        try:
            cur = conn.execute(
                "SELECT role, content FROM messages WHERE session_id = ? ORDER BY ts ASC, rowid ASC",
                (query,),
            )
            return cur.fetchall()
        finally:
            conn.close()

    def stream_events(client: TestClient, body: dict) -> list[tuple[str, dict]]:
        """Normalise an SSE stream into (event, data) pairs.

        The bootstrap info event is written as `data: {"session_id": ...}`; every trace
        event is written as `data: <TraceEvent.model_dump_json()>`, i.e. an object whose
        `data` key is already the event payload. This un-wraps both so assertions read
        event data, not transport format.
        """
        out: list[tuple[str, dict]] = []
        with client.stream("POST", "/chat/stream", json=body, headers=auth) as resp:
            assert resp.status_code == 200, f"{resp.status_code}: {resp.text[:200]}"
            for line in resp.iter_lines():
                if not line.startswith("data:"):
                    continue
                envelope: object = json.loads(line[5:])
                if not isinstance(envelope, dict):
                    continue
                if envelope.get("session_id"):
                    out.append(("info", envelope))
                    continue
                payload = envelope.get("data")
                if isinstance(payload, str):  # belt-and-braces double encoding
                    try:
                        payload = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                if isinstance(payload, dict):
                    out.append((str(envelope.get("event", "?")), payload))
        return out

    # --- 1. First turn on a server that has "restarted" ------------------------
    first_client = TestClient(app)
    first_run = stream_events(first_client, {"manager_query": CANONICAL})
    sid = next((p.get("session_id") for _, p in first_run if p.get("session_id")), None)
    check("first turn returns a session_id", bool(sid), str(sid))
    if not sid:
        print(f"\nSessions test FAILED: {failures}")
        return 1

    # --- 2. The thread is really on disk, via a connection the app never opened ---
    disk_msgs = on_disk(sid)
    user_on_disk = [c for r, c in disk_msgs if r == "user"]
    asst_on_disk = [c for r, c in disk_msgs if r == "assistant"]
    check("turn 1 user message persisted to disk", len(user_on_disk) == 1, str(len(user_on_disk)))
    check("turn 1 assistant reply persisted to disk", len(asst_on_disk) == 1, str(len(asst_on_disk)))

    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT title FROM sessions WHERE id = ?", (sid,)).fetchone()
    finally:
        conn.close()
    check("sessions row persisted (sidebar can list it)", bool(row) and "mumbai" in (row[0] or "").lower(), str(row))

    # --- 3. A fresh client (browser restart) resumes the same thread -------------
    restarted = TestClient(app)  # new transport, reads the same DB file
    resumed = stream_events(restarted, {"session_id": sid, "manager_query": FOLLOW_UP})
    resumed_sid = next((p.get("session_id") for _, p in resumed if p.get("session_id")), None)
    check("restart resumes the same session_id", resumed_sid == sid, str(resumed_sid))

    follow_up_event = next(p for ev, p in resumed if ev == "info" and p.get("node") == "follow_up")
    check(
        "resumed turn is planned as a follow-up (rewritten from on-disk history)",
        bool(follow_up_event),
        "",
    )
    rewritten = (follow_up_event or {}).get("rewritten", "")
    check(
        "follow-up rewrite actually carries the base query's scope",
        "mumbai" in rewritten.lower() and "revenue" in rewritten.lower(),
        rewritten[:80],
    )

    # --- 4. Both turns live under the same session on disk ----------------------
    disk_msgs = on_disk(sid)
    check(
        "thread on disk now holds both turns (2 pairs under one session)",
        sum(1 for r, _ in disk_msgs if r == "user") == 2
        and sum(1 for r, _ in disk_msgs if r == "assistant") == 2,
        f"{len(disk_msgs)} messages",
    )

    if failures:
        print(f"\nSessions test FAILED: {failures}")
        return 1
    print("\nSessions tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))

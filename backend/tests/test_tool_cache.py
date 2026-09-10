"""Tool-result caching regression tests.

`tool_cache` was a dead table (schema declared, no reader/writer) called out in
design.md. These pin the wiring: deterministic tools replay within the TTL with a
`cache: "hit"` marker, expiry pushes a recompute, and the write/generate tools can
never be cached.
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
    from app.application.tool_registry import invoke_tool
    from app.db.sqlite_engine import bootstrap, get_async_conn, get_sync_conn
    from app.infrastructure.tool_cache import CACHEABLE_TOOLS, make_cache_key

    bootstrap()
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        print(f"  [{'ok' if cond else 'FAIL'}] {name}{(' - ' + detail) if detail else ''}")
        if not cond:
            failures.append(name)

    async with get_async_conn() as conn:
        await conn.execute("DELETE FROM tool_cache")
        await conn.commit()

    args = {"cities": ["Mumbai"], "counter_types": ["ferry"], "limit": 5}

    first = await invoke_tool("query_counters", args)
    check("first call runs through", first["ok"], f"err={first.get('error')}")
    check("first call is a cache miss (no marker)", first.get("cache") is None)

    second = await invoke_tool("query_counters", args)
    check("second call is a cache hit", second.get("cache") == "hit")

    check(
        "hit replays identical rows",
        [c["id"] for c in first["data"]["counters"]] == [c["id"] for c in second["data"]["counters"]],
    )

    async with get_async_conn() as conn:
        cur = await conn.execute("SELECT cache_key, payload_json FROM tool_cache")
        rows = await cur.fetchall()
    check("the result row is on record", len(rows) == 1, f"got {len(rows)} rows")
    key = rows[0]["cache_key"]
    check(
        "the stored payload round-trips",
        make_cache_key("query_counters", args) == key,
    )

    # Expire the entry (backdate it well past the TTL) and confirm a recompute.
    with get_sync_conn() as conn:
        conn.execute("UPDATE tool_cache SET created_at = ? WHERE cache_key = ?", (1, key))
        conn.commit()
    expired = await invoke_tool("query_counters", args)
    check("expired entry recomputes (no cache marker)", expired.get("cache") is None)
    async with get_async_conn() as conn:
        cur = await conn.execute("SELECT created_at FROM tool_cache WHERE cache_key = ?", (key,))
        row = await cur.fetchone()
    check("expired entry is refreshed with a new timestamp", int(row["created_at"]) > 1)

    check(
        "write/generate tools are excluded from the cache",
        {"create_outreach_batch", "generate_whatsapp"}.isdisjoint(CACHEABLE_TOOLS),
        f"cached={sorted(CACHEABLE_TOOLS & {'create_outreach_batch', 'generate_whatsapp'})}",
    )

    if failures:
        print(f"\nTool cache test FAILED: {failures}")
        return 1
    print("\nTool cache tests passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))

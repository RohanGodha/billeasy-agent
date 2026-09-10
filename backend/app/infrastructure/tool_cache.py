"""Deterministic tool-result cache over the `tool_cache` table.

The schema declared `tool_cache` long before anything read or wrote it (design.md
called it a dead table). This wires it into `invoke_tool` for the read-only,
deterministic tools — query, value, propensity, recommend, field-notes search and
transaction aggregates. Mutating or generative tools (`create_outreach_batch`,
`generate_whatsapp`) are excluded by design: a cached batch write would be a lie, and a
cached LLM draft would pin stale prose.

The `cache_key` is a canonical JSON of (tool, args), so two plans that resolve the same
arguments hit the same row. TTL bounds staleness: the demo warehouse is an immutable
seed, but if it were refreshed, an entry older than `tool_cache_ttl_seconds` is ignored
and re-computed. Cache hits mark the returned envelope `cache: "hit"` so the trace can
show where the answer came from. Every failure degrades to a miss — the cache can never
break the tool path.
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from app.db.sqlite_engine import get_async_conn
from app.observability import get_logger

logger = get_logger(__name__)

# Tools whose output depends only on their validated arguments. Nothing in the seed
# changes during a process lifetime, so repeat calls with identical args are safe to
# replay within the TTL.
#
# The new 2026 batch adds only the *pure* text/config mappers here. Diagnostic tools
# (diagnose_reconciliation, analyze_telemetry) read operational state and are deliberately
# NOT cached: triage and health are meant to reflect the current estate, not a replayed
# snapshot.
CACHEABLE_TOOLS = {
    "query_counters",
    "compute_counter_value",
    "predict_module_propensity",
    "recommend_modules",
    "search_field_notes",
    "get_counter_transactions",
    "validate_invoice_layout",
    "generate_erp_mapping",
}


def make_cache_key(tool_name: str, args: dict[str, Any]) -> str:
    canonical = json.dumps(args, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{tool_name}:{canonical}".encode()).hexdigest()


async def get_cached(key: str, ttl: int) -> dict[str, Any] | None:
    try:
        async with get_async_conn() as conn:
            cur = await conn.execute(
                "SELECT payload_json, created_at FROM tool_cache WHERE cache_key = ?",
                (key,),
            )
            row = await cur.fetchone()
    except Exception as e:  # noqa: BLE001 - a broken cache is a miss, not a crash
        logger.debug("tool_cache read failed: %s", e)
        return None
    if row is None:
        return None
    if int(time.time()) - int(row["created_at"]) > ttl:
        return None
    return json.loads(row["payload_json"])


async def put_cached(key: str, payload: dict[str, Any]) -> None:
    try:
        async with get_async_conn() as conn:
            await conn.execute(
                "INSERT OR REPLACE INTO tool_cache (cache_key, payload_json, created_at) "
                "VALUES (?, ?, ?)",
                (key, json.dumps(payload, default=str), int(time.time())),
            )
            await conn.commit()
    except Exception as e:  # noqa: BLE001
        logger.debug("tool_cache write failed: %s", e)

"""SQLite adapter. Always available — also acts as the failover target."""
from __future__ import annotations

import json
import time
from typing import Any

from app.db.sqlite_engine import get_async_conn
from app.domain import Counter, CounterFilters, Module, Transaction
from app.observability import get_logger

from .base import DataSource, DataSourceResult

logger = get_logger(__name__)


class SQLiteSource(DataSource):
    name = "sqlite"

    async def find_counters(self, filters: CounterFilters) -> DataSourceResult:
        start = time.perf_counter()
        clauses: list[str] = []
        params: list[Any] = []
        if filters.cities:
            placeholders = ",".join(["?"] * len(filters.cities))
            clauses.append(f"c.city IN ({placeholders})")
            params.extend(filters.cities)
        if filters.tiers:
            placeholders = ",".join(["?"] * len(filters.tiers))
            clauses.append(f"c.tier IN ({placeholders})")
            params.extend(filters.tiers)
        if filters.counter_types:
            placeholders = ",".join(["?"] * len(filters.counter_types))
            clauses.append(f"c.counter_type IN ({placeholders})")
            params.extend(filters.counter_types)
        if filters.min_tpv is not None:
            clauses.append("c.monthly_tpv >= ?")
            params.append(filters.min_tpv)
        if filters.max_tpv is not None:
            clauses.append("c.monthly_tpv <= ?")
            params.append(filters.max_tpv)
        if filters.min_pending_settlement is not None:
            clauses.append("h.pending_settlement >= ?")
            params.append(filters.min_pending_settlement)
        if filters.min_daily_txns is not None:
            clauses.append("h.avg_daily_txns >= ?")
            params.append(filters.min_daily_txns)
        if filters.max_daily_txns is not None:
            clauses.append("h.avg_daily_txns <= ?")
            params.append(filters.max_daily_txns)
        if filters.settlement_cycles:
            placeholders = ",".join(["?"] * len(filters.settlement_cycles))
            clauses.append(f"c.settlement_cycle IN ({placeholders})")
            params.extend(filters.settlement_cycles)
        if filters.exclude_modules:
            placeholders = ",".join(["?"] * len(filters.exclude_modules))
            clauses.append(
                f"c.id NOT IN (SELECT counter_id FROM counter_modules WHERE module_id IN ({placeholders}) AND status='active')"
            )
            params.extend(filters.exclude_modules)

        where_sql = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"""
            SELECT c.*, h.pending_settlement, h.avg_daily_txns, h.digital_share, h.device_offline_minutes
            FROM counters c
            LEFT JOIN counter_health h ON h.counter_id = c.id
            {where_sql}
            ORDER BY h.avg_daily_txns DESC
            LIMIT ?
        """
        params.append(int(filters.limit))

        async with get_async_conn() as conn:
            cur = await conn.execute(sql, params)
            rows = [dict(r) for r in await cur.fetchall()]

        counters = [Counter(**r).model_dump() for r in rows]
        elapsed = int((time.perf_counter() - start) * 1000)
        return DataSourceResult(source=self.name, latency_ms=elapsed, rows=len(counters), data=counters)

    async def get_counter(self, counter_id: str) -> DataSourceResult:
        start = time.perf_counter()
        async with get_async_conn() as conn:
            cur = await conn.execute(
                """
                SELECT c.*, h.pending_settlement, h.avg_daily_txns, h.digital_share, h.device_offline_minutes
                FROM counters c
                LEFT JOIN counter_health h ON h.counter_id = c.id
                WHERE c.id = ?
                """,
                (counter_id,),
            )
            row = await cur.fetchone()
        if not row:
            return DataSourceResult(source=self.name, latency_ms=int((time.perf_counter() - start) * 1000), rows=0, data=None)
        data = Counter(**dict(row)).model_dump()
        return DataSourceResult(source=self.name, latency_ms=int((time.perf_counter() - start) * 1000), rows=1, data=data)

    async def get_transactions(self, counter_id: str, months: int = 6) -> DataSourceResult:
        start = time.perf_counter()
        async with get_async_conn() as conn:
            cur = await conn.execute(
                """
                SELECT id, counter_id, ts, amount, category, channel, instrument
                FROM transactions
                WHERE counter_id = ?
                  AND ts >= datetime('now', ?)
                ORDER BY ts DESC
                """,
                (counter_id, f"-{months * 30} days"),
            )
            rows = [dict(r) for r in await cur.fetchall()]
        txns = [Transaction(**r).model_dump() for r in rows]
        return DataSourceResult(
            source=self.name,
            latency_ms=int((time.perf_counter() - start) * 1000),
            rows=len(txns),
            data=txns,
        )

    # --- Bulk fetchers: one query for many counters (kills N+1) ---

    async def get_transactions_bulk(self, counter_ids: list[str], months: int = 6) -> dict[str, list[dict[str, Any]]]:
        if not counter_ids:
            return {}
        placeholders = ",".join(["?"] * len(counter_ids))
        out: dict[str, list[dict[str, Any]]] = {cid: [] for cid in counter_ids}
        async with get_async_conn() as conn:
            cur = await conn.execute(
                f"""
                SELECT id, counter_id, ts, amount, category, channel, instrument
                FROM transactions
                WHERE counter_id IN ({placeholders})
                  AND ts >= datetime('now', ?)
                ORDER BY ts DESC
                """,
                (*counter_ids, f"-{months * 30} days"),
            )
            for r in await cur.fetchall():
                d = dict(r)
                out.setdefault(d["counter_id"], []).append(d)
        return out

    async def get_holdings_bulk(self, counter_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        if not counter_ids:
            return {}
        placeholders = ",".join(["?"] * len(counter_ids))
        out: dict[str, list[dict[str, Any]]] = {cid: [] for cid in counter_ids}
        async with get_async_conn() as conn:
            cur = await conn.execute(
                f"""
                SELECT cm.counter_id, cm.module_id, m.name, m.category, cm.status, cm.activated_at
                FROM counter_modules cm JOIN modules m ON m.id = cm.module_id
                WHERE cm.counter_id IN ({placeholders})
                """,
                tuple(counter_ids),
            )
            for r in await cur.fetchall():
                d = dict(r)
                out.setdefault(d["counter_id"], []).append(d)
        return out

    async def get_field_notes_bulk(self, counter_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        if not counter_ids:
            return {}
        placeholders = ",".join(["?"] * len(counter_ids))
        out: dict[str, list[dict[str, Any]]] = {cid: [] for cid in counter_ids}
        async with get_async_conn() as conn:
            cur = await conn.execute(
                f"""
                SELECT id, counter_id, ts, channel, summary
                FROM field_notes WHERE counter_id IN ({placeholders}) ORDER BY ts DESC
                """,
                tuple(counter_ids),
            )
            for r in await cur.fetchall():
                d = dict(r)
                out.setdefault(d["counter_id"], []).append(d)
        return out

    async def get_counters_bulk(self, counter_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not counter_ids:
            return {}
        placeholders = ",".join(["?"] * len(counter_ids))
        out: dict[str, dict[str, Any]] = {}
        async with get_async_conn() as conn:
            cur = await conn.execute(
                f"""
                SELECT c.*, h.pending_settlement, h.avg_daily_txns, h.digital_share, h.device_offline_minutes
                FROM counters c LEFT JOIN counter_health h ON h.counter_id = c.id
                WHERE c.id IN ({placeholders})
                """,
                tuple(counter_ids),
            )
            for r in await cur.fetchall():
                d = Counter(**dict(r)).model_dump()
                out[d["id"]] = d
        return out

    async def get_modules(self) -> DataSourceResult:
        start = time.perf_counter()
        async with get_async_conn() as conn:
            cur = await conn.execute("SELECT * FROM modules")
            rows = [dict(r) for r in await cur.fetchall()]
        modules = []
        for r in rows:
            elig = json.loads(r.pop("eligibility_json", "{}") or "{}")
            r["eligibility"] = elig
            modules.append(Module(**r).model_dump())
        return DataSourceResult(
            source=self.name,
            latency_ms=int((time.perf_counter() - start) * 1000),
            rows=len(modules),
            data=modules,
        )

    async def get_holdings(self, counter_id: str) -> DataSourceResult:
        start = time.perf_counter()
        async with get_async_conn() as conn:
            cur = await conn.execute(
                """
                SELECT cm.module_id, m.name, m.category, cm.status, cm.activated_at
                FROM counter_modules cm
                JOIN modules m ON m.id = cm.module_id
                WHERE cm.counter_id = ?
                """,
                (counter_id,),
            )
            rows = [dict(r) for r in await cur.fetchall()]
        return DataSourceResult(
            source=self.name,
            latency_ms=int((time.perf_counter() - start) * 1000),
            rows=len(rows),
            data=rows,
        )

    async def get_field_notes(self, counter_id: str | None = None) -> DataSourceResult:
        start = time.perf_counter()
        async with get_async_conn() as conn:
            if counter_id:
                cur = await conn.execute(
                    "SELECT id, counter_id, ts, channel, summary FROM field_notes WHERE counter_id = ? ORDER BY ts DESC",
                    (counter_id,),
                )
            else:
                cur = await conn.execute(
                    "SELECT id, counter_id, ts, channel, summary FROM field_notes ORDER BY ts DESC"
                )
            rows = [dict(r) for r in await cur.fetchall()]
        return DataSourceResult(
            source=self.name,
            latency_ms=int((time.perf_counter() - start) * 1000),
            rows=len(rows),
            data=rows,
        )

    async def health(self) -> bool:
        try:
            async with get_async_conn() as conn:
                await conn.execute("SELECT 1")
            return True
        except Exception as e:  # noqa: BLE001
            logger.warning("SQLite health failed: %s", e)
            return False

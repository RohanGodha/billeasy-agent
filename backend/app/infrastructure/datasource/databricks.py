"""Databricks adapter — Delta tables via the SQL connector.

Sync connector wrapped in `asyncio.to_thread`. Timeout enforced via wait_for.
On any failure the FailoverSource silently falls back to SQLite.
"""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from app.domain import Counter, CounterFilters, Module, Transaction
from app.observability import get_logger
from app.settings import get_settings

from .base import DataSource, DataSourceResult

logger = get_logger(__name__)


class DatabricksSource(DataSource):
    name = "databricks"

    def __init__(self) -> None:
        self.settings = get_settings()
        self._catalog = self.settings.databricks_catalog
        self._schema = self.settings.databricks_schema

    # -----------------------------------------------------------------------
    # connector helpers
    # -----------------------------------------------------------------------
    def _connect(self):
        # imported lazily so the package is optional in dev
        from databricks import sql  # type: ignore[import-not-found]

        return sql.connect(
            server_hostname=self.settings.databricks_host,
            http_path=self.settings.databricks_http_path,
            access_token=self.settings.databricks_token,
        )

    def _query_sync(self, sql_text: str, params: tuple = ()) -> list[dict[str, Any]]:
        with self._connect() as conn, conn.cursor() as cur:
            if params:
                cur.execute(sql_text, params)
            else:
                cur.execute(sql_text)
            cols = [c[0] for c in cur.description] if cur.description else []
            return [dict(zip(cols, row, strict=False)) for row in cur.fetchall()]

    async def _query(self, sql_text: str, params: tuple = ()) -> list[dict[str, Any]]:
        return await asyncio.wait_for(
            asyncio.to_thread(self._query_sync, sql_text, params),
            timeout=self.settings.databricks_timeout_seconds,
        )

    def _t(self, name: str) -> str:
        return f"{self._catalog}.{self._schema}.{name}"

    # -----------------------------------------------------------------------
    # DataSource implementation
    # -----------------------------------------------------------------------
    async def find_counters(self, filters: CounterFilters) -> DataSourceResult:
        start = time.perf_counter()
        clauses: list[str] = []
        params: list[Any] = []
        if filters.cities:
            clauses.append("c.city IN (" + ",".join(["?"] * len(filters.cities)) + ")")
            params.extend(filters.cities)
        if filters.tiers:
            clauses.append("c.tier IN (" + ",".join(["?"] * len(filters.tiers)) + ")")
            params.extend(filters.tiers)
        if filters.counter_types:
            clauses.append("c.counter_type IN (" + ",".join(["?"] * len(filters.counter_types)) + ")")
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

        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        sql = f"""
            SELECT c.*, h.pending_settlement, h.avg_daily_txns, h.digital_share, h.device_offline_minutes
            FROM {self._t('counters')} c
            LEFT JOIN {self._t('counter_health')} h ON h.counter_id = c.id
            {where}
            ORDER BY h.avg_daily_txns DESC
            LIMIT {int(filters.limit)}
        """
        rows = await self._query(sql, tuple(params))
        counters = [Counter(**r).model_dump() for r in rows]
        return DataSourceResult(
            source=self.name,
            latency_ms=int((time.perf_counter() - start) * 1000),
            rows=len(counters),
            data=counters,
        )

    async def get_counter(self, counter_id: str) -> DataSourceResult:
        start = time.perf_counter()
        sql = f"""
            SELECT c.*, h.pending_settlement, h.avg_daily_txns, h.digital_share, h.device_offline_minutes
            FROM {self._t('counters')} c
            LEFT JOIN {self._t('counter_health')} h ON h.counter_id = c.id
            WHERE c.id = ?
        """
        rows = await self._query(sql, (counter_id,))
        data = Counter(**rows[0]).model_dump() if rows else None
        return DataSourceResult(
            source=self.name,
            latency_ms=int((time.perf_counter() - start) * 1000),
            rows=1 if data else 0,
            data=data,
        )

    async def get_transactions(self, counter_id: str, months: int = 6) -> DataSourceResult:
        start = time.perf_counter()
        sql = f"""
            SELECT id, counter_id, ts, amount, category, channel, instrument
            FROM {self._t('transactions')}
            WHERE counter_id = ? AND ts >= date_sub(current_timestamp(), {int(months * 30)})
            ORDER BY ts DESC
        """
        rows = await self._query(sql, (counter_id,))
        txns = [Transaction(**r).model_dump() for r in rows]
        return DataSourceResult(
            source=self.name,
            latency_ms=int((time.perf_counter() - start) * 1000),
            rows=len(txns),
            data=txns,
        )

    # --- Bulk fetchers (single IN-clause query per type) ---
    async def get_counters_bulk(self, counter_ids: list[str]) -> dict[str, Any]:
        if not counter_ids:
            return {}
        ph = ",".join(["?"] * len(counter_ids))
        sql = f"""
            SELECT c.*, h.pending_settlement, h.avg_daily_txns, h.digital_share, h.device_offline_minutes
            FROM {self._t('counters')} c
            LEFT JOIN {self._t('counter_health')} h ON h.counter_id = c.id
            WHERE c.id IN ({ph})
        """
        rows = await self._query(sql, tuple(counter_ids))
        return {r["id"]: Counter(**r).model_dump() for r in rows}

    async def get_transactions_bulk(self, counter_ids: list[str], months: int = 6) -> dict[str, list]:
        if not counter_ids:
            return {}
        ph = ",".join(["?"] * len(counter_ids))
        sql = f"""
            SELECT id, counter_id, ts, amount, category, channel, instrument
            FROM {self._t('transactions')}
            WHERE counter_id IN ({ph}) AND ts >= date_sub(current_timestamp(), {int(months * 30)})
            ORDER BY ts DESC
        """
        rows = await self._query(sql, tuple(counter_ids))
        out: dict[str, list] = {cid: [] for cid in counter_ids}
        for r in rows:
            out.setdefault(r["counter_id"], []).append(r)
        return out

    async def get_holdings_bulk(self, counter_ids: list[str]) -> dict[str, list]:
        if not counter_ids:
            return {}
        ph = ",".join(["?"] * len(counter_ids))
        sql = f"""
            SELECT cm.counter_id, cm.module_id, m.name, m.category, cm.status, cm.activated_at
            FROM {self._t('counter_modules')} cm JOIN {self._t('modules')} m ON m.id = cm.module_id
            WHERE cm.counter_id IN ({ph})
        """
        rows = await self._query(sql, tuple(counter_ids))
        out: dict[str, list] = {cid: [] for cid in counter_ids}
        for r in rows:
            out.setdefault(r["counter_id"], []).append(r)
        return out

    async def get_field_notes_bulk(self, counter_ids: list[str]) -> dict[str, list]:
        if not counter_ids:
            return {}
        ph = ",".join(["?"] * len(counter_ids))
        sql = f"""
            SELECT id, counter_id, ts, channel, summary
            FROM {self._t('field_notes')} WHERE counter_id IN ({ph}) ORDER BY ts DESC
        """
        rows = await self._query(sql, tuple(counter_ids))
        out: dict[str, list] = {cid: [] for cid in counter_ids}
        for r in rows:
            out.setdefault(r["counter_id"], []).append(r)
        return out

    async def get_modules(self) -> DataSourceResult:
        start = time.perf_counter()
        rows = await self._query(f"SELECT * FROM {self._t('modules')}")
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
        sql = f"""
            SELECT cm.module_id, m.name, m.category, cm.status, cm.activated_at
            FROM {self._t('counter_modules')} cm
            JOIN {self._t('modules')} m ON m.id = cm.module_id
            WHERE cm.counter_id = ?
        """
        rows = await self._query(sql, (counter_id,))
        return DataSourceResult(
            source=self.name,
            latency_ms=int((time.perf_counter() - start) * 1000),
            rows=len(rows),
            data=rows,
        )

    async def get_field_notes(self, counter_id: str | None = None) -> DataSourceResult:
        start = time.perf_counter()
        if counter_id:
            sql = f"SELECT id, counter_id, ts, channel, summary FROM {self._t('field_notes')} WHERE counter_id = ? ORDER BY ts DESC"
            rows = await self._query(sql, (counter_id,))
        else:
            sql = f"SELECT id, counter_id, ts, channel, summary FROM {self._t('field_notes')} ORDER BY ts DESC"
            rows = await self._query(sql)
        return DataSourceResult(
            source=self.name,
            latency_ms=int((time.perf_counter() - start) * 1000),
            rows=len(rows),
            data=rows,
        )

    async def health(self) -> bool:
        try:
            await self._query("SELECT 1")
            return True
        except Exception as e:  # noqa: BLE001
            logger.info("Databricks health check failed (will fail over): %s", e)
            return False

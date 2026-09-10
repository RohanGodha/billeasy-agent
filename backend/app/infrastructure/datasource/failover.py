"""FailoverSource — tries primary (Databricks), falls back to secondary (SQLite).

Every result still carries `source` so the trace panel shows which path served the call.
A failed primary call also marks a short-lived circuit-breaker so we don't retry every tool.
"""
from __future__ import annotations

import time
from typing import Any

from app.observability import get_logger

from .base import DataSource, DataSourceResult

logger = get_logger(__name__)


class FailoverSource(DataSource):
    name = "failover"

    def __init__(self, primary: DataSource, secondary: DataSource, breaker_seconds: int = 60) -> None:
        self.primary = primary
        self.secondary = secondary
        self.breaker_seconds = breaker_seconds
        self._breaker_open_until: float = 0.0

    def _breaker_open(self) -> bool:
        return time.time() < self._breaker_open_until

    def _trip(self) -> None:
        self._breaker_open_until = time.time() + self.breaker_seconds
        logger.warning("Primary DataSource breaker tripped for %ds.", self.breaker_seconds)

    async def _call(self, method: str, *args, **kwargs) -> DataSourceResult:
        if not self._breaker_open():
            try:
                fn = getattr(self.primary, method)
                return await fn(*args, **kwargs)
            except Exception as e:  # noqa: BLE001
                logger.info("Primary %s failed (%s) — failing over.", method, e.__class__.__name__)
                self._trip()
        fn = getattr(self.secondary, method)
        result: DataSourceResult = await fn(*args, **kwargs)
        # mark fallback source explicitly
        return result.model_copy(update={"source": f"{self.secondary.name}(failover)"})

    async def find_counters(self, filters: Any) -> DataSourceResult:
        return await self._call("find_counters", filters)

    async def get_counter(self, counter_id: str) -> DataSourceResult:
        return await self._call("get_counter", counter_id)

    async def get_transactions(self, counter_id: str, months: int = 6) -> DataSourceResult:
        return await self._call("get_transactions", counter_id, months)

    async def get_modules(self) -> DataSourceResult:
        return await self._call("get_modules")

    async def get_holdings(self, counter_id: str) -> DataSourceResult:
        return await self._call("get_holdings", counter_id)

    async def get_field_notes(self, counter_id: str | None = None) -> DataSourceResult:
        return await self._call("get_field_notes", counter_id)

    # --- Bulk fetchers delegate through the same breaker logic ---
    async def _call_bulk(self, method: str, *args, **kwargs):
        if not self._breaker_open() and hasattr(self.primary, method):
            try:
                return await getattr(self.primary, method)(*args, **kwargs)
            except Exception as e:  # noqa: BLE001
                logger.info("Primary %s failed (%s) — failing over.", method, e.__class__.__name__)
                self._trip()
        return await getattr(self.secondary, method)(*args, **kwargs)

    async def get_transactions_bulk(self, counter_ids, months: int = 6):
        return await self._call_bulk("get_transactions_bulk", counter_ids, months)

    async def get_holdings_bulk(self, counter_ids):
        return await self._call_bulk("get_holdings_bulk", counter_ids)

    async def get_field_notes_bulk(self, counter_ids):
        return await self._call_bulk("get_field_notes_bulk", counter_ids)

    async def get_counters_bulk(self, counter_ids):
        return await self._call_bulk("get_counters_bulk", counter_ids)

    async def health(self) -> bool:
        try:
            return await self.primary.health() or await self.secondary.health()
        except Exception:  # noqa: BLE001
            return await self.secondary.health()

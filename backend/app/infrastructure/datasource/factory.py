"""Wires the active DataSource based on settings."""
from __future__ import annotations

from functools import lru_cache

from app.observability import get_logger
from app.settings import get_settings

from .base import DataSource
from .failover import FailoverSource
from .sqlite import SQLiteSource

logger = get_logger(__name__)


@lru_cache(maxsize=1)
def get_datasource() -> DataSource:
    settings = get_settings()
    sqlite = SQLiteSource()
    if settings.databricks_enabled:
        try:
            from .databricks import DatabricksSource

            db = DatabricksSource()
            logger.info("DataSource: FailoverSource(databricks → sqlite)")
            return FailoverSource(primary=db, secondary=sqlite)
        except Exception as e:  # noqa: BLE001
            logger.warning("Databricks adapter could not be instantiated: %s. Using SQLite only.", e)
    logger.info("DataSource: SQLiteSource (Databricks not configured)")
    return sqlite

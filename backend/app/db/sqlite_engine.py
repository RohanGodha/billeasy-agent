"""SQLite engine helpers (sync + async).

We expose:
  - get_sync_conn()   — for seeders and one-off scripts
  - get_async_conn()  — for the FastAPI request lifecycle (aiosqlite)
  - bootstrap()       — applies schema.sql and seeds on first boot
"""
from __future__ import annotations

import sqlite3
from contextlib import asynccontextmanager, contextmanager
from pathlib import Path

import aiosqlite

from app.observability import get_logger
from app.settings import get_settings

logger = get_logger(__name__)

_SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def _apply_schema_sync(db_path: Path) -> None:
    sql = _SCHEMA_PATH.read_text(encoding="utf-8")
    with sqlite3.connect(db_path) as conn:
        conn.executescript(sql)
        conn.commit()


def _add_column(conn: sqlite3.Connection, table: str, ddl: str, column: str) -> None:
    """Idempotent column migration for DBs created before the column existed.

    `CREATE TABLE IF NOT EXISTS` only shapes fresh databases; an existing dev or prod
    DB keeps its old layout. ALTER is cheap here and guarded so it can never double-apply.
    """
    try:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
        conn.commit()
    except sqlite3.OperationalError as e:
        if "duplicate column" not in str(e).lower():
            raise


@contextmanager
def get_sync_conn():
    settings = get_settings()
    db_path = settings.sqlite_abs_path
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.execute("PRAGMA journal_mode = WAL;")
    try:
        yield conn
    finally:
        conn.close()


@asynccontextmanager
async def get_async_conn():
    settings = get_settings()
    db_path = settings.sqlite_abs_path
    conn = await aiosqlite.connect(db_path)
    conn.row_factory = aiosqlite.Row
    await conn.execute("PRAGMA foreign_keys = ON;")
    await conn.execute("PRAGMA journal_mode = WAL;")
    try:
        yield conn
    finally:
        await conn.close()


def bootstrap() -> None:
    """Idempotent: ensures DB exists, schema applied, seed loaded if empty."""
    settings = get_settings()
    db_path = settings.sqlite_abs_path
    is_new = not db_path.exists()
    _apply_schema_sync(db_path)
    with get_sync_conn() as conn:
        _add_column(conn, "agent_traces", "fallback_reason TEXT", "fallback_reason")
        _add_column(conn, "counters", "consent_ok INTEGER NOT NULL DEFAULT 1", "consent_ok")
        # Backfill hero consent on DBs seeded before the consent gate existed, so the
        # demo invariant holds everywhere: the leakage hero is opted out, the rest in.
        # Data-driven from hero_counters() — no hardcoded ids drifting out of sync.
        from app.db.seeders.hero_counters import hero_counters

        for h in hero_counters():
            conn.execute(
                "UPDATE counters SET consent_ok = ? WHERE id = ?",
                (1 if h.consent_ok else 0, h.id),
            )
        conn.commit()
    if is_new:
        logger.info("Fresh SQLite at %s — running seeder.", db_path)
    # Even on existing DB, check if counters is empty.
    with get_sync_conn() as conn:
        row = conn.execute("SELECT COUNT(*) AS c FROM counters").fetchone()
        if row["c"] == 0:
            logger.info("counters table is empty — seeding.")
            from app.db.seeders.faker_seed import run_seed

            run_seed(conn)
            conn.commit()
            logger.info("Seed complete.")
        else:
            logger.info("DB already populated (%d counters).", row["c"])

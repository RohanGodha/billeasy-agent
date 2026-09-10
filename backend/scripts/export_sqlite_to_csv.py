"""Export the SQLite seed to CSVs that the Databricks notebook can MERGE in.

Usage:  python -m scripts.export_sqlite_to_csv  [output_dir]

Defaults to `data/exports/`.
"""
from __future__ import annotations

import csv
import sqlite3
import sys
from pathlib import Path

from app.settings import get_settings

TABLES = [
    "counters", "counter_health", "transactions", "modules", "counter_modules", "field_notes",
]


def main(out_dir: str = "data/exports") -> int:
    settings = get_settings()
    out = Path(out_dir)
    if not out.is_absolute():
        out = Path(__file__).resolve().parent.parent / out
    out.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(settings.sqlite_abs_path) as conn:
        conn.row_factory = sqlite3.Row
        for t in TABLES:
            rows = list(conn.execute(f"SELECT * FROM {t}"))
            if not rows:
                print(f"  {t:20s} 0 rows (skipped)")
                continue
            cols = rows[0].keys()
            csv_path = out / f"{t}.csv"
            with csv_path.open("w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(cols)
                for r in rows:
                    w.writerow([r[c] for c in cols])
            print(f"  {t:20s} {len(rows):>6d} rows  →  {csv_path}")
    volume = f"/Volumes/{settings.databricks_catalog}/{settings.databricks_schema}/seed/"
    print(f"\nDone. Upload {out} to {volume} in Databricks.")
    return 0


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "data/exports"
    raise SystemExit(main(out))

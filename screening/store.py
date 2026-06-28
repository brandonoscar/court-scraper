"""SQLite store for the clean judgments table.

Why SQLite (and not Postgres) for this layer:
  * Scale is one county at a time -- thousands to low-millions of judgments,
    read-heavy, single analyst. SQLite handles that comfortably.
  * Zero ops: a single file, ships with Python, trivially diffable/portable,
    and easy to point a notebook or DB browser at when auditing a flag.
  * It matches the scraper's own choice (cases.db is SQLite), so nothing new
    to run. Move to Postgres only if you later need concurrent writers or a
    shared multi-user service -- nothing here needs that yet.
"""
from __future__ import annotations

import sqlite3
from typing import Iterable, List

from .models import JudgmentRecord

_COLUMNS = [
    "source_place_id", "case_number", "debtor_name", "debtor_names_all",
    "creditor_name", "judgment_amount", "judgment_date", "date_entered",
    "last_activity_date", "last_enforcement_date", "court", "jurisdiction_label",
    "case_type", "judgment_type", "raw_source", "is_synthetic",
]


class JudgmentStore:
    def __init__(self, path: str):
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self._create()

    def _create(self) -> None:
        cols = ",\n            ".join(f"{c} TEXT" for c in _COLUMNS)
        self.conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS judgments (
            id INTEGER PRIMARY KEY,
            {cols},
            UNIQUE(source_place_id, case_number)
            )
            """
        )
        self.conn.commit()

    def upsert(self, records: Iterable[JudgmentRecord]) -> int:
        n = 0
        for rec in records:
            row = rec.to_row()
            placeholders = ", ".join("?" for _ in _COLUMNS)
            updates = ", ".join(f"{c}=excluded.{c}" for c in _COLUMNS
                                if c not in ("source_place_id", "case_number"))
            self.conn.execute(
                f"""
                INSERT INTO judgments ({", ".join(_COLUMNS)})
                VALUES ({placeholders})
                ON CONFLICT(source_place_id, case_number)
                DO UPDATE SET {updates}
                """,
                [row.get(c) for c in _COLUMNS],
            )
            n += 1
        self.conn.commit()
        return n

    def all_rows(self) -> List[sqlite3.Row]:
        return list(self.conn.execute("SELECT * FROM judgments"))

    def close(self) -> None:
        self.conn.close()

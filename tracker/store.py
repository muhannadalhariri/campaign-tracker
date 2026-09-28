"""SQLite persistence for investigations (seed, parameters and analyst decisions).

Collected posts are not stored: they are re-fetched from the connector when an
investigation is reopened, so the database holds only the analyst's work.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS investigations (
    name        TEXT PRIMARY KEY,
    state_json  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);
"""


class Store:
    def __init__(self, path: str | Path = "tracker.db"):
        self.conn = sqlite3.connect(str(path), check_same_thread=False)
        self.conn.execute(SCHEMA)
        self.conn.commit()

    def save(self, name: str, state: dict) -> None:
        self.conn.execute(
            "INSERT INTO investigations(name, state_json, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(name) DO UPDATE SET state_json=excluded.state_json, "
            "updated_at=excluded.updated_at",
            (name, json.dumps(state, ensure_ascii=False),
             datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        self.conn.commit()

    def load(self, name: str) -> dict | None:
        row = self.conn.execute(
            "SELECT state_json FROM investigations WHERE name = ?", (name,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def list(self) -> list[tuple[str, str]]:
        return self.conn.execute(
            "SELECT name, updated_at FROM investigations ORDER BY updated_at DESC"
        ).fetchall()

    def delete(self, name: str) -> None:
        self.conn.execute("DELETE FROM investigations WHERE name = ?", (name,))
        self.conn.commit()

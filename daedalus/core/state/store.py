"""Persistence ports.

`StateStore` is the port. `SQLiteStateStore` is the reference adapter used by the
runtime and tests. PostgreSQL / Redis adapters implement the same protocol (see
docs/architecture/persistence.md) and are not required to run the system.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Protocol


class StateStore(Protocol):
    def save_snapshot(self, run_id: str, tick: int, snapshot: dict[str, Any]) -> None: ...
    def load_snapshot(self, run_id: str) -> dict[str, Any] | None: ...
    def append_events(self, run_id: str, events: list[dict[str, Any]]) -> None: ...
    def list_runs(self) -> list[dict[str, Any]]: ...


class SQLiteStateStore:
    def __init__(self, path: str | Path = "daedalus.db") -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
                run_id TEXT NOT NULL, tick INTEGER NOT NULL, created REAL NOT NULL,
                body TEXT NOT NULL, PRIMARY KEY (run_id, tick));
            CREATE TABLE IF NOT EXISTS events (
                run_id TEXT NOT NULL, tick INTEGER NOT NULL, type TEXT NOT NULL,
                body TEXT NOT NULL);
            CREATE INDEX IF NOT EXISTS events_run_tick ON events(run_id, tick);
            """
        )

    def save_snapshot(self, run_id: str, tick: int, snapshot: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO snapshots VALUES (?,?,?,?)",
            (run_id, tick, time.time(), json.dumps(snapshot)),
        )
        self._conn.commit()

    def load_snapshot(self, run_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT body FROM snapshots WHERE run_id=? ORDER BY tick DESC LIMIT 1", (run_id,)
        ).fetchone()
        return json.loads(row[0]) if row else None

    def append_events(self, run_id: str, events: list[dict[str, Any]]) -> None:
        self._conn.executemany(
            "INSERT INTO events VALUES (?,?,?,?)",
            [(run_id, e["tick"], e["type"], json.dumps(e)) for e in events],
        )
        self._conn.commit()

    def list_runs(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT run_id, MAX(tick), MAX(created) FROM snapshots GROUP BY run_id"
        ).fetchall()
        return [{"run_id": r[0], "tick": r[1], "saved_at": r[2]} for r in rows]

    def close(self) -> None:
        self._conn.close()

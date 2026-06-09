"""Persist sessions and events to SQLite."""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id           TEXT PRIMARY KEY,
    participant  TEXT NOT NULL,
    notes        TEXT NOT NULL DEFAULT '',
    started_at   TEXT NOT NULL,
    ended_at     TEXT,
    xdf_path     TEXT,
    status       TEXT NOT NULL DEFAULT 'running'
);

CREATE TABLE IF NOT EXISTS events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT NOT NULL REFERENCES sessions(id),
    event_type   TEXT NOT NULL,
    source       TEXT NOT NULL DEFAULT '',
    payload      TEXT NOT NULL DEFAULT '{}',
    occurred_at  TEXT NOT NULL
);
"""


class SqliteStore:
    """Thread-safe SQLite persistence for recording sessions and events."""

    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def create_session(self, participant: str, notes: str = "") -> str:
        sid = str(uuid.uuid4())
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            "INSERT INTO sessions (id, participant, notes, started_at) VALUES (?,?,?,?)",
            (sid, participant, notes, now),
        )
        self._conn.commit()
        return sid

    def end_session(self, session_id: str, xdf_path: str | None = None) -> None:
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            "UPDATE sessions SET ended_at=?, xdf_path=?, status='done' WHERE id=?",
            (now, xdf_path, session_id),
        )
        self._conn.commit()

    def record_event(
        self,
        session_id: str,
        event_type: str,
        source: str,
        payload: dict[str, Any],
    ) -> None:
        now = datetime.now(UTC).isoformat()
        self._conn.execute(
            "INSERT INTO events (session_id, event_type, source, payload, occurred_at)"
            " VALUES (?,?,?,?,?)",
            (session_id, event_type, source, json.dumps(payload), now),
        )
        self._conn.commit()

    def list_sessions(self) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            """
            SELECT s.*, COUNT(e.id) AS event_count
            FROM sessions s
            LEFT JOIN events e ON e.session_id = s.id
            GROUP BY s.id
            ORDER BY s.started_at DESC
            """
        ).fetchall()
        return [dict(r) for r in rows]

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT * FROM sessions WHERE id=?", (session_id,)
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        events = self._conn.execute(
            "SELECT * FROM events WHERE session_id=? ORDER BY occurred_at ASC",
            (session_id,),
        ).fetchall()
        result["events"] = [dict(e) for e in events]
        return result

    def close(self) -> None:
        self._conn.close()

"""SQLite cache, credit ledger, and saved reports."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from app.boot import note

SCHEMA = """
CREATE TABLE IF NOT EXISTS serp_cache (
    cache_key TEXT PRIMARY KEY,
    engine TEXT NOT NULL,
    params_json TEXT NOT NULL,
    response_json TEXT NOT NULL,
    search_id TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS serp_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    engine TEXT,
    cache_key TEXT,
    source TEXT NOT NULL,
    report_id TEXT
);
CREATE TABLE IF NOT EXISTS reports (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    keyword TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
"""


def connect(path: Path, bucket: list[str] | None = None) -> sqlite3.Connection:
    """Open SQLite. Falls back to /tmp, then a shared in-memory database. Never raises."""
    try:
        return _open(path)
    except Exception as exc:
        note("db:configured", exc, bucket)
    tmp = Path("/tmp") / "bazaar-radar" / (path.name or "bazaar.sqlite")
    try:
        same = path.resolve() == tmp.resolve()
    except OSError:
        same = False
    if not same:
        try:
            conn = _open(tmp)
            note("db:tmp", bucket=bucket)
            return conn
        except Exception as exc:
            note("db:tmp", exc, bucket)
    note("db:memory", bucket=bucket)
    return memory_connection()


def memory_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(
        "file:bazaar-radar?mode=memory&cache=shared",
        uri=True,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    return conn


def _open(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    probe = path.parent / f".write-{path.name}"
    probe.write_text("", encoding="utf-8")
    try:
        probe.unlink()
    except OSError:
        pass
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()

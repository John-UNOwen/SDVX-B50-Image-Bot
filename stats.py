"""Query statistics recorder (SQLite).

Records every command invocation: command type (b50 / link / unlink), the
mode for /b50 (nabla / exceed), the invoking Discord user, the target Tachi
username and a timestamp. The database file is ``stats.db`` next to this
module and is gitignored.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stats.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS queries (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id    TEXT,
            command    TEXT NOT NULL,
            mode       TEXT,
            status     TEXT,
            target     TEXT,
            created_at INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def record(
    command: str,
    user_id: str | None = None,
    mode: str | None = None,
    status: str | None = None,
    target: str | None = None,
) -> None:
    """Insert one query record (fire-and-forget; never raises)."""
    try:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO queries (user_id, command, mode, status, target, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, command, mode, status, target, int(time.time())),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("stats: could not record %s: %s", command, exc)
        return
    logger.info(
        "stats: %s%s%s",
        command,
        f" (mode={mode})" if mode else "",
        f" target={target}" if target else "",
    )


def summary() -> dict:
    """Return total / last-24h counts and per-(command, mode) breakdown."""
    conn = _connect()
    try:
        total = conn.execute("SELECT COUNT(*) FROM queries").fetchone()[0]
        today = conn.execute(
            "SELECT COUNT(*) FROM queries WHERE created_at >= ?",
            (int(time.time()) - 86400,),
        ).fetchone()[0]
        by_type = conn.execute(
            "SELECT command, mode, COUNT(*) FROM queries GROUP BY command, mode ORDER BY 3 DESC"
        ).fetchall()
        return {"total": total, "today": today, "by_type": by_type}
    finally:
        conn.close()

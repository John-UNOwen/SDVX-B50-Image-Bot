"""Persistent Discord-user <-> Tachi-username link storage (SQLite).

The database file is ``links.db`` next to this module and is gitignored.
"""

from __future__ import annotations

import logging
import os
import sqlite3
import time

logger = logging.getLogger(__name__)

_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "links.db")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS links (
            user_id        TEXT PRIMARY KEY,
            tachi_username TEXT NOT NULL,
            created_at     INTEGER NOT NULL
        )
        """
    )
    conn.commit()
    return conn


def set_link(user_id: str, tachi_username: str) -> bool:
    """Store (or overwrite) the link; returns True on success, False on error."""
    try:
        conn = _connect()
        try:
            conn.execute(
                "INSERT INTO links (user_id, tachi_username, created_at) VALUES (?, ?, ?) "
                "ON CONFLICT(user_id) DO UPDATE SET "
                "tachi_username = excluded.tachi_username, created_at = excluded.created_at",
                (user_id, tachi_username, int(time.time())),
            )
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Link set failed for user %s: %s", user_id, exc)
        return False
    logger.info("Link set: user %s -> %s", user_id, tachi_username)
    return True


def get_link(user_id: str) -> str | None:
    """Return the linked Tachi username, or None. Never raises."""
    result = None
    try:
        conn = _connect()
        try:
            row = conn.execute(
                "SELECT tachi_username FROM links WHERE user_id = ?", (user_id,)
            ).fetchone()
            result = row[0] if row else None
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Link lookup failed for user %s: %s", user_id, exc)
        return None
    logger.debug("Link lookup: %s -> %s", user_id, result)
    return result


def unlink(user_id: str) -> bool | None:
    """Remove the link.

    Returns True if a link existed and was removed, False if there was no link
    to remove, or None when the store could not be read (storage error).
    """
    removed: bool | None = None
    try:
        conn = _connect()
        try:
            cur = conn.execute("DELETE FROM links WHERE user_id = ?", (user_id,))
            conn.commit()
            removed = cur.rowcount > 0
        finally:
            conn.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("Unlink failed for user %s: %s", user_id, exc)
        return None
    logger.info("Link unlinked: user %s (existed=%s)", user_id, removed)
    return removed

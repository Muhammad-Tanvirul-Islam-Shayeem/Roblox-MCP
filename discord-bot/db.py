import asyncio
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).parent / "moderation.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS warnings (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id     INTEGER NOT NULL,
    user_id      INTEGER NOT NULL,
    moderator_id INTEGER NOT NULL,
    reason       TEXT    NOT NULL,
    created_at   INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_warnings_user ON warnings (guild_id, user_id);

CREATE TABLE IF NOT EXISTS guild_settings (
    guild_id       INTEGER PRIMARY KEY,
    log_channel_id INTEGER
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init() -> None:
    with _connect() as conn:
        conn.executescript(SCHEMA)


def _add_warning(guild_id: int, user_id: int, moderator_id: int, reason: str) -> int:
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO warnings (guild_id, user_id, moderator_id, reason, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (guild_id, user_id, moderator_id, reason, int(time.time())),
        )
        return cur.lastrowid


def _get_warnings(guild_id: int, user_id: int) -> list[sqlite3.Row]:
    with _connect() as conn:
        return conn.execute(
            "SELECT * FROM warnings WHERE guild_id = ? AND user_id = ? ORDER BY id",
            (guild_id, user_id),
        ).fetchall()


def _clear_warnings(guild_id: int, user_id: int) -> int:
    with _connect() as conn:
        return conn.execute(
            "DELETE FROM warnings WHERE guild_id = ? AND user_id = ?",
            (guild_id, user_id),
        ).rowcount


def _set_log_channel(guild_id: int, channel_id: int) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO guild_settings (guild_id, log_channel_id) VALUES (?, ?) "
            "ON CONFLICT(guild_id) DO UPDATE SET log_channel_id = excluded.log_channel_id",
            (guild_id, channel_id),
        )


def _get_log_channel(guild_id: int) -> int | None:
    with _connect() as conn:
        row = conn.execute(
            "SELECT log_channel_id FROM guild_settings WHERE guild_id = ?", (guild_id,)
        ).fetchone()
        return row["log_channel_id"] if row else None


# sqlite3 is blocking, so every call is pushed onto a worker thread.
async def init() -> None:
    await asyncio.to_thread(_init)


async def add_warning(guild_id: int, user_id: int, moderator_id: int, reason: str) -> int:
    return await asyncio.to_thread(_add_warning, guild_id, user_id, moderator_id, reason)


async def get_warnings(guild_id: int, user_id: int) -> list[sqlite3.Row]:
    return await asyncio.to_thread(_get_warnings, guild_id, user_id)


async def clear_warnings(guild_id: int, user_id: int) -> int:
    return await asyncio.to_thread(_clear_warnings, guild_id, user_id)


async def set_log_channel(guild_id: int, channel_id: int) -> None:
    await asyncio.to_thread(_set_log_channel, guild_id, channel_id)


async def get_log_channel(guild_id: int) -> int | None:
    return await asyncio.to_thread(_get_log_channel, guild_id)

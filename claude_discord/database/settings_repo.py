"""Key-value settings repository for bot configuration."""

from __future__ import annotations

import logging

import aiosqlite

logger = logging.getLogger(__name__)


class SettingsRepository:
    """Simple key-value store for bot settings, persisted in SQLite."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    async def get(self, key: str, *, default: str | None = None) -> str | None:
        """Get a setting value by key. Returns default if not found."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute(
                "SELECT value FROM settings WHERE key = ?",
                (key,),
            )
            row = await cursor.fetchone()
            return row[0] if row else default

    async def set(self, key: str, value: str) -> None:
        """Set a setting value. Creates or overwrites."""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            await db.commit()

    async def delete(self, key: str) -> bool:
        """Delete a setting. Returns True if a row was deleted."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("DELETE FROM settings WHERE key = ?", (key,))
            await db.commit()
            return cursor.rowcount > 0

    async def get_all(self) -> dict[str, str]:
        """Get all settings as a dict."""
        async with aiosqlite.connect(self.db_path) as db:
            cursor = await db.execute("SELECT key, value FROM settings ORDER BY key")
            rows = await cursor.fetchall()
            return {row[0]: row[1] for row in rows}

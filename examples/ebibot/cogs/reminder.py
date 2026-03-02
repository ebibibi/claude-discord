"""/remind slash command & 30-second notification send loop.

Self-contained custom Cog: includes DB schema, repository, embed builders,
and the ReminderCog itself.  No external dependencies beyond discord.py.

Usage:
    CUSTOM_COGS_DIR=examples/ebibot/cogs ccdb start
"""

from __future__ import annotations

import logging
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands, tasks

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS scheduled_notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    message TEXT NOT NULL,
    title TEXT,
    color INTEGER DEFAULT 49151,
    scheduled_at TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT 'api',
    channel_id INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    sent_at TEXT,
    error_message TEXT,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE INDEX IF NOT EXISTS idx_notif_status_scheduled
    ON scheduled_notifications(status, scheduled_at);
"""


class _Database:
    """Minimal synchronous SQLite wrapper for notifications."""

    def __init__(self, db_path: str = "data/bot.db") -> None:
        self.db_path = db_path
        self._connection: sqlite3.Connection | None = None

    def connect(self) -> sqlite3.Connection:
        if self._connection is not None:
            return self._connection
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        return self._connection

    def initialize(self) -> None:
        conn = self.connect()
        conn.executescript(_SCHEMA)
        conn.commit()

    def close(self) -> None:
        if self._connection:
            self._connection.close()
            self._connection = None

    @property
    def connection(self) -> sqlite3.Connection:
        return self.connect()


class _NotificationRepository:
    """CRUD for scheduled_notifications table."""

    def __init__(self, db: _Database) -> None:
        self.db = db

    def create(
        self,
        message: str,
        scheduled_at: str,
        *,
        title: str | None = None,
        color: int = 0x00BFFF,
        source: str = "api",
        channel_id: int | None = None,
    ) -> int:
        conn = self.db.connection
        cursor = conn.execute(
            """
            INSERT INTO scheduled_notifications
                (message, title, color, scheduled_at, source, channel_id)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (message, title, color, scheduled_at, source, channel_id),
        )
        conn.commit()
        return cursor.lastrowid  # type: ignore[return-value]

    def get_pending(self, before: str | None = None) -> list[dict]:
        conn = self.db.connection
        if before:
            rows = conn.execute(
                """
                SELECT * FROM scheduled_notifications
                WHERE status = 'pending' AND scheduled_at <= ?
                ORDER BY scheduled_at
                """,
                (before,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT * FROM scheduled_notifications
                WHERE status = 'pending'
                ORDER BY scheduled_at
                """,
            ).fetchall()
        return [dict(row) for row in rows]

    def mark_sent(self, notification_id: int) -> None:
        conn = self.db.connection
        conn.execute(
            """
            UPDATE scheduled_notifications
            SET status = 'sent', sent_at = datetime('now', 'localtime')
            WHERE id = ?
            """,
            (notification_id,),
        )
        conn.commit()

    def mark_failed(self, notification_id: int, error: str) -> None:
        conn = self.db.connection
        conn.execute(
            """
            UPDATE scheduled_notifications
            SET status = 'failed', error_message = ?
            WHERE id = ?
            """,
            (error, notification_id),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Embeds
# ---------------------------------------------------------------------------

_COLOR_REMINDER = 0x00BFFF
_COLOR_SUCCESS = 0x00FF00


def _build_reminder_embed(message: str, title: str | None = None) -> discord.Embed:
    embed = discord.Embed(
        title=title or "\u23f0 Remind!",
        description=message,
        color=_COLOR_REMINDER,
        timestamp=datetime.now(),
    )
    embed.set_footer(text="EbiBot Reminder")
    return embed


def _build_schedule_confirm_embed(message: str, scheduled_at: str) -> discord.Embed:
    embed = discord.Embed(
        title="\u2705 Reminder scheduled!",
        description=f"**{scheduled_at}** — notification set.\n\n> {message}",
        color=_COLOR_SUCCESS,
        timestamp=datetime.now(),
    )
    embed.set_footer(text="EbiBot Reminder")
    return embed


# ---------------------------------------------------------------------------
# Cog
# ---------------------------------------------------------------------------


class ReminderCog(commands.Cog):
    """Reminder: /remind slash command + periodic send loop."""

    def __init__(self, bot: commands.Bot, repo: _NotificationRepository) -> None:
        self.bot = bot
        self.repo = repo

    async def cog_load(self) -> None:
        self.check_scheduled.start()
        logger.info("ReminderCog loaded, check loop started")

    async def cog_unload(self) -> None:
        self.check_scheduled.cancel()

    @app_commands.command(
        name="remind",
        description="Set a reminder at a specific time!",
    )
    @app_commands.describe(
        time="Time in HH:MM format",
        message="Reminder message",
    )
    async def remind(
        self,
        interaction: discord.Interaction,
        time: str,
        message: str,
    ) -> None:
        match = re.match(r"^(\d{1,2}):(\d{2})$", time.strip())
        if not match:
            await interaction.response.send_message(
                "Please use HH:MM format (e.g. 14:30)",
                ephemeral=True,
            )
            return

        hour, minute = int(match.group(1)), int(match.group(2))
        if not (0 <= hour <= 23 and 0 <= minute <= 59):
            await interaction.response.send_message(
                "Time out of range! Use 00:00-23:59.",
                ephemeral=True,
            )
            return

        now = datetime.now()
        scheduled = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if scheduled <= now:
            scheduled += timedelta(days=1)

        scheduled_str = scheduled.strftime("%Y-%m-%dT%H:%M:%S")

        self.repo.create(
            message=message,
            scheduled_at=scheduled_str,
            source="slash_command",
            channel_id=interaction.channel_id,
        )

        embed = _build_schedule_confirm_embed(
            message=message,
            scheduled_at=scheduled.strftime("%m/%d %H:%M"),
        )
        await interaction.response.send_message(embed=embed)

    @tasks.loop(seconds=30)
    async def check_scheduled(self) -> None:
        """Check pending notifications every 30 seconds and send them."""
        now_str = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        pending = self.repo.get_pending(before=now_str)

        for notif in pending:
            try:
                channel_id = notif.get("channel_id") or getattr(
                    self.bot, "default_channel_id", None
                )
                if not channel_id:
                    logger.warning("No channel ID for notification %d", notif["id"])
                    self.repo.mark_failed(notif["id"], "No channel ID")
                    continue

                channel = self.bot.get_channel(int(channel_id))
                if not channel:
                    channel = await self.bot.fetch_channel(int(channel_id))

                embed = _build_reminder_embed(
                    message=notif["message"],
                    title=notif.get("title"),
                )
                if notif.get("color"):
                    embed.color = notif["color"]

                await channel.send(embed=embed)
                self.repo.mark_sent(notif["id"])
                logger.info("Notification sent: id=%d", notif["id"])

            except Exception as e:
                logger.error("Failed to send notification %d: %s", notif["id"], e)
                self.repo.mark_failed(notif["id"], str(e))

    @check_scheduled.before_loop
    async def before_check_scheduled(self) -> None:
        await self.bot.wait_until_ready()


# ---------------------------------------------------------------------------
# setup() — called by load_custom_cogs
# ---------------------------------------------------------------------------


async def setup(bot: commands.Bot, runner: object, components: object) -> None:
    """Entry point for the custom Cog loader."""
    db = _Database(db_path="data/bot.db")
    db.initialize()
    repo = _NotificationRepository(db)
    await bot.add_cog(ReminderCog(bot, repo))

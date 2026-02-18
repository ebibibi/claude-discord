"""REST API server for Discord bot push notifications.

Optional extension — requires aiohttp. Install with:
    pip install claude-code-discord-bridge[api]

Provides endpoints for sending immediate and scheduled notifications
to Discord channels via the bot.

Security:
- Binds to 127.0.0.1 by default (localhost only)
- Optional Bearer token authentication via api_secret
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING

from aiohttp import web

if TYPE_CHECKING:
    import discord
    from discord.ext.commands import Bot

    from ..database.notification_repo import NotificationRepository

logger = logging.getLogger(__name__)


class ApiServer:
    """Embedded REST API server for Discord bot notifications.

    Usage::

        from claude_discord.database.notification_repo import NotificationRepository
        from claude_discord.ext.api_server import ApiServer

        repo = NotificationRepository("data/notifications.db")
        await repo.init_db()
        api = ApiServer(repo=repo, bot=bot, default_channel_id=12345)
        await api.start()
        # ... bot runs ...
        await api.stop()
    """

    def __init__(
        self,
        repo: NotificationRepository,
        bot: Bot,
        default_channel_id: int | None = None,
        host: str = "127.0.0.1",
        port: int = 8080,
        api_secret: str | None = None,
    ) -> None:
        self.repo = repo
        self.bot = bot
        self.default_channel_id = default_channel_id
        self.host = host
        self.port = port
        self.api_secret = api_secret

        self.app = web.Application()
        if self.api_secret:
            self.app.middlewares.append(self._auth_middleware)
        self._setup_routes()
        self._runner: web.AppRunner | None = None

    def _setup_routes(self) -> None:
        self.app.router.add_get("/api/health", self.health)
        self.app.router.add_post("/api/notify", self.notify)
        self.app.router.add_post("/api/schedule", self.schedule)
        self.app.router.add_get("/api/scheduled", self.list_scheduled)
        self.app.router.add_delete("/api/scheduled/{id}", self.cancel_scheduled)

    @web.middleware
    async def _auth_middleware(
        self,
        request: web.Request,
        handler: web.RequestHandler,
    ) -> web.StreamResponse:
        """Bearer token authentication middleware."""
        if request.path == "/api/health":
            return await handler(request)

        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return web.json_response({"error": "Missing Authorization header"}, status=401)

        token = auth_header[7:]
        if token != self.api_secret:
            return web.json_response({"error": "Invalid token"}, status=401)

        return await handler(request)

    async def start(self) -> None:
        """Start the API server."""
        self._runner = web.AppRunner(self.app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        logger.info("REST API started: http://%s:%d", self.host, self.port)

    async def stop(self) -> None:
        """Stop the API server."""
        if self._runner:
            await self._runner.cleanup()

    async def health(self, request: web.Request) -> web.Response:
        """GET /api/health — health check."""
        return web.json_response(
            {
                "status": "ok",
                "timestamp": datetime.now().isoformat(),
            }
        )

    async def notify(self, request: web.Request) -> web.Response:
        """POST /api/notify — send an immediate notification."""
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        message = data.get("message")
        if not message:
            return web.json_response({"error": "message is required"}, status=400)

        channel_id = data.get("channel_id") or self.default_channel_id
        if not channel_id:
            return web.json_response({"error": "No channel specified"}, status=400)

        channel = self.bot.get_channel(channel_id)
        if not channel:
            try:
                channel = await self.bot.fetch_channel(channel_id)
            except Exception as e:
                return web.json_response({"error": str(e)}, status=500)

        title = data.get("title")
        embed = self._build_embed(message=message, title=title, color=data.get("color"))
        await channel.send(embed=embed)

        return web.json_response({"status": "sent"})

    async def schedule(self, request: web.Request) -> web.Response:
        """POST /api/schedule — schedule a notification for later."""
        try:
            data = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        message = data.get("message")
        scheduled_at = data.get("scheduled_at")

        if not message:
            return web.json_response({"error": "message is required"}, status=400)
        if not scheduled_at:
            return web.json_response({"error": "scheduled_at is required"}, status=400)

        try:
            dt = datetime.fromisoformat(scheduled_at)
            scheduled_str = dt.strftime("%Y-%m-%dT%H:%M:%S")
        except ValueError:
            return web.json_response(
                {"error": "scheduled_at must be ISO 8601 format"},
                status=400,
            )

        notification_id = await self.repo.create(
            message=message,
            scheduled_at=scheduled_str,
            title=data.get("title"),
            color=data.get("color", 0x00BFFF),
            source="api",
            channel_id=data.get("channel_id"),
        )

        return web.json_response({"status": "scheduled", "id": notification_id})

    async def list_scheduled(self, request: web.Request) -> web.Response:
        """GET /api/scheduled — list pending notifications."""
        pending = await self.repo.get_pending()
        return web.json_response({"notifications": pending})

    async def cancel_scheduled(self, request: web.Request) -> web.Response:
        """DELETE /api/scheduled/{id} — cancel a pending notification."""
        try:
            notification_id = int(request.match_info["id"])
        except (ValueError, KeyError):
            return web.json_response({"error": "Invalid ID"}, status=400)

        success = await self.repo.cancel(notification_id)
        if success:
            return web.json_response({"status": "cancelled"})
        return web.json_response(
            {"error": "Not found or already processed"},
            status=404,
        )

    @staticmethod
    def _build_embed(
        message: str,
        title: str | None = None,
        color: int | None = None,
    ) -> discord.Embed:
        """Build a Discord embed for notification display."""
        import discord

        return discord.Embed(
            title=title or "Notification",
            description=message,
            color=color or 0x00BFFF,
            timestamp=datetime.now(),
        )

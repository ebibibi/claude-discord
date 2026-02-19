"""Tests for /sync-settings command and thread style switching."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import discord

from claude_discord.database.repository import SessionRecord


def _make_record(
    thread_id: int = 100,
    session_id: str = "abc-123",
    origin: str = "cli",
    summary: str | None = "Test session",
) -> SessionRecord:
    return SessionRecord(
        thread_id=thread_id,
        session_id=session_id,
        working_dir="/home/user",
        model="sonnet",
        origin=origin,
        summary=summary,
        created_at="2026-02-19 10:00:00",
        last_used_at="2026-02-19 11:00:00",
    )


def _make_interaction() -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.channel = MagicMock(spec=discord.TextChannel)
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


def _make_cog(
    cli_sessions_path: str | None = None,
    channel_id: int = 999,
):
    from claude_discord.cogs.session_manage import SessionManageCog

    bot = MagicMock()
    bot.channel_id = channel_id
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    thread = MagicMock(spec=discord.Thread)
    thread.id = 50000
    thread.send = AsyncMock()
    # For message-based threads: channel.send() returns msg, msg.create_thread()
    summary_msg = MagicMock()
    summary_msg.create_thread = AsyncMock(return_value=thread)
    channel.send = AsyncMock(return_value=summary_msg)
    # For channel-based threads: channel.create_thread()
    channel.create_thread = AsyncMock(return_value=thread)
    bot.get_channel = MagicMock(return_value=channel)

    repo = MagicMock()
    repo.get = AsyncMock(return_value=None)
    repo.save = AsyncMock(return_value=_make_record())
    repo.list_all = AsyncMock(return_value=[])
    repo.get_by_session_id = AsyncMock(return_value=None)

    settings_repo = MagicMock()
    settings_repo.get = AsyncMock(return_value=None)
    settings_repo.set = AsyncMock()

    return SessionManageCog(
        bot=bot,
        repo=repo,
        cli_sessions_path=cli_sessions_path,
        settings_repo=settings_repo,
    )


class TestSyncSettings:
    """Test /sync-settings command."""

    async def test_shows_current_style_default_channel(self):
        """When no setting is stored, shows 'channel' as current."""
        cog = _make_cog()
        cog.settings_repo.get = AsyncMock(return_value=None)
        interaction = _make_interaction()
        await cog.sync_settings.callback(cog, interaction)
        call_args = interaction.response.send_message.call_args
        embed = call_args.kwargs.get("embed")
        assert embed is not None
        assert "channel" in embed.description.lower()

    async def test_shows_current_style_message(self):
        """When setting is 'message', shows it."""
        cog = _make_cog()
        cog.settings_repo.get = AsyncMock(return_value="message")
        interaction = _make_interaction()
        await cog.sync_settings.callback(cog, interaction)
        call_args = interaction.response.send_message.call_args
        embed = call_args.kwargs.get("embed")
        assert embed is not None
        assert "message" in embed.description.lower()


class TestSyncThreadStyleChannel:
    """Test that sync_sessions uses channel threads when style is 'channel'."""

    async def test_channel_style_uses_create_thread(self, tmp_path):
        """With channel style, should use channel.create_thread() directly."""
        import json

        session_id = "aaa11111-1234-5678-9abc-def012345678"
        jsonl_path = tmp_path / f"{session_id}.jsonl"
        with open(jsonl_path, "w") as f:
            f.write(
                json.dumps(
                    {
                        "type": "user",
                        "isMeta": False,
                        "sessionId": session_id,
                        "cwd": "/home/user/project",
                        "timestamp": "2026-02-19T10:00:00.000Z",
                        "message": {"role": "user", "content": "Build the API"},
                    }
                )
                + "\n"
            )

        cog = _make_cog(cli_sessions_path=str(tmp_path))
        # Default style = channel
        cog.settings_repo.get = AsyncMock(return_value=None)
        interaction = _make_interaction()
        await cog.sync_sessions.callback(cog, interaction)

        channel = cog.bot.get_channel(999)
        # Channel style: should call channel.create_thread, NOT channel.send
        channel.create_thread.assert_called_once()
        # channel.send should NOT be called for the summary message
        # (it's only used in message style)
        channel.send.assert_not_called()

    async def test_message_style_uses_msg_create_thread(self, tmp_path):
        """With message style, should post embed then create thread from it."""
        import json

        session_id = "bbb22222-1234-5678-9abc-def012345678"
        jsonl_path = tmp_path / f"{session_id}.jsonl"
        with open(jsonl_path, "w") as f:
            f.write(
                json.dumps(
                    {
                        "type": "user",
                        "isMeta": False,
                        "sessionId": session_id,
                        "cwd": "/home/user/project",
                        "timestamp": "2026-02-19T10:00:00.000Z",
                        "message": {"role": "user", "content": "Fix bug"},
                    }
                )
                + "\n"
            )

        cog = _make_cog(cli_sessions_path=str(tmp_path))
        cog.settings_repo.get = AsyncMock(return_value="message")
        interaction = _make_interaction()
        await cog.sync_sessions.callback(cog, interaction)

        channel = cog.bot.get_channel(999)
        # Message style: should call channel.send (embed), then msg.create_thread
        channel.send.assert_called_once()
        summary_msg = channel.send.return_value
        summary_msg.create_thread.assert_called_once()
        # channel.create_thread should NOT be called directly
        channel.create_thread.assert_not_called()

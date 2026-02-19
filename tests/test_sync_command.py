"""Tests for /sync-sessions command and background sync task."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from claude_discord.database.models import init_db
from claude_discord.database.repository import SessionRecord, SessionRepository


@pytest.fixture
async def repo(tmp_path):
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)
    return SessionRepository(db_path)


def _make_channel_interaction() -> MagicMock:
    interaction = MagicMock(spec=discord.Interaction)
    interaction.channel = MagicMock(spec=discord.TextChannel)
    interaction.response = MagicMock()
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    return interaction


def _make_record(
    thread_id: int = 100,
    session_id: str = "abc-123",
    origin: str = "discord",
    summary: str | None = "Fix login bug",
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


def _make_cog(
    cli_sessions_path: str | None = None,
    channel_id: int = 999,
):
    from claude_discord.cogs.session_manage import SessionManageCog

    bot = MagicMock()
    bot.channel_id = channel_id
    # Mock get_channel to return an async-capable channel
    channel = MagicMock(spec=discord.TextChannel)
    channel.id = channel_id
    thread = MagicMock(spec=discord.Thread)
    thread.id = 50000
    thread.send = AsyncMock()
    channel.create_thread = AsyncMock(return_value=thread)
    bot.get_channel = MagicMock(return_value=channel)
    repo = MagicMock()
    repo.get = AsyncMock(return_value=None)
    repo.save = AsyncMock(return_value=_make_record())
    repo.list_all = AsyncMock(return_value=[])
    repo.get_by_session_id = AsyncMock(return_value=None)
    return SessionManageCog(bot=bot, repo=repo, cli_sessions_path=cli_sessions_path)


class TestSyncSessions:
    """Test /sync-sessions command."""

    async def test_sync_no_path_configured(self):
        cog = _make_cog(cli_sessions_path=None)
        interaction = _make_channel_interaction()
        await cog.sync_sessions.callback(cog, interaction)
        call_args = interaction.response.send_message.call_args
        assert call_args.kwargs.get("ephemeral") is True
        assert (
            "not configured" in str(call_args).lower()
            or "not configured" in str(call_args.args).lower()
        )

    async def test_sync_no_new_sessions(self, tmp_path):
        cog = _make_cog(cli_sessions_path=str(tmp_path))
        interaction = _make_channel_interaction()
        await cog.sync_sessions.callback(cog, interaction)
        # Should defer then send followup
        interaction.response.defer.assert_called_once()
        call_args = interaction.followup.send.call_args
        embed = call_args.kwargs.get("embed")
        assert embed is not None

    async def test_sync_imports_cli_sessions(self, tmp_path):
        # Create a CLI session JSONL
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
        # Session not yet in DB
        cog.repo.get_by_session_id = AsyncMock(return_value=None)
        interaction = _make_channel_interaction()
        await cog.sync_sessions.callback(cog, interaction)

        # Should have created a thread
        channel = cog.bot.get_channel(999)
        channel.create_thread.assert_called_once()

        # Should have saved to DB with origin='cli'
        save_calls = cog.repo.save.call_args_list
        assert len(save_calls) >= 1
        save_kwargs = save_calls[0].kwargs
        assert save_kwargs["origin"] == "cli"
        assert save_kwargs["session_id"] == session_id

    async def test_sync_skips_already_known_sessions(self, tmp_path):
        session_id = "bbb22222-1234-5678-9abc-def012345678"
        jsonl_path = tmp_path / f"{session_id}.jsonl"
        with open(jsonl_path, "w") as f:
            f.write(
                json.dumps(
                    {
                        "type": "user",
                        "isMeta": False,
                        "sessionId": session_id,
                        "cwd": "/home",
                        "timestamp": "2026-02-19T10:00:00.000Z",
                        "message": {"role": "user", "content": "Already synced"},
                    }
                )
                + "\n"
            )

        cog = _make_cog(cli_sessions_path=str(tmp_path))
        # Session already in DB
        cog.repo.get_by_session_id = AsyncMock(
            return_value=_make_record(session_id=session_id, origin="cli")
        )
        interaction = _make_channel_interaction()
        await cog.sync_sessions.callback(cog, interaction)

        # Should NOT create a thread
        channel = cog.bot.get_channel(999)
        channel.create_thread.assert_not_called()


class TestSyncSessionsEmbed:
    """Test the sync result embed."""

    async def test_sync_result_shows_count(self, tmp_path):
        # Create 2 CLI sessions
        for i, sid in enumerate(
            ["ccc33333-1234-5678-9abc-def012345678", "ddd44444-1234-5678-9abc-def012345678"]
        ):
            jsonl_path = tmp_path / f"{sid}.jsonl"
            with open(jsonl_path, "w") as f:
                f.write(
                    json.dumps(
                        {
                            "type": "user",
                            "isMeta": False,
                            "sessionId": sid,
                            "cwd": f"/home/proj{i}",
                            "timestamp": f"2026-02-19T1{i}:00:00.000Z",
                            "message": {"role": "user", "content": f"Task {i}"},
                        }
                    )
                    + "\n"
                )

        cog = _make_cog(cli_sessions_path=str(tmp_path))
        cog.repo.get_by_session_id = AsyncMock(return_value=None)
        interaction = _make_channel_interaction()
        await cog.sync_sessions.callback(cog, interaction)

        embed = interaction.followup.send.call_args.kwargs["embed"]
        assert "2" in embed.description  # Should mention 2 imported


class TestListAllWithOriginFilter:
    """Test list_all with origin filter in repository."""

    async def test_list_all_filter_by_origin(self, repo):
        await repo.save(thread_id=5000, session_id="disc-1", origin="discord")
        await repo.save(thread_id=5001, session_id="cli-1", origin="cli")
        await repo.save(thread_id=5002, session_id="cli-2", origin="cli")

        cli_only = await repo.list_all(origin="cli")
        assert len(cli_only) == 2
        assert all(r.origin == "cli" for r in cli_only)

        discord_only = await repo.list_all(origin="discord")
        assert len(discord_only) == 1
        assert discord_only[0].origin == "discord"

    async def test_list_all_no_filter_returns_all(self, repo):
        await repo.save(thread_id=5100, session_id="d1", origin="discord")
        await repo.save(thread_id=5101, session_id="c1", origin="cli")
        all_sessions = await repo.list_all()
        assert len(all_sessions) == 2


class TestSessionsFilterCommand:
    """Test /sessions with origin filter parameter."""

    async def test_sessions_filter_cli(self):
        cog = _make_cog()
        records = [
            _make_record(session_id="c1", origin="cli", summary="CLI only"),
        ]
        cog.repo.list_all = AsyncMock(return_value=records)
        interaction = _make_channel_interaction()
        await cog.sessions_list.callback(cog, interaction, origin="cli")
        cog.repo.list_all.assert_called_once_with(limit=25, origin="cli")

    async def test_sessions_filter_all(self):
        cog = _make_cog()
        cog.repo.list_all = AsyncMock(return_value=[])
        interaction = _make_channel_interaction()
        await cog.sessions_list.callback(cog, interaction, origin=None)
        cog.repo.list_all.assert_called_once_with(limit=25, origin=None)

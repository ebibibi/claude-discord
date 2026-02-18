"""Tests for session repository."""

import pytest
import tempfile
import os

from claude_discord.database.models import init_db
from claude_discord.database.repository import SessionRepository


@pytest.fixture
async def repo(tmp_path):
    """Create a repository backed by a temporary database."""
    db_path = str(tmp_path / "test.db")
    await init_db(db_path)
    return SessionRepository(db_path)


class TestSessionRepository:
    async def test_save_and_get(self, repo):
        record = await repo.save(thread_id=12345, session_id="session-abc")
        assert record.thread_id == 12345
        assert record.session_id == "session-abc"

        fetched = await repo.get(12345)
        assert fetched is not None
        assert fetched.session_id == "session-abc"

    async def test_get_nonexistent(self, repo):
        result = await repo.get(99999)
        assert result is None

    async def test_save_updates_existing(self, repo):
        await repo.save(thread_id=100, session_id="first")
        await repo.save(thread_id=100, session_id="second")

        record = await repo.get(100)
        assert record.session_id == "second"

    async def test_save_with_metadata(self, repo):
        await repo.save(
            thread_id=200,
            session_id="sess-1",
            working_dir="/home/user/project",
            model="opus",
        )
        record = await repo.get(200)
        assert record.working_dir == "/home/user/project"
        assert record.model == "opus"

    async def test_delete(self, repo):
        await repo.save(thread_id=300, session_id="sess-to-delete")
        assert await repo.delete(300) is True
        assert await repo.get(300) is None

    async def test_delete_nonexistent(self, repo):
        assert await repo.delete(99999) is False

    async def test_cleanup_old(self, repo):
        # Create a session (it will be "now")
        await repo.save(thread_id=400, session_id="recent")

        # Cleanup with 0 days should delete everything
        deleted = await repo.cleanup_old(days=0)
        assert deleted == 1


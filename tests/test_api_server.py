"""Tests for ApiServer REST API extension."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from claude_discord.database.notification_repo import NotificationRepository
from claude_discord.ext.api_server import ApiServer


@pytest.fixture
async def repo() -> NotificationRepository:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    repo = NotificationRepository(path)
    await repo.init_db()
    yield repo
    os.unlink(path)


@pytest.fixture
def bot() -> MagicMock:
    b = MagicMock()
    channel = MagicMock()
    channel.send = AsyncMock()
    b.get_channel.return_value = channel
    return b


@pytest.fixture
async def client(repo: NotificationRepository, bot: MagicMock) -> TestClient:
    api = ApiServer(
        repo=repo,
        bot=bot,
        default_channel_id=12345,
        host="127.0.0.1",
        port=0,
    )
    server = TestServer(api.app)
    client = TestClient(server)
    await client.start_server()
    yield client
    await client.close()


@pytest.fixture
async def auth_client(repo: NotificationRepository, bot: MagicMock) -> TestClient:
    api = ApiServer(
        repo=repo,
        bot=bot,
        default_channel_id=12345,
        api_secret="test-secret-123",
    )
    server = TestServer(api.app)
    client = TestClient(server)
    await client.start_server()
    yield client
    await client.close()


class TestHealth:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client: TestClient) -> None:
        resp = await client.get("/api/health")
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "ok"
        assert "timestamp" in data


class TestNotify:
    @pytest.mark.asyncio
    async def test_notify_sends_message(self, client: TestClient, bot: MagicMock) -> None:
        resp = await client.post("/api/notify", json={"message": "Hello!"})
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "sent"
        bot.get_channel.assert_called_with(12345)

    @pytest.mark.asyncio
    async def test_notify_missing_message(self, client: TestClient) -> None:
        resp = await client.post("/api/notify", json={})
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_notify_invalid_json(self, client: TestClient) -> None:
        resp = await client.post(
            "/api/notify",
            data=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_notify_no_channel(self, repo: NotificationRepository) -> None:
        bot = MagicMock()
        api = ApiServer(repo=repo, bot=bot, default_channel_id=None)
        server = TestServer(api.app)
        client = TestClient(server)
        await client.start_server()
        try:
            resp = await client.post("/api/notify", json={"message": "test"})
            assert resp.status == 400
        finally:
            await client.close()


class TestSchedule:
    @pytest.mark.asyncio
    async def test_schedule_creates_notification(self, client: TestClient) -> None:
        resp = await client.post("/api/schedule", json={
            "message": "Reminder",
            "scheduled_at": "2026-01-01T09:00:00",
        })
        assert resp.status == 200
        data = await resp.json()
        assert data["status"] == "scheduled"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_schedule_missing_message(self, client: TestClient) -> None:
        resp = await client.post("/api/schedule", json={"scheduled_at": "2026-01-01T09:00:00"})
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_schedule_missing_time(self, client: TestClient) -> None:
        resp = await client.post("/api/schedule", json={"message": "test"})
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_schedule_invalid_time(self, client: TestClient) -> None:
        resp = await client.post("/api/schedule", json={
            "message": "test",
            "scheduled_at": "not-a-date",
        })
        assert resp.status == 400


class TestListScheduled:
    @pytest.mark.asyncio
    async def test_list_empty(self, client: TestClient) -> None:
        resp = await client.get("/api/scheduled")
        assert resp.status == 200
        data = await resp.json()
        assert data["notifications"] == []

    @pytest.mark.asyncio
    async def test_list_after_schedule(self, client: TestClient) -> None:
        await client.post("/api/schedule", json={
            "message": "test",
            "scheduled_at": "2026-01-01T09:00:00",
        })
        resp = await client.get("/api/scheduled")
        data = await resp.json()
        assert len(data["notifications"]) == 1


class TestCancelScheduled:
    @pytest.mark.asyncio
    async def test_cancel_existing(self, client: TestClient) -> None:
        resp = await client.post("/api/schedule", json={
            "message": "test",
            "scheduled_at": "2026-01-01T09:00:00",
        })
        nid = (await resp.json())["id"]
        resp = await client.delete(f"/api/scheduled/{nid}")
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_cancel_nonexistent(self, client: TestClient) -> None:
        resp = await client.delete("/api/scheduled/99999")
        assert resp.status == 404

    @pytest.mark.asyncio
    async def test_cancel_invalid_id(self, client: TestClient) -> None:
        resp = await client.delete("/api/scheduled/abc")
        assert resp.status == 400


class TestAuthentication:
    @pytest.mark.asyncio
    async def test_health_bypasses_auth(self, auth_client: TestClient) -> None:
        resp = await auth_client.get("/api/health")
        assert resp.status == 200

    @pytest.mark.asyncio
    async def test_missing_auth_header(self, auth_client: TestClient) -> None:
        resp = await auth_client.post("/api/notify", json={"message": "test"})
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_invalid_token(self, auth_client: TestClient) -> None:
        resp = await auth_client.post(
            "/api/notify",
            json={"message": "test"},
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_valid_token(self, auth_client: TestClient, bot: MagicMock) -> None:
        resp = await auth_client.post(
            "/api/notify",
            json={"message": "test"},
            headers={"Authorization": "Bearer test-secret-123"},
        )
        assert resp.status == 200

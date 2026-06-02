"""
P3-010 测试：终端指令下发 API
"""

import pytest
from unittest.mock import MagicMock, patch
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestCommandOffline:
    @pytest.mark.asyncio
    async def test_offline(self, client):
        with patch("app.routes.terminal._get_tmux", return_value=None):
            resp = await client.post("/api/terminal/agent_dev_001/command", json={"command": "ls"})
        assert resp.status_code == 200
        assert resp.json()["sent"] is False


class TestCommandMocked:
    @pytest.mark.asyncio
    async def test_sends_command(self, client):
        mgr = MagicMock()
        mgr.is_available = True
        mgr.list_sessions.return_value = ["openboss"]
        mgr.list_windows.return_value = ["agent_dev_001"]
        with patch("app.routes.terminal._get_tmux", return_value=mgr):
            resp = await client.post("/api/terminal/agent_dev_001/command", json={"command": "npm test"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["sent"] is True
        assert "npm test" in data["command"]
        mgr.send_command.assert_called_once_with("openboss", "agent_dev_001", "npm test")

    @pytest.mark.asyncio
    async def test_session_not_found(self, client):
        mgr = MagicMock()
        mgr.is_available = True
        mgr.list_sessions.return_value = []
        with patch("app.routes.terminal._get_tmux", return_value=mgr):
            resp = await client.post("/api/terminal/agent_dev_001/command", json={"command": "ls"})
        assert resp.status_code == 200
        assert resp.json()["sent"] is False

    @pytest.mark.asyncio
    async def test_window_not_found(self, client):
        mgr = MagicMock()
        mgr.is_available = True
        mgr.list_sessions.return_value = ["openboss"]
        mgr.list_windows.return_value = ["agent_pm_001"]
        with patch("app.routes.terminal._get_tmux", return_value=mgr):
            resp = await client.post("/api/terminal/agent_dev_001/command", json={"command": "ls"})
        assert resp.status_code == 200
        assert resp.json()["sent"] is False

    @pytest.mark.asyncio
    async def test_empty_command_rejected(self, client):
        mgr = MagicMock()
        mgr.is_available = True
        with patch("app.routes.terminal._get_tmux", return_value=mgr):
            resp = await client.post("/api/terminal/agent_dev_001/command", json={"command": ""})
        assert resp.status_code == 422

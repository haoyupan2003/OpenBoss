"""
P3-009 测试：终端输出 API
"""

import pytest
from unittest.mock import patch, MagicMock
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestTerminalOffline:
    @pytest.mark.asyncio
    async def test_offline_when_no_tmux(self, client):
        with patch("app.routes.terminal._get_tmux", return_value=None):
            resp = await client.get("/api/terminal/agent_dev_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is False
        assert data["agent_id"] == "agent_dev_001"

    @pytest.mark.asyncio
    async def test_status_offline(self, client):
        with patch("app.routes.terminal._get_tmux", return_value=None):
            resp = await client.get("/api/terminal/agent_dev_001/status")
        assert resp.status_code == 200
        assert resp.json()["available"] is False


class TestTerminalMocked:
    @pytest.mark.asyncio
    async def test_session_not_found(self, client):
        mgr = MagicMock()
        mgr.is_available = True
        mgr.list_sessions.return_value = []
        with patch("app.routes.terminal._get_tmux", return_value=mgr):
            resp = await client.get("/api/terminal/agent_dev_001")
        assert resp.status_code == 200
        assert "not found" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_window_not_found(self, client):
        mgr = MagicMock()
        mgr.is_available = True
        mgr.list_sessions.return_value = ["openboss"]
        mgr.list_windows.return_value = ["agent_pm_001"]
        with patch("app.routes.terminal._get_tmux", return_value=mgr):
            resp = await client.get("/api/terminal/agent_dev_001")
        assert resp.status_code == 200
        assert "not found" in resp.json()["message"]

    @pytest.mark.asyncio
    async def test_captures_output(self, client):
        mgr = MagicMock()
        mgr.is_available = True
        mgr.list_sessions.return_value = ["openboss"]
        mgr.list_windows.return_value = ["agent_dev_001"]
        mgr.capture_pane_history.return_value = ["line 1", "line 2", "line 3"]
        with patch("app.routes.terminal._get_tmux", return_value=mgr):
            resp = await client.get("/api/terminal/agent_dev_001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["available"] is True
        assert data["output"] == ["line 1", "line 2", "line 3"]
        assert data["lines"] == 3

    @pytest.mark.asyncio
    async def test_custom_lines_param(self, client):
        mgr = MagicMock()
        mgr.is_available = True
        mgr.list_sessions.return_value = ["openboss"]
        mgr.list_windows.return_value = ["agent_dev_001"]
        mgr.capture_pane_history.return_value = ["x"]
        with patch("app.routes.terminal._get_tmux", return_value=mgr):
            await client.get("/api/terminal/agent_dev_001?lines=100")
        mgr.capture_pane_history.assert_called_with("openboss", "agent_dev_001", lines=100)

    @pytest.mark.asyncio
    async def test_status_with_window(self, client):
        mgr = MagicMock()
        mgr.is_available = True
        mgr.list_sessions.return_value = ["openboss"]
        mgr.list_windows.return_value = ["agent_dev_001"]
        with patch("app.routes.terminal._get_tmux", return_value=mgr):
            resp = await client.get("/api/terminal/agent_dev_001/status")
        data = resp.json()
        assert data["session_exists"] is True
        assert data["window_exists"] is True

    @pytest.mark.asyncio
    async def test_status_no_window(self, client):
        mgr = MagicMock()
        mgr.is_available = True
        mgr.list_sessions.return_value = ["openboss"]
        mgr.list_windows.return_value = []
        with patch("app.routes.terminal._get_tmux", return_value=mgr):
            resp = await client.get("/api/terminal/agent_dev_001/status")
        data = resp.json()
        assert data["window_exists"] is False

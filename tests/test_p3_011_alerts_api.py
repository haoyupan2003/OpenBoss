"""
P3-011 测试：告警历史 API
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routes.alerts import _alerts, add_alert


@pytest.fixture(autouse=True)
def clear_alerts():
    _alerts.clear()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestAlertsAPI:
    @pytest.mark.asyncio
    async def test_empty(self, client):
        resp = await client.get("/api/alerts")
        assert resp.status_code == 200
        assert resp.json()["alerts"] == []

    @pytest.mark.asyncio
    async def test_returns_alerts(self, client):
        add_alert("error", "task failed", task_id="task-001")
        add_alert("warning", "high memory", source="openclaw")
        resp = await client.get("/api/alerts")
        data = resp.json()
        assert data["total"] == 2
        assert data["alerts"][0]["level"] == "error"

    @pytest.mark.asyncio
    async def test_filter_by_level(self, client):
        add_alert("error", "e1")
        add_alert("warning", "w1")
        resp = await client.get("/api/alerts?level=error")
        data = resp.json()
        assert data["total"] == 1
        assert data["alerts"][0]["level"] == "error"

    @pytest.mark.asyncio
    async def test_filter_by_task(self, client):
        add_alert("error", "fail", task_id="task-001")
        add_alert("error", "fail", task_id="task-002")
        resp = await client.get("/api/alerts?task_id=task-001")
        assert resp.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_limit(self, client):
        for i in range(5):
            add_alert("info", f"msg-{i}")
        resp = await client.get("/api/alerts?limit=2")
        assert len(resp.json()["alerts"]) == 2

    def test_add_alert(self):
        add_alert("error", "test", task_id="task-001", source="openclaw")
        assert len(_alerts) == 1
        assert _alerts[0]["id"] == "alert-0001"

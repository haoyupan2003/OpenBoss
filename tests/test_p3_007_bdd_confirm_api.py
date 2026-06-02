"""
P3-007 测试：BDD 确认 API
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routes.requirements import _store as req_store
from app.routes.bdd import _bdd_records


@pytest.fixture(autouse=True)
def clear_store():
    req_store._items.clear()
    _bdd_records.clear()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
async def req_id(client):
    """创建一个需求并返回其 ID"""
    r = await client.post("/api/requirements", json={"raw_need": "test"})
    return r.json()["id"]


class TestConfirmBDD:
    @pytest.mark.asyncio
    async def test_confirm_sets_status(self, client, req_id):
        resp = await client.post("/api/bdd/confirm", json={
            "req_id": req_id, "given": "用户已登录", "when": "点击按钮", "then": "显示结果",
            "confirmed": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "confirmed"
        assert data["bdd"]["given"] == "用户已登录"

    @pytest.mark.asyncio
    async def test_confirm_updates_requirement_status(self, client, req_id):
        await client.post("/api/bdd/confirm", json={
            "req_id": req_id, "given": "G", "when": "W", "then": "T", "confirmed": True,
        })
        r = await client.get(f"/api/requirements/{req_id}")
        assert r.json()["status"] == "bdd_confirmed"

    @pytest.mark.asyncio
    async def test_reject_with_feedback(self, client, req_id):
        resp = await client.post("/api/bdd/confirm", json={
            "req_id": req_id, "confirmed": False, "feedback": "缺少异常场景",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "rejected"
        assert data["feedback"] == "缺少异常场景"

    @pytest.mark.asyncio
    async def test_nonexistent_req_404(self, client):
        resp = await client.post("/api/bdd/confirm", json={
            "req_id": "req-nope", "confirmed": True,
        })
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_bdd_status(self, client, req_id):
        await client.post("/api/bdd/confirm", json={
            "req_id": req_id, "given": "G", "when": "W", "then": "T", "confirmed": True,
        })
        resp = await client.get(f"/api/bdd/{req_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "confirmed"

    @pytest.mark.asyncio
    async def test_get_pending_bdd(self, client, req_id):
        resp = await client.get(f"/api/bdd/{req_id}")
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

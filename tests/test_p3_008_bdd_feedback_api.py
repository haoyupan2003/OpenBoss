"""
P3-008 测试：BDD 修改 API（附加到 P3-007 测试之上）
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
    r = await client.post("/api/requirements", json={"raw_need": "test"})
    return r.json()["id"]


class TestBDDFeedback:
    @pytest.mark.asyncio
    async def test_submit_feedback(self, client, req_id):
        resp = await client.post("/api/bdd/feedback", json={
            "req_id": req_id, "feedback": "需要增加边界条件",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "draft"
        assert data["feedback_count"] == 1

    @pytest.mark.asyncio
    async def test_feedback_with_modified_bdd(self, client, req_id):
        resp = await client.post("/api/bdd/feedback", json={
            "req_id": req_id, "feedback": "修正 Given",
            "given": "新前置条件", "when": "新操作", "then": "新结果",
        })
        assert resp.status_code == 200
        # 验证 BDD 已更新
        r = await client.get(f"/api/bdd/{req_id}")
        data = r.json()
        assert data["bdd"]["given"] == "新前置条件"

    @pytest.mark.asyncio
    async def test_feedback_history_accumulates(self, client, req_id):
        await client.post("/api/bdd/feedback", json={
            "req_id": req_id, "feedback": "第一次修改",
        })
        await client.post("/api/bdd/feedback", json={
            "req_id": req_id, "feedback": "第二次修改",
        })
        resp = await client.post("/api/bdd/feedback", json={
            "req_id": req_id, "feedback": "第三次修改",
        })
        assert resp.json()["feedback_count"] == 3

    @pytest.mark.asyncio
    async def test_updates_requirement_status(self, client, req_id):
        await client.post("/api/bdd/feedback", json={
            "req_id": req_id, "feedback": "修改",
        })
        r = await client.get(f"/api/requirements/{req_id}")
        assert r.json()["status"] == "bdd_feedback_received"

    @pytest.mark.asyncio
    async def test_empty_feedback_rejected(self, client, req_id):
        resp = await client.post("/api/bdd/feedback", json={
            "req_id": req_id, "feedback": "",
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_nonexistent_404(self, client):
        resp = await client.post("/api/bdd/feedback", json={
            "req_id": "req-nope", "feedback": "x",
        })
        assert resp.status_code == 404

"""
P3-006 测试：需求提交 API
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routes.requirements import _store


@pytest.fixture(autouse=True)
def clear_store():
    """每个测试前清空 store"""
    _store._items.clear()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestSubmitRequirement:
    @pytest.mark.asyncio
    async def test_submit_creates_record(self, client):
        resp = await client.post("/api/requirements", json={"raw_need": "构建用户认证系统"})
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"].startswith("req-")
        assert data["raw_need"] == "构建用户认证系统"
        assert data["status"] == "pending"
        assert data["created_at"] is not None

    @pytest.mark.asyncio
    async def test_submit_with_title(self, client):
        resp = await client.post("/api/requirements", json={
            "raw_need": "实现支付功能", "title": "支付模块"
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "支付模块"

    @pytest.mark.asyncio
    async def test_empty_need_rejected(self, client):
        resp = await client.post("/api/requirements", json={"raw_need": ""})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_unique_ids(self, client):
        r1 = await client.post("/api/requirements", json={"raw_need": "A"})
        r2 = await client.post("/api/requirements", json={"raw_need": "B"})
        assert r1.json()["id"] != r2.json()["id"]


class TestListRequirements:
    @pytest.mark.asyncio
    async def test_list_empty(self, client):
        resp = await client.get("/api/requirements")
        assert resp.status_code == 200
        assert resp.json()["requirements"] == []

    @pytest.mark.asyncio
    async def test_list_multiple(self, client):
        await client.post("/api/requirements", json={"raw_need": "A"})
        await client.post("/api/requirements", json={"raw_need": "B"})
        resp = await client.get("/api/requirements")
        data = resp.json()
        assert len(data["requirements"]) == 2


class TestGetRequirement:
    @pytest.mark.asyncio
    async def test_get_existing(self, client):
        r = await client.post("/api/requirements", json={"raw_need": "need"})
        rid = r.json()["id"]
        resp = await client.get(f"/api/requirements/{rid}")
        assert resp.status_code == 200
        assert resp.json()["id"] == rid

    @pytest.mark.asyncio
    async def test_get_nonexistent(self, client):
        resp = await client.get("/api/requirements/req-nonexist")
        assert resp.status_code == 404


class TestStatusUpdate:
    def test_update_status(self):
        rid = _store.add("need", "title")
        _store.update_status(rid, "processing")
        assert _store.get(rid)["status"] == "processing"

        _store.update_status(rid, "task_json_ready", task_json_path="/tmp/task.json")
        item = _store.get(rid)
        assert item["status"] == "task_json_ready"
        assert item["task_json_path"] == "/tmp/task.json"

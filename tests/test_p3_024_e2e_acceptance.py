"""
P3-024 迭代验收测试：P3 API 协作流程 E2E 验证

覆盖完整 PM+Dev API 协作场景：
1. 需求提交 → 确认 BDD → 查看 Agents/Tasks → 查看 Alerts
2. 验证所有 P3 端点可用且数据一致
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routes.requirements import _store as req_store
from app.routes.bdd import _bdd_records
from app.routes.alerts import _alerts


@pytest.fixture(autouse=True)
def clear_stores():
    req_store._items.clear()
    _bdd_records.clear()
    _alerts.clear()


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


class TestP3E2EWorkflow:
    """P3 完整协作流程"""

    @pytest.mark.asyncio
    async def test_full_requirement_to_bdd_workflow(self, client):
        # 1. Health check
        r = await client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "healthy"

        # 2. Submit requirement
        r = await client.post("/api/requirements", json={
            "raw_need": "构建用户认证系统",
            "title": "Auth Module",
        })
        assert r.status_code == 201
        req_id = r.json()["id"]
        assert req_id.startswith("req-")
        assert r.json()["status"] == "pending"

        # 3. Verify requirement appears in list
        r = await client.get("/api/requirements")
        reqs = r.json()["requirements"]
        assert len(reqs) == 1
        assert reqs[0]["id"] == req_id

        # 4. Confirm BDD
        r = await client.post("/api/bdd/confirm", json={
            "req_id": req_id,
            "given": "用户未登录",
            "when": "提交登录表单",
            "then": "返回 token",
            "confirmed": True,
        })
        assert r.status_code == 200
        assert r.json()["status"] == "confirmed"

        # 5. Check BDD status
        r = await client.get(f"/api/bdd/{req_id}")
        assert r.status_code == 200
        assert r.json()["bdd"]["given"] == "用户未登录"

        # 6. Requirement status updated to bdd_confirmed
        r = await client.get(f"/api/requirements/{req_id}")
        assert r.json()["status"] == "bdd_confirmed"

    @pytest.mark.asyncio
    async def test_agents_tasks_alerts_integration(self, client):
        # Verify agent/task/alerts endpoints return expected structure
        for url in ["/api/agents", "/api/tasks"]:
            r = await client.get(url)
            assert r.status_code == 200
            data = r.json()
            assert "summary" in data

        # Alerts can be posted and retrieved
        from app.routes.alerts import add_alert
        add_alert("error", "E2E test alert", task_id="task-001")
        r = await client.get("/api/alerts")
        assert r.status_code == 200
        assert r.json()["total"] >= 1

    @pytest.mark.asyncio
    async def test_terminal_endpoint_responsive(self, client):
        r = await client.get("/api/terminal/agent_test/status")
        assert r.status_code == 200
        assert "agent_id" in r.json()
        assert "available" in r.json()

    @pytest.mark.asyncio
    async def test_all_p3_endpoints_accessible(self, client):
        """所有 P3 端点可达"""
        endpoints = [
            ("GET", "/health"),
            ("GET", "/api/agents"),
            ("GET", "/api/tasks"),
            ("GET", "/api/requirements"),
            ("GET", "/api/alerts"),
        ]
        for method, url in endpoints:
            r = await client.get(url)
            assert r.status_code == 200, f"{method} {url} failed: {r.status_code}"

    @pytest.mark.asyncio
    async def test_bdd_feedback_loop(self, client):
        """BDD 反馈-修改-确认完整循环"""
        # Submit
        r = await client.post("/api/requirements", json={"raw_need": "need"})
        req_id = r.json()["id"]

        # Send feedback (reject with suggestions)
        r = await client.post("/api/bdd/feedback", json={
            "req_id": req_id, "feedback": "Given 不够清晰",
            "given": "修正后 Given",
        })
        assert r.status_code == 200
        assert r.json()["status"] == "draft"

        # Confirm updated BDD
        r = await client.post("/api/bdd/confirm", json={
            "req_id": req_id,
            "given": "修正后 Given", "when": "W", "then": "T",
            "confirmed": True,
        })
        assert r.status_code == 200
        assert r.json()["status"] == "confirmed"
        assert r.json()["bdd"]["given"] == "修正后 Given"

    @pytest.mark.asyncio
    async def test_requirement_detail_404(self, client):
        r = await client.get("/api/requirements/req-nonexist")
        assert r.status_code == 404

        r = await client.get("/api/bdd/req-nonexist")
        assert r.status_code == 404

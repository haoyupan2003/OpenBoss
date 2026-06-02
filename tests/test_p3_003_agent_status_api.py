"""
P3-003 测试：Agent 状态 API

验证 GET /api/agents 和 GET /api/agents/{task_id}
1. 空 progress.txt 返回空列表
2. 有数据时返回正确状态
3. role / status 过滤
4. by_role 聚合
5. 单 agent 详情
6. 404 场景
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routes.agents import _get_progress_manager, _entry_to_dict, _summarize_agents
from agent_automation_system.file_io.progress_manager import ProgressManager
from agent_automation_system.models.progress import ProgressEntry, ProgressStatus


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def tmp_progress():
    """创建临时 progress.txt 并写入数据"""
    d = tempfile.mkdtemp()
    path = Path(d) / "progress.txt"
    pm = ProgressManager(file_path=path)
    now = datetime(2026, 5, 27, 10, 0, 0)
    entries = [
        ProgressEntry(
            task_id="task-001", status=ProgressStatus.COMPLETED, role="dev",
            started=now, finished=now + timedelta(minutes=15),
            git_sha="abc1234", git_msg="[task-001] dev: 实现登录",
        ),
        ProgressEntry(
            task_id="task-002", status=ProgressStatus.FAILED, role="qa",
            started=now, finished=now + timedelta(minutes=5),
            error="assert False",
        ),
        ProgressEntry(
            task_id="task-003", status=ProgressStatus.COMPLETED, role="dev",
            started=now + timedelta(minutes=10),
            finished=now + timedelta(minutes=25), git_sha="def5678",
            git_msg="[task-003] dev: 实现注册",
        ),
        ProgressEntry(
            task_id="task-004", status=ProgressStatus.BLOCKED, role="pm",
            error="依赖未满足",
        ),
    ]
    for e in entries:
        pm.write_entry(e)
    yield path, entries
    import shutil
    shutil.rmtree(d, ignore_errors=True)


# ── Helper 测试 ───────────────────────────────────────────


class TestHelpers:
    """辅助函数"""

    def test_entry_to_dict_completed(self):
        e = ProgressEntry(
            task_id="task-001", status=ProgressStatus.COMPLETED, role="dev",
            git_sha="abc1234", git_msg="msg",
            started=datetime(2026, 5, 27, 10, 0),
            finished=datetime(2026, 5, 27, 10, 15),
        )
        d = _entry_to_dict(e)
        assert d["task_id"] == "task-001"
        assert d["status"] == "COMPLETED"
        assert d["role"] == "dev"
        assert d["git_sha"] == "abc1234"
        assert d["started"] is not None
        assert d["finished"] is not None

    def test_entry_to_dict_failed(self):
        e = ProgressEntry(
            task_id="task-002", status=ProgressStatus.FAILED, role="qa",
            error="test fail",
        )
        d = _entry_to_dict(e)
        assert d["status"] == "FAILED"
        assert d["error"] == "test fail"
        assert d["git_sha"] is None

    def test_summarize_agents(self):
        now = datetime(2026, 5, 27, 10, 0)
        entries = [
            ProgressEntry(task_id="t1", status=ProgressStatus.COMPLETED, role="dev", finished=now),
            ProgressEntry(task_id="t2", status=ProgressStatus.FAILED, role="dev"),
            ProgressEntry(task_id="t3", status=ProgressStatus.COMPLETED, role="qa", finished=now + timedelta(hours=1)),
        ]
        summary = _summarize_agents(entries)
        assert len(summary) == 2  # dev + qa
        dev = next(s for s in summary if s["role"] == "dev")
        assert dev["total"] == 2
        assert dev["completed"] == 1
        assert dev["failed"] == 1
        qa = next(s for s in summary if s["role"] == "qa")
        assert qa["total"] == 1
        assert qa["completed"] == 1


# ── API 端点 ──────────────────────────────────────────────


class TestAgentsEndpoint:
    """GET /api/agents"""

    @pytest.mark.asyncio
    async def test_empty_returns_empty_list(self, client):
        resp = await client.get("/api/agents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["agents"] == []
        assert data["summary"]["total"] == 0

    @pytest.mark.asyncio
    async def test_returns_all_agents(self, client, tmp_progress):
        path, entries = tmp_progress
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.routes.agents._get_progress_manager",
                       lambda: ProgressManager(file_path=path))

            resp = await client.get("/api/agents")
            assert resp.status_code == 200
            data = resp.json()
            assert len(data["agents"]) == 4
            assert data["summary"]["total"] == 4
            assert data["summary"]["completed"] == 2
            assert data["summary"]["failed"] == 1
            assert data["summary"]["blocked"] == 1

    @pytest.mark.asyncio
    async def test_filter_by_role(self, client, tmp_progress):
        path, _ = tmp_progress
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.routes.agents._get_progress_manager",
                       lambda: ProgressManager(file_path=path))

            resp = await client.get("/api/agents?role=dev")
            data = resp.json()
            assert len(data["agents"]) == 2
            for a in data["agents"]:
                assert a["role"] == "dev"

    @pytest.mark.asyncio
    async def test_filter_by_status(self, client, tmp_progress):
        path, _ = tmp_progress
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.routes.agents._get_progress_manager",
                       lambda: ProgressManager(file_path=path))

            resp = await client.get("/api/agents?status=FAILED")
            data = resp.json()
            assert len(data["agents"]) == 1
            assert data["agents"][0]["status"] == "FAILED"

    @pytest.mark.asyncio
    async def test_by_role_aggregation(self, client, tmp_progress):
        path, _ = tmp_progress
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.routes.agents._get_progress_manager",
                       lambda: ProgressManager(file_path=path))

            resp = await client.get("/api/agents")
            data = resp.json()
            roles = [r["role"] for r in data["by_role"]]
            assert "dev" in roles
            assert "qa" in roles
            # dev 有 2 条
            dev = next(r for r in data["by_role"] if r["role"] == "dev")
            assert dev["total"] == 2

    @pytest.mark.asyncio
    async def test_response_has_correct_structure(self, client, tmp_progress):
        path, _ = tmp_progress
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.routes.agents._get_progress_manager",
                       lambda: ProgressManager(file_path=path))

            resp = await client.get("/api/agents")
            data = resp.json()
            assert "agents" in data
            assert "summary" in data
            assert "by_role" in data
            if data["agents"]:
                a = data["agents"][0]
                for key in ["task_id", "status", "role", "git_sha"]:
                    assert key in a


# ── 详情端点 ──────────────────────────────────────────────


class TestAgentDetailEndpoint:
    """GET /api/agents/{task_id}"""

    @pytest.mark.asyncio
    async def test_get_existing_agent(self, client, tmp_progress):
        path, _ = tmp_progress
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.routes.agents._get_progress_manager",
                       lambda: ProgressManager(file_path=path))

            resp = await client.get("/api/agents/task-001")
            assert resp.status_code == 200
            data = resp.json()
            assert data["task_id"] == "task-001"
            assert data["status"] == "COMPLETED"
            assert data["role"] == "dev"

    @pytest.mark.asyncio
    async def test_get_nonexistent_agent(self, client, tmp_progress):
        path, _ = tmp_progress
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr("app.routes.agents._get_progress_manager",
                       lambda: ProgressManager(file_path=path))

            resp = await client.get("/api/agents/task-999")
            assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_agent_with_no_progress_file(self, client):
        resp = await client.get("/api/agents/task-001")
        assert resp.status_code == 404

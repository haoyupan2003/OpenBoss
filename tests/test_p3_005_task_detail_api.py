"""
P3-005 测试：任务详情 API 增强

验证 GET /api/tasks/{id} 返回完整任务详情：
- 依赖关系（depends_on / blocks）
- 执行历史（duration, error, retry）
- 404 场景
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from agent_automation_system.file_io.progress_manager import ProgressManager
from agent_automation_system.file_io.task_file_manager import TaskFileManager
from agent_automation_system.models.task import Task, TaskComplexity, TaskPriority, TaskStatus
from agent_automation_system.models.task_json import TaskJSON
from agent_automation_system.models.progress import ProgressEntry, ProgressStatus


def _task(id, title, status=TaskStatus.PENDING, deps=None):
    return Task(id=id, title=title, description=title, dependencies=deps or [],
                suggested_role="dev", priority=TaskPriority.HIGH,
                estimated_complexity=TaskComplexity.MEDIUM, status=status)


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.fixture
def tmp_data():
    d = tempfile.mkdtemp()
    task_path = Path(d) / "task.json"
    progress_path = Path(d) / "progress.txt"

    tasks = [
        _task("task-001", "登录页面", TaskStatus.COMPLETED),
        _task("task-002", "注册页面", TaskStatus.FAILED),
        _task("task-003", "首页重构", TaskStatus.PENDING, deps=["task-001", "task-002"]),
        _task("task-004", "支付模块", TaskStatus.PENDING, deps=["task-003"]),
        _task("task-005", "通知服务", TaskStatus.PENDING),
    ]
    tfm = TaskFileManager(file_path=task_path)
    tfm.write_tasks(TaskJSON(project_name="test", created_by="t", total_tasks=5, tasks=tasks))

    now = datetime(2026, 5, 27, 10, 0)
    pm = ProgressManager(file_path=progress_path)
    pm.write_entry(ProgressEntry(task_id="task-001", status=ProgressStatus.COMPLETED, role="dev",
                                  git_sha="abc1234", started=now,
                                  finished=now + timedelta(minutes=15)))
    pm.write_entry(ProgressEntry(task_id="task-002", status=ProgressStatus.FAILED, role="qa",
                                  error="assert False", started=now,
                                  finished=now + timedelta(minutes=5)))

    yield task_path, progress_path
    import shutil
    shutil.rmtree(d, ignore_errors=True)


def _patch_paths(task_path, progress_path):
    import app.routes.tasks as mod
    orig = (mod._DEFAULT_TASK_PATH, mod._DEFAULT_PROGRESS_PATH)
    mod._DEFAULT_TASK_PATH, mod._DEFAULT_PROGRESS_PATH = task_path, progress_path
    return orig


def _restore_paths(orig):
    import app.routes.tasks as mod
    mod._DEFAULT_TASK_PATH, mod._DEFAULT_PROGRESS_PATH = orig


class TestTaskDetailEnhanced:
    @pytest.mark.asyncio
    async def test_depends_on(self, client, tmp_data):
        task_path, progress_path = tmp_data
        orig = _patch_paths(task_path, progress_path)
        try:
            resp = await client.get("/api/tasks/task-003")
            assert resp.status_code == 200
            data = resp.json()
            assert data["id"] == "task-003"
            assert "dependencies" in data
            deps = data["dependencies"]["depends_on"]
            assert len(deps) == 2
            dep_ids = [d["id"] for d in deps]
            assert "task-001" in dep_ids
            assert "task-002" in dep_ids
            # 依赖任务的状态
            t1_dep = next(d for d in deps if d["id"] == "task-001")
            assert t1_dep["status"] == "COMPLETED"
            t2_dep = next(d for d in deps if d["id"] == "task-002")
            assert t2_dep["status"] == "FAILED"
        finally:
            _restore_paths(orig)

    @pytest.mark.asyncio
    async def test_blocks(self, client, tmp_data):
        task_path, progress_path = tmp_data
        orig = _patch_paths(task_path, progress_path)
        try:
            resp = await client.get("/api/tasks/task-003")
            data = resp.json()
            blocks = data["dependencies"]["blocks"]
            assert len(blocks) == 1
            assert blocks[0]["id"] == "task-004"
        finally:
            _restore_paths(orig)

    @pytest.mark.asyncio
    async def test_no_dependencies(self, client, tmp_data):
        task_path, progress_path = tmp_data
        orig = _patch_paths(task_path, progress_path)
        try:
            resp = await client.get("/api/tasks/task-005")
            data = resp.json()
            assert data["dependencies"]["depends_on"] == []
            assert data["dependencies"]["blocks"] == []
        finally:
            _restore_paths(orig)

    @pytest.mark.asyncio
    async def test_execution_detail(self, client, tmp_data):
        task_path, progress_path = tmp_data
        orig = _patch_paths(task_path, progress_path)
        try:
            resp = await client.get("/api/tasks/task-001")
            data = resp.json()
            ex = data["execution"]
            assert ex is not None
            assert ex["git_sha"] == "abc1234"
            assert ex["role"] == "dev"
            assert ex["duration_seconds"] is not None
            assert ex["duration_seconds"] > 0
            assert ex["error"] is None
        finally:
            _restore_paths(orig)

    @pytest.mark.asyncio
    async def test_execution_with_error(self, client, tmp_data):
        task_path, progress_path = tmp_data
        orig = _patch_paths(task_path, progress_path)
        try:
            resp = await client.get("/api/tasks/task-002")
            data = resp.json()
            ex = data["execution"]
            assert ex is not None
            assert ex["status"] == "FAILED"
            assert "assert False" in ex["error"]
        finally:
            _restore_paths(orig)

    @pytest.mark.asyncio
    async def test_no_execution_yet(self, client, tmp_data):
        task_path, progress_path = tmp_data
        orig = _patch_paths(task_path, progress_path)
        try:
            resp = await client.get("/api/tasks/task-005")
            data = resp.json()
            assert data["execution"] is None
        finally:
            _restore_paths(orig)

    @pytest.mark.asyncio
    async def test_not_found(self, client, tmp_data):
        task_path, progress_path = tmp_data
        orig = _patch_paths(task_path, progress_path)
        try:
            resp = await client.get("/api/tasks/task-999")
            assert resp.status_code == 404
        finally:
            _restore_paths(orig)

    @pytest.mark.asyncio
    async def test_no_data_files(self, client):
        resp = await client.get("/api/tasks/task-001")
        assert resp.status_code == 404

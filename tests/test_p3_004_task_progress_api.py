"""
P3-004 测试：任务进度 API
"""

import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.routes.tasks import _merge_task_progress
from agent_automation_system.file_io.progress_manager import ProgressManager
from agent_automation_system.file_io.task_file_manager import TaskFileManager
from agent_automation_system.models.task import Task, TaskComplexity, TaskPriority, TaskStatus
from agent_automation_system.models.task_json import TaskJSON
from agent_automation_system.models.progress import ProgressEntry, ProgressStatus


def _task(id, title, status=TaskStatus.PENDING, deps=None):
    return Task(id=id, title=title, description=title, dependencies=deps or [],
                suggested_role="dev", priority=TaskPriority.HIGH,
                estimated_complexity=TaskComplexity.MEDIUM, status=status)


def _progress(task_id, status, role="dev", git_sha="", error=""):
    now = datetime(2026, 5, 27, 10, 0)
    return ProgressEntry(task_id=task_id, status=status, role=role, git_sha=git_sha,
                         error=error, started=now, finished=now + timedelta(minutes=10))


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
        _task("task-003", "首页重构", TaskStatus.PENDING, deps=["task-001"]),
        _task("task-004", "支付模块", TaskStatus.IN_PROGRESS),
    ]
    tfm = TaskFileManager(file_path=task_path)
    tfm.write_tasks(TaskJSON(project_name="测试项目", created_by="test", total_tasks=4, tasks=tasks))

    pm = ProgressManager(file_path=progress_path)
    for e in [
        _progress("task-001", ProgressStatus.COMPLETED, "dev", "abc1234"),
        _progress("task-002", ProgressStatus.FAILED, "qa", error="assert False"),
        _progress("task-004", ProgressStatus.BLOCKED, "dev"),
    ]:
        pm.write_entry(e)

    yield task_path, progress_path
    import shutil
    shutil.rmtree(d, ignore_errors=True)


# ── Helpers ────────────────────────────────────────────────


class TestHelpers:
    def test_merge_with_progress(self):
        task = _task("task-001", "登录")
        entry = _progress("task-001", ProgressStatus.COMPLETED, git_sha="abc")
        result = _merge_task_progress(task, {"task-001": entry})
        assert result["id"] == "task-001"
        assert result["progress"] is not None
        assert result["progress"]["git_sha"] == "abc"

    def test_merge_without_progress(self):
        task = _task("task-002", "注册")
        result = _merge_task_progress(task, {})
        assert result["progress"] is None


# ── API ───────────────────────────────────────────────────


class TestTasksEndpoint:
    @pytest.mark.asyncio
    async def test_empty(self, client):
        resp = await client.get("/api/tasks")
        assert resp.status_code == 200
        assert resp.json()["tasks"] == []

    @pytest.mark.asyncio
    async def test_all_tasks(self, client, tmp_data):
        task_path, progress_path = tmp_data
        import app.routes.tasks as mod
        orig = (mod._DEFAULT_TASK_PATH, mod._DEFAULT_PROGRESS_PATH)
        mod._DEFAULT_TASK_PATH, mod._DEFAULT_PROGRESS_PATH = task_path, progress_path
        try:
            resp = await client.get("/api/tasks")
            data = resp.json()
            assert data["project_name"] == "测试项目"
            assert len(data["tasks"]) == 4
            assert data["summary"]["completed"] == 1
            assert data["summary"]["failed"] == 1
        finally:
            mod._DEFAULT_TASK_PATH, mod._DEFAULT_PROGRESS_PATH = orig

    @pytest.mark.asyncio
    async def test_filter_by_status(self, client, tmp_data):
        task_path, progress_path = tmp_data
        import app.routes.tasks as mod
        orig = (mod._DEFAULT_TASK_PATH, mod._DEFAULT_PROGRESS_PATH)
        mod._DEFAULT_TASK_PATH, mod._DEFAULT_PROGRESS_PATH = task_path, progress_path
        try:
            resp = await client.get("/api/tasks?status=completed")
            data = resp.json()
            assert len(data["tasks"]) == 1
            assert data["tasks"][0]["id"] == "task-001"
        finally:
            mod._DEFAULT_TASK_PATH, mod._DEFAULT_PROGRESS_PATH = orig

    @pytest.mark.asyncio
    async def test_merged_progress(self, client, tmp_data):
        task_path, progress_path = tmp_data
        import app.routes.tasks as mod
        orig = (mod._DEFAULT_TASK_PATH, mod._DEFAULT_PROGRESS_PATH)
        mod._DEFAULT_TASK_PATH, mod._DEFAULT_PROGRESS_PATH = task_path, progress_path
        try:
            resp = await client.get("/api/tasks")
            data = resp.json()
            t1 = next(t for t in data["tasks"] if t["id"] == "task-001")
            assert t1["progress"] is not None
            assert t1["progress"]["git_sha"] == "abc1234"
            t3 = next(t for t in data["tasks"] if t["id"] == "task-003")
            assert t3["progress"] is None
        finally:
            mod._DEFAULT_TASK_PATH, mod._DEFAULT_PROGRESS_PATH = orig


class TestTaskDetailEndpoint:
    @pytest.mark.asyncio
    async def test_existing(self, client, tmp_data):
        task_path, progress_path = tmp_data
        import app.routes.tasks as mod
        orig = (mod._DEFAULT_TASK_PATH, mod._DEFAULT_PROGRESS_PATH)
        mod._DEFAULT_TASK_PATH, mod._DEFAULT_PROGRESS_PATH = task_path, progress_path
        try:
            resp = await client.get("/api/tasks/task-001")
            assert resp.status_code == 200
            assert resp.json()["id"] == "task-001"
        finally:
            mod._DEFAULT_TASK_PATH, mod._DEFAULT_PROGRESS_PATH = orig

    @pytest.mark.asyncio
    async def test_nonexistent(self, client, tmp_data):
        task_path, progress_path = tmp_data
        import app.routes.tasks as mod
        orig = (mod._DEFAULT_TASK_PATH, mod._DEFAULT_PROGRESS_PATH)
        mod._DEFAULT_TASK_PATH, mod._DEFAULT_PROGRESS_PATH = task_path, progress_path
        try:
            resp = await client.get("/api/tasks/task-999")
            assert resp.status_code == 404
        finally:
            mod._DEFAULT_TASK_PATH, mod._DEFAULT_PROGRESS_PATH = orig

"""
TaskFileManager 单元测试

覆盖 TaskFileManager 的所有公共方法和边界场景：
- read_tasks: 正常读取、文件不存在、JSON 格式错误、数据校验失败
- write_tasks: 正常写入、自动创建目录、自动备份
- update_task_status: 正常更新、附带错误信息、任务 ID 不存在
- get_task: 正常获取、任务 ID 不存在
- get_pending_tasks: 有待执行任务、无待执行任务
"""

import json
from pathlib import Path

import pytest

from agent_automation_system.file_io.task_file_manager import TaskFileManager
from agent_automation_system.models.task import Task, TaskPriority, TaskStatus
from agent_automation_system.models.task_json import TaskJSON


# ─── Fixtures ──────────────────────────────────────


@pytest.fixture
def tmp_dirs(tmp_path: Path):
    """创建临时目录结构"""
    data_dir = tmp_path / "data"
    backup_dir = data_dir / "backup"
    data_dir.mkdir()
    backup_dir.mkdir()
    return data_dir, backup_dir


@pytest.fixture
def task_file_manager(tmp_dirs):
    """创建使用临时目录的 TaskFileManager 实例"""
    data_dir, backup_dir = tmp_dirs
    return TaskFileManager(
        file_path=data_dir / "task.json",
        backup_dir=backup_dir,
    )


@pytest.fixture
def valid_task_json() -> TaskJSON:
    """返回一个合法的 TaskJSON 对象"""
    return TaskJSON(
        project_name="测试项目",
        description="用于单元测试的项目",
        created_by="PM-Agent",
        total_tasks=3,
        tasks=[
            Task(
                id="task-001",
                title="创建项目结构",
                description="初始化项目目录和基础文件",
                dependencies=[],
                suggested_role="dev",
                priority=TaskPriority.HIGH,
                status=TaskStatus.PENDING,
            ),
            Task(
                id="task-002",
                title="配置 CI 流水线",
                description="创建 CI 配置文件",
                dependencies=["task-001"],
                suggested_role="dev",
                priority=TaskPriority.MEDIUM,
                status=TaskStatus.PENDING,
            ),
            Task(
                id="task-003",
                title="编写单元测试",
                description="为核心模块编写测试",
                dependencies=["task-001"],
                suggested_role="qa",
                priority=TaskPriority.MEDIUM,
                status=TaskStatus.PENDING,
            ),
        ],
    )


@pytest.fixture
def task_json_data() -> dict:
    """返回合法的 task.json 原始数据字典"""
    return {
        "project_name": "测试项目",
        "description": "用于单元测试",
        "created_by": "PM-Agent",
        "created_at": "2026-05-16T10:00:00Z",
        "total_tasks": 2,
        "tasks": [
            {
                "id": "task-001",
                "title": "任务一",
                "description": "第一个任务",
                "dependencies": [],
                "suggested_role": "dev",
                "priority": "high",
                "status": "pending",
            },
            {
                "id": "task-002",
                "title": "任务二",
                "description": "第二个任务",
                "dependencies": ["task-001"],
                "suggested_role": "qa",
                "priority": "medium",
                "status": "pending",
            },
        ],
    }


# ─── read_tasks 测试 ───────────────────────────────


class TestReadTasks:
    """read_tasks() 方法测试"""

    def test_read_valid_file(self, task_file_manager, task_json_data):
        """正常读取合法的 task.json 文件"""
        # 先写入文件
        file_path = task_file_manager.file_path
        file_path.write_text(json.dumps(task_json_data, ensure_ascii=False), encoding="utf-8")

        result = task_file_manager.read_tasks()
        assert isinstance(result, TaskJSON)
        assert result.project_name == "测试项目"
        assert result.total_tasks == 2
        assert len(result.tasks) == 2
        assert result.tasks[0].id == "task-001"
        assert result.tasks[1].dependencies == ["task-001"]

    def test_read_nonexistent_file(self, task_file_manager):
        """读取不存在的文件应抛出 FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            task_file_manager.read_tasks()

    def test_read_invalid_json(self, task_file_manager):
        """读取 JSON 格式错误的文件应抛出 json.JSONDecodeError"""
        task_file_manager.file_path.write_text("{invalid json content", encoding="utf-8")
        with pytest.raises(json.JSONDecodeError):
            task_file_manager.read_tasks()

    def test_read_invalid_data(self, task_file_manager):
        """读取数据校验失败的文件应抛出 ValidationError"""
        # total_tasks 与实际 tasks 数量不匹配
        bad_data = {
            "project_name": "测试项目",
            "total_tasks": 5,  # 实际只有 1 个 task
            "tasks": [
                {
                    "id": "task-001",
                    "title": "任务一",
                    "description": "描述",
                },
            ],
        }
        task_file_manager.file_path.write_text(
            json.dumps(bad_data, ensure_ascii=False), encoding="utf-8"
        )
        with pytest.raises(Exception):  # pydantic.ValidationError
            task_file_manager.read_tasks()


# ─── write_tasks 测试 ──────────────────────────────


class TestWriteTasks:
    """write_tasks() 方法测试"""

    def test_write_creates_file(self, task_file_manager, valid_task_json):
        """正常写入应创建 task.json 文件"""
        task_file_manager.write_tasks(valid_task_json)

        assert task_file_manager.file_path.exists()

        # 验证写入的内容可以正确读回
        result = task_file_manager.read_tasks()
        assert result.project_name == "测试项目"
        assert result.total_tasks == 3
        assert len(result.tasks) == 3

    def test_write_creates_parent_directory(self, tmp_path):
        """写入时应自动创建父目录"""
        deep_path = tmp_path / "deep" / "nested" / "dir" / "task.json"
        backup_dir = tmp_path / "backup"
        backup_dir.mkdir()
        mgr = TaskFileManager(file_path=deep_path, backup_dir=backup_dir)

        task_json = TaskJSON(
            project_name="嵌套目录测试",
            total_tasks=1,
            tasks=[
                Task(
                    id="task-001",
                    title="测试任务",
                    description="测试自动创建目录",
                )
            ],
        )
        mgr.write_tasks(task_json)
        assert deep_path.exists()

    def test_write_creates_backup_on_overwrite(self, task_file_manager, valid_task_json):
        """覆盖写入时应自动备份已有文件"""
        # 第一次写入
        task_file_manager.write_tasks(valid_task_json)
        original_content = task_file_manager.file_path.read_text(encoding="utf-8")

        # 修改后第二次写入
        modified = valid_task_json.model_copy(
            update={"project_name": "修改后的项目"}
        )
        # 需要更新 total_tasks 和 tasks 列表长度一致
        modified = TaskJSON(
            project_name="修改后的项目",
            total_tasks=1,
            tasks=[valid_task_json.tasks[0]],
        )
        task_file_manager.write_tasks(modified)

        # 验证备份文件存在
        backup_files = list(task_file_manager.backup_dir.glob("task.json.*.bak"))
        assert len(backup_files) == 1, f"应有一个备份文件，实际: {backup_files}"

        # 验证备份内容与原始文件一致
        backup_content = backup_files[0].read_text(encoding="utf-8")
        assert backup_content == original_content

    def test_write_no_backup_on_first_write(self, task_file_manager, valid_task_json):
        """首次写入（文件不存在时）不应创建备份"""
        task_file_manager.write_tasks(valid_task_json)

        backup_files = list(task_file_manager.backup_dir.glob("task.json.*.bak"))
        assert len(backup_files) == 0, "首次写入不应创建备份"

    def test_write_and_read_roundtrip(self, task_file_manager, valid_task_json):
        """写入后读回应保持数据一致"""
        task_file_manager.write_tasks(valid_task_json)
        result = task_file_manager.read_tasks()

        assert result.project_name == valid_task_json.project_name
        assert result.total_tasks == valid_task_json.total_tasks
        assert len(result.tasks) == len(valid_task_json.tasks)

        for original, loaded in zip(valid_task_json.tasks, result.tasks):
            assert original.id == loaded.id
            assert original.title == loaded.title
            assert original.description == loaded.description
            assert original.dependencies == loaded.dependencies
            assert original.status == loaded.status


# ─── update_task_status 测试 ────────────────────────


class TestUpdateTaskStatus:
    """update_task_status() 方法测试"""

    def test_update_status_to_in_progress(self, task_file_manager, valid_task_json):
        """更新任务状态为 in_progress"""
        task_file_manager.write_tasks(valid_task_json)

        result = task_file_manager.update_task_status("task-001", TaskStatus.IN_PROGRESS)
        assert result.status == TaskStatus.IN_PROGRESS

        # 验证持久化
        reloaded = task_file_manager.read_tasks()
        task = reloaded.tasks[0]
        assert task.status == TaskStatus.IN_PROGRESS

    def test_update_status_to_completed(self, task_file_manager, valid_task_json):
        """更新任务状态为 completed"""
        task_file_manager.write_tasks(valid_task_json)

        result = task_file_manager.update_task_status("task-001", TaskStatus.COMPLETED)
        assert result.status == TaskStatus.COMPLETED

    def test_update_status_with_error_message(self, task_file_manager, valid_task_json):
        """更新状态为 failed 并附带错误信息"""
        task_file_manager.write_tasks(valid_task_json)

        result = task_file_manager.update_task_status(
            "task-002",
            TaskStatus.FAILED,
            error_message="Git push 超时",
        )
        assert result.status == TaskStatus.FAILED
        assert result.error_message == "Git push 超时"

        # 验证持久化
        reloaded = task_file_manager.read_tasks()
        task = reloaded.tasks[1]
        assert task.error_message == "Git push 超时"

    def test_update_status_nonexistent_task(self, task_file_manager, valid_task_json):
        """更新不存在的任务 ID 应抛出 KeyError"""
        task_file_manager.write_tasks(valid_task_json)

        with pytest.raises(KeyError, match="task-999"):
            task_file_manager.update_task_status("task-999", TaskStatus.COMPLETED)

    def test_update_triggers_backup(self, task_file_manager, valid_task_json):
        """更新状态时应触发备份"""
        task_file_manager.write_tasks(valid_task_json)

        task_file_manager.update_task_status("task-001", TaskStatus.IN_PROGRESS)

        backup_files = list(task_file_manager.backup_dir.glob("task.json.*.bak"))
        assert len(backup_files) >= 1, "更新状态应触发备份"


# ─── get_task 测试 ──────────────────────────────────


class TestGetTask:
    """get_task() 方法测试"""

    def test_get_existing_task(self, task_file_manager, valid_task_json):
        """获取已存在的任务"""
        task_file_manager.write_tasks(valid_task_json)

        result = task_file_manager.get_task("task-001")
        assert result.id == "task-001"
        assert result.title == "创建项目结构"

    def test_get_task_with_dependencies(self, task_file_manager, valid_task_json):
        """获取有依赖的任务"""
        task_file_manager.write_tasks(valid_task_json)

        result = task_file_manager.get_task("task-002")
        assert result.dependencies == ["task-001"]

    def test_get_nonexistent_task(self, task_file_manager, valid_task_json):
        """获取不存在的任务应抛出 KeyError"""
        task_file_manager.write_tasks(valid_task_json)

        with pytest.raises(KeyError, match="task-999"):
            task_file_manager.get_task("task-999")

    def test_get_task_without_file(self, task_file_manager):
        """文件不存在时获取任务应抛出 FileNotFoundError"""
        with pytest.raises(FileNotFoundError):
            task_file_manager.get_task("task-001")


# ─── get_pending_tasks 测试 ──────────────────────────


class TestGetPendingTasks:
    """get_pending_tasks() 方法测试"""

    def test_get_all_pending(self, task_file_manager, valid_task_json):
        """所有任务都是 pending 状态"""
        task_file_manager.write_tasks(valid_task_json)

        pending = task_file_manager.get_pending_tasks()
        assert len(pending) == 3
        assert all(t.status == TaskStatus.PENDING for t in pending)

    def test_get_some_pending(self, task_file_manager, valid_task_json):
        """部分任务已完成"""
        task_file_manager.write_tasks(valid_task_json)

        # 完成第一个任务
        task_file_manager.update_task_status("task-001", TaskStatus.COMPLETED)

        pending = task_file_manager.get_pending_tasks()
        assert len(pending) == 2
        pending_ids = {t.id for t in pending}
        assert "task-001" not in pending_ids
        assert "task-002" in pending_ids
        assert "task-003" in pending_ids

    def test_get_no_pending(self, task_file_manager, valid_task_json):
        """所有任务都已完成"""
        task_file_manager.write_tasks(valid_task_json)

        task_file_manager.update_task_status("task-001", TaskStatus.COMPLETED)
        task_file_manager.update_task_status("task-002", TaskStatus.COMPLETED)
        task_file_manager.update_task_status("task-003", TaskStatus.COMPLETED)

        pending = task_file_manager.get_pending_tasks()
        assert len(pending) == 0


# ─── 边界和集成场景 ──────────────────────────────────


class TestEdgeCases:
    """边界场景和集成测试"""

    def test_overwrite_creates_backup(
        self, task_file_manager, valid_task_json
    ):
        """覆盖写入应创建备份文件"""
        task_file_manager.write_tasks(valid_task_json)

        modified = TaskJSON(
            project_name="修改后版本",
            total_tasks=1,
            tasks=[valid_task_json.tasks[0]],
        )
        task_file_manager.write_tasks(modified)

        # 备份文件存在（注意：同秒内多次写入会覆盖同名备份，这是预期行为）
        backup_files = list(task_file_manager.backup_dir.glob("task.json.*.bak"))
        assert len(backup_files) >= 1, f"应至少有 1 个备份，实际: {len(backup_files)}"

        # 备份内容应为原始数据
        backup_content = backup_files[0].read_text(encoding="utf-8")
        assert "测试项目" in backup_content, "备份应包含原始项目名称"

    def test_single_task_json(self, task_file_manager):
        """只包含一个任务的 task.json"""
        single = TaskJSON(
            project_name="单任务项目",
            total_tasks=1,
            tasks=[
                Task(
                    id="task-001",
                    title="唯一任务",
                    description="只有一个任务",
                )
            ],
        )
        task_file_manager.write_tasks(single)
        result = task_file_manager.read_tasks()
        assert result.total_tasks == 1
        assert len(result.tasks) == 1

    def test_status_transitions(self, task_file_manager, valid_task_json):
        """完整状态流转：pending → in_progress → completed"""
        task_file_manager.write_tasks(valid_task_json)

        # pending → in_progress
        task = task_file_manager.update_task_status("task-001", TaskStatus.IN_PROGRESS)
        assert task.status == TaskStatus.IN_PROGRESS

        # in_progress → completed
        task = task_file_manager.update_task_status("task-001", TaskStatus.COMPLETED)
        assert task.status == TaskStatus.COMPLETED

        # 最终验证
        final = task_file_manager.get_task("task-001")
        assert final.status == TaskStatus.COMPLETED

    def test_failed_with_retry(self, task_file_manager, valid_task_json):
        """任务失败并附带错误信息"""
        task_file_manager.write_tasks(valid_task_json)

        task = task_file_manager.update_task_status(
            "task-002",
            TaskStatus.FAILED,
            error_message="测试执行超时",
        )
        assert task.status == TaskStatus.FAILED
        assert task.error_message == "测试执行超时"

"""
P1-063: 集成测试 — 文件系统状态流转（task.json → progress.txt → memory.md）

验证三个文件管理器在任务执行过程中的协同工作：
  1. TaskFileManager  → task.json 任务状态读写
  2. ProgressManager  → progress.txt 进度条目读写
  3. MemoryManager    → memory.md 知识库追加/搜索

核心验证场景：
  - 任务状态变化时 task.json 与 progress.txt 的一致性
  - 任务执行完成后 memory.md 记录经验
  - 完整任务生命周期中三个文件的状态流转
  - 跨文件数据引用完整性（task_id / role / git_sha）
  - 并发写入与覆盖场景
  - 异常恢复后的文件状态
"""

import json
from datetime import datetime
from pathlib import Path

import pytest

from agent_automation_system.file_io.memory_manager import MemoryManager
from agent_automation_system.file_io.progress_manager import ProgressManager
from agent_automation_system.file_io.task_file_manager import TaskFileManager
from agent_automation_system.models.memory_entry import MemoryEntry
from agent_automation_system.models.progress import ProgressEntry, ProgressStatus
from agent_automation_system.models.task import BDDSpec, Task, TaskPriority, TaskStatus
from agent_automation_system.models.task_json import TaskJSON


# ── 工具函数 ──────────────────────────────────────────

def _make_task(task_id: str = "task-001", **overrides) -> Task:
    """创建测试用 Task"""
    defaults = dict(
        id=task_id,
        title=f"测试任务 {task_id}",
        description=f"用于集成测试的 {task_id} 任务",
        bdd=BDDSpec(given="前置条件", when="执行操作", then="预期结果"),
        test_script=f"tests/test_{task_id}.py",
        dependencies=[],
        suggested_role="senior-developer",
        priority=TaskPriority.HIGH,
    )
    defaults.update(overrides)
    return Task(**defaults)


def _make_task_json(tasks: list[Task] | None = None, **overrides) -> TaskJSON:
    """创建测试用 TaskJSON"""
    task_list = tasks or [_make_task()]
    defaults = dict(
        project_name="集成测试项目",
        description="文件系统状态流转集成测试",
        created_by="IntegrationTest",
        total_tasks=len(task_list),
        tasks=task_list,
    )
    defaults.update(overrides)
    return TaskJSON(**defaults)


def _setup_managers(tmp_path: Path):
    """创建三个文件管理器并返回"""
    task_path = tmp_path / "task.json"
    progress_path = tmp_path / "progress.txt"
    memory_path = tmp_path / "memory.md"
    backup_dir = tmp_path / "backup"

    tfm = TaskFileManager(file_path=task_path, backup_dir=backup_dir)
    pm = ProgressManager(file_path=progress_path)
    mm = MemoryManager(file_path=memory_path)

    return tfm, pm, mm


# ══════════════════════════════════════════════════════════
# 1. 任务创建 → task.json 写入与读取
# ══════════════════════════════════════════════════════════
class TestTaskJsonWriteAndRead:
    """task.json 写入后读取一致性验证"""

    def test_write_then_read_round_trip(self, tmp_path):
        """写入 task.json 后读取内容一致"""
        tfm, _, _ = _setup_managers(tmp_path)
        task_json = _make_task_json()

        tfm.write_tasks(task_json)
        loaded = tfm.read_tasks()

        assert loaded.project_name == task_json.project_name
        assert loaded.total_tasks == task_json.total_tasks
        assert len(loaded.tasks) == len(task_json.tasks)
        assert loaded.tasks[0].id == task_json.tasks[0].id
        assert loaded.tasks[0].status == TaskStatus.PENDING

    def test_write_creates_backup(self, tmp_path):
        """第二次写入时自动创建备份"""
        tfm, _, _ = _setup_managers(tmp_path)

        # 第一次写入
        tfm.write_tasks(_make_task_json())
        # 第二次写入（触发备份）
        tfm.write_tasks(_make_task_json())

        backup_dir = tmp_path / "backup"
        assert backup_dir.exists()
        backups = list(backup_dir.glob("task.json.*.bak"))
        assert len(backups) == 1

    def test_read_nonexistent_file_raises(self, tmp_path):
        """读取不存在的文件抛 FileNotFoundError"""
        tfm, _, _ = _setup_managers(tmp_path)
        with pytest.raises(FileNotFoundError):
            tfm.read_tasks()

    def test_json_format_is_valid(self, tmp_path):
        """写入的文件是合法 JSON"""
        tfm, _, _ = _setup_managers(tmp_path)
        tfm.write_tasks(_make_task_json())

        content = (tmp_path / "task.json").read_text(encoding="utf-8")
        parsed = json.loads(content)
        assert "project_name" in parsed
        assert "tasks" in parsed


# ══════════════════════════════════════════════════════════
# 2. 状态流转：PENDING → IN_PROGRESS → COMPLETED
# ══════════════════════════════════════════════════════════
class TestTaskStatusTransitions:
    """task.json 中任务状态流转验证"""

    def test_pending_to_in_progress(self, tmp_path):
        """PENDING → IN_PROGRESS 状态更新"""
        tfm, _, _ = _setup_managers(tmp_path)
        tfm.write_tasks(_make_task_json())

        task = tfm.update_task_status("task-001", TaskStatus.IN_PROGRESS)
        assert task.status == TaskStatus.IN_PROGRESS

        # 验证持久化
        loaded = tfm.read_tasks()
        assert loaded.tasks[0].status == TaskStatus.IN_PROGRESS

    def test_in_progress_to_completed(self, tmp_path):
        """IN_PROGRESS → COMPLETED 状态更新"""
        tfm, _, _ = _setup_managers(tmp_path)
        tfm.write_tasks(_make_task_json())

        tfm.update_task_status("task-001", TaskStatus.IN_PROGRESS)
        task = tfm.update_task_status("task-001", TaskStatus.COMPLETED)
        assert task.status == TaskStatus.COMPLETED

    def test_pending_to_failed_with_error(self, tmp_path):
        """PENDING → FAILED 并记录错误信息"""
        tfm, _, _ = _setup_managers(tmp_path)
        tfm.write_tasks(_make_task_json())

        task = tfm.update_task_status(
            "task-001", TaskStatus.FAILED, error_message="编译错误"
        )
        assert task.status == TaskStatus.FAILED
        assert task.error_message == "编译错误"

    def test_pending_to_blocked(self, tmp_path):
        """PENDING → BLOCKED 状态更新"""
        tfm, _, _ = _setup_managers(tmp_path)
        tfm.write_tasks(_make_task_json())

        task = tfm.update_task_status("task-001", TaskStatus.BLOCKED)
        assert task.status == TaskStatus.BLOCKED

    def test_update_nonexistent_task_raises(self, tmp_path):
        """更新不存在的 task_id 抛 KeyError"""
        tfm, _, _ = _setup_managers(tmp_path)
        tfm.write_tasks(_make_task_json())

        with pytest.raises(KeyError, match="not found"):
            tfm.update_task_status("task-999", TaskStatus.COMPLETED)

    def test_get_pending_tasks(self, tmp_path):
        """获取所有 PENDING 状态任务"""
        tfm, _, _ = _setup_managers(tmp_path)
        tasks = [
            _make_task("task-001"),
            _make_task("task-002"),
        ]
        tfm.write_tasks(_make_task_json(tasks))

        pending = tfm.get_pending_tasks()
        assert len(pending) == 2

        # 将 task-001 标记为 COMPLETED
        tfm.update_task_status("task-001", TaskStatus.COMPLETED)
        pending = tfm.get_pending_tasks()
        assert len(pending) == 1
        assert pending[0].id == "task-002"


# ══════════════════════════════════════════════════════════
# 3. progress.txt 与 task.json 状态同步
# ══════════════════════════════════════════════════════════
class TestProgressTaskJsonSync:
    """progress.txt 与 task.json 状态同步验证"""

    def test_task_start_syncs_to_progress(self, tmp_path):
        """task.json 设为 IN_PROGRESS 时，progress.txt 记录 IN_PROGRESS"""
        tfm, pm, _ = _setup_managers(tmp_path)
        tfm.write_tasks(_make_task_json())

        # 更新 task.json 状态
        tfm.update_task_status("task-001", TaskStatus.IN_PROGRESS)

        # 同步写入 progress.txt
        pm.write_entry(ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.IN_PROGRESS,
            role="senior-developer",
            started=datetime(2026, 5, 19, 10, 0, 0),
        ))

        # 验证一致性
        task = tfm.get_task("task-001")
        entry = pm.get_entry("task-001")
        assert task.status == TaskStatus.IN_PROGRESS
        assert entry.status == ProgressStatus.IN_PROGRESS
        assert entry.role == "senior-developer"

    def test_task_complete_syncs_to_progress(self, tmp_path):
        """task.json 设为 COMPLETED 时，progress.txt 记录 COMPLETED + git 信息"""
        tfm, pm, _ = _setup_managers(tmp_path)
        tfm.write_tasks(_make_task_json())

        tfm.update_task_status("task-001", TaskStatus.COMPLETED)
        pm.write_entry(ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.COMPLETED,
            role="senior-developer",
            started=datetime(2026, 5, 19, 10, 0, 0),
            finished=datetime(2026, 5, 19, 10, 30, 0),
            git_sha="a1b2c3d",
            git_msg="[task-001] senior-developer: 实现测试任务",
        ))

        task = tfm.get_task("task-001")
        entry = pm.get_entry("task-001")
        assert task.status == TaskStatus.COMPLETED
        assert entry.status == ProgressStatus.COMPLETED
        assert entry.git_sha == "a1b2c3d"
        assert entry.finished is not None

    def test_task_failed_syncs_to_progress_with_error(self, tmp_path):
        """task.json 设为 FAILED 时，progress.txt 记录 FAILED + error"""
        tfm, pm, _ = _setup_managers(tmp_path)
        tfm.write_tasks(_make_task_json())

        tfm.update_task_status("task-001", TaskStatus.FAILED, error_message="编译失败")
        pm.write_entry(ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.FAILED,
            role="senior-developer",
            error="编译失败",
        ))

        task = tfm.get_task("task-001")
        entry = pm.get_entry("task-001")
        assert task.status == TaskStatus.FAILED
        assert entry.status == ProgressStatus.FAILED
        assert entry.error == "编译失败"

    def test_multiple_tasks_progress_sync(self, tmp_path):
        """多个任务的状态同步"""
        tfm, pm, _ = _setup_managers(tmp_path)
        tasks = [
            _make_task("task-001"),
            _make_task("task-002", dependencies=["task-001"], suggested_role="test-engineer"),
            _make_task("task-003", dependencies=["task-001"]),
        ]
        tfm.write_tasks(_make_task_json(tasks))

        # task-001 完成
        tfm.update_task_status("task-001", TaskStatus.COMPLETED)
        pm.write_entry(ProgressEntry(
            task_id="task-001", status=ProgressStatus.COMPLETED,
            role="senior-developer",
            started=datetime(2026, 5, 19, 10, 0, 0),
            finished=datetime(2026, 5, 19, 10, 30, 0),
        ))

        # task-002 开始
        tfm.update_task_status("task-002", TaskStatus.IN_PROGRESS)
        pm.write_entry(ProgressEntry(
            task_id="task-002", status=ProgressStatus.IN_PROGRESS,
            role="test-engineer",
            started=datetime(2026, 5, 19, 10, 35, 0),
        ))

        # task-003 阻塞
        tfm.update_task_status("task-003", TaskStatus.BLOCKED)
        pm.write_entry(ProgressEntry(
            task_id="task-003", status=ProgressStatus.BLOCKED,
            role="senior-developer",
        ))

        # 验证进度统计
        assert pm.get_completed_count() == 1

        # 验证每个条目
        e1 = pm.get_entry("task-001")
        e2 = pm.get_entry("task-002")
        e3 = pm.get_entry("task-003")
        assert e1.status == ProgressStatus.COMPLETED
        assert e2.status == ProgressStatus.IN_PROGRESS
        assert e3.status == ProgressStatus.BLOCKED

    def test_progress_update_replaces_existing_entry(self, tmp_path):
        """更新 progress.txt 中已有条目（同 task_id）"""
        tfm, pm, _ = _setup_managers(tmp_path)
        tfm.write_tasks(_make_task_json())

        # 先写 IN_PROGRESS
        pm.write_entry(ProgressEntry(
            task_id="task-001", status=ProgressStatus.IN_PROGRESS,
            role="senior-developer",
        ))

        # 再写 COMPLETED（替换）
        pm.write_entry(ProgressEntry(
            task_id="task-001", status=ProgressStatus.COMPLETED,
            role="senior-developer",
            git_sha="abc123",
        ))

        entries = pm.read_progress()
        assert len(entries) == 1
        assert entries[0].status == ProgressStatus.COMPLETED
        assert entries[0].git_sha == "abc123"


# ══════════════════════════════════════════════════════════
# 4. memory.md 与执行结果关联
# ══════════════════════════════════════════════════════════
class TestMemoryWithExecutionResults:
    """memory.md 记录执行结果与经验验证"""

    def test_record_lesson_after_task_completion(self, tmp_path):
        """任务完成后在 memory.md 记录经验教训"""
        _, _, mm = _setup_managers(tmp_path)

        mm.append(MemoryEntry(
            title="Learnings",
            content="- task-001: 使用 pytest fixture 管理 tmp_path 可避免文件残留",
            tags=["testing", "task-001"],
        ))

        results = mm.search("task-001")
        assert len(results) == 1
        assert "pytest" in results[0].content

    def test_record_key_decision(self, tmp_path):
        """记录关键决策到 memory.md"""
        _, _, mm = _setup_managers(tmp_path)

        mm.append(MemoryEntry(
            title="Key Decisions",
            content="采用 pydantic v2 做数据校验，而非 dataclasses",
            tags=["architecture"],
        ))

        section = mm.read_section("Key Decisions")
        assert section is not None
        assert "pydantic" in section.content

    def test_search_by_tag(self, tmp_path):
        """通过标签搜索 memory.md"""
        _, _, mm = _setup_managers(tmp_path)

        mm.append(MemoryEntry(
            title="Testing Patterns",
            content="使用 tmp_path fixture 创建临时文件",
            tags=["testing", "pytest"],
        ))
        mm.append(MemoryEntry(
            title="Architecture",
            content="依赖注入模式用于解耦",
            tags=["architecture", "design"],
        ))

        results = mm.search("pytest")
        assert len(results) == 1
        assert results[0].title == "Testing Patterns"

    def test_replace_section(self, tmp_path):
        """替换 memory.md 中的 section"""
        _, _, mm = _setup_managers(tmp_path)

        mm.append(MemoryEntry(
            title="Current State",
            content="正在开发 P1-063",
        ))
        mm.replace_section(MemoryEntry(
            title="Current State",
            content="P1-063 已完成，进入 P1-064",
        ))

        section = mm.read_section("Current State")
        assert "P1-064" in section.content

    def test_delete_section(self, tmp_path):
        """删除 memory.md 中的 section"""
        _, _, mm = _setup_managers(tmp_path)

        mm.append(MemoryEntry(title="Temporary", content="临时内容"))
        assert mm.read_section("Temporary") is not None

        deleted = mm.delete_section("Temporary")
        assert deleted is True
        assert mm.read_section("Temporary") is None


# ══════════════════════════════════════════════════════════
# 5. 完整任务生命周期文件状态流转
# ══════════════════════════════════════════════════════════
class TestFullLifecycleStateFlow:
    """完整任务生命周期中三个文件的协同流转"""

    def test_single_task_full_lifecycle(self, tmp_path):
        """单任务完整生命周期：创建→执行→完成→记录"""
        tfm, pm, mm = _setup_managers(tmp_path)

        # Step 1: 创建任务 → task.json
        task_json = _make_task_json()
        tfm.write_tasks(task_json)

        task = tfm.get_task("task-001")
        assert task.status == TaskStatus.PENDING

        # Step 2: 开始执行 → task.json IN_PROGRESS + progress.txt IN_PROGRESS
        tfm.update_task_status("task-001", TaskStatus.IN_PROGRESS)
        pm.write_entry(ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.IN_PROGRESS,
            role="senior-developer",
            started=datetime(2026, 5, 19, 10, 0, 0),
        ))

        assert tfm.get_task("task-001").status == TaskStatus.IN_PROGRESS
        assert pm.get_entry("task-001").status == ProgressStatus.IN_PROGRESS

        # Step 3: 完成 → task.json COMPLETED + progress.txt COMPLETED
        tfm.update_task_status("task-001", TaskStatus.COMPLETED)
        pm.write_entry(ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.COMPLETED,
            role="senior-developer",
            started=datetime(2026, 5, 19, 10, 0, 0),
            finished=datetime(2026, 5, 19, 10, 30, 0),
            git_sha="a1b2c3d",
            git_msg="[task-001] senior-developer: 完成测试任务",
        ))

        assert tfm.get_task("task-001").status == TaskStatus.COMPLETED
        entry = pm.get_entry("task-001")
        assert entry.status == ProgressStatus.COMPLETED
        assert entry.git_sha == "a1b2c3d"

        # Step 4: 记录经验 → memory.md
        mm.append(MemoryEntry(
            title="Learnings",
            content="- task-001: 任务执行耗时约 30 分钟",
            tags=["task-001", "performance"],
        ))

        results = mm.search("task-001")
        assert len(results) == 1

    def test_failed_task_lifecycle(self, tmp_path):
        """失败任务生命周期：创建→执行→失败→记录错误"""
        tfm, pm, mm = _setup_managers(tmp_path)

        tfm.write_tasks(_make_task_json())
        tfm.update_task_status("task-001", TaskStatus.IN_PROGRESS)
        pm.write_entry(ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.IN_PROGRESS,
            role="senior-developer",
            started=datetime(2026, 5, 19, 10, 0, 0),
        ))

        # 任务失败
        tfm.update_task_status("task-001", TaskStatus.FAILED, error_message="断言失败")
        pm.write_entry(ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.FAILED,
            role="senior-developer",
            error="断言失败",
        ))

        # 记录失败经验
        mm.append(MemoryEntry(
            title="Failed Tasks",
            content="- task-001: 断言失败，需检查边界条件",
            tags=["task-001", "failure"],
        ))

        assert tfm.get_task("task-001").status == TaskStatus.FAILED
        assert pm.get_entry("task-001").status == ProgressStatus.FAILED
        assert mm.search("task-001")[0].content == "- task-001: 断言失败，需检查边界条件"

    def test_retry_task_lifecycle(self, tmp_path):
        """重试任务生命周期：失败→重试→成功"""
        tfm, pm, _ = _setup_managers(tmp_path)

        tfm.write_tasks(_make_task_json())

        # 第一次尝试失败
        tfm.update_task_status("task-001", TaskStatus.FAILED, error_message="超时")
        pm.write_entry(ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.FAILED,
            role="senior-developer",
            error="超时",
            retry=0,
        ))

        # 重试：重置为 IN_PROGRESS
        tfm.update_task_status("task-001", TaskStatus.IN_PROGRESS)
        pm.write_entry(ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.RETRYING,
            role="senior-developer",
            retry=1,
        ))

        # 第二次成功
        tfm.update_task_status("task-001", TaskStatus.COMPLETED)
        pm.write_entry(ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.COMPLETED,
            role="senior-developer",
            retry=1,
            git_sha="def456",
        ))

        assert tfm.get_task("task-001").status == TaskStatus.COMPLETED
        entry = pm.get_entry("task-001")
        assert entry.status == ProgressStatus.COMPLETED
        assert entry.retry == 1

    def test_blocked_task_lifecycle(self, tmp_path):
        """阻塞任务生命周期：PENDING→BLOCKED→PENDING→IN_PROGRESS→COMPLETED"""
        tfm, pm, _ = _setup_managers(tmp_path)
        tasks = [
            _make_task("task-001"),
            _make_task("task-002", dependencies=["task-001"]),
        ]
        tfm.write_tasks(_make_task_json(tasks))

        # task-002 因依赖未满足被阻塞
        tfm.update_task_status("task-002", TaskStatus.BLOCKED)
        pm.write_entry(ProgressEntry(
            task_id="task-002",
            status=ProgressStatus.BLOCKED,
            role="test-engineer",
        ))

        # 依赖完成后解除阻塞
        tfm.update_task_status("task-001", TaskStatus.COMPLETED)
        tfm.update_task_status("task-002", TaskStatus.PENDING)
        pm.write_entry(ProgressEntry(
            task_id="task-002",
            status=ProgressStatus.IN_PROGRESS,
            role="test-engineer",
            started=datetime(2026, 5, 19, 11, 0, 0),
        ))

        # 完成
        tfm.update_task_status("task-002", TaskStatus.COMPLETED)
        pm.write_entry(ProgressEntry(
            task_id="task-002",
            status=ProgressStatus.COMPLETED,
            role="test-engineer",
            finished=datetime(2026, 5, 19, 11, 30, 0),
            git_sha="ghi789",
        ))

        assert tfm.get_task("task-002").status == TaskStatus.COMPLETED


# ══════════════════════════════════════════════════════════
# 6. 跨文件数据引用完整性
# ══════════════════════════════════════════════════════════
class TestCrossFileDataIntegrity:
    """跨文件数据引用完整性验证"""

    def test_task_id_consistency_across_files(self, tmp_path):
        """task_id 在 task.json 和 progress.txt 中一致"""
        tfm, pm, _ = _setup_managers(tmp_path)
        tfm.write_tasks(_make_task_json())

        tfm.update_task_status("task-001", TaskStatus.COMPLETED)
        pm.write_entry(ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.COMPLETED,
            role="senior-developer",
        ))

        task = tfm.get_task("task-001")
        entry = pm.get_entry("task-001")
        assert task.id == entry.task_id

    def test_role_consistency_across_files(self, tmp_path):
        """suggested_role 在 task.json 和 role 在 progress.txt 中一致"""
        tfm, pm, _ = _setup_managers(tmp_path)
        tasks = [
            _make_task("task-001", suggested_role="senior-developer"),
            _make_task("task-002", suggested_role="test-engineer"),
        ]
        tfm.write_tasks(_make_task_json(tasks))

        for t in tasks:
            pm.write_entry(ProgressEntry(
                task_id=t.id,
                status=ProgressStatus.COMPLETED,
                role=t.suggested_role,
            ))

        for t in tasks:
            entry = pm.get_entry(t.id)
            assert entry.role == t.suggested_role

    def test_git_sha_recorded_in_progress(self, tmp_path):
        """git_sha 在 progress.txt 中正确记录"""
        tfm, pm, _ = _setup_managers(tmp_path)
        tfm.write_tasks(_make_task_json())

        tfm.update_task_status("task-001", TaskStatus.COMPLETED)
        pm.write_entry(ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.COMPLETED,
            role="senior-developer",
            git_sha="a1b2c3d",
            git_msg="[task-001] senior-developer: done",
        ))

        entry = pm.get_entry("task-001")
        assert entry.git_sha == "a1b2c3d"

        # progress.txt 文件内容包含 git SHA
        content = (tmp_path / "progress.txt").read_text(encoding="utf-8")
        assert "a1b2c3d" in content

    def test_progress_file_format_matches_prd(self, tmp_path):
        """progress.txt 格式符合 PRD §6.3 规范"""
        _, pm, _ = _setup_managers(tmp_path)

        pm.write_entry(ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.COMPLETED,
            role="senior-developer",
            started=datetime(2026, 5, 19, 10, 0, 0),
            finished=datetime(2026, 5, 19, 10, 30, 0),
            git_sha="abc123",
            git_msg="[task-001] senior-developer: done",
        ))

        content = (tmp_path / "progress.txt").read_text(encoding="utf-8")
        # 验证 PRD §6.3 关键格式元素
        assert "[task-001]" in content
        assert "Status:" in content
        assert "COMPLETED" in content
        assert "Role:" in content
        assert "Started:" in content
        assert "Finished:" in content
        assert "Git SHA:" in content

    def test_memory_references_task_results(self, tmp_path):
        """memory.md 中引用的任务结果与 progress.txt 对应"""
        tfm, pm, mm = _setup_managers(tmp_path)
        tfm.write_tasks(_make_task_json())

        tfm.update_task_status("task-001", TaskStatus.COMPLETED)
        pm.write_entry(ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.COMPLETED,
            role="senior-developer",
            git_sha="abc123",
        ))

        # 在 memory.md 中记录该任务的 key result
        mm.append(MemoryEntry(
            title="Key Results",
            content="- task-001 (abc123): 成功实现测试任务",
            tags=["task-001"],
        ))

        # 通过搜索 task-001 可在 memory.md 找到对应记录
        results = mm.search("task-001")
        assert len(results) == 1
        assert "abc123" in results[0].content


# ══════════════════════════════════════════════════════════
# 7. 并发写入与覆盖场景
# ══════════════════════════════════════════════════════════
class TestConcurrentWriteAndOverwrite:
    """并发写入与覆盖场景验证"""

    def test_overwrite_task_status_multiple_times(self, tmp_path):
        """多次覆盖 task.json 状态"""
        tfm, _, _ = _setup_managers(tmp_path)
        tfm.write_tasks(_make_task_json())

        for status in [TaskStatus.IN_PROGRESS, TaskStatus.COMPLETED]:
            tfm.update_task_status("task-001", status)

        assert tfm.get_task("task-001").status == TaskStatus.COMPLETED

    def test_progress_update_status_multiple_times(self, tmp_path):
        """多次更新 progress.txt 同一任务状态"""
        _, pm, _ = _setup_managers(tmp_path)

        pm.update_status("task-001", ProgressStatus.IN_PROGRESS, role="dev")
        pm.update_status("task-001", ProgressStatus.COMPLETED, role="dev", git_sha="abc")

        entry = pm.get_entry("task-001")
        assert entry.status == ProgressStatus.COMPLETED
        assert entry.git_sha == "abc"

    def test_memory_append_same_title_merges(self, tmp_path):
        """memory.md 追加相同标题 section 合并 tags"""
        _, _, mm = _setup_managers(tmp_path)

        mm.append(MemoryEntry(
            title="Learnings",
            content="第一条经验",
            tags=["python"],
        ))
        mm.append(MemoryEntry(
            title="Learnings",
            content="第二条经验",
            tags=["testing"],
        ))

        section = mm.read_section("Learnings")
        # 第二次 append 替换内容为第二条，但合并 tags
        assert section.content == "第二条经验"
        assert "python" in section.tags
        assert "testing" in section.tags

    def test_sequential_writes_to_all_three_files(self, tmp_path):
        """顺序写入三个文件，验证最终一致性"""
        tfm, pm, mm = _setup_managers(tmp_path)

        # Round 1: task-001
        tfm.write_tasks(_make_task_json([_make_task("task-001")]))
        tfm.update_task_status("task-001", TaskStatus.COMPLETED)
        pm.write_entry(ProgressEntry(
            task_id="task-001", status=ProgressStatus.COMPLETED, role="dev",
        ))
        mm.append(MemoryEntry(title="Results", content="task-001 done", tags=["task-001"]))

        # Round 2: task-002
        tfm2_data = _make_task_json([_make_task("task-002")])
        # 写入新 task.json（会备份旧文件）
        tfm.write_tasks(tfm2_data)
        tfm.update_task_status("task-002", TaskStatus.COMPLETED)
        pm.write_entry(ProgressEntry(
            task_id="task-002", status=ProgressStatus.COMPLETED, role="dev",
        ))
        mm.append(MemoryEntry(title="Results", content="task-002 done", tags=["task-002"]))

        # 验证最终状态
        assert tfm.read_tasks().tasks[0].id == "task-002"
        entries = pm.read_progress()
        assert len(entries) == 2
        results = mm.search("done")
        assert len(results) == 1  # Results section 包含两条内容（但第二次 append 替换了）
        assert "task-002" in results[0].content


# ══════════════════════════════════════════════════════════
# 8. 异常恢复后的文件状态
# ══════════════════════════════════════════════════════════
class TestErrorRecoveryFileState:
    """异常恢复后文件状态验证"""

    def test_empty_progress_file_returns_empty_list(self, tmp_path):
        """空的 progress.txt 返回空列表"""
        _, pm, _ = _setup_managers(tmp_path)
        (tmp_path / "progress.txt").write_text("", encoding="utf-8")
        assert pm.read_progress() == []

    def test_empty_memory_file_returns_empty_list(self, tmp_path):
        """空的 memory.md 返回空列表"""
        _, _, mm = _setup_managers(tmp_path)
        (tmp_path / "memory.md").write_text("# Project Memory\n", encoding="utf-8")
        assert mm.read() == []

    def test_corrupted_task_json_raises(self, tmp_path):
        """损坏的 task.json 抛 JSON 解析异常"""
        tfm, _, _ = _setup_managers(tmp_path)
        (tmp_path / "task.json").write_text("{invalid json", encoding="utf-8")
        with pytest.raises(Exception):  # json.JSONDecodeError
            tfm.read_tasks()

    def test_progress_recovery_after_partial_write(self, tmp_path):
        """progress.txt 部分写入后可恢复已有条目"""
        _, pm, _ = _setup_managers(tmp_path)

        # 写入两个条目
        pm.write_entry(ProgressEntry(
            task_id="task-001", status=ProgressStatus.COMPLETED, role="dev",
        ))
        pm.write_entry(ProgressEntry(
            task_id="task-002", status=ProgressStatus.IN_PROGRESS, role="dev",
        ))

        # 模拟部分写入：追加不完整内容
        progress_path = tmp_path / "progress.txt"
        with open(progress_path, "a", encoding="utf-8") as f:
            f.write("\n[task-003]\n  Status:    IN_PROGRESS\n")

        # 已有条目仍可读取
        entries = pm.read_progress()
        assert len(entries) >= 2  # task-001 和 task-002 至少存在
        e1 = pm.get_entry("task-001")
        assert e1 is not None
        assert e1.status == ProgressStatus.COMPLETED

    def test_nonexistent_directories_auto_created(self, tmp_path):
        """文件路径中不存在的目录自动创建"""
        deep_path = tmp_path / "a" / "b" / "c"
        tfm = TaskFileManager(
            file_path=deep_path / "task.json",
            backup_dir=deep_path / "backup",
        )
        pm = ProgressManager(file_path=deep_path / "progress.txt")
        mm = MemoryManager(file_path=deep_path / "memory.md")

        tfm.write_tasks(_make_task_json())
        pm.write_entry(ProgressEntry(
            task_id="task-001", status=ProgressStatus.COMPLETED, role="dev",
        ))
        mm.append(MemoryEntry(title="Test", content="auto-created dirs"))

        assert (deep_path / "task.json").exists()
        assert (deep_path / "progress.txt").exists()
        assert (deep_path / "memory.md").exists()

    def test_backup_preserves_previous_state(self, tmp_path):
        """备份保留 task.json 前一个状态"""
        tfm, _, _ = _setup_managers(tmp_path)

        # 写入初始版本
        tfm.write_tasks(_make_task_json([_make_task("task-001")]))
        initial_content = (tmp_path / "task.json").read_text(encoding="utf-8")

        # 更新后触发备份
        tfm.update_task_status("task-001", TaskStatus.COMPLETED)

        # 验证备份文件内容
        backup_dir = tmp_path / "backup"
        backups = list(backup_dir.glob("task.json.*.bak"))
        assert len(backups) == 1
        backup_content = backups[0].read_text(encoding="utf-8")
        assert backup_content == initial_content


# ══════════════════════════════════════════════════════════
# 9. 多任务场景文件状态流转
# ══════════════════════════════════════════════════════════
class TestMultiTaskFileStateFlow:
    """多任务场景下文件状态流转验证"""

    def test_three_tasks_sequential_flow(self, tmp_path):
        """三个顺序依赖任务的文件状态流转"""
        tfm, pm, mm = _setup_managers(tmp_path)
        tasks = [
            _make_task("task-001", suggested_role="senior-developer"),
            _make_task("task-002", dependencies=["task-001"], suggested_role="test-engineer"),
            _make_task("task-003", dependencies=["task-002"], suggested_role="qa-engineer"),
        ]
        tfm.write_tasks(_make_task_json(tasks))

        # task-001 完成
        tfm.update_task_status("task-001", TaskStatus.COMPLETED)
        pm.write_entry(ProgressEntry(
            task_id="task-001", status=ProgressStatus.COMPLETED,
            role="senior-developer", git_sha="sha001",
        ))

        # task-002 完成
        tfm.update_task_status("task-002", TaskStatus.COMPLETED)
        pm.write_entry(ProgressEntry(
            task_id="task-002", status=ProgressStatus.COMPLETED,
            role="test-engineer", git_sha="sha002",
        ))

        # task-003 完成
        tfm.update_task_status("task-003", TaskStatus.COMPLETED)
        pm.write_entry(ProgressEntry(
            task_id="task-003", status=ProgressStatus.COMPLETED,
            role="qa-engineer", git_sha="sha003",
        ))

        # 记录到 memory.md
        mm.append(MemoryEntry(
            title="Key Results",
            content="三个顺序任务全部完成: task-001→task-002→task-003",
            tags=["milestone"],
        ))

        # 验证所有状态
        for t in tasks:
            assert tfm.get_task(t.id).status == TaskStatus.COMPLETED
        assert pm.get_completed_count() == 3
        assert mm.search("milestone")

    def test_fan_out_fan_in_flow(self, tmp_path):
        """扇出/扇入 DAG 的文件状态流转"""
        tfm, pm, _ = _setup_managers(tmp_path)
        tasks = [
            _make_task("task-001"),                              # root
            _make_task("task-002", dependencies=["task-001"]),   # fan-out
            _make_task("task-003", dependencies=["task-001"]),   # fan-out
            _make_task("task-004", dependencies=["task-002", "task-003"]),  # fan-in
        ]
        tfm.write_tasks(_make_task_json(tasks))

        # task-001 完成
        tfm.update_task_status("task-001", TaskStatus.COMPLETED)
        pm.write_entry(ProgressEntry(
            task_id="task-001", status=ProgressStatus.COMPLETED, role="dev",
        ))

        # task-002 和 task-003 并行完成
        for tid in ["task-002", "task-003"]:
            tfm.update_task_status(tid, TaskStatus.COMPLETED)
            pm.write_entry(ProgressEntry(
                task_id=tid, status=ProgressStatus.COMPLETED, role="dev",
            ))

        # task-004 完成
        tfm.update_task_status("task-004", TaskStatus.COMPLETED)
        pm.write_entry(ProgressEntry(
            task_id="task-004", status=ProgressStatus.COMPLETED, role="dev",
        ))

        assert pm.get_completed_count() == 4
        pending = tfm.get_pending_tasks()
        assert len(pending) == 0

    def test_skipped_task_flow(self, tmp_path):
        """跳过任务的文件状态流转"""
        tfm, pm, _ = _setup_managers(tmp_path)
        tfm.write_tasks(_make_task_json())

        tfm.update_task_status("task-001", TaskStatus.SKIPPED)
        pm.write_entry(ProgressEntry(
            task_id="task-001", status=ProgressStatus.SKIPPED, role="dev",
        ))

        task = tfm.get_task("task-001")
        entry = pm.get_entry("task-001")
        assert task.status == TaskStatus.SKIPPED
        assert entry.status == ProgressStatus.SKIPPED

    def test_mixed_status_tasks(self, tmp_path):
        """混合状态多任务"""
        tfm, pm, _ = _setup_managers(tmp_path)
        tasks = [
            _make_task("task-001"),
            _make_task("task-002"),
            _make_task("task-003"),
            _make_task("task-004"),
        ]
        tfm.write_tasks(_make_task_json(tasks))

        statuses = [
            ("task-001", TaskStatus.COMPLETED, ProgressStatus.COMPLETED),
            ("task-002", TaskStatus.FAILED, ProgressStatus.FAILED),
            ("task-003", TaskStatus.IN_PROGRESS, ProgressStatus.IN_PROGRESS),
            ("task-004", TaskStatus.BLOCKED, ProgressStatus.BLOCKED),
        ]

        for tid, t_status, p_status in statuses:
            tfm.update_task_status(tid, t_status)
            pm.write_entry(ProgressEntry(task_id=tid, status=p_status, role="dev"))

        # 验证各状态
        assert tfm.get_task("task-001").status == TaskStatus.COMPLETED
        assert tfm.get_task("task-002").status == TaskStatus.FAILED
        assert tfm.get_task("task-003").status == TaskStatus.IN_PROGRESS
        assert tfm.get_task("task-004").status == TaskStatus.BLOCKED

        assert pm.get_completed_count() == 1


# ══════════════════════════════════════════════════════════
# 10. progress.txt 格式与解析一致性
# ══════════════════════════════════════════════════════════
class TestProgressFormatAndParsingConsistency:
    """progress.txt 格式写入与解析一致性验证"""

    def test_write_read_round_trip(self, tmp_path):
        """写入后读取的 ProgressEntry 字段一致"""
        _, pm, _ = _setup_managers(tmp_path)

        entry = ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.COMPLETED,
            role="senior-developer",
            started=datetime(2026, 5, 19, 10, 0, 0),
            finished=datetime(2026, 5, 19, 10, 30, 0),
            git_sha="abc123",
            git_msg="[task-001] senior-developer: done",
            error=None,
            retry=0,
        )
        pm.write_entry(entry)

        entries = pm.read_progress()
        assert len(entries) == 1
        loaded = entries[0]
        assert loaded.task_id == entry.task_id
        assert loaded.status == entry.status
        assert loaded.role == entry.role
        assert loaded.started == entry.started
        assert loaded.finished == entry.finished
        assert loaded.git_sha == entry.git_sha
        assert loaded.git_msg == entry.git_msg

    def test_header_contains_progress_count(self, tmp_path):
        """progress.txt 头部包含进度统计"""
        _, pm, _ = _setup_managers(tmp_path)

        pm.write_entry(ProgressEntry(
            task_id="task-001", status=ProgressStatus.COMPLETED, role="dev",
        ))

        content = (tmp_path / "progress.txt").read_text(encoding="utf-8")
        assert "1 / 1 tasks completed" in content

    def test_multiple_entries_order_preserved(self, tmp_path):
        """多条目的顺序保持一致"""
        _, pm, _ = _setup_managers(tmp_path)

        for i in range(1, 4):
            pm.write_entry(ProgressEntry(
                task_id=f"task-00{i}",
                status=ProgressStatus.COMPLETED,
                role="dev",
            ))

        entries = pm.read_progress()
        assert len(entries) == 3
        assert entries[0].task_id == "task-001"
        assert entries[1].task_id == "task-002"
        assert entries[2].task_id == "task-003"


# ══════════════════════════════════════════════════════════
# 11. memory.md 格式与搜索一致性
# ══════════════════════════════════════════════════════════
class TestMemoryFormatAndSearchConsistency:
    """memory.md 格式写入与搜索一致性验证"""

    def test_write_read_round_trip(self, tmp_path):
        """写入后读取的 MemoryEntry 字段一致"""
        _, _, mm = _setup_managers(tmp_path)

        entry = MemoryEntry(
            title="Learnings",
            content="使用 fixture 管理临时文件",
            tags=["pytest", "testing"],
        )
        mm.append(entry)

        entries = mm.read()
        assert len(entries) == 1
        loaded = entries[0]
        assert loaded.title == entry.title
        assert loaded.content == entry.content
        assert "pytest" in loaded.tags
        assert "testing" in loaded.tags

    def test_case_insensitive_search(self, tmp_path):
        """搜索不区分大小写"""
        _, _, mm = _setup_managers(tmp_path)

        mm.append(MemoryEntry(title="Architecture", content="Use dependency injection"))
        results = mm.search("DEPENDENCY")
        assert len(results) == 1

    def test_search_in_tags(self, tmp_path):
        """在 tags 中搜索"""
        _, _, mm = _setup_managers(tmp_path)

        mm.append(MemoryEntry(
            title="Tips",
            content="some content",
            tags=["performance"],
        ))
        results = mm.search("performance")
        assert len(results) == 1

    def test_get_all_titles(self, tmp_path):
        """获取所有 section 标题"""
        _, _, mm = _setup_managers(tmp_path)

        mm.append(MemoryEntry(title="Section A", content="a"))
        mm.append(MemoryEntry(title="Section B", content="b"))

        titles = mm.get_all_titles()
        assert "Section A" in titles
        assert "Section B" in titles

    def test_read_nonexistent_section_returns_none(self, tmp_path):
        """读取不存在的 section 返回 None"""
        _, _, mm = _setup_managers(tmp_path)
        mm.append(MemoryEntry(title="Existing", content="data"))
        assert mm.read_section("Nonexistent") is None

"""
P1-054 测试 — 断点恢复场景测试：模拟各种中断场景

基于 P1-051 实现的 restore_from_progress() 及相关方法，
以端到端场景视角验证各种中断/恢复路径的正确性。

与 P1-051 单元测试的区别：
  - P1-051：方法级别测试（映射、单个状态恢复）
  - P1-054：场景级别测试（模拟完整中断→恢复→继续调度流程）
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from agent_automation_system.master_agent.master_agent import (
    MasterAgent,
    MasterAgentState,
)
from agent_automation_system.models.progress import ProgressEntry, ProgressStatus
from agent_automation_system.models.task import (
    Task,
    TaskPriority,
    TaskStatus,
    BDDSpec,
)
from agent_automation_system.models.task_json import TaskJSON
from agent_automation_system.sub_agent.sub_agent import (
    SubAgentResult,
    SubAgentResultStatus,
    AgentPhase,
)


# ── 辅助工具 ──────────────────────────────────────────────


def _make_task(
    task_id: str = "task-001",
    title: str = "Test task",
    priority: TaskPriority = TaskPriority.MEDIUM,
    status: TaskStatus = TaskStatus.PENDING,
    dependencies: list[str] | None = None,
    retry_count: int = 0,
    suggested_role: str = "senior-developer",
    error_message: str | None = None,
) -> Task:
    """创建测试用 Task"""
    return Task(
        id=task_id,
        title=title,
        description=f"Description for {title}",
        bdd=BDDSpec(given="context", when="action", then="result"),
        dependencies=dependencies or [],
        priority=priority,
        status=status,
        retry_count=retry_count,
        suggested_role=suggested_role,
        error_message=error_message,
    )


def _make_task_json(tasks: list[Task]) -> TaskJSON:
    """创建测试用 TaskJSON"""
    return TaskJSON(
        project_name="test-project",
        total_tasks=len(tasks),
        tasks=tasks,
    )


def _make_progress_entry(
    task_id: str = "task-001",
    status: ProgressStatus = ProgressStatus.COMPLETED,
    role: str = "senior-developer",
    git_sha: str | None = "abc1234",
    error: str | None = None,
    retry: int = 0,
) -> ProgressEntry:
    """创建测试用 ProgressEntry"""
    return ProgressEntry(
        task_id=task_id,
        status=status,
        role=role,
        started=datetime(2026, 5, 18, 10, 0, 0),
        finished=datetime(2026, 5, 18, 10, 30, 0) if status in (
            ProgressStatus.COMPLETED,
            ProgressStatus.FAILED,
            ProgressStatus.SKIPPED,
        ) else None,
        git_sha=git_sha,
        git_msg=f"[{task_id}] {role}: completed" if status == ProgressStatus.COMPLETED else None,
        error=error,
        retry=retry,
    )


def _make_master(
    max_concurrent: int = 3,
    task_max_retries: int = 1,
    state: MasterAgentState = MasterAgentState.DISPATCHING,
    progress_manager: MagicMock | None = None,
) -> MasterAgent:
    """创建测试用 MasterAgent（带 mock ProgressManager）"""
    master = MasterAgent(
        max_concurrent_agents=max_concurrent,
        task_max_retries=task_max_retries,
        progress_manager=progress_manager,
    )
    master._state = state
    return master


# ── 场景 1：执行中中断 ──────────────────────────────────────


class TestMidExecutionInterruption:
    """模拟执行过程中 MasterAgent 崩溃/中断的场景

    典型场景：MasterAgent 正在运行，部分任务 IN_PROGRESS，
    突然进程崩溃，重启后从 progress.txt 恢复。
    """

    def test_single_in_progress_task_resets_to_pending(self):
        """单个任务执行中被中断 → 重置为 PENDING，可继续调度"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.IN_PROGRESS),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        task = _make_task(task_id="task-001", status=TaskStatus.IN_PROGRESS)
        master._task_json = _make_task_json([task])

        result = master.restore_from_progress()

        assert task.status == TaskStatus.PENDING
        assert result["reset_to_pending"] == 1
        assert result["state"] == "dispatching"
        # 验证可被调度器选中
        dispatchable = master.get_dispatchable_tasks()
        assert any(t.id == "task-001" for t in dispatchable)

    def test_multiple_in_progress_tasks_all_reset(self):
        """多个任务同时执行中被中断 → 全部重置为 PENDING"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.IN_PROGRESS),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.IN_PROGRESS),
            _make_progress_entry(task_id="task-003", status=ProgressStatus.IN_PROGRESS),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001", status=TaskStatus.IN_PROGRESS),
            _make_task(task_id="task-002", status=TaskStatus.IN_PROGRESS),
            _make_task(task_id="task-003", status=TaskStatus.IN_PROGRESS),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.restore_from_progress()

        assert result["reset_to_pending"] == 3
        assert all(t.status == TaskStatus.PENDING for t in tasks)
        assert master._state == MasterAgentState.DISPATCHING

    def test_completed_plus_in_progress_partial_recovery(self):
        """部分任务已完成 + 部分任务中断 → 已完成保留，中断重调度"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.IN_PROGRESS),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002", dependencies=["task-001"]),
            _make_task(task_id="task-003", dependencies=["task-002"]),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.restore_from_progress()

        assert tasks[0].status == TaskStatus.COMPLETED
        assert tasks[1].status == TaskStatus.PENDING  # IN_PROGRESS → PENDING
        assert tasks[2].status == TaskStatus.PENDING  # untouched，保持原始 PENDING
        assert result["already_completed"] == 1
        assert result["reset_to_pending"] == 1
        assert result["untouched"] == 1
        # task-002 依赖 task-001 已完成 → 可调度
        dispatchable = master.get_dispatchable_tasks()
        assert any(t.id == "task-002" for t in dispatchable)
        # task-003 依赖 task-002（未完成） → 不可调度
        assert not any(t.id == "task-003" for t in dispatchable)


# ── 场景 2：重试中断 ────────────────────────────────────────


class TestRetryInterruption:
    """模拟任务重试过程中被中断的场景

    典型场景：任务失败后进入 RETRYING 状态，重试过程中进程崩溃。
    """

    def test_retrying_task_resets_with_retry_count_preserved(self):
        """重试中中断 → 重置为 PENDING，但保留 retry_count"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.RETRYING, retry=2),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        task = _make_task(task_id="task-001", retry_count=0)
        master._task_json = _make_task_json([task])

        result = master.restore_from_progress()

        assert task.status == TaskStatus.PENDING
        assert task.retry_count == 2
        assert result["reset_to_pending"] == 1

    def test_retrying_after_first_failure(self):
        """失败一次后重试中断 → 恢复后保留错误信息和重试计数"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(
                task_id="task-001",
                status=ProgressStatus.RETRYING,
                retry=1,
                error="build timeout",
            ),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        task = _make_task(task_id="task-001")
        master._task_json = _make_task_json([task])

        result = master.restore_from_progress()

        assert task.status == TaskStatus.PENDING
        assert task.retry_count == 1
        assert task.error_message == "build timeout"

    def test_mixed_retry_and_completed(self):
        """部分任务完成 + 部分重试中断 → 完成任务保留结果，重试任务重调度"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.RETRYING, retry=1, error="test fail"),
            _make_progress_entry(task_id="task-003", status=ProgressStatus.IN_PROGRESS),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002", dependencies=["task-001"]),
            _make_task(task_id="task-003", dependencies=["task-001"]),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.restore_from_progress()

        assert tasks[0].status == TaskStatus.COMPLETED
        assert tasks[1].status == TaskStatus.PENDING
        assert tasks[1].retry_count == 1
        assert tasks[2].status == TaskStatus.PENDING
        assert result["already_completed"] == 1
        assert result["reset_to_pending"] == 2
        # task-002 和 task-003 都依赖已完成的 task-001 → 可调度
        dispatchable = master.get_dispatchable_tasks()
        assert any(t.id == "task-002" for t in dispatchable)
        assert any(t.id == "task-003" for t in dispatchable)


# ── 场景 3：全完成恢复 ──────────────────────────────────────


class TestAllCompletedRecovery:
    """所有任务都已完成时的恢复场景"""

    def test_all_completed_state_becomes_completed(self):
        """全部已完成 → 状态变为 COMPLETED"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-003", status=ProgressStatus.COMPLETED),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(state=MasterAgentState.IDLE, progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
            _make_task(task_id="task-003"),
        ]
        master._task_json = _make_task_json(tasks)

        master.restore_from_progress()

        assert master._state == MasterAgentState.COMPLETED
        assert all(t.status == TaskStatus.COMPLETED for t in tasks)

    def test_all_completed_or_skipped_state_completed(self):
        """全部完成或跳过 → 状态变为 COMPLETED"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.SKIPPED),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(state=MasterAgentState.IDLE, progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
        ]
        master._task_json = _make_task_json(tasks)

        master.restore_from_progress()

        assert master._state == MasterAgentState.COMPLETED

    def test_all_completed_no_dispatchable_tasks(self):
        """全部完成后无可调度任务"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        task = _make_task(task_id="task-001")
        master._task_json = _make_task_json([task])

        master.restore_from_progress()

        # 手动设为 DISPATCHING 才能查询
        master._state = MasterAgentState.DISPATCHING
        assert len(master.get_dispatchable_tasks()) == 0

    def test_all_completed_execution_results_populated(self):
        """全部完成后 execution_results 正确填充"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED, git_sha="a1b2c3d"),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.COMPLETED, git_sha="e4f5g6h"),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
        ]
        master._task_json = _make_task_json(tasks)

        master.restore_from_progress()

        assert len(master._execution_results) == 2
        assert master._execution_results["task-001"].commit_hash == "a1b2c3d"
        assert master._execution_results["task-002"].commit_hash == "e4f5g6h"


# ── 场景 4：失败恢复 ─────────────────────────────────────────


class TestFailureRecovery:
    """任务失败后的恢复场景"""

    def test_all_failed_state_becomes_failed(self):
        """全部失败 → 状态变为 FAILED"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.FAILED, error="err1"),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.FAILED, error="err2"),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(state=MasterAgentState.IDLE, progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
        ]
        master._task_json = _make_task_json(tasks)

        master.restore_from_progress()

        assert master._state == MasterAgentState.FAILED
        assert all(t.status == TaskStatus.FAILED for t in tasks)

    def test_mixed_completed_and_failed(self):
        """部分完成 + 部分失败 → 状态 FAILED"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.FAILED, error="err"),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(state=MasterAgentState.IDLE, progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
        ]
        master._task_json = _make_task_json(tasks)

        master.restore_from_progress()

        assert master._state == MasterAgentState.FAILED
        assert tasks[0].status == TaskStatus.COMPLETED
        assert tasks[1].status == TaskStatus.FAILED

    def test_failed_plus_in_progress_reset_to_pending(self):
        """部分失败 + 部分中断 → 中断任务重调度，状态 DISPATCHING"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.FAILED, error="err"),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.IN_PROGRESS),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.restore_from_progress()

        # 有 reset_to_pending → DISPATCHING
        assert master._state == MasterAgentState.DISPATCHING
        assert tasks[0].status == TaskStatus.FAILED
        assert tasks[1].status == TaskStatus.PENDING

    def test_failed_task_execution_result_populated(self):
        """失败任务的 execution_result 正确填充（含 error）"""
        pm = MagicMock()
        entry = _make_progress_entry(
            task_id="task-001",
            status=ProgressStatus.FAILED,
            error="segmentation fault",
        )
        pm.read_progress.return_value = [entry]
        master = _make_master(progress_manager=pm)
        task = _make_task(task_id="task-001")
        master._task_json = _make_task_json([task])

        master.restore_from_progress()

        result = master._execution_results["task-001"]
        assert result.status == SubAgentResultStatus.FAILED
        assert result.phase == AgentPhase.FAILED
        assert result.error == "segmentation fault"


# ── 场景 5：阻塞恢复 ─────────────────────────────────────────


class TestBlockedRecovery:
    """任务因依赖失败被阻塞的恢复场景"""

    def test_all_blocked_state_becomes_paused(self):
        """全部阻塞 → 状态 PAUSED"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.BLOCKED),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.BLOCKED),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(state=MasterAgentState.IDLE, progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
        ]
        master._task_json = _make_task_json(tasks)

        master.restore_from_progress()

        assert master._state == MasterAgentState.PAUSED

    def test_failed_and_blocked_no_pending(self):
        """部分失败 + 部分阻塞（无 PENDING）→ PAUSED

        _update_state_after_restore: completed=0, failed=1, total=2
        → 0+1=1 < 2 → not all terminal → reset_to_pending=0 → PAUSED
        """
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.FAILED, error="err"),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.BLOCKED),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(state=MasterAgentState.IDLE, progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
        ]
        master._task_json = _make_task_json(tasks)

        master.restore_from_progress()

        assert master._state == MasterAgentState.PAUSED

    def test_blocked_not_dispatchable_after_restore(self):
        """恢复后阻塞任务不可调度"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.FAILED, error="err"),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.BLOCKED),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002", dependencies=["task-001"]),
        ]
        master._task_json = _make_task_json(tasks)

        master.restore_from_progress()
        master._state = MasterAgentState.DISPATCHING

        dispatchable = master.get_dispatchable_tasks()
        assert not any(t.id == "task-002" for t in dispatchable)


# ── 场景 6：空进度与未知任务 ─────────────────────────────────


class TestEmptyAndUnknownProgress:
    """进度文件为空或包含未知任务的场景"""

    def test_empty_progress_all_untouched(self):
        """空进度文件 → 所有任务 untouched，保持原状态"""
        pm = MagicMock()
        pm.read_progress.return_value = []
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
            _make_task(task_id="task-003"),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.restore_from_progress()

        assert result["restored"] is True
        assert result["untouched"] == 3
        assert result["already_completed"] == 0
        assert result["reset_to_pending"] == 0
        # 所有任务保持 PENDING
        assert all(t.status == TaskStatus.PENDING for t in tasks)

    def test_progress_with_unknown_task_ids(self):
        """进度文件包含 task_json 中不存在的 task_id → 不影响现有任务"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-999", status=ProgressStatus.COMPLETED),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.restore_from_progress()

        assert result["already_completed"] == 1
        assert result["untouched"] == 1
        assert tasks[0].status == TaskStatus.COMPLETED
        assert tasks[1].status == TaskStatus.PENDING  # untouched

    def test_no_progress_manager_returns_not_restored(self):
        """ProgressManager 不可用 → restored=False"""
        master = _make_master(progress_manager=None)
        master._task_json = _make_task_json([_make_task()])

        result = master.restore_from_progress()

        assert result["restored"] is False
        assert result["untouched"] == 1

    def test_progress_read_exception_graceful_fallback(self):
        """progress 读取异常 → 优雅降级，不抛异常"""
        pm = MagicMock()
        pm.read_progress.side_effect = IOError("disk read error")
        master = _make_master(progress_manager=pm)
        master._task_json = _make_task_json([_make_task()])

        result = master.restore_from_progress()

        assert result["restored"] is False

    def test_no_task_json_raises_runtime_error(self):
        """task_json 未加载 → RuntimeError"""
        master = _make_master(progress_manager=MagicMock())

        with pytest.raises(RuntimeError, match="task_json not loaded"):
            master.restore_from_progress()


# ── 场景 7：完整崩溃重启模拟 ─────────────────────────────────


class TestCrashRestartSimulation:
    """模拟 MasterAgent 完整崩溃后重启的场景

    这是最核心的场景：模拟一个真实的中断-重启流程，
    验证从 progress.txt 恢复后所有状态和任务状态都正确。
    """

    def test_diamond_dag_crash_and_resume(self):
        """菱形 DAG 执行到一半崩溃 → 恢复后正确继续

        菱形结构：
            task-101 → task-102 → task-104
            task-101 → task-103 → task-104

        崩溃时：task-101 完成，task-102 和 task-103 正在执行，task-104 未开始
        恢复后：task-101 保持 COMPLETED，task-102/103 重置为 PENDING，task-104 保持 PENDING
        """
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-101", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-102", status=ProgressStatus.IN_PROGRESS),
            _make_progress_entry(task_id="task-103", status=ProgressStatus.IN_PROGRESS),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-101"),
            _make_task(task_id="task-102", dependencies=["task-101"]),
            _make_task(task_id="task-103", dependencies=["task-101"]),
            _make_task(task_id="task-104", dependencies=["task-102", "task-103"]),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.restore_from_progress()

        # task-101 完成，task-102/103 重置 PENDING，task-104 untouched PENDING
        assert tasks[0].status == TaskStatus.COMPLETED
        assert tasks[1].status == TaskStatus.PENDING
        assert tasks[2].status == TaskStatus.PENDING
        assert tasks[3].status == TaskStatus.PENDING
        assert master._state == MasterAgentState.DISPATCHING
        # task-102 和 task-103 依赖 task-101 已完成 → 可调度
        dispatchable = master.get_dispatchable_tasks()
        ids = {t.id for t in dispatchable}
        assert "task-102" in ids
        assert "task-103" in ids
        assert "task-104" not in ids  # task-104 依赖 task-102+103，尚未完成

    def test_chain_crash_at_middle(self):
        """链式 DAG task-101→task-102→task-103→task-104 崩溃在 task-102 执行中

        崩溃时：task-101 完成，task-102 执行中，task-103/104 未开始
        恢复后：task-101 保持 COMPLETED，task-102 重置 PENDING，task-103/104 保持 PENDING
        """
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-101", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-102", status=ProgressStatus.IN_PROGRESS),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-101"),
            _make_task(task_id="task-102", dependencies=["task-101"]),
            _make_task(task_id="task-103", dependencies=["task-102"]),
            _make_task(task_id="task-104", dependencies=["task-103"]),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.restore_from_progress()

        assert tasks[0].status == TaskStatus.COMPLETED
        assert tasks[1].status == TaskStatus.PENDING
        assert tasks[2].status == TaskStatus.PENDING
        assert tasks[3].status == TaskStatus.PENDING
        # 只有 task-102 可调度
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 1
        assert dispatchable[0].id == "task-102"

    def test_fan_out_crash_with_partial_completion(self):
        """扇出 DAG 崩溃时部分完成部分中断

        task-101 → task-102, task-103, task-104（task-101 是根，其余独立）
        崩溃时：task-101 完成，task-102 完成，task-103 执行中，task-104 未开始
        """
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-101", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-102", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-103", status=ProgressStatus.IN_PROGRESS),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-101"),
            _make_task(task_id="task-102", dependencies=["task-101"]),
            _make_task(task_id="task-103", dependencies=["task-101"]),
            _make_task(task_id="task-104", dependencies=["task-101"]),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.restore_from_progress()

        assert tasks[0].status == TaskStatus.COMPLETED
        assert tasks[1].status == TaskStatus.COMPLETED
        assert tasks[2].status == TaskStatus.PENDING  # IN_PROGRESS → PENDING
        assert tasks[3].status == TaskStatus.PENDING  # untouched
        # task-103 和 task-104 都可调度（依赖 task-101 已完成）
        dispatchable = master.get_dispatchable_tasks()
        ids = {t.id for t in dispatchable}
        assert "task-103" in ids
        assert "task-104" in ids

    def test_restart_with_failure_and_blocked_downstream(self):
        """崩溃恢复后上游失败 → 下游阻塞

        task-101→task-102→task-103，崩溃时 task-101 失败，task-102 阻塞，task-103 未开始
        """
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-101", status=ProgressStatus.FAILED, error="critical"),
            _make_progress_entry(task_id="task-102", status=ProgressStatus.BLOCKED),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-101"),
            _make_task(task_id="task-102", dependencies=["task-101"]),
            _make_task(task_id="task-103", dependencies=["task-102"]),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.restore_from_progress()

        assert tasks[0].status == TaskStatus.FAILED
        assert tasks[1].status == TaskStatus.BLOCKED
        assert tasks[2].status == TaskStatus.PENDING  # untouched
        # 无 reset_to_pending，但有未终态任务 → PAUSED
        assert master._state == MasterAgentState.PAUSED


# ── 场景 8：部分恢复 ────────────────────────────────────────


class TestPartialProgressRecovery:
    """只有部分任务有进度记录的场景"""

    def test_some_tasks_no_progress_entry(self):
        """部分任务有进度记录、部分没有 → 无记录的保持原状"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED),
            # task-002 没有 progress entry
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002", dependencies=["task-001"]),
            _make_task(task_id="task-003", dependencies=["task-002"]),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.restore_from_progress()

        assert tasks[0].status == TaskStatus.COMPLETED
        assert tasks[1].status == TaskStatus.PENDING  # untouched
        assert tasks[2].status == TaskStatus.PENDING  # untouched
        assert result["untouched"] == 2

    def test_larger_task_set_partial_progress(self):
        """5 个任务中 3 个有进度记录 → 正确分类"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.FAILED, error="err"),
            _make_progress_entry(task_id="task-004", status=ProgressStatus.IN_PROGRESS),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
            _make_task(task_id="task-003"),
            _make_task(task_id="task-004"),
            _make_task(task_id="task-005"),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.restore_from_progress()

        assert result["already_completed"] == 1
        assert result["already_failed"] == 1
        assert result["reset_to_pending"] == 1
        assert result["untouched"] == 2

    def test_untouched_tasks_still_dispatchable_after_restore(self):
        """无进度记录的 PENDING 任务恢复后仍可调度"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),  # 无依赖，无进度
        ]
        master._task_json = _make_task_json(tasks)

        master.restore_from_progress()

        # 恢复后状态 PAUSED（task-001 COMPLETED + task-002 untouched → 不全终态且无 reset）
        # 需手动切为 DISPATCHING 才能查询
        master._state = MasterAgentState.DISPATCHING
        dispatchable = master.get_dispatchable_tasks()
        assert any(t.id == "task-002" for t in dispatchable)


# ── 场景 9：恢复后调度集成 ───────────────────────────────────


class TestRestoreDispatchIntegration:
    """恢复后与调度器的集成场景

    验证恢复后的任务状态能被 get_dispatchable_tasks()
    和 select_next_task() 正确识别和调度。
    """

    def test_restored_pending_tasks_dispatchable_with_concurrency(self):
        """恢复后的 PENDING 任务受并发度约束"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.IN_PROGRESS),
            _make_progress_entry(task_id="task-003", status=ProgressStatus.IN_PROGRESS),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(max_concurrent=2, progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002", dependencies=["task-001"]),
            _make_task(task_id="task-003", dependencies=["task-001"]),
        ]
        master._task_json = _make_task_json(tasks)

        master.restore_from_progress()

        # task-002 和 task-003 都被重置为 PENDING
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 2
        ids = {t.id for t in dispatchable}
        assert "task-002" in ids
        assert "task-003" in ids

    def test_restored_tasks_respect_dependencies(self):
        """恢复后的任务仍然遵守依赖约束"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-101", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-102", status=ProgressStatus.IN_PROGRESS),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-101"),
            _make_task(task_id="task-102", dependencies=["task-101"]),
            _make_task(task_id="task-103", dependencies=["task-102"]),  # 依赖 task-102（未完成）
        ]
        master._task_json = _make_task_json(tasks)

        master.restore_from_progress()

        dispatchable = master.get_dispatchable_tasks()
        ids = {t.id for t in dispatchable}
        assert "task-102" in ids
        assert "task-103" not in ids  # task-102 未完成

    def test_execution_results_after_restore_match_progress(self):
        """恢复后 execution_results 与 progress 状态一致"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED, git_sha="sha1"),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.FAILED, error="oom"),
            _make_progress_entry(task_id="task-003", status=ProgressStatus.SKIPPED),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
            _make_task(task_id="task-003"),
        ]
        master._task_json = _make_task_json(tasks)

        master.restore_from_progress()

        assert master._execution_results["task-001"].status == SubAgentResultStatus.SUCCESS
        assert master._execution_results["task-001"].commit_hash == "sha1"
        assert master._execution_results["task-002"].status == SubAgentResultStatus.FAILED
        assert master._execution_results["task-002"].error == "oom"
        assert master._execution_results["task-003"].status == SubAgentResultStatus.SUCCESS
        # SKIPPED → SUCCESS，有结果
        assert "task-003" in master._execution_results

    def test_select_next_task_after_restore(self):
        """恢复后 select_next_task 优先调度高优先级任务"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.IN_PROGRESS),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001", priority=TaskPriority.HIGH),
            _make_task(task_id="task-002", priority=TaskPriority.LOW, dependencies=["task-001"]),
            _make_task(task_id="task-003", priority=TaskPriority.HIGH, dependencies=["task-001"]),
        ]
        master._task_json = _make_task_json(tasks)

        master.restore_from_progress()

        # task-002 和 task-003 都可调度，HIGH 优先
        next_task = master.select_next_task()
        assert next_task is not None
        assert next_task.id == "task-003"  # HIGH > LOW

    def test_progress_summary_correct_after_restore(self):
        """恢复后 get_progress_summary 反映正确进度"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.FAILED, error="err"),
            _make_progress_entry(task_id="task-003", status=ProgressStatus.IN_PROGRESS),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
            _make_task(task_id="task-003"),
            _make_task(task_id="task-004"),  # untouched
        ]
        master._task_json = _make_task_json(tasks)

        master.restore_from_progress()
        summary = master.get_progress_summary()

        assert summary["total"] == 4
        assert summary["completed"] == 1
        assert summary["failed"] == 1


# ── 场景 10：混合中断+重试+失败+完成 ─────────────────────────


class TestComplexMixedScenario:
    """复杂混合场景：多种状态同时存在的恢复"""

    def test_full_mixed_state_recovery(self):
        """全部 6 种 ProgressStatus 同时出现的恢复"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-101", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-102", status=ProgressStatus.FAILED, error="err"),
            _make_progress_entry(task_id="task-103", status=ProgressStatus.IN_PROGRESS),
            _make_progress_entry(task_id="task-104", status=ProgressStatus.BLOCKED),
            _make_progress_entry(task_id="task-105", status=ProgressStatus.SKIPPED),
            _make_progress_entry(task_id="task-106", status=ProgressStatus.RETRYING, retry=2, error="retry err"),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-101"),
            _make_task(task_id="task-102"),
            _make_task(task_id="task-103"),
            _make_task(task_id="task-104"),
            _make_task(task_id="task-105"),
            _make_task(task_id="task-106"),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.restore_from_progress()

        assert tasks[0].status == TaskStatus.COMPLETED
        assert tasks[1].status == TaskStatus.FAILED
        assert tasks[2].status == TaskStatus.PENDING  # IN_PROGRESS → PENDING
        assert tasks[3].status == TaskStatus.BLOCKED
        assert tasks[4].status == TaskStatus.SKIPPED
        assert tasks[5].status == TaskStatus.PENDING  # RETRYING → PENDING
        assert tasks[5].retry_count == 2
        assert tasks[5].error_message == "retry err"

        # 统计：completed=2(COMPLETED+SKIPPED), failed=1, blocked=1, reset=2
        assert result["already_completed"] == 2  # COMPLETED + SKIPPED
        assert result["already_failed"] == 1
        assert result["already_blocked"] == 1
        assert result["reset_to_pending"] == 2
        assert result["untouched"] == 0
        # 有 reset_to_pending → DISPATCHING
        assert master._state == MasterAgentState.DISPATCHING

    def test_mixed_with_dependency_chain_recovery(self):
        """混合状态 + 依赖链的恢复场景

        task-101→task-102→task-103→task-104→task-105
        崩溃时：task-101 完成，task-102 失败，task-103 阻塞，task-104 执行中，task-105 未开始
        """
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-101", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-102", status=ProgressStatus.FAILED, error="build fail"),
            _make_progress_entry(task_id="task-103", status=ProgressStatus.BLOCKED),
            _make_progress_entry(task_id="task-104", status=ProgressStatus.IN_PROGRESS),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-101"),
            _make_task(task_id="task-102", dependencies=["task-101"]),
            _make_task(task_id="task-103", dependencies=["task-102"]),
            _make_task(task_id="task-104", dependencies=["task-103"]),
            _make_task(task_id="task-105", dependencies=["task-104"]),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.restore_from_progress()

        assert tasks[0].status == TaskStatus.COMPLETED
        assert tasks[1].status == TaskStatus.FAILED
        assert tasks[2].status == TaskStatus.BLOCKED
        assert tasks[3].status == TaskStatus.PENDING  # IN_PROGRESS → PENDING
        assert tasks[4].status == TaskStatus.PENDING  # untouched

        # task-104 的依赖 task-103 是 BLOCKED → 不满足
        master._state = MasterAgentState.DISPATCHING
        dispatchable = master.get_dispatchable_tasks()
        # task-104 依赖 task-103（BLOCKED，非 COMPLETED）→ 不可调度
        assert not any(t.id == "task-104" for t in dispatchable)

    def test_state_from_idle_to_dispatching_after_restore(self):
        """从 IDLE 恢复到 DISPATCHING 的完整流程"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.IN_PROGRESS),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(state=MasterAgentState.IDLE, progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002", dependencies=["task-001"]),
        ]
        master._task_json = _make_task_json(tasks)

        # 恢复前是 IDLE
        assert master._state == MasterAgentState.IDLE

        master.restore_from_progress()

        # 恢复后应为 DISPATCHING（有 reset_to_pending）
        assert master._state == MasterAgentState.DISPATCHING

    def test_skipped_dependency_allows_downstream(self):
        """SKIPPED 的上游任务，下游重置为 PENDING

        场景：task-101 SKIPPED, task-102 依赖 task-101 且被中断
        恢复后 task-102 重置为 PENDING，task-101 为 SKIPPED
        依赖检查是否认可 SKIPPED 取决于 get_dispatchable_tasks 实现
        """
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-101", status=ProgressStatus.SKIPPED),
            _make_progress_entry(task_id="task-102", status=ProgressStatus.IN_PROGRESS),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-101"),
            _make_task(task_id="task-102", dependencies=["task-101"]),
        ]
        master._task_json = _make_task_json(tasks)

        master.restore_from_progress()

        # task-101 被标记为 SKIPPED，task-102 重置为 PENDING
        assert tasks[0].status == TaskStatus.SKIPPED
        assert tasks[1].status == TaskStatus.PENDING


# ── 场景 11：恢复摘要一致性 ──────────────────────────────────


class TestRestoreSummaryConsistency:
    """恢复摘要各项计数的一致性校验"""

    def test_summary_counts_sum_to_total(self):
        """摘要各项计数之和等于任务总数"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-101", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-102", status=ProgressStatus.FAILED, error="err"),
            _make_progress_entry(task_id="task-103", status=ProgressStatus.IN_PROGRESS),
            _make_progress_entry(task_id="task-104", status=ProgressStatus.BLOCKED),
            _make_progress_entry(task_id="task-105", status=ProgressStatus.SKIPPED),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-101"),
            _make_task(task_id="task-102"),
            _make_task(task_id="task-103"),
            _make_task(task_id="task-104"),
            _make_task(task_id="task-105"),
            _make_task(task_id="task-106"),  # untouched
        ]
        master._task_json = _make_task_json(tasks)

        result = master.restore_from_progress()

        total_from_counts = (
            result["already_completed"]
            + result["already_failed"]
            + result["already_blocked"]
            + result["reset_to_pending"]
            + result["untouched"]
        )
        assert total_from_counts == result["total_tasks"]
        assert result["total_tasks"] == 6

    def test_summary_state_matches_actual_state(self):
        """摘要中的 state 字段与实际 _state 一致"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.IN_PROGRESS),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        master._task_json = _make_task_json([_make_task(task_id="task-001")])

        result = master.restore_from_progress()

        assert result["state"] == master._state.value

    def test_double_restore_idempotent(self):
        """连续两次恢复结果一致（幂等性）"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.IN_PROGRESS),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
        ]
        master._task_json = _make_task_json(tasks)

        result1 = master.restore_from_progress()
        # 第一次恢复后 task-002 变为 PENDING，第二次恢复再次读取 IN_PROGRESS → PENDING
        result2 = master.restore_from_progress()

        assert result1["already_completed"] == result2["already_completed"]
        assert result1["reset_to_pending"] == result2["reset_to_pending"]
        assert tasks[1].status == TaskStatus.PENDING

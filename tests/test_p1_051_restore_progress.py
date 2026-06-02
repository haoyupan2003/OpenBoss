"""
P1-051 测试 — MasterAgent 断点恢复

测试内容：
- restore_from_progress(): 从 progress.txt 恢复断点
- _map_progress_to_task_status(): ProgressStatus → TaskStatus 映射
- _restore_execution_results(): 恢复执行结果
- _progress_to_result_status(): ProgressStatus → SubAgentResultStatus 映射
- _update_state_after_restore(): 根据恢复结果更新调度状态
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

from agent_automation_system.master_agent.master_agent import (
    MasterAgent,
    MasterAgentState,
)
from agent_automation_system.file_io.progress_manager import ProgressManager
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
    openclaw_notifier=None,
    progress_manager: ProgressManager | None = None,
) -> MasterAgent:
    """创建测试用 MasterAgent"""
    master = MasterAgent(
        max_concurrent_agents=max_concurrent,
        task_max_retries=task_max_retries,
        openclaw_notifier=openclaw_notifier,
        progress_manager=progress_manager,
    )
    master._state = state
    return master


# ── _map_progress_to_task_status 测试 ──────────────────────


class TestMapProgressToTaskStatus:
    """ProgressStatus → TaskStatus 恢复映射"""

    def test_completed_maps_to_completed(self):
        master = _make_master()
        assert master._map_progress_to_task_status(ProgressStatus.COMPLETED) == TaskStatus.COMPLETED

    def test_skipped_maps_to_skipped(self):
        master = _make_master()
        assert master._map_progress_to_task_status(ProgressStatus.SKIPPED) == TaskStatus.SKIPPED

    def test_failed_maps_to_failed(self):
        master = _make_master()
        assert master._map_progress_to_task_status(ProgressStatus.FAILED) == TaskStatus.FAILED

    def test_blocked_maps_to_blocked(self):
        master = _make_master()
        assert master._map_progress_to_task_status(ProgressStatus.BLOCKED) == TaskStatus.BLOCKED

    def test_in_progress_maps_to_pending(self):
        master = _make_master()
        assert master._map_progress_to_task_status(ProgressStatus.IN_PROGRESS) == TaskStatus.PENDING

    def test_retrying_maps_to_pending(self):
        master = _make_master()
        assert master._map_progress_to_task_status(ProgressStatus.RETRYING) == TaskStatus.PENDING


# ── _progress_to_result_status 测试 ────────────────────────


class TestProgressToResultStatus:
    """ProgressStatus → SubAgentResultStatus 映射"""

    def test_completed_to_success(self):
        master = _make_master()
        assert master._progress_to_result_status(ProgressStatus.COMPLETED) == SubAgentResultStatus.SUCCESS

    def test_skipped_to_success(self):
        master = _make_master()
        assert master._progress_to_result_status(ProgressStatus.SKIPPED) == SubAgentResultStatus.SUCCESS

    def test_failed_to_failed(self):
        master = _make_master()
        assert master._progress_to_result_status(ProgressStatus.FAILED) == SubAgentResultStatus.FAILED

    def test_blocked_to_blocked(self):
        master = _make_master()
        assert master._progress_to_result_status(ProgressStatus.BLOCKED) == SubAgentResultStatus.BLOCKED

    def test_in_progress_to_retry(self):
        master = _make_master()
        assert master._progress_to_result_status(ProgressStatus.IN_PROGRESS) == SubAgentResultStatus.RETRY

    def test_retrying_to_retry(self):
        master = _make_master()
        assert master._progress_to_result_status(ProgressStatus.RETRYING) == SubAgentResultStatus.RETRY


# ── _update_state_after_restore 测试 ───────────────────────


class TestUpdateStateAfterRestore:
    """恢复后调度状态更新"""

    def test_all_completed_sets_completed(self):
        master = _make_master()
        master._task_json = _make_task_json([
            _make_task(task_id="task-001", status=TaskStatus.COMPLETED),
            _make_task(task_id="task-002", status=TaskStatus.COMPLETED),
        ])
        master._update_state_after_restore(completed=2, failed=0, reset_to_pending=0)
        assert master._state == MasterAgentState.COMPLETED

    def test_all_completed_or_failed_with_failures_sets_failed(self):
        master = _make_master()
        master._task_json = _make_task_json([
            _make_task(task_id="task-001", status=TaskStatus.COMPLETED),
            _make_task(task_id="task-002", status=TaskStatus.FAILED),
        ])
        master._update_state_after_restore(completed=1, failed=1, reset_to_pending=0)
        assert master._state == MasterAgentState.FAILED

    def test_has_pending_tasks_sets_dispatching(self):
        master = _make_master()
        master._task_json = _make_task_json([
            _make_task(task_id="task-001", status=TaskStatus.COMPLETED),
            _make_task(task_id="task-002", status=TaskStatus.PENDING),
        ])
        master._update_state_after_restore(completed=1, failed=0, reset_to_pending=1)
        assert master._state == MasterAgentState.DISPATCHING

    def test_all_blocked_sets_paused(self):
        master = _make_master()
        master._task_json = _make_task_json([
            _make_task(task_id="task-001", status=TaskStatus.BLOCKED),
            _make_task(task_id="task-002", status=TaskStatus.BLOCKED),
        ])
        master._update_state_after_restore(completed=0, failed=0, reset_to_pending=0)
        assert master._state == MasterAgentState.PAUSED

    def test_all_failed_sets_failed(self):
        master = _make_master()
        master._task_json = _make_task_json([
            _make_task(task_id="task-001", status=TaskStatus.FAILED),
        ])
        master._update_state_after_restore(completed=0, failed=1, reset_to_pending=0)
        assert master._state == MasterAgentState.FAILED


# ── _restore_execution_results 测试 ────────────────────────


class TestRestoreExecutionResults:
    """从进度记录恢复执行结果"""

    def test_restores_completed_result(self):
        master = _make_master()
        entry = _make_progress_entry(status=ProgressStatus.COMPLETED)
        progress_map = {"task-001": entry}

        master._restore_execution_results(progress_map)

        assert "task-001" in master._execution_results
        result = master._execution_results["task-001"]
        assert result.status == SubAgentResultStatus.SUCCESS
        assert result.phase == AgentPhase.COMPLETED

    def test_restores_failed_result(self):
        master = _make_master()
        entry = _make_progress_entry(status=ProgressStatus.FAILED, error="build error")
        progress_map = {"task-001": entry}

        master._restore_execution_results(progress_map)

        result = master._execution_results["task-001"]
        assert result.status == SubAgentResultStatus.FAILED
        assert result.phase == AgentPhase.FAILED
        assert result.error == "build error"

    def test_skips_in_progress_entries(self):
        master = _make_master()
        entry = _make_progress_entry(status=ProgressStatus.IN_PROGRESS)
        progress_map = {"task-001": entry}

        master._restore_execution_results(progress_map)

        assert "task-001" not in master._execution_results

    def test_skips_retrying_entries(self):
        master = _make_master()
        entry = _make_progress_entry(status=ProgressStatus.RETRYING)
        progress_map = {"task-001": entry}

        master._restore_execution_results(progress_map)

        assert "task-001" not in master._execution_results

    def test_restores_git_info(self):
        master = _make_master()
        entry = _make_progress_entry(
            status=ProgressStatus.COMPLETED,
            git_sha="a1b2c3d",
        )
        progress_map = {"task-001": entry}

        master._restore_execution_results(progress_map)

        result = master._execution_results["task-001"]
        assert result.commit_hash == "a1b2c3d"

    def test_restores_multiple_results(self):
        master = _make_master()
        e1 = _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED)
        e2 = _make_progress_entry(task_id="task-002", status=ProgressStatus.FAILED, error="err")
        progress_map = {"task-001": e1, "task-002": e2}

        master._restore_execution_results(progress_map)

        assert len(master._execution_results) == 2


# ── restore_from_progress 核心测试 ─────────────────────────


class TestRestoreFromProgress:
    """restore_from_progress() 核心逻辑"""

    def test_no_task_json_raises_runtime_error(self):
        """task_json 未加载 → RuntimeError"""
        master = _make_master()
        with pytest.raises(RuntimeError, match="task_json not loaded"):
            master.restore_from_progress()

    def test_no_progress_manager_returns_not_restored(self):
        """ProgressManager 不可用 → restored=False"""
        master = _make_master()  # 无 progress_manager
        task = _make_task()
        master._task_json = _make_task_json([task])

        result = master.restore_from_progress()

        assert result["restored"] is False
        assert result["untouched"] == 1

    def test_empty_progress_file_untouched(self):
        """progress.txt 为空 → 所有任务 untouched"""
        pm = MagicMock()
        pm.read_progress.return_value = []
        master = _make_master(progress_manager=pm)
        task = _make_task()
        master._task_json = _make_task_json([task])

        result = master.restore_from_progress()

        assert result["restored"] is True
        assert result["untouched"] == 1
        assert result["already_completed"] == 0

    def test_completed_tasks_restored(self):
        """已完成任务正确恢复"""
        pm = MagicMock()
        entry = _make_progress_entry(status=ProgressStatus.COMPLETED)
        pm.read_progress.return_value = [entry]
        master = _make_master(progress_manager=pm)
        task = _make_task()
        master._task_json = _make_task_json([task])

        result = master.restore_from_progress()

        assert result["already_completed"] == 1
        assert task.status == TaskStatus.COMPLETED

    def test_failed_tasks_restored(self):
        """失败任务正确恢复"""
        pm = MagicMock()
        entry = _make_progress_entry(status=ProgressStatus.FAILED, error="timeout")
        pm.read_progress.return_value = [entry]
        master = _make_master(progress_manager=pm)
        task = _make_task()
        master._task_json = _make_task_json([task])

        result = master.restore_from_progress()

        assert result["already_failed"] == 1
        assert task.status == TaskStatus.FAILED
        assert task.error_message == "timeout"

    def test_in_progress_reset_to_pending(self):
        """中断中任务重置为 PENDING"""
        pm = MagicMock()
        entry = _make_progress_entry(status=ProgressStatus.IN_PROGRESS)
        pm.read_progress.return_value = [entry]
        master = _make_master(progress_manager=pm)
        task = _make_task(status=TaskStatus.IN_PROGRESS)
        master._task_json = _make_task_json([task])

        result = master.restore_from_progress()

        assert result["reset_to_pending"] == 1
        assert task.status == TaskStatus.PENDING

    def test_retrying_reset_to_pending(self):
        """重试中中断的任务重置为 PENDING"""
        pm = MagicMock()
        entry = _make_progress_entry(status=ProgressStatus.RETRYING, retry=2)
        pm.read_progress.return_value = [entry]
        master = _make_master(progress_manager=pm)
        task = _make_task()
        master._task_json = _make_task_json([task])

        result = master.restore_from_progress()

        assert result["reset_to_pending"] == 1
        assert task.status == TaskStatus.PENDING
        assert task.retry_count == 2

    def test_blocked_tasks_restored(self):
        """阻塞任务保持 BLOCKED"""
        pm = MagicMock()
        entry = _make_progress_entry(status=ProgressStatus.BLOCKED)
        pm.read_progress.return_value = [entry]
        master = _make_master(progress_manager=pm)
        task = _make_task()
        master._task_json = _make_task_json([task])

        result = master.restore_from_progress()

        assert result["already_blocked"] == 1
        assert task.status == TaskStatus.BLOCKED

    def test_skipped_counts_as_completed(self):
        """SKIPPED 计入 already_completed"""
        pm = MagicMock()
        entry = _make_progress_entry(status=ProgressStatus.SKIPPED)
        pm.read_progress.return_value = [entry]
        master = _make_master(progress_manager=pm)
        task = _make_task()
        master._task_json = _make_task_json([task])

        result = master.restore_from_progress()

        assert result["already_completed"] == 1
        assert task.status == TaskStatus.SKIPPED

    def test_mixed_progress_states(self):
        """混合进度状态恢复"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.FAILED, error="err"),
            _make_progress_entry(task_id="task-003", status=ProgressStatus.IN_PROGRESS),
            _make_progress_entry(task_id="task-004", status=ProgressStatus.BLOCKED),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
            _make_task(task_id="task-003"),
            _make_task(task_id="task-004"),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.restore_from_progress()

        assert result["already_completed"] == 1
        assert result["already_failed"] == 1
        assert result["reset_to_pending"] == 1
        assert result["already_blocked"] == 1
        assert result["untouched"] == 0

    def test_retry_count_restored(self):
        """retry_count 从 progress 恢复"""
        pm = MagicMock()
        entry = _make_progress_entry(status=ProgressStatus.RETRYING, retry=3)
        pm.read_progress.return_value = [entry]
        master = _make_master(progress_manager=pm)
        task = _make_task(retry_count=0)
        master._task_json = _make_task_json([task])

        master.restore_from_progress()

        assert task.retry_count == 3

    def test_error_message_restored(self):
        """error_message 从 progress 恢复"""
        pm = MagicMock()
        entry = _make_progress_entry(status=ProgressStatus.FAILED, error="OOM")
        pm.read_progress.return_value = [entry]
        master = _make_master(progress_manager=pm)
        task = _make_task()
        master._task_json = _make_task_json([task])

        master.restore_from_progress()

        assert task.error_message == "OOM"

    def test_progress_read_exception_returns_not_restored(self):
        """progress 读取异常 → restored=False"""
        pm = MagicMock()
        pm.read_progress.side_effect = IOError("disk error")
        master = _make_master(progress_manager=pm)
        task = _make_task()
        master._task_json = _make_task_json([task])

        result = master.restore_from_progress()

        assert result["restored"] is False

    def test_partial_progress_some_untouched(self):
        """部分任务有进度、部分无"""
        pm = MagicMock()
        entry = _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED)
        pm.read_progress.return_value = [entry]
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.restore_from_progress()

        assert result["already_completed"] == 1
        assert result["untouched"] == 1


# ── restore_from_progress 状态转换测试 ──────────────────────


class TestRestoreStateTransition:
    """恢复后的调度状态转换"""

    def test_all_completed_transitions_to_completed(self):
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.COMPLETED),
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

    def test_has_pending_transitions_to_dispatching(self):
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.IN_PROGRESS),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(state=MasterAgentState.IDLE, progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
        ]
        master._task_json = _make_task_json(tasks)

        master.restore_from_progress()

        assert master._state == MasterAgentState.DISPATCHING

    def test_has_failed_no_pending_transitions_to_failed(self):
        pm = MagicMock()
        entry = _make_progress_entry(status=ProgressStatus.FAILED, error="err")
        pm.read_progress.return_value = [entry]
        master = _make_master(state=MasterAgentState.IDLE, progress_manager=pm)
        task = _make_task()
        master._task_json = _make_task_json([task])

        master.restore_from_progress()

        assert master._state == MasterAgentState.FAILED

    def test_all_blocked_transitions_to_paused(self):
        pm = MagicMock()
        entry = _make_progress_entry(status=ProgressStatus.BLOCKED)
        pm.read_progress.return_value = [entry]
        master = _make_master(state=MasterAgentState.IDLE, progress_manager=pm)
        task = _make_task()
        master._task_json = _make_task_json([task])

        master.restore_from_progress()

        assert master._state == MasterAgentState.PAUSED


# ── restore_from_progress 执行结果恢复测试 ──────────────────


class TestRestoreExecutionResultsIntegration:
    """restore_from_progress 恢复 execution_results 的集成测试"""

    def test_completed_task_has_execution_result(self):
        pm = MagicMock()
        entry = _make_progress_entry(status=ProgressStatus.COMPLETED, git_sha="deadbeef")
        pm.read_progress.return_value = [entry]
        master = _make_master(progress_manager=pm)
        task = _make_task()
        master._task_json = _make_task_json([task])

        master.restore_from_progress()

        assert "task-001" in master._execution_results
        result = master._execution_results["task-001"]
        assert result.status == SubAgentResultStatus.SUCCESS
        assert result.commit_hash == "deadbeef"

    def test_failed_task_has_execution_result(self):
        pm = MagicMock()
        entry = _make_progress_entry(status=ProgressStatus.FAILED, error="segfault")
        pm.read_progress.return_value = [entry]
        master = _make_master(progress_manager=pm)
        task = _make_task()
        master._task_json = _make_task_json([task])

        master.restore_from_progress()

        result = master._execution_results["task-001"]
        assert result.status == SubAgentResultStatus.FAILED
        assert result.error == "segfault"

    def test_in_progress_task_no_execution_result(self):
        pm = MagicMock()
        entry = _make_progress_entry(status=ProgressStatus.IN_PROGRESS)
        pm.read_progress.return_value = [entry]
        master = _make_master(progress_manager=pm)
        task = _make_task()
        master._task_json = _make_task_json([task])

        master.restore_from_progress()

        assert "task-001" not in master._execution_results

    def test_progress_summary_after_restore(self):
        """恢复后 get_progress_summary 正确反映进度"""
        pm = MagicMock()
        entries = [
            _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED),
            _make_progress_entry(task_id="task-002", status=ProgressStatus.FAILED, error="err"),
        ]
        pm.read_progress.return_value = entries
        master = _make_master(progress_manager=pm)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
        ]
        master._task_json = _make_task_json(tasks)

        master.restore_from_progress()
        summary = master.get_progress_summary()

        assert summary["completed"] == 1
        assert summary["failed"] == 1
        assert summary["total"] == 2


# ── restore_from_progress 与调度集成 ────────────────────────


class TestRestoreDispatchIntegration:
    """恢复后调度器正确识别可调度任务"""

    def test_restored_pending_tasks_are_dispatchable(self):
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
        ]
        master._task_json = _make_task_json(tasks)

        master.restore_from_progress()

        # task-002 被重置为 PENDING，依赖 task-001 已完成 → 可调度
        dispatchable = master.get_dispatchable_tasks()
        assert any(t.id == "task-002" for t in dispatchable)

    def test_restored_blocked_tasks_not_dispatchable(self):
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

        # 恢复后状态为 PAUSED（全 BLOCKED），需切到 DISPATCHING 才能查询
        master._state = MasterAgentState.DISPATCHING
        dispatchable = master.get_dispatchable_tasks()
        assert not any(t.id == "task-002" for t in dispatchable)

    def test_completed_tasks_not_dispatchable(self):
        pm = MagicMock()
        entry = _make_progress_entry(status=ProgressStatus.COMPLETED)
        pm.read_progress.return_value = [entry]
        master = _make_master(progress_manager=pm)
        task = _make_task()
        master._task_json = _make_task_json([task])

        master.restore_from_progress()

        # 恢复后状态为 COMPLETED，手动设为 DISPATCHING 检查
        master._state = MasterAgentState.DISPATCHING
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 0

    def test_untouched_tasks_remain_dispatchable(self):
        """无进度记录的任务保持原状态，仍可调度"""
        pm = MagicMock()
        pm.read_progress.return_value = []
        master = _make_master(progress_manager=pm)
        task = _make_task()
        master._task_json = _make_task_json([task])

        master.restore_from_progress()

        # 恢复后为 PAUSED（无进度但有任务），手动设为 DISPATCHING
        master._state = MasterAgentState.DISPATCHING
        dispatchable = master.get_dispatchable_tasks()
        assert any(t.id == "task-001" for t in dispatchable)


# ── 恢复摘要格式测试 ──────────────────────────────────────


class TestRestoreSummaryFormat:
    """恢复返回摘要格式验证"""

    def test_summary_has_all_keys(self):
        pm = MagicMock()
        pm.read_progress.return_value = []
        master = _make_master(progress_manager=pm)
        task = _make_task()
        master._task_json = _make_task_json([task])

        result = master.restore_from_progress()

        expected_keys = {
            "restored", "total_tasks", "already_completed",
            "already_failed", "already_blocked", "reset_to_pending",
            "untouched", "state",
        }
        assert set(result.keys()) == expected_keys

    def test_total_tasks_matches_task_json(self):
        pm = MagicMock()
        pm.read_progress.return_value = []
        master = _make_master(progress_manager=pm)
        tasks = [_make_task(task_id=f"task-{i:03d}") for i in range(1, 6)]
        master._task_json = _make_task_json(tasks)

        result = master.restore_from_progress()

        assert result["total_tasks"] == 5

    def test_state_reflects_current_state(self):
        pm = MagicMock()
        entry = _make_progress_entry(status=ProgressStatus.COMPLETED)
        pm.read_progress.return_value = [entry]
        master = _make_master(progress_manager=pm)
        task = _make_task()
        master._task_json = _make_task_json([task])

        result = master.restore_from_progress()

        assert result["state"] == "completed"

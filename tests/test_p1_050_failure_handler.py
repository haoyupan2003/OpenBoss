"""
P1-050 测试 — MasterAgent 失败处理

测试内容：
- on_task_failed(task, error): 任务失败处理入口
- _pause_dependent_tasks(task_id): 暂停依赖任务
- _record_failure(task, error): 记录失败详情
- _notify_openclaw(event, details): 通知 OpenClaw
- FailureAction 枚举
- openclaw_notifier 注入
- failure_log 记录
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from agent_automation_system.master_agent.master_agent import (
    FailureAction,
    MasterAgent,
    MasterAgentState,
)
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


def _make_master(
    max_concurrent: int = 3,
    task_max_retries: int = 1,
    state: MasterAgentState = MasterAgentState.DISPATCHING,
    openclaw_notifier=None,
    poll_interval: float = 0.01,
) -> MasterAgent:
    """创建测试用 MasterAgent"""
    master = MasterAgent(
        max_concurrent_agents=max_concurrent,
        task_max_retries=task_max_retries,
        openclaw_notifier=openclaw_notifier,
        poll_interval=poll_interval,
    )
    master._state = state
    return master


# ── FailureAction 枚举测试 ─────────────────────────────────


class TestFailureAction:
    """FailureAction 枚举值验证"""

    def test_retry_value(self):
        assert FailureAction.RETRY == "retry"

    def test_abort_value(self):
        assert FailureAction.ABORT == "abort"

    def test_is_str_enum(self):
        assert isinstance(FailureAction.RETRY, str)
        assert isinstance(FailureAction.ABORT, str)

    def test_enum_members(self):
        members = list(FailureAction)
        assert len(members) == 2
        assert FailureAction.RETRY in members
        assert FailureAction.ABORT in members


# ── on_task_failed 核心测试 ────────────────────────────────


class TestOnTaskFailed:
    """on_task_failed(task, error) 核心逻辑"""

    def test_retryable_task_returns_retry(self):
        """可重试任务 → RETRY"""
        master = _make_master(task_max_retries=1)
        task = _make_task(retry_count=0)
        master._task_json = _make_task_json([task])

        action = master.on_task_failed(task, "build error")

        assert action == FailureAction.RETRY

    def test_retryable_task_increments_retry_count(self):
        """可重试任务 → retry_count 递增"""
        master = _make_master(task_max_retries=2)
        task = _make_task(retry_count=0)
        master._task_json = _make_task_json([task])

        master.on_task_failed(task, "timeout")

        assert task.retry_count == 1
        assert task.status == TaskStatus.PENDING

    def test_retryable_task_resets_to_pending(self):
        """可重试任务 → 状态重置为 PENDING"""
        master = _make_master(task_max_retries=1)
        task = _make_task(retry_count=0, status=TaskStatus.IN_PROGRESS)
        master._task_json = _make_task_json([task])

        master.on_task_failed(task, "error")

        assert task.status == TaskStatus.PENDING

    def test_retryable_task_sets_error_message(self):
        """可重试任务 → 记录 error_message"""
        master = _make_master(task_max_retries=1)
        task = _make_task(retry_count=0)
        master._task_json = _make_task_json([task])

        master.on_task_failed(task, "syntax error")

        assert task.error_message == "syntax error"

    def test_unrecoverable_task_returns_abort(self):
        """不可恢复任务 → ABORT"""
        master = _make_master(task_max_retries=1)
        task = _make_task(retry_count=1)  # retry_count == max_retries
        master._task_json = _make_task_json([task])

        action = master.on_task_failed(task, "fatal error")

        assert action == FailureAction.ABORT

    def test_unrecoverable_task_sets_failed(self):
        """不可恢复任务 → 状态设为 FAILED"""
        master = _make_master(task_max_retries=1)
        task = _make_task(retry_count=1)
        master._task_json = _make_task_json([task])

        master.on_task_failed(task, "catastrophic")

        assert task.status == TaskStatus.FAILED
        assert task.error_message == "catastrophic"

    def test_zero_max_retries_always_aborts(self):
        """max_retries=0 → 任何失败直接 ABORT"""
        master = _make_master(task_max_retries=0)
        task = _make_task(retry_count=0)
        master._task_json = _make_task_json([task])

        action = master.on_task_failed(task, "no retries allowed")

        assert action == FailureAction.ABORT
        assert task.status == TaskStatus.FAILED

    def test_retry_then_abort_sequence(self):
        """模拟重试后仍失败 → 先 RETRY 再 ABORT"""
        master = _make_master(task_max_retries=1)
        task = _make_task(retry_count=0)
        master._task_json = _make_task_json([task])

        # 第一次失败 → RETRY
        action1 = master.on_task_failed(task, "first failure")
        assert action1 == FailureAction.RETRY
        assert task.retry_count == 1
        assert task.status == TaskStatus.PENDING

        # 第二次失败 → ABORT
        action2 = master.on_task_failed(task, "second failure")
        assert action2 == FailureAction.ABORT
        assert task.status == TaskStatus.FAILED

    def test_none_task_raises_value_error(self):
        """task=None → ValueError"""
        master = _make_master()
        master._task_json = _make_task_json([_make_task()])

        with pytest.raises(ValueError, match="task cannot be None"):
            master.on_task_failed(None, "error")

    def test_no_task_json_raises_runtime_error(self):
        """task_json 未加载 → RuntimeError"""
        master = _make_master()
        task = _make_task()

        with pytest.raises(RuntimeError, match="task_json not loaded"):
            master.on_task_failed(task, "error")

    def test_error_none_is_accepted(self):
        """error=None 不抛异常"""
        master = _make_master(task_max_retries=0)
        task = _make_task(retry_count=0)
        master._task_json = _make_task_json([task])

        action = master.on_task_failed(task, None)

        assert action == FailureAction.ABORT
        assert task.error_message is None

    def test_multiple_retries_before_abort(self):
        """多次重试后最终 ABORT"""
        master = _make_master(task_max_retries=3)
        task = _make_task(retry_count=0)
        master._task_json = _make_task_json([task])

        # 第 1~3 次失败 → RETRY
        for i in range(3):
            action = master.on_task_failed(task, f"failure #{i+1}")
            assert action == FailureAction.RETRY
            assert task.retry_count == i + 1

        # 第 4 次失败 → ABORT (retry_count=3 == max_retries=3)
        action = master.on_task_failed(task, "final failure")
        assert action == FailureAction.ABORT
        assert task.status == TaskStatus.FAILED


# ── _pause_dependent_tasks 测试 ────────────────────────────


class TestPauseDependentTasks:
    """_pause_dependent_tasks(task_id) 依赖任务暂停"""

    def test_pauses_pending_dependents(self):
        """暂停依赖失败任务的 PENDING 任务"""
        master = _make_master()
        t1 = _make_task(task_id="task-001", status=TaskStatus.FAILED)
        t2 = _make_task(task_id="task-002", dependencies=["task-001"])
        t3 = _make_task(task_id="task-003", dependencies=[])
        master._task_json = _make_task_json([t1, t2, t3])

        paused = master._pause_dependent_tasks("task-001")

        assert "task-002" in paused
        assert t2.status == TaskStatus.BLOCKED
        assert t3.status == TaskStatus.PENDING  # 不受影响

    def test_pauses_in_progress_dependents(self):
        """暂停依赖失败任务的 IN_PROGRESS 任务"""
        master = _make_master()
        t1 = _make_task(task_id="task-001", status=TaskStatus.FAILED)
        t2 = _make_task(
            task_id="task-002",
            status=TaskStatus.IN_PROGRESS,
            dependencies=["task-001"],
        )
        master._task_json = _make_task_json([t1, t2])

        paused = master._pause_dependent_tasks("task-001")

        assert "task-002" in paused
        assert t2.status == TaskStatus.BLOCKED

    def test_does_not_pause_completed_dependents(self):
        """不暂停已完成的依赖任务"""
        master = _make_master()
        t1 = _make_task(task_id="task-001", status=TaskStatus.FAILED)
        t2 = _make_task(
            task_id="task-002",
            status=TaskStatus.COMPLETED,
            dependencies=["task-001"],
        )
        master._task_json = _make_task_json([t1, t2])

        paused = master._pause_dependent_tasks("task-001")

        assert "task-002" not in paused
        assert t2.status == TaskStatus.COMPLETED

    def test_does_not_pause_failed_dependents(self):
        """不暂停已失败的任务"""
        master = _make_master()
        t1 = _make_task(task_id="task-001", status=TaskStatus.FAILED)
        t2 = _make_task(
            task_id="task-002",
            status=TaskStatus.FAILED,
            dependencies=["task-001"],
        )
        master._task_json = _make_task_json([t1, t2])

        paused = master._pause_dependent_tasks("task-001")

        assert "task-002" not in paused

    def test_no_dependents_returns_empty(self):
        """无依赖任务 → 返回空列表"""
        master = _make_master()
        t1 = _make_task(task_id="task-001", status=TaskStatus.FAILED)
        t2 = _make_task(task_id="task-002", dependencies=[])
        master._task_json = _make_task_json([t1, t2])

        paused = master._pause_dependent_tasks("task-001")

        assert paused == []

    def test_no_task_json_returns_empty(self):
        """task_json 为 None → 返回空列表"""
        master = _make_master()

        paused = master._pause_dependent_tasks("task-001")

        assert paused == []

    def test_cascading_dependencies(self):
        """链式依赖：t1→t2→t3，t1 失败暂停 t2（t3 不受影响因为只直接依赖 t2）"""
        master = _make_master()
        t1 = _make_task(task_id="task-001", status=TaskStatus.FAILED)
        t2 = _make_task(task_id="task-002", dependencies=["task-001"])
        t3 = _make_task(task_id="task-003", dependencies=["task-002"])
        master._task_json = _make_task_json([t1, t2, t3])

        paused = master._pause_dependent_tasks("task-001")

        assert "task-002" in paused
        assert t2.status == TaskStatus.BLOCKED
        # t3 不直接依赖 t1，所以不暂停
        assert t3.status == TaskStatus.PENDING

    def test_multiple_dependents(self):
        """多个下游任务同时暂停"""
        master = _make_master()
        t1 = _make_task(task_id="task-001", status=TaskStatus.FAILED)
        t2 = _make_task(task_id="task-002", dependencies=["task-001"])
        t3 = _make_task(task_id="task-003", dependencies=["task-001"])
        t4 = _make_task(task_id="task-004", dependencies=["task-001"])
        master._task_json = _make_task_json([t1, t2, t3, t4])

        paused = master._pause_dependent_tasks("task-001")

        assert len(paused) == 3
        assert all(tid in paused for tid in ["task-002", "task-003", "task-004"])

    def test_dependent_on_multiple_deps(self):
        """任务依赖多个前置，其中一个失败也暂停"""
        master = _make_master()
        t1 = _make_task(task_id="task-001", status=TaskStatus.FAILED)
        t2 = _make_task(task_id="task-002", status=TaskStatus.COMPLETED)
        t3 = _make_task(
            task_id="task-003",
            dependencies=["task-001", "task-002"],
        )
        master._task_json = _make_task_json([t1, t2, t3])

        paused = master._pause_dependent_tasks("task-001")

        assert "task-003" in paused
        assert t3.status == TaskStatus.BLOCKED


# ── _record_failure 测试 ───────────────────────────────────


class TestRecordFailure:
    """_record_failure(task, error) 失败记录"""

    def test_appends_to_failure_log(self):
        """失败事件追加到 failure_log"""
        master = _make_master()
        task = _make_task(retry_count=1)

        master._record_failure(task, "test error")

        assert len(master.failure_log) == 1
        record = master.failure_log[0]
        assert record["task_id"] == "task-001"
        assert record["error"] == "test error"
        assert record["retry_count"] == 1

    def test_record_includes_timestamp(self):
        """记录包含 timestamp"""
        master = _make_master()
        task = _make_task()

        master._record_failure(task, "error")

        record = master.failure_log[0]
        assert "timestamp" in record
        # timestamp 是 ISO 格式字符串
        parsed = datetime.fromisoformat(record["timestamp"])
        assert isinstance(parsed, datetime)

    def test_record_includes_max_retries(self):
        """记录包含 max_retries"""
        master = _make_master(task_max_retries=3)
        task = _make_task()

        master._record_failure(task, "error")

        record = master.failure_log[0]
        assert record["max_retries"] == 3

    def test_record_includes_task_status(self):
        """记录包含任务当时的状态"""
        master = _make_master()
        task = _make_task(status=TaskStatus.IN_PROGRESS)

        master._record_failure(task, "error")

        record = master.failure_log[0]
        assert record["task_status"] == "in_progress"

    def test_multiple_failures_accumulate(self):
        """多次失败记录累积"""
        master = _make_master()
        task = _make_task()

        master._record_failure(task, "error 1")
        master._record_failure(task, "error 2")

        assert len(master.failure_log) == 2

    def test_error_none_recorded_as_none(self):
        """error=None 时记录为 None"""
        master = _make_master()
        task = _make_task()

        master._record_failure(task, None)

        record = master.failure_log[0]
        assert record["error"] is None

    def test_updates_task_error_message(self):
        """记录时更新 task 的 error_message"""
        master = _make_master()
        task = _make_task()

        master._record_failure(task, "new error")

        assert task.error_message == "new error"

    def test_does_not_overwrite_error_when_none(self):
        """error=None 不覆盖已有 error_message"""
        master = _make_master()
        task = _make_task(error_message="original error")

        master._record_failure(task, None)

        assert task.error_message == "original error"


# ── _notify_openclaw 测试 ──────────────────────────────────


class TestNotifyOpenclaw:
    """_notify_openclaw(event, details) 通知 OpenClaw"""

    def test_calls_injected_notifier(self):
        """调用注入的通知回调"""
        notifier = MagicMock()
        master = _make_master(openclaw_notifier=notifier)

        master._notify_openclaw("task_failed", {"task_id": "task-001"})

        notifier.assert_called_once_with(
            "task_failed",
            {"task_id": "task-001"},
        )

    def test_default_notifier_does_not_raise(self):
        """默认通知器不抛异常"""
        master = _make_master()  # 无注入，使用默认

        # 不应抛异常
        master._notify_openclaw("task_failed", {"task_id": "task-001"})

    def test_notifier_exception_does_not_propagate(self):
        """通知器异常不影响主流程"""
        failing_notifier = MagicMock(side_effect=ConnectionError("network down"))
        master = _make_master(openclaw_notifier=failing_notifier)

        # 不应抛异常
        master._notify_openclaw("task_failed", {"task_id": "task-001"})

    def test_on_task_failed_retry_notifies(self):
        """重试时发送 task_retry 通知"""
        notifier = MagicMock()
        master = _make_master(task_max_retries=1, openclaw_notifier=notifier)
        task = _make_task(retry_count=0)
        master._task_json = _make_task_json([task])

        master.on_task_failed(task, "retry error")

        notifier.assert_called_once()
        call_args = notifier.call_args
        assert call_args[0][0] == "task_retry"
        assert call_args[0][1]["task_id"] == "task-001"
        assert call_args[0][1]["retry_count"] == 1

    def test_on_task_failed_abort_notifies(self):
        """不可恢复时发送 task_failed 通知"""
        notifier = MagicMock()
        master = _make_master(task_max_retries=0, openclaw_notifier=notifier)
        task = _make_task(retry_count=0)
        master._task_json = _make_task_json([task])

        master.on_task_failed(task, "fatal error")

        notifier.assert_called_once()
        call_args = notifier.call_args
        assert call_args[0][0] == "task_failed"
        assert call_args[0][1]["task_id"] == "task-001"
        assert call_args[0][1]["error"] == "fatal error"

    def test_abort_notification_includes_paused_dependents(self):
        """ABORT 通知包含暂停的依赖任务列表"""
        notifier = MagicMock()
        master = _make_master(task_max_retries=0, openclaw_notifier=notifier)
        t1 = _make_task(task_id="task-001", retry_count=0)
        t2 = _make_task(task_id="task-002", dependencies=["task-001"])
        master._task_json = _make_task_json([t1, t2])

        master.on_task_failed(t1, "upstream failed")

        call_args = notifier.call_args
        details = call_args[0][1]
        assert "paused_dependents" in details
        assert "task-002" in details["paused_dependents"]

    def test_abort_notification_includes_progress_summary(self):
        """ABORT 通知包含进度摘要"""
        notifier = MagicMock()
        master = _make_master(task_max_retries=0, openclaw_notifier=notifier)
        task = _make_task(retry_count=0)
        master._task_json = _make_task_json([task])

        master.on_task_failed(task, "error")

        call_args = notifier.call_args
        details = call_args[0][1]
        assert "progress_summary" in details
        assert details["progress_summary"]["total"] == 1


# ── failure_log 属性测试 ──────────────────────────────────


class TestFailureLog:
    """failure_log 属性"""

    def test_initial_failure_log_empty(self):
        """初始 failure_log 为空"""
        master = _make_master()
        assert master.failure_log == []

    def test_failure_log_returns_copy(self):
        """failure_log 返回副本，不影响内部状态"""
        master = _make_master()
        task = _make_task()
        master._task_json = _make_task_json([task])
        master.on_task_failed(task, "error")

        log_copy = master.failure_log
        log_copy.clear()

        assert len(master.failure_log) == 1

    def test_reset_clears_failure_log(self):
        """reset() 清空 failure_log"""
        master = _make_master()
        task = _make_task()
        master._task_json = _make_task_json([task])
        master.on_task_failed(task, "error")

        assert len(master.failure_log) == 1

        master._state = MasterAgentState.FAILED
        master.reset()

        assert master.failure_log == []


# ── openclaw_notifier 属性测试 ─────────────────────────────


class TestOpenclawNotifierProperty:
    """openclaw_notifier 属性"""

    def test_default_notifier_is_callable(self):
        """默认通知器可调用"""
        master = _make_master()
        assert callable(master.openclaw_notifier)

    def test_custom_notifier_accessible(self):
        """自定义通知器可通过属性访问"""
        notifier = MagicMock()
        master = _make_master(openclaw_notifier=notifier)
        assert master.openclaw_notifier is notifier


# ── on_task_failed 与主循环集成 ────────────────────────────


class TestOnTaskFailedIntegration:
    """on_task_failed 与主循环的集成"""

    def test_failed_task_triggers_termination_check(self):
        """失败任务在主循环中触发终止检查"""
        master = _make_master(task_max_retries=0, poll_interval=0.01)
        t1 = _make_task(task_id="task-001", retry_count=0)
        master._task_json = _make_task_json([t1])

        # 手动触发失败处理
        action = master.on_task_failed(t1, "test failure")

        assert action == FailureAction.ABORT
        assert t1.status == TaskStatus.FAILED
        # 检查不可恢复失败
        assert master._has_unrecoverable_failure()

    def test_blocked_dependents_prevent_dispatch(self):
        """被暂停的依赖任务不再被调度"""
        master = _make_master(task_max_retries=0)
        t1 = _make_task(task_id="task-001", retry_count=0)
        t2 = _make_task(task_id="task-002", dependencies=["task-001"])
        master._task_json = _make_task_json([t1, t2])

        # t1 失败 → t2 被 BLOCKED
        master.on_task_failed(t1, "upstream failed")

        assert t2.status == TaskStatus.BLOCKED
        # BLOCKED 任务不在可调度列表中
        dispatchable = master.get_dispatchable_tasks()
        assert all(t.id != "task-002" for t in dispatchable)

    def test_partial_failure_with_independent_tasks(self):
        """部分任务失败不影响独立任务"""
        master = _make_master(task_max_retries=0)
        t1 = _make_task(task_id="task-001", retry_count=0)
        t2 = _make_task(task_id="task-002", dependencies=["task-001"])
        t3 = _make_task(task_id="task-003", dependencies=[])
        master._task_json = _make_task_json([t1, t2, t3])

        # t1 失败 → t2 BLOCKED，t3 不受影响
        master.on_task_failed(t1, "task-001 failed")

        assert t1.status == TaskStatus.FAILED
        assert t2.status == TaskStatus.BLOCKED
        assert t3.status == TaskStatus.PENDING
        # t3 仍可调度
        dispatchable = master.get_dispatchable_tasks()
        assert any(t.id == "task-003" for t in dispatchable)

    def test_failure_log_tracks_full_sequence(self):
        """failure_log 追踪完整失败序列"""
        master = _make_master(task_max_retries=2)
        task = _make_task(retry_count=0)
        master._task_json = _make_task_json([task])

        master.on_task_failed(task, "fail 1")
        master.on_task_failed(task, "fail 2")
        master.on_task_failed(task, "fail 3")

        assert len(master.failure_log) == 3
        assert master.failure_log[0]["error"] == "fail 1"
        assert master.failure_log[1]["error"] == "fail 2"
        assert master.failure_log[2]["error"] == "fail 3"

    def test_notifier_receives_all_events(self):
        """通知器接收所有事件（retry + abort）"""
        notifier = MagicMock()
        master = _make_master(task_max_retries=1, openclaw_notifier=notifier)
        task = _make_task(retry_count=0)
        master._task_json = _make_task_json([task])

        master.on_task_failed(task, "fail 1")  # RETRY
        master.on_task_failed(task, "fail 2")  # ABORT

        assert notifier.call_count == 2
        events = [call[0][0] for call in notifier.call_args_list]
        assert events == ["task_retry", "task_failed"]

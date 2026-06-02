"""
P1-049 测试 — MasterAgent 主循环与进度监控

测试内容：
- poll_sub_agent_status(): 轮询活跃 Agent 状态
- run_main_loop(): 主调度循环
- _dispatch_available_tasks(): 批量调度
- _check_termination(): 终止条件检查
- _has_unrecoverable_failure(): 不可恢复失败检测
- _build_result_from_progress(): ProgressEntry → SubAgentResult 转换
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

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
    SubAgent,
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
    poll_interval: float = 0.01,
    state: MasterAgentState = MasterAgentState.DISPATCHING,
) -> MasterAgent:
    """创建测试用 MasterAgent"""
    master = MasterAgent(
        max_concurrent_agents=max_concurrent,
        task_max_retries=task_max_retries,
        poll_interval=poll_interval,
    )
    master._state = state
    return master


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


def _make_success_result(task_id: str = "task-001") -> SubAgentResult:
    """创建成功执行结果"""
    return SubAgentResult(
        task_id=task_id,
        status=SubAgentResultStatus.SUCCESS,
        phase=AgentPhase.COMPLETED,
        role="senior-developer",
        output="Task completed",
    )


def _make_failed_result(task_id: str = "task-001", error: str = "error") -> SubAgentResult:
    """创建失败执行结果"""
    return SubAgentResult(
        task_id=task_id,
        status=SubAgentResultStatus.FAILED,
        phase=AgentPhase.FAILED,
        role="senior-developer",
        error=error,
    )


def _make_mock_agent(result: SubAgentResult | None = None) -> MagicMock:
    """创建 mock SubAgent"""
    agent = MagicMock(spec=SubAgent)
    agent.role_name = "senior-developer"
    agent.run.return_value = result or _make_success_result()
    return agent


# ── poll_sub_agent_status 测试 ───────────────────────────────────


class TestPollSubAgentStatus:
    """poll_sub_agent_status 轮询活跃 Agent 状态"""

    def test_no_active_agents_returns_empty(self):
        """无活跃 Agent 时返回空字典"""
        master = _make_master()
        changes = master.poll_sub_agent_status()
        assert changes == {}

    def test_detects_completed_agent(self):
        """检测到 progress.txt 中的已完成 Agent"""
        master = _make_master()
        tasks = [_make_task(status=TaskStatus.IN_PROGRESS)]
        master._task_json = _make_task_json(tasks)

        # 模拟活跃 Agent
        mock_agent = _make_mock_agent()
        master._active_agents["task-001"] = mock_agent

        # 模拟 ProgressManager
        mock_pm = MagicMock()
        entry = _make_progress_entry(task_id="task-001", status=ProgressStatus.COMPLETED)
        mock_pm.read_progress.return_value = [entry]
        master._progress_manager = mock_pm

        changes = master.poll_sub_agent_status()

        assert "task-001" in changes
        assert changes["task-001"] == "COMPLETED"
        # Agent 应从活跃列表移除（通过 record_result）
        assert "task-001" not in master._active_agents
        # 任务状态应更新为 COMPLETED
        assert tasks[0].status == TaskStatus.COMPLETED

    def test_detects_failed_agent(self):
        """检测到 progress.txt 中的失败 Agent"""
        master = _make_master()
        tasks = [_make_task(status=TaskStatus.IN_PROGRESS)]
        master._task_json = _make_task_json(tasks)
        master._active_agents["task-001"] = _make_mock_agent()

        mock_pm = MagicMock()
        entry = _make_progress_entry(
            task_id="task-001",
            status=ProgressStatus.FAILED,
            error="Build failed",
        )
        mock_pm.read_progress.return_value = [entry]
        master._progress_manager = mock_pm

        changes = master.poll_sub_agent_status()

        assert changes["task-001"] == "FAILED"
        assert tasks[0].status == TaskStatus.FAILED

    def test_detects_blocked_agent(self):
        """检测到 progress.txt 中的阻塞 Agent"""
        master = _make_master()
        tasks = [_make_task(status=TaskStatus.IN_PROGRESS)]
        master._task_json = _make_task_json(tasks)
        master._active_agents["task-001"] = _make_mock_agent()

        mock_pm = MagicMock()
        entry = _make_progress_entry(
            task_id="task-001",
            status=ProgressStatus.BLOCKED,
            error="Dependency missing",
        )
        mock_pm.read_progress.return_value = [entry]
        master._progress_manager = mock_pm

        changes = master.poll_sub_agent_status()

        assert changes["task-001"] == "BLOCKED"
        assert tasks[0].status == TaskStatus.BLOCKED

    def test_detects_retrying_agent(self):
        """检测到重试中的 Agent — 重新排队"""
        master = _make_master()
        tasks = [_make_task(status=TaskStatus.IN_PROGRESS, retry_count=0)]
        master._task_json = _make_task_json(tasks)
        master._active_agents["task-001"] = _make_mock_agent()

        mock_pm = MagicMock()
        entry = _make_progress_entry(
            task_id="task-001",
            status=ProgressStatus.RETRYING,
            retry=1,
        )
        mock_pm.read_progress.return_value = [entry]
        master._progress_manager = mock_pm

        changes = master.poll_sub_agent_status()

        assert changes["task-001"] == "RETRYING"
        # 任务应重新排队
        assert tasks[0].status == TaskStatus.PENDING
        assert tasks[0].retry_count == 1
        # Agent 应从活跃列表移除
        assert "task-001" not in master._active_agents

    def test_no_progress_entry_for_task(self):
        """progress.txt 中无对应条目时不产生变更"""
        master = _make_master()
        master._task_json = _make_task_json([_make_task()])
        master._active_agents["task-001"] = _make_mock_agent()

        mock_pm = MagicMock()
        mock_pm.read_progress.return_value = []  # 空
        master._progress_manager = mock_pm

        changes = master.poll_sub_agent_status()
        assert changes == {}
        assert "task-001" in master._active_agents

    def test_no_progress_manager_returns_empty(self):
        """无 ProgressManager 时返回空字典"""
        master = _make_master()
        master._task_json = _make_task_json([_make_task()])
        master._active_agents["task-001"] = _make_mock_agent()
        # 不设置 _progress_manager

        changes = master.poll_sub_agent_status()
        assert changes == {}

    def test_progress_read_exception_returns_empty(self):
        """ProgressManager 读取异常时返回空字典"""
        master = _make_master()
        master._task_json = _make_task_json([_make_task()])
        master._active_agents["task-001"] = _make_mock_agent()

        mock_pm = MagicMock()
        mock_pm.read_progress.side_effect = IOError("file not found")
        master._progress_manager = mock_pm

        changes = master.poll_sub_agent_status()
        assert changes == {}

    def test_invalid_state_raises_error(self):
        """非 DISPATCHING/MONITORING 状态下调用抛 RuntimeError"""
        master = _make_master(state=MasterAgentState.IDLE)
        with pytest.raises(RuntimeError, match="Cannot poll status"):
            master.poll_sub_agent_status()

    def test_skipped_entry_maps_to_success(self):
        """SKIPPED 状态映射为 SUCCESS"""
        master = _make_master()
        tasks = [_make_task(status=TaskStatus.IN_PROGRESS)]
        master._task_json = _make_task_json(tasks)
        master._active_agents["task-001"] = _make_mock_agent()

        mock_pm = MagicMock()
        entry = _make_progress_entry(
            task_id="task-001",
            status=ProgressStatus.SKIPPED,
            git_sha=None,
        )
        mock_pm.read_progress.return_value = [entry]
        master._progress_manager = mock_pm

        changes = master.poll_sub_agent_status()
        assert changes["task-001"] == "SKIPPED"
        assert tasks[0].status == TaskStatus.COMPLETED


# ── _has_unrecoverable_failure 测试 ───────────────────────────────


class TestHasUnrecoverableFailure:
    """不可恢复失败检测"""

    def test_no_task_json_returns_false(self):
        """无 task_json 时返回 False"""
        master = _make_master()
        assert master._has_unrecoverable_failure() is False

    def test_failed_task_retries_exhausted(self):
        """失败任务且重试耗尽 → 不可恢复"""
        master = _make_master(task_max_retries=1)
        tasks = [_make_task(status=TaskStatus.FAILED, retry_count=2)]
        master._task_json = _make_task_json(tasks)

        assert master._has_unrecoverable_failure() is True

    def test_failed_task_retries_remaining(self):
        """失败任务但重试未耗尽 → 可恢复"""
        master = _make_master(task_max_retries=2)
        tasks = [_make_task(status=TaskStatus.FAILED, retry_count=1)]
        master._task_json = _make_task_json(tasks)

        assert master._has_unrecoverable_failure() is False

    def test_no_failed_tasks(self):
        """无失败任务 → 不存在不可恢复失败"""
        master = _make_master()
        tasks = [_make_task(status=TaskStatus.PENDING)]
        master._task_json = _make_task_json(tasks)

        assert master._has_unrecoverable_failure() is False

    def test_completed_task_not_counted(self):
        """已完成任务不计入不可恢复"""
        master = _make_master(task_max_retries=0)
        tasks = [_make_task(status=TaskStatus.COMPLETED)]
        master._task_json = _make_task_json(tasks)

        assert master._has_unrecoverable_failure() is False

    def test_zero_retries_failed_immediately(self):
        """task_max_retries=0，任何 FAILED 都不可恢复"""
        master = _make_master(task_max_retries=0)
        tasks = [_make_task(status=TaskStatus.FAILED, retry_count=1)]
        master._task_json = _make_task_json(tasks)

        assert master._has_unrecoverable_failure() is True


# ── _check_termination 测试 ──────────────────────────────────────


class TestCheckTermination:
    """终止条件检查"""

    def test_all_completed(self):
        """所有任务完成 → COMPLETED"""
        master = _make_master()
        tasks = [_make_task(status=TaskStatus.COMPLETED)]
        master._task_json = _make_task_json(tasks)

        result = master._check_termination()
        assert result == "all_completed"
        assert master._state == MasterAgentState.COMPLETED

    def test_unrecoverable_failure(self):
        """不可恢复失败 → FAILED"""
        master = _make_master(task_max_retries=0)
        tasks = [_make_task(status=TaskStatus.FAILED, retry_count=1)]
        master._task_json = _make_task_json(tasks)

        result = master._check_termination()
        assert result == "unrecoverable_failure"
        assert master._state == MasterAgentState.FAILED

    def test_blocked_no_progress(self):
        """阻塞且无活跃 Agent → PAUSED"""
        master = _make_master()
        tasks = [_make_task(status=TaskStatus.BLOCKED)]
        master._task_json = _make_task_json(tasks)
        master._active_agents.clear()

        result = master._check_termination()
        assert result == "blocked_no_progress"
        assert master._state == MasterAgentState.PAUSED

    def test_blocked_with_active_agents(self):
        """阻塞但有活跃 Agent → 不终止"""
        master = _make_master()
        tasks = [_make_task(status=TaskStatus.BLOCKED)]
        master._task_json = _make_task_json(tasks)
        master._active_agents["task-002"] = _make_mock_agent()

        result = master._check_termination()
        assert result is None

    def test_no_termination_condition(self):
        """无终止条件 → 不终止"""
        master = _make_master()
        tasks = [
            _make_task(task_id="task-001", status=TaskStatus.COMPLETED),
            _make_task(task_id="task-002", status=TaskStatus.PENDING),
        ]
        master._task_json = _make_task_json(tasks)

        result = master._check_termination()
        assert result is None

    def test_no_task_json_not_completed(self):
        """无 task_json → is_all_completed 为 False → 不终止"""
        master = _make_master()
        result = master._check_termination()
        assert result is None


# ── _build_result_from_progress 测试 ──────────────────────────────


class TestBuildResultFromProgress:
    """ProgressEntry → SubAgentResult 转换"""

    def test_completed_entry(self):
        """COMPLETED → SUCCESS + COMPLETED phase"""
        master = _make_master()
        entry = _make_progress_entry(status=ProgressStatus.COMPLETED)
        result = master._build_result_from_progress("task-001", entry)

        assert result.task_id == "task-001"
        assert result.status == SubAgentResultStatus.SUCCESS
        assert result.phase == AgentPhase.COMPLETED
        assert result.commit_hash == "abc1234"

    def test_failed_entry(self):
        """FAILED → FAILED + FAILED phase"""
        master = _make_master()
        entry = _make_progress_entry(
            status=ProgressStatus.FAILED,
            error="Build error",
        )
        result = master._build_result_from_progress("task-001", entry)

        assert result.status == SubAgentResultStatus.FAILED
        assert result.phase == AgentPhase.FAILED
        assert result.error == "Build error"

    def test_blocked_entry(self):
        """BLOCKED → BLOCKED + BLOCKED phase"""
        master = _make_master()
        entry = _make_progress_entry(
            status=ProgressStatus.BLOCKED,
            error="Dependency missing",
        )
        result = master._build_result_from_progress("task-001", entry)

        assert result.status == SubAgentResultStatus.BLOCKED
        assert result.phase == AgentPhase.BLOCKED

    def test_skipped_entry(self):
        """SKIPPED → SUCCESS + COMPLETED phase"""
        master = _make_master()
        entry = _make_progress_entry(status=ProgressStatus.SKIPPED, git_sha=None)
        result = master._build_result_from_progress("task-001", entry)

        assert result.status == SubAgentResultStatus.SUCCESS
        assert result.phase == AgentPhase.COMPLETED

    def test_preserves_metadata(self):
        """保留 progress.txt 中的元数据"""
        master = _make_master()
        entry = ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.COMPLETED,
            role="test-engineer",
            started=datetime(2026, 5, 18, 10, 0, 0),
            finished=datetime(2026, 5, 18, 10, 30, 0),
            git_sha="deadbeef",
            git_msg="[task-001] test-engineer: passed all tests",
            retry=2,
        )
        result = master._build_result_from_progress("task-001", entry)

        assert result.role == "test-engineer"
        assert result.commit_hash == "deadbeef"
        assert result.commit_message == "[task-001] test-engineer: passed all tests"
        assert result.retries == 2
        assert result.started_at == datetime(2026, 5, 18, 10, 0, 0)
        assert result.finished_at == datetime(2026, 5, 18, 10, 30, 0)


# ── _dispatch_available_tasks 测试 ────────────────────────────────


class TestDispatchAvailableTasks:
    """批量调度可用任务"""

    def test_dispatches_multiple_tasks(self):
        """同步模式：所有任务顺序调度（dispatch_task 同步完成释放槽位）"""
        master = _make_master(max_concurrent=2)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
            _make_task(task_id="task-003"),
        ]
        master._task_json = _make_task_json(tasks)

        # Mock agent_factory — 每次返回新的 mock agent
        call_count = 0
        def mock_factory(role_name):
            nonlocal call_count
            call_count += 1
            agent = _make_mock_agent()
            agent.run.return_value = _make_success_result(
                task_id=f"task-00{call_count}"
            )
            return agent

        master._agent_factory = mock_factory

        count = master._dispatch_available_tasks()
        # 同步模式：dispatch_task 阻塞完成后释放槽位，3 个任务全部调度
        assert count == 3

    def test_dispatches_nothing_when_no_tasks(self):
        """无可用任务时调度 0 个"""
        master = _make_master()
        master._task_json = _make_task_json([])

        count = master._dispatch_available_tasks()
        assert count == 0

    def test_dispatch_stops_on_dispatch_failure(self):
        """调度失败时停止继续调度"""
        master = _make_master(max_concurrent=3)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
        ]
        master._task_json = _make_task_json(tasks)

        call_count = 0
        def failing_factory(role_name):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("Agent creation failed")
            return _make_mock_agent()

        master._agent_factory = failing_factory

        count = master._dispatch_available_tasks()
        assert count == 0  # 第一次就失败

    def test_dispatches_single_task(self):
        """同步模式：调度一个任务（全部完成）"""
        master = _make_master(max_concurrent=1)
        tasks = [
            _make_task(task_id="task-001"),
        ]
        master._task_json = _make_task_json(tasks)

        master._agent_factory = lambda role: _make_mock_agent(
            result=_make_success_result("task-001")
        )

        count = master._dispatch_available_tasks()
        assert count == 1


# ── run_main_loop 测试 ──────────────────────────────────────────


class TestRunMainLoop:
    """主调度循环"""

    def test_all_tasks_complete(self):
        """所有任务完成 → COMPLETED 状态"""
        master = _make_master(poll_interval=0.01)
        tasks = [_make_task(task_id="task-001")]
        master._task_json = _make_task_json(tasks)

        master._agent_factory = lambda role: _make_mock_agent(
            result=_make_success_result("task-001")
        )

        summary = master.run_main_loop()

        assert master._state == MasterAgentState.COMPLETED
        assert summary["completed"] == 1
        assert summary["total"] == 1
        assert summary["progress_pct"] == 100.0

    def test_multiple_tasks_sequential(self):
        """多个任务按序完成"""
        master = _make_master(max_concurrent=1, poll_interval=0.01)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
        ]
        master._task_json = _make_task_json(tasks)

        call_count = 0
        def factory(role):
            nonlocal call_count
            call_count += 1
            return _make_mock_agent(
                result=_make_success_result(f"task-00{call_count}")
            )

        master._agent_factory = factory

        summary = master.run_main_loop()

        assert master._state == MasterAgentState.COMPLETED
        assert summary["completed"] == 2

    def test_failed_task_unrecoverable(self):
        """不可恢复失败 → FAILED 状态"""
        master = _make_master(task_max_retries=0, poll_interval=0.01)
        tasks = [_make_task(task_id="task-001")]
        master._task_json = _make_task_json(tasks)

        master._agent_factory = lambda role: _make_mock_agent(
            result=_make_failed_result("task-001", "Build failed")
        )

        summary = master.run_main_loop()

        assert master._state == MasterAgentState.FAILED

    def test_blocked_task_no_agents(self):
        """阻塞且无活跃 Agent → PAUSED 状态"""
        master = _make_master(poll_interval=0.01)
        tasks = [_make_task(task_id="task-001", status=TaskStatus.BLOCKED)]
        master._task_json = _make_task_json(tasks)

        # 无可调度任务（唯一的 task 是 BLOCKED）
        # 直接进入 _check_termination
        summary = master.run_main_loop()

        assert master._state == MasterAgentState.PAUSED

    def test_empty_task_list_immediate_complete(self):
        """空任务列表 → 立即 COMPLETED"""
        master = _make_master(poll_interval=0.01)
        master._task_json = _make_task_json([])

        summary = master.run_main_loop()

        assert master._state == MasterAgentState.COMPLETED
        assert summary["total"] == 0

    def test_invalid_state_raises_error(self):
        """非 DISPATCHING/MONITORING 状态下调用抛 RuntimeError"""
        master = _make_master(state=MasterAgentState.IDLE)
        with pytest.raises(RuntimeError, match="Cannot run main loop"):
            master.run_main_loop()

    def test_monitoring_state_accepted(self):
        """MONITORING 状态下也可以启动主循环"""
        master = _make_master(
            state=MasterAgentState.MONITORING,
            poll_interval=0.01,
        )
        master._task_json = _make_task_json([])

        summary = master.run_main_loop()
        assert master._state == MasterAgentState.COMPLETED

    def test_dependency_chain_execution(self):
        """依赖链任务按序执行"""
        master = _make_master(max_concurrent=1, poll_interval=0.01)
        tasks = [
            _make_task(task_id="task-001", dependencies=[]),
            _make_task(task_id="task-002", dependencies=["task-001"]),
            _make_task(task_id="task-003", dependencies=["task-002"]),
        ]
        master._task_json = _make_task_json(tasks)

        call_count = 0
        def factory(role):
            nonlocal call_count
            call_count += 1
            return _make_mock_agent(
                result=_make_success_result(f"task-00{call_count}")
            )

        master._agent_factory = factory

        summary = master.run_main_loop()

        assert master._state == MasterAgentState.COMPLETED
        assert summary["completed"] == 3

    def test_returns_progress_summary(self):
        """返回进度摘要字典"""
        master = _make_master(poll_interval=0.01)
        tasks = [
            _make_task(task_id="task-001"),
        ]
        master._task_json = _make_task_json(tasks)

        master._agent_factory = lambda role: _make_mock_agent(
            result=_make_success_result("task-001")
        )

        summary = master.run_main_loop()

        assert isinstance(summary, dict)
        assert "total" in summary
        assert "completed" in summary
        assert "progress_pct" in summary
        assert "state" in summary
        assert summary["state"] == MasterAgentState.COMPLETED.value


# ── _ensure_progress_manager 测试 ────────────────────────────────


class TestEnsureProgressManager:
    """ProgressManager 懒创建"""

    def test_returns_existing_manager(self):
        """已有 ProgressManager 时直接返回"""
        master = _make_master()
        mock_pm = MagicMock()
        master._progress_manager = mock_pm

        result = master._ensure_progress_manager()
        assert result is mock_pm

    def test_creates_from_task_file_manager(self):
        """从 TaskFileManager 路径推断创建"""
        from pathlib import Path

        master = _make_master()
        mock_tfm = MagicMock()
        mock_tfm.file_path = Path("/tmp/data/task.json")
        master._task_file_manager = mock_tfm

        result = master._ensure_progress_manager()
        assert result is not None
        assert result.file_path == Path("/tmp/data/progress.txt")
        # 缓存到 _progress_manager
        assert master._progress_manager is result

    def test_returns_none_when_no_dependencies(self):
        """无 TaskFileManager 也无 ProgressManager → None"""
        master = _make_master()
        result = master._ensure_progress_manager()
        assert result is None


# ── 集成测试 ──────────────────────────────────────────────


class TestMainLoopIntegration:
    """主循环集成场景"""

    def test_partial_failure_continues(self):
        """部分失败但可重试 → 继续执行其他任务"""
        master = _make_master(task_max_retries=2, poll_interval=0.01)
        tasks = [
            _make_task(task_id="task-001"),
            _make_task(task_id="task-002"),
        ]
        master._task_json = _make_task_json(tasks)

        call_count = 0
        def factory(role):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return _make_mock_agent(
                    result=_make_failed_result("task-001", "retry me")
                )
            return _make_mock_agent(
                result=_make_success_result("task-002")
            )

        master._agent_factory = factory

        summary = master.run_main_loop()

        # task-001 失败但可重试（retry_count=1 ≤ task_max_retries=2）
        # task-002 应该成功
        # 最终状态取决于是否所有任务都完成
        # task-001 失败后 retry_count=1，still retryable，会被重新调度
        # 但因为 call_count 机制，重新调度时 call_count > 2，会成功
        # 实际上主循环会继续调度直到所有任务完成或不可恢复

    def test_mixed_priorities_dispatch_order(self):
        """不同优先级任务按优先级调度"""
        master = _make_master(max_concurrent=1, poll_interval=0.01)
        tasks = [
            _make_task(task_id="task-001", priority=TaskPriority.LOW),
            _make_task(task_id="task-002", priority=TaskPriority.HIGH),
            _make_task(task_id="task-003", priority=TaskPriority.MEDIUM),
        ]
        master._task_json = _make_task_json(tasks)

        dispatched_order = []
        call_count = 0
        def factory(role):
            nonlocal call_count
            call_count += 1
            return _make_mock_agent()

        master._agent_factory = factory

        # Patch dispatch_task to track order and update status
        original_dispatch = master.dispatch_task
        def tracking_dispatch(task=None):
            if task:
                dispatched_order.append(task.id)
            result = original_dispatch(task)
            return result

        master.dispatch_task = tracking_dispatch

        summary = master.run_main_loop()

        # HIGH 应最先调度
        assert dispatched_order[0] == "task-002"
        assert master._state == MasterAgentState.COMPLETED

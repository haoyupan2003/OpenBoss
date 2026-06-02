"""
P1-047 测试 — 调度策略 select_next_task

测试 MasterAgent 的核心调度决策方法：
- select_next_task(): 选择下一个可调度任务
- _can_dispatch_more(): 并发度检查
- _is_task_retryable(): 重试次数检查
- get_dispatchable_tasks() 增强版：含重试过滤
"""

import pytest
from unittest.mock import MagicMock

from agent_automation_system.master_agent.master_agent import (
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
from agent_automation_system.sub_agent.sub_agent import SubAgent


# ── 辅助工具 ──────────────────────────────────────────────


def _make_task(
    task_id: str = "task-001",
    title: str = "Test task",
    priority: TaskPriority = TaskPriority.MEDIUM,
    status: TaskStatus = TaskStatus.PENDING,
    dependencies: list[str] | None = None,
    retry_count: int = 0,
    suggested_role: str = "dev",
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
    state: MasterAgentState = MasterAgentState.DISPATCHING,
) -> MasterAgent:
    """创建处于 DISPATCHING 状态的 MasterAgent"""
    master = MasterAgent(
        max_concurrent_agents=max_concurrent,
        task_max_retries=task_max_retries,
    )
    master._state = state
    return master


# ── select_next_task 基础 ────────────────────────────────────


class TestSelectNextTask:
    """select_next_task 核心调度决策"""

    def test_selects_highest_priority_task(self):
        """优先级排序：HIGH > MEDIUM > LOW"""
        master = _make_master()
        tasks = [
            _make_task("task-001", priority=TaskPriority.LOW),
            _make_task("task-002", priority=TaskPriority.HIGH),
            _make_task("task-003", priority=TaskPriority.MEDIUM),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.select_next_task()
        assert result is not None
        assert result.id == "task-002"  # HIGH 优先

    def test_returns_none_when_no_dispatchable(self):
        """无可用任务时返回 None"""
        master = _make_master()
        tasks = [
            _make_task("task-001", status=TaskStatus.COMPLETED),
            _make_task("task-002", status=TaskStatus.IN_PROGRESS),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.select_next_task()
        assert result is None

    def test_returns_none_when_no_task_json(self):
        """无 TaskJSON 时返回 None"""
        master = _make_master()
        master._task_json = None

        result = master.select_next_task()
        assert result is None

    def test_respects_dependency_order(self):
        """依赖未满足的任务不会被选中"""
        master = _make_master()
        tasks = [
            _make_task("task-001", status=TaskStatus.PENDING),
            _make_task("task-002", status=TaskStatus.PENDING, dependencies=["task-001"]),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.select_next_task()
        assert result is not None
        assert result.id == "task-001"  # task-002 依赖 task-001

    def test_selects_task_with_deps_met(self):
        """依赖已满足时，后继任务可被选中"""
        master = _make_master()
        tasks = [
            _make_task("task-001", status=TaskStatus.COMPLETED),
            _make_task("task-002", status=TaskStatus.PENDING, dependencies=["task-001"]),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.select_next_task()
        assert result is not None
        assert result.id == "task-002"

    def test_state_check_raises(self):
        """非 DISPATCHING/MONITORING 状态抛 RuntimeError"""
        master = _make_master(state=MasterAgentState.IDLE)
        master._task_json = _make_task_json([_make_task()])

        with pytest.raises(RuntimeError, match="Cannot select next task"):
            master.select_next_task()

    def test_allowed_in_monitoring_state(self):
        """MONITORING 状态下也可调度"""
        master = _make_master(state=MasterAgentState.MONITORING)
        tasks = [_make_task("task-001", priority=TaskPriority.HIGH)]
        master._task_json = _make_task_json(tasks)

        result = master.select_next_task()
        assert result is not None
        assert result.id == "task-001"


# ── 并发度控制 ────────────────────────────────────────────


class TestConcurrencyControl:
    """_can_dispatch_more / select_next_task 并发度检查"""

    def test_can_dispatch_when_below_limit(self):
        """活跃 Agent 数 < 上限时可调度"""
        master = _make_master(max_concurrent=3)
        assert master._can_dispatch_more() is True

    def test_cannot_dispatch_at_limit(self):
        """活跃 Agent 数 = 上限时不可调度"""
        master = _make_master(max_concurrent=2)
        master._active_agents = {"task-001": MagicMock(spec=SubAgent),
                                  "task-002": MagicMock(spec=SubAgent)}
        assert master._can_dispatch_more() is False

    def test_can_dispatch_with_one_slot(self):
        """还有 1 个空闲位时可调度"""
        master = _make_master(max_concurrent=3)
        master._active_agents = {"task-001": MagicMock(spec=SubAgent),
                                  "task-002": MagicMock(spec=SubAgent)}
        assert master._can_dispatch_more() is True

    def test_select_returns_none_at_concurrency_limit(self):
        """达到并发上限时 select_next_task 返回 None"""
        master = _make_master(max_concurrent=1)
        master._active_agents = {"task-001": MagicMock(spec=SubAgent)}
        master._task_json = _make_task_json([
            _make_task("task-002", priority=TaskPriority.HIGH)
        ])

        result = master.select_next_task()
        assert result is None

    def test_concurrency_at_limit_blocks(self):
        """max_concurrent 达上限时不可调度"""
        master = _make_master(max_concurrent=1)
        master._active_agents = {"task-001": MagicMock(spec=SubAgent)}
        assert master._can_dispatch_more() is False

    def test_select_returns_task_when_slot_available(self):
        """有空闲位时正常返回任务"""
        master = _make_master(max_concurrent=2)
        master._active_agents = {"task-001": MagicMock(spec=SubAgent)}
        master._task_json = _make_task_json([
            _make_task("task-002", priority=TaskPriority.HIGH)
        ])

        result = master.select_next_task()
        assert result is not None
        assert result.id == "task-002"


# ── 重试检查 ────────────────────────────────────────────


class TestRetryCheck:
    """_is_task_retryable / select_next_task 重试逻辑"""

    def test_retryable_when_within_limit(self):
        """retry_count ≤ task_max_retries 时可重试"""
        master = _make_master(task_max_retries=2)
        task = _make_task("task-001", retry_count=2)
        assert master._is_task_retryable(task) is True

    def test_not_retryable_when_exceeded(self):
        """retry_count > task_max_retries 时不可重试"""
        master = _make_master(task_max_retries=1)
        task = _make_task("task-001", retry_count=2)
        assert master._is_task_retryable(task) is False

    def test_zero_retries_disallows_retry(self):
        """task_max_retries=0 仅允许首次执行"""
        master = _make_master(task_max_retries=0)
        task_fresh = _make_task("task-001", retry_count=0)
        assert master._is_task_retryable(task_fresh) is True

        task_retried = _make_task("task-001", retry_count=1)
        assert master._is_task_retryable(task_retried) is False

    def test_exceeded_retry_task_not_in_dispatchable(self):
        """超过重试上限的任务不出现在可调度列表"""
        master = _make_master(task_max_retries=1)
        tasks = [
            _make_task("task-001", retry_count=2),  # 已超限
            _make_task("task-002", retry_count=0),  # 可调度
        ]
        master._task_json = _make_task_json(tasks)

        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 1
        assert dispatchable[0].id == "task-002"

    def test_select_skips_exceeded_retry_task(self):
        """select_next_task 跳过超过重试上限的任务"""
        master = _make_master(task_max_retries=1)
        tasks = [
            _make_task("task-001", priority=TaskPriority.HIGH, retry_count=2),
            _make_task("task-002", priority=TaskPriority.LOW, retry_count=0),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.select_next_task()
        assert result is not None
        assert result.id == "task-002"  # task-001 被跳过


# ── get_dispatchable_tasks 增强 ──────────────────────────


class TestGetDispatchableTasksEnhanced:
    """get_dispatchable_tasks 重试过滤增强"""

    def test_filters_out_exceeded_retry_tasks(self):
        """过滤掉超过重试上限的 PENDING 任务"""
        master = _make_master(task_max_retries=1)
        tasks = [
            _make_task("task-001", retry_count=0),
            _make_task("task-002", retry_count=1),  # 刚好到上限
            _make_task("task-003", retry_count=2),  # 超过上限
        ]
        master._task_json = _make_task_json(tasks)

        dispatchable = master.get_dispatchable_tasks()
        ids = [t.id for t in dispatchable]
        assert "task-001" in ids
        assert "task-002" in ids
        assert "task-003" not in ids

    def test_all_tasks_exceeded_retry_returns_empty(self):
        """所有任务都超过重试上限时返回空列表"""
        master = _make_master(task_max_retries=0)
        tasks = [
            _make_task("task-001", retry_count=1),
            _make_task("task-002", retry_count=2),
        ]
        master._task_json = _make_task_json(tasks)

        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 0

    def test_backward_compat_without_retry_filter(self):
        """默认 task_max_retries=1 时，retry_count=0 的任务正常可调度"""
        master = _make_master(task_max_retries=1)
        tasks = [_make_task("task-001", retry_count=0)]
        master._task_json = _make_task_json(tasks)

        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 1


# ── 综合调度场景 ────────────────────────────────────────


class TestSchedulingScenarios:
    """端到端调度场景"""

    def test_diamond_dependency_pattern(self):
        """菱形依赖模式：A→B, A→C, B+C→D"""
        master = _make_master(max_concurrent=3)
        tasks = [
            _make_task("task-001", priority=TaskPriority.HIGH),
            _make_task("task-002", dependencies=["task-001"], priority=TaskPriority.MEDIUM),
            _make_task("task-003", dependencies=["task-001"], priority=TaskPriority.HIGH),
            _make_task("task-004", dependencies=["task-002", "task-003"]),
        ]
        master._task_json = _make_task_json(tasks)

        # 首先调度 task-001
        result = master.select_next_task()
        assert result.id == "task-001"

        # 完成 task-001
        tasks[0].status = TaskStatus.COMPLETED

        # 接下来 task-003 (HIGH) 优先于 task-002 (MEDIUM)
        result = master.select_next_task()
        assert result.id == "task-003"

        # 完成 task-003
        tasks[2].status = TaskStatus.COMPLETED

        # 接下来 task-002
        result = master.select_next_task()
        assert result.id == "task-002"

        # 完成 task-002
        tasks[1].status = TaskStatus.COMPLETED

        # 最后 task-004
        result = master.select_next_task()
        assert result.id == "task-004"

    def test_concurrency_blocks_dispatch(self):
        """并发上限阻塞调度"""
        master = _make_master(max_concurrent=1)

        tasks = [
            _make_task("task-001", priority=TaskPriority.HIGH),
            _make_task("task-002", priority=TaskPriority.MEDIUM),
        ]
        master._task_json = _make_task_json(tasks)

        # 第一个正常调度
        result = master.select_next_task()
        assert result.id == "task-001"

        # 模拟 task-001 正在执行
        master._active_agents["task-001"] = MagicMock(spec=SubAgent)

        # 达到上限，无法调度
        result = master.select_next_task()
        assert result is None

        # 完成 task-001，释放槽位
        master._active_agents.pop("task-001", None)
        tasks[0].status = TaskStatus.COMPLETED
        result = master.select_next_task()
        assert result is not None
        assert result.id == "task-002"

    def test_retry_and_concurrency_combined(self):
        """重试 + 并发综合场景"""
        master = _make_master(max_concurrent=2, task_max_retries=1)
        tasks = [
            _make_task("task-001", priority=TaskPriority.HIGH, retry_count=2),  # 超限
            _make_task("task-002", priority=TaskPriority.MEDIUM, retry_count=0),
            _make_task("task-003", priority=TaskPriority.LOW, retry_count=0),
        ]
        master._task_json = _make_task_json(tasks)
        master._active_agents = {"task-099": MagicMock(spec=SubAgent)}

        # task-001 被跳过（超限），选 task-002
        result = master.select_next_task()
        assert result.id == "task-002"

    def test_multiple_dispatchable_prioritized(self):
        """多个可调度任务按优先级选择"""
        master = _make_master(max_concurrent=5)
        tasks = [
            _make_task("task-001", priority=TaskPriority.LOW),
            _make_task("task-002", priority=TaskPriority.MEDIUM),
            _make_task("task-003", priority=TaskPriority.HIGH),
            _make_task("task-004", priority=TaskPriority.MEDIUM),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.select_next_task()
        assert result.id == "task-003"
        assert result.priority == TaskPriority.HIGH

    def test_empty_tasks_returns_none(self):
        """空任务列表返回 None"""
        master = _make_master()
        master._task_json = _make_task_json([])

        result = master.select_next_task()
        assert result is None

    def test_all_completed_returns_none(self):
        """所有任务已完成返回 None"""
        master = _make_master()
        tasks = [
            _make_task("task-001", status=TaskStatus.COMPLETED),
            _make_task("task-002", status=TaskStatus.COMPLETED),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.select_next_task()
        assert result is None

    def test_blocked_tasks_not_selected(self):
        """BLOCKED 状态的任务不被选中"""
        master = _make_master()
        tasks = [
            _make_task("task-001", status=TaskStatus.BLOCKED),
            _make_task("task-002", status=TaskStatus.PENDING, priority=TaskPriority.LOW),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.select_next_task()
        assert result.id == "task-002"

    def test_in_progress_not_selected(self):
        """IN_PROGRESS 状态的任务不被选中"""
        master = _make_master()
        tasks = [
            _make_task("task-001", status=TaskStatus.IN_PROGRESS),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.select_next_task()
        assert result is None


# ── 状态验证 ────────────────────────────────────────────


class TestSelectNextTaskStateValidation:
    """select_next_task 状态校验"""

    @pytest.mark.parametrize(
        "state",
        [
            MasterAgentState.IDLE,
            MasterAgentState.ANALYZING,
            MasterAgentState.PLANNING,
            MasterAgentState.COMPLETED,
            MasterAgentState.FAILED,
            MasterAgentState.PAUSED,
        ],
    )
    def test_invalid_states_raise(self, state):
        """非法状态抛 RuntimeError"""
        master = _make_master(state=state)
        master._task_json = _make_task_json([_make_task()])

        with pytest.raises(RuntimeError):
            master.select_next_task()

    def test_dispatching_state_allowed(self):
        """DISPATCHING 状态合法"""
        master = _make_master(state=MasterAgentState.DISPATCHING)
        master._task_json = _make_task_json([_make_task()])

        result = master.select_next_task()
        assert result is not None

    def test_monitoring_state_allowed(self):
        """MONITORING 状态合法"""
        master = _make_master(state=MasterAgentState.MONITORING)
        master._task_json = _make_task_json([_make_task()])

        result = master.select_next_task()
        assert result is not None


# ── 属性与配置 ──────────────────────────────────────────


class TestSchedulingProperties:
    """调度相关属性和配置"""

    def test_max_concurrent_agents_default(self):
        """默认 max_concurrent_agents=3"""
        master = MasterAgent()
        assert master.max_concurrent_agents == 3

    def test_task_max_retries_default(self):
        """默认 task_max_retries=1"""
        master = MasterAgent()
        assert master.task_max_retries == 1

    def test_active_agents_count(self):
        """active_agents 反映当前并发数"""
        master = _make_master()
        assert len(master.active_agents) == 0

        master._active_agents = {"task-001": MagicMock(spec=SubAgent)}
        assert len(master.active_agents) == 1

    def test_concurrency_validation(self):
        """max_concurrent_agents 必须 > 0"""
        with pytest.raises(ValueError, match="positive"):
            MasterAgent(max_concurrent_agents=0)

    def test_task_max_retries_validation(self):
        """task_max_retries 必须 ≥ 0"""
        with pytest.raises(ValueError, match="non-negative"):
            MasterAgent(task_max_retries=-1)

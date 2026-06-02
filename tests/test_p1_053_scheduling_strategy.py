"""
P1-053 测试 — 调度策略场景单元测试：优先级、并行度、依赖约束

在 P1-047 基础测试之上，补充更深入的调度策略场景测试：
- 优先级排序：同优先级稳定性、动态优先级竞争、优先级与依赖交互
- 并行度控制：动态槽位释放/重新填充、串行模式、并发与依赖组合
- 依赖约束：多层链式依赖、扇出/扇入、部分依赖满足、传递依赖
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


# ════════════════════════════════════════════════════════════════
# 一、优先级排序场景
# ════════════════════════════════════════════════════════════════


class TestPriorityOrdering:
    """优先级排序场景：深度测试调度策略的优先级决策"""

    def test_same_priority_stability(self):
        """同优先级任务多次调用结果稳定（不随机）"""
        master = _make_master()
        tasks = [
            _make_task("task-001", priority=TaskPriority.MEDIUM),
            _make_task("task-002", priority=TaskPriority.MEDIUM),
            _make_task("task-003", priority=TaskPriority.MEDIUM),
        ]
        master._task_json = _make_task_json(tasks)

        results = [master.select_next_task().id for _ in range(5)]
        # 同优先级应始终返回同一任务（列表中第一个 MEDIUM）
        assert all(r == results[0] for r in results)

    def test_same_priority_dispatchable_list_order(self):
        """同优先级任务在 get_dispatchable_tasks 中保持原始顺序"""
        master = _make_master()
        tasks = [
            _make_task("task-001", priority=TaskPriority.MEDIUM),
            _make_task("task-002", priority=TaskPriority.MEDIUM),
            _make_task("task-003", priority=TaskPriority.MEDIUM),
        ]
        master._task_json = _make_task_json(tasks)

        dispatchable = master.get_dispatchable_tasks()
        ids = [t.id for t in dispatchable]
        assert ids == ["task-001", "task-002", "task-003"]

    def test_high_priority_downstream_vs_low_independent(self):
        """高优先级依赖任务 vs 低优先级独立任务

        task-001 (HIGH, COMPLETED) → task-002 (MEDIUM, PENDING, dep=task-001)
        task-003 (LOW, PENDING, no deps)

        独立低优先级任务先于有依赖的中优先级任务
        （因为 task-003 无依赖可直接调度，task-002 依赖已满足也可调度，
          但 MEDIUM > LOW 所以 task-002 优先）
        """
        master = _make_master()
        tasks = [
            _make_task("task-001", priority=TaskPriority.HIGH, status=TaskStatus.COMPLETED),
            _make_task("task-002", priority=TaskPriority.MEDIUM, dependencies=["task-001"]),
            _make_task("task-003", priority=TaskPriority.LOW),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.select_next_task()
        # task-002 (MEDIUM) > task-003 (LOW)
        assert result.id == "task-002"

    def test_priority_with_partial_completion(self):
        """部分完成后的优先级重新排序

        3 个任务：HIGH、MEDIUM、LOW
        完成 HIGH 后，MEDIUM 升为最高优先
        """
        master = _make_master()
        tasks = [
            _make_task("task-001", priority=TaskPriority.HIGH),
            _make_task("task-002", priority=TaskPriority.MEDIUM),
            _make_task("task-003", priority=TaskPriority.LOW),
        ]
        master._task_json = _make_task_json(tasks)

        # 初始选 HIGH
        result = master.select_next_task()
        assert result.id == "task-001"

        # 完成 HIGH
        tasks[0].status = TaskStatus.COMPLETED

        # 现在选 MEDIUM
        result = master.select_next_task()
        assert result.id == "task-002"

        # 完成 MEDIUM
        tasks[1].status = TaskStatus.COMPLETED

        # 最后选 LOW
        result = master.select_next_task()
        assert result.id == "task-003"

    def test_priority_interaction_with_concurrency_slots(self):
        """优先级与并发槽位交互：先填高优先级再填低优先级

        max_concurrent=2, 3 个可用任务
        两次 select_next_task 应依次选出 HIGH → MEDIUM
        """
        master = _make_master(max_concurrent=3)
        tasks = [
            _make_task("task-001", priority=TaskPriority.LOW),
            _make_task("task-002", priority=TaskPriority.HIGH),
            _make_task("task-003", priority=TaskPriority.MEDIUM),
        ]
        master._task_json = _make_task_json(tasks)

        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 3
        assert dispatchable[0].id == "task-002"  # HIGH
        assert dispatchable[1].id == "task-003"  # MEDIUM
        assert dispatchable[2].id == "task-001"  # LOW

    def test_all_priorities_same_high(self):
        """全部 HIGH 优先级时按原始顺序选择"""
        master = _make_master()
        tasks = [
            _make_task("task-001", priority=TaskPriority.HIGH),
            _make_task("task-002", priority=TaskPriority.HIGH),
            _make_task("task-003", priority=TaskPriority.HIGH),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.select_next_task()
        assert result.id == "task-001"

    def test_priority_with_retry_eligible(self):
        """重试任务与优先级交互：重试任务优先级低于新任务

        task-001 (LOW, retry_count=1) — 可重试
        task-002 (HIGH, retry_count=0) — 新任务

        虽然 task-001 在重试，但 task-002 优先级更高应先调度
        """
        master = _make_master(task_max_retries=2)
        tasks = [
            _make_task("task-001", priority=TaskPriority.LOW, retry_count=1),
            _make_task("task-002", priority=TaskPriority.HIGH, retry_count=0),
        ]
        master._task_json = _make_task_json(tasks)

        result = master.select_next_task()
        assert result.id == "task-002"

    def test_dispatchable_tasks_all_three_priorities(self):
        """get_dispatchable_tasks 返回三种优先级的正确排序"""
        master = _make_master()
        tasks = [
            _make_task("task-001", priority=TaskPriority.LOW),
            _make_task("task-002", priority=TaskPriority.MEDIUM),
            _make_task("task-003", priority=TaskPriority.HIGH),
            _make_task("task-004", priority=TaskPriority.LOW),
            _make_task("task-005", priority=TaskPriority.HIGH),
        ]
        master._task_json = _make_task_json(tasks)

        dispatchable = master.get_dispatchable_tasks()
        priorities = [t.priority for t in dispatchable]

        # 前两个 HIGH，中间 MEDIUM，后两个 LOW
        assert priorities[0] == TaskPriority.HIGH
        assert priorities[1] == TaskPriority.HIGH
        assert priorities[2] == TaskPriority.MEDIUM
        assert priorities[3] == TaskPriority.LOW
        assert priorities[4] == TaskPriority.LOW


# ════════════════════════════════════════════════════════════════
# 二、并行度控制场景
# ════════════════════════════════════════════════════════════════


class TestConcurrencyScenarios:
    """并行度控制场景：动态槽位、串行模式、并发与依赖组合"""

    def test_dynamic_slot_release_and_refill(self):
        """动态槽位释放与重新填充

        max_concurrent=2
        1. 填充 2 个槽位 → 无法继续调度
        2. 释放 1 个槽位 → 可调度 1 个新任务
        3. 释放所有槽位 → 可调度剩余所有任务
        """
        master = _make_master(max_concurrent=2)
        tasks = [
            _make_task("task-001", priority=TaskPriority.HIGH),
            _make_task("task-002", priority=TaskPriority.MEDIUM),
            _make_task("task-003", priority=TaskPriority.LOW),
        ]
        master._task_json = _make_task_json(tasks)

        # Step 1: 填充 2 个槽位（模拟 dispatch，标记 IN_PROGRESS）
        master._active_agents["task-001"] = MagicMock(spec=SubAgent)
        master._active_agents["task-002"] = MagicMock(spec=SubAgent)
        tasks[0].status = TaskStatus.IN_PROGRESS
        tasks[1].status = TaskStatus.IN_PROGRESS
        assert master._can_dispatch_more() is False
        assert master.select_next_task() is None

        # Step 2: task-001 完成，释放 1 个槽位
        master._active_agents.pop("task-001", None)
        tasks[0].status = TaskStatus.COMPLETED
        assert master._can_dispatch_more() is True
        result = master.select_next_task()
        assert result is not None
        assert result.id == "task-003"  # LOW 是剩余唯一的 PENDING

        # Step 3: 释放所有槽位
        master._active_agents.clear()
        tasks[1].status = TaskStatus.COMPLETED
        tasks[2].status = TaskStatus.COMPLETED
        # 所有任务完成 → 无可调度
        assert master.select_next_task() is None

    def test_serial_execution_mode(self):
        """串行模式 (max_concurrent=1)

        一次只能调度一个任务，严格串行执行
        """
        master = _make_master(max_concurrent=1)
        tasks = [
            _make_task("task-001", priority=TaskPriority.HIGH),
            _make_task("task-002", priority=TaskPriority.MEDIUM),
            _make_task("task-003", priority=TaskPriority.LOW),
        ]
        master._task_json = _make_task_json(tasks)

        # 第 1 个任务
        result = master.select_next_task()
        assert result.id == "task-001"

        # 占用槽位
        master._active_agents["task-001"] = MagicMock(spec=SubAgent)
        assert master.select_next_task() is None

        # 完成第 1 个
        master._active_agents.pop("task-001", None)
        tasks[0].status = TaskStatus.COMPLETED

        # 第 2 个
        result = master.select_next_task()
        assert result.id == "task-002"

        # 占用槽位
        master._active_agents["task-002"] = MagicMock(spec=SubAgent)
        assert master.select_next_task() is None

        # 完成第 2 个
        master._active_agents.pop("task-002", None)
        tasks[1].status = TaskStatus.COMPLETED

        # 第 3 个
        result = master.select_next_task()
        assert result.id == "task-003"

    def test_concurrency_with_more_available_than_slots(self):
        """可用任务数 > 并发槽位数

        max_concurrent=2, 5 个可用 PENDING 任务
        通过 get_dispatchable_tasks 验证优先级排序，
        并模拟 dispatch 流程验证槽位控制
        """
        master = _make_master(max_concurrent=2)
        tasks = [
            _make_task("task-001", priority=TaskPriority.LOW),
            _make_task("task-002", priority=TaskPriority.HIGH),
            _make_task("task-003", priority=TaskPriority.MEDIUM),
            _make_task("task-004", priority=TaskPriority.LOW),
            _make_task("task-005", priority=TaskPriority.HIGH),
        ]
        master._task_json = _make_task_json(tasks)

        # 验证优先级排序
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 5
        assert dispatchable[0].priority == TaskPriority.HIGH  # task-002
        assert dispatchable[1].priority == TaskPriority.HIGH  # task-005
        assert dispatchable[2].priority == TaskPriority.MEDIUM  # task-003
        assert dispatchable[3].priority == TaskPriority.LOW  # task-001
        assert dispatchable[4].priority == TaskPriority.LOW  # task-004

        # 模拟 dispatch 前 2 个（优先级最高的）
        first = dispatchable[0]
        second = dispatchable[1]
        assert first.id != second.id

        master._active_agents[first.id] = MagicMock(spec=SubAgent)
        master._active_agents[second.id] = MagicMock(spec=SubAgent)
        first.status = TaskStatus.IN_PROGRESS
        second.status = TaskStatus.IN_PROGRESS

        # 占满槽位 → 无法继续
        assert master.select_next_task() is None

    def test_concurrency_with_dependency_bottleneck(self):
        """并发 + 依赖瓶颈

        max_concurrent=3
        task-001 (PENDING) → task-002 (PENDING, dep=task-001)
        task-003 (PENDING, 无依赖)

        初始只有 task-001 和 task-003 可调度（task-002 依赖未满足）
        即使有 3 个槽位，也只调度 2 个
        """
        master = _make_master(max_concurrent=3)
        tasks = [
            _make_task("task-001", priority=TaskPriority.HIGH),
            _make_task("task-002", priority=TaskPriority.MEDIUM, dependencies=["task-001"]),
            _make_task("task-003", priority=TaskPriority.LOW),
        ]
        master._task_json = _make_task_json(tasks)

        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 2
        ids = [t.id for t in dispatchable]
        assert "task-002" not in ids

    def test_max_concurrent_equals_task_count(self):
        """max_concurrent 等于任务总数时，所有可调度任务一次性填充"""
        master = _make_master(max_concurrent=5)
        tasks = [_make_task(f"task-{i:03d}", priority=TaskPriority.MEDIUM) for i in range(1, 6)]
        master._task_json = _make_task_json(tasks)

        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 5

        # 通过 get_dispatchable_tasks 验证全部可调度
        # 模拟 dispatch：标记 IN_PROGRESS + 占用槽位
        for i in range(5):
            assert master._can_dispatch_more()
            task = dispatchable[i]
            task.status = TaskStatus.IN_PROGRESS
            master._active_agents[task.id] = MagicMock(spec=SubAgent)

        # 5 个槽位填满
        assert not master._can_dispatch_more()

    def test_slot_freed_allows_new_dispatch(self):
        """槽位释放后允许新任务调度

        模拟完整的 dispatch → execute → complete → dispatch 循环
        """
        master = _make_master(max_concurrent=2)
        tasks = [
            _make_task("task-001", priority=TaskPriority.HIGH),
            _make_task("task-002", priority=TaskPriority.MEDIUM),
            _make_task("task-003", priority=TaskPriority.LOW),
        ]
        master._task_json = _make_task_json(tasks)

        # dispatch task-001
        t1 = master.select_next_task()
        assert t1.id == "task-001"
        master._active_agents["task-001"] = MagicMock(spec=SubAgent)
        tasks[0].status = TaskStatus.IN_PROGRESS

        # dispatch task-002
        t2 = master.select_next_task()
        assert t2.id == "task-002"
        master._active_agents["task-002"] = MagicMock(spec=SubAgent)
        tasks[1].status = TaskStatus.IN_PROGRESS

        # 槽位满
        assert master.select_next_task() is None

        # task-001 完成
        master._active_agents.pop("task-001", None)
        tasks[0].status = TaskStatus.COMPLETED

        # 现在可调度 task-003
        t3 = master.select_next_task()
        assert t3.id == "task-003"

    def test_concurrency_one_with_dependencies(self):
        """max_concurrent=1 + 依赖链

        A → B → C, 严格串行
        """
        master = _make_master(max_concurrent=1)
        tasks = [
            _make_task("task-001", priority=TaskPriority.MEDIUM),
            _make_task("task-002", dependencies=["task-001"], priority=TaskPriority.HIGH),
            _make_task("task-003", dependencies=["task-002"], priority=TaskPriority.LOW),
        ]
        master._task_json = _make_task_json(tasks)

        # 选 A
        assert master.select_next_task().id == "task-001"
        master._active_agents["task-001"] = MagicMock(spec=SubAgent)

        # 槽位满
        assert master.select_next_task() is None

        # A 完成，B 依赖满足
        master._active_agents.pop("task-001", None)
        tasks[0].status = TaskStatus.COMPLETED
        assert master.select_next_task().id == "task-002"

    def test_concurrency_and_retry_occupied_slot(self):
        """重试任务占用槽位时不影响新任务调度判断

        一个重试中的 Agent 占用 1 个槽位，max_concurrent=2
        仍有 1 个空位可调度新任务
        """
        master = _make_master(max_concurrent=2, task_max_retries=2)
        tasks = [
            _make_task("task-001", priority=TaskPriority.LOW, retry_count=1),
            _make_task("task-002", priority=TaskPriority.HIGH, retry_count=0),
        ]
        master._task_json = _make_task_json(tasks)

        # 1 个槽位被重试 Agent 占用
        master._active_agents["task-retry"] = MagicMock(spec=SubAgent)

        # 还能调度
        result = master.select_next_task()
        assert result is not None
        assert result.id == "task-002"  # HIGH 优先


# ════════════════════════════════════════════════════════════════
# 三、依赖约束场景
# ════════════════════════════════════════════════════════════════


class TestDependencyConstraints:
    """依赖约束场景：多层链式、扇出/扇入、部分依赖满足、传递依赖"""

    def test_deep_chain_dependency(self):
        """4 层链式依赖 A→B→C→D

        只有 A 可调度，依次完成后 B→C→D 解锁
        """
        master = _make_master()
        tasks = [
            _make_task("task-001", priority=TaskPriority.LOW),
            _make_task("task-002", dependencies=["task-001"], priority=TaskPriority.MEDIUM),
            _make_task("task-003", dependencies=["task-002"], priority=TaskPriority.HIGH),
            _make_task("task-004", dependencies=["task-003"], priority=TaskPriority.LOW),
        ]
        master._task_json = _make_task_json(tasks)

        # 初始只有 task-001 可调度
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 1
        assert dispatchable[0].id == "task-001"

        # 完成 A → B 解锁
        tasks[0].status = TaskStatus.COMPLETED
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 1
        assert dispatchable[0].id == "task-002"

        # 完成 B → C 解锁
        tasks[1].status = TaskStatus.COMPLETED
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 1
        assert dispatchable[0].id == "task-003"

        # 完成 C → D 解锁
        tasks[2].status = TaskStatus.COMPLETED
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 1
        assert dispatchable[0].id == "task-004"

    def test_fan_out_dependency(self):
        """扇出依赖：A → B, C, D（A 完成后 B/C/D 同时解锁）"""
        master = _make_master()
        tasks = [
            _make_task("task-001", priority=TaskPriority.HIGH),
            _make_task("task-002", dependencies=["task-001"], priority=TaskPriority.MEDIUM),
            _make_task("task-003", dependencies=["task-001"], priority=TaskPriority.HIGH),
            _make_task("task-004", dependencies=["task-001"], priority=TaskPriority.LOW),
        ]
        master._task_json = _make_task_json(tasks)

        # 初始只有 A 可调度
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 1

        # A 完成后 B/C/D 全部解锁
        tasks[0].status = TaskStatus.COMPLETED
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 3
        # 优先级排序: task-003 (HIGH), task-002 (MEDIUM), task-004 (LOW)
        assert dispatchable[0].id == "task-003"
        assert dispatchable[1].id == "task-002"
        assert dispatchable[2].id == "task-004"

    def test_fan_in_dependency(self):
        """扇入依赖：A, B, C → D（D 依赖 A+B+C 全部完成）"""
        master = _make_master()
        tasks = [
            _make_task("task-001", priority=TaskPriority.HIGH),
            _make_task("task-002", priority=TaskPriority.MEDIUM),
            _make_task("task-003", priority=TaskPriority.LOW),
            _make_task("task-004", dependencies=["task-001", "task-002", "task-003"]),
        ]
        master._task_json = _make_task_json(tasks)

        # 初始 A/B/C 可调度，D 不可
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 3
        ids = [t.id for t in dispatchable]
        assert "task-004" not in ids

        # 完成 A → D 仍不可（缺 B+C）
        tasks[0].status = TaskStatus.COMPLETED
        dispatchable = master.get_dispatchable_tasks()
        assert "task-004" not in [t.id for t in dispatchable]

        # 完成 B → D 仍不可（缺 C）
        tasks[1].status = TaskStatus.COMPLETED
        dispatchable = master.get_dispatchable_tasks()
        assert "task-004" not in [t.id for t in dispatchable]

        # 完成 C → D 解锁
        tasks[2].status = TaskStatus.COMPLETED
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 1
        assert dispatchable[0].id == "task-004"

    def test_partial_dependency_satisfaction(self):
        """部分依赖满足：任务依赖 3 个，只完成 2 个，仍不可调度"""
        master = _make_master()
        tasks = [
            _make_task("task-001", status=TaskStatus.COMPLETED),
            _make_task("task-002", status=TaskStatus.COMPLETED),
            _make_task("task-003", status=TaskStatus.PENDING),
            _make_task("task-004", dependencies=["task-001", "task-002", "task-003"]),
        ]
        master._task_json = _make_task_json(tasks)

        dispatchable = master.get_dispatchable_tasks()
        ids = [t.id for t in dispatchable]
        # task-003 可调度，task-004 不可（缺少 task-003）
        assert "task-003" in ids
        assert "task-004" not in ids

    def test_diamond_dependency_with_priority(self):
        """菱形依赖 + 优先级：A→B(LOW), A→C(HIGH), B+C→D

        A 完成后，C (HIGH) 优先于 B (LOW) 被选中
        """
        master = _make_master()
        tasks = [
            _make_task("task-001", priority=TaskPriority.HIGH),
            _make_task("task-002", dependencies=["task-001"], priority=TaskPriority.LOW),
            _make_task("task-003", dependencies=["task-001"], priority=TaskPriority.HIGH),
            _make_task("task-004", dependencies=["task-002", "task-003"], priority=TaskPriority.MEDIUM),
        ]
        master._task_json = _make_task_json(tasks)

        # 完成 A
        tasks[0].status = TaskStatus.COMPLETED

        # B/C 解锁，C (HIGH) 优先
        result = master.select_next_task()
        assert result.id == "task-003"

    def test_transitive_dependency_not_auto_resolved(self):
        """传递依赖不自动解析

        A→B→C, task-003 依赖 task-002 但不依赖 task-001
        验证 get_dispatchable_tasks 只检查显式声明的依赖
        """
        master = _make_master()
        tasks = [
            _make_task("task-001", status=TaskStatus.PENDING),
            _make_task("task-002", dependencies=["task-001"], status=TaskStatus.PENDING),
            _make_task("task-003", dependencies=["task-002"], status=TaskStatus.PENDING),
        ]
        master._task_json = _make_task_json(tasks)

        # 初始只有 task-001 可调度
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 1
        assert dispatchable[0].id == "task-001"

        # 完成 task-001，task-002 解锁但 task-003 仍被 task-002 阻塞
        tasks[0].status = TaskStatus.COMPLETED
        dispatchable = master.get_dispatchable_tasks()
        ids = [t.id for t in dispatchable]
        assert "task-002" in ids
        assert "task-003" not in ids

    def test_multiple_independent_chains(self):
        """多条独立链并行调度

        Chain 1: A1 → A2
        Chain 2: B1 → B2
        """
        master = _make_master()
        tasks = [
            _make_task("task-001", priority=TaskPriority.HIGH),     # A1
            _make_task("task-002", dependencies=["task-001"]),      # A2
            _make_task("task-003", priority=TaskPriority.LOW),      # B1
            _make_task("task-004", dependencies=["task-003"]),      # B2
        ]
        master._task_json = _make_task_json(tasks)

        # A1 和 B1 可调度
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 2
        ids = [t.id for t in dispatchable]
        assert "task-001" in ids
        assert "task-003" in ids

        # 完成 A1 → A2 解锁，B1 也完成 → B2 解锁
        tasks[0].status = TaskStatus.COMPLETED
        tasks[2].status = TaskStatus.COMPLETED
        dispatchable = master.get_dispatchable_tasks()
        ids = [t.id for t in dispatchable]
        assert "task-002" in ids
        assert "task-004" in ids

    def test_dependency_on_failed_task_blocks(self):
        """依赖 FAILED 任务的后继任务不可调度

        task-001 (FAILED) → task-002 (PENDING, dep=task-001)
        task-002 因为 task-001 不是 COMPLETED，所以依赖不满足
        """
        master = _make_master()
        tasks = [
            _make_task("task-001", status=TaskStatus.FAILED),
            _make_task("task-002", dependencies=["task-001"], status=TaskStatus.PENDING),
            _make_task("task-003", status=TaskStatus.PENDING),
        ]
        master._task_json = _make_task_json(tasks)

        dispatchable = master.get_dispatchable_tasks()
        ids = [t.id for t in dispatchable]
        assert "task-002" not in ids  # 依赖未满足（FAILED ≠ COMPLETED）
        assert "task-003" in ids

    def test_dependency_on_blocked_task(self):
        """依赖 BLOCKED 任务的后继任务不可调度"""
        master = _make_master()
        tasks = [
            _make_task("task-001", status=TaskStatus.BLOCKED),
            _make_task("task-002", dependencies=["task-001"], status=TaskStatus.PENDING),
        ]
        master._task_json = _make_task_json(tasks)

        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 0

    def test_no_dependency_independent_tasks(self):
        """无依赖的独立任务全部可调度"""
        master = _make_master()
        tasks = [
            _make_task("task-001"),
            _make_task("task-002"),
            _make_task("task-003"),
            _make_task("task-004"),
            _make_task("task-005"),
        ]
        master._task_json = _make_task_json(tasks)

        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 5

    def test_dependency_chain_with_mixed_priorities(self):
        """依赖链 + 混合优先级

        A (LOW) → B (HIGH) → C (MEDIUM)
        虽然 B 是 HIGH，但必须等 A (LOW) 完成
        """
        master = _make_master()
        tasks = [
            _make_task("task-001", priority=TaskPriority.LOW),
            _make_task("task-002", dependencies=["task-001"], priority=TaskPriority.HIGH),
            _make_task("task-003", dependencies=["task-002"], priority=TaskPriority.MEDIUM),
        ]
        master._task_json = _make_task_json(tasks)

        # B 是 HIGH 但依赖 A (LOW)，必须先调 A
        result = master.select_next_task()
        assert result.id == "task-001"  # LOW 但是唯一可调度的

        # A 完成
        tasks[0].status = TaskStatus.COMPLETED
        result = master.select_next_task()
        assert result.id == "task-002"  # HIGH 解锁


# ════════════════════════════════════════════════════════════════
# 四、综合场景：优先级 + 并行度 + 依赖交互
# ════════════════════════════════════════════════════════════════


class TestCombinedScenarios:
    """综合场景：优先级、并行度、依赖三者交互"""

    def test_priority_deps_concurrency_combined(self):
        """三方交互综合场景

        max_concurrent=2
        task-001 (HIGH, PENDING)     → 无依赖
        task-002 (MEDIUM, PENDING)   → 无依赖
        task-003 (LOW, PENDING)      → dep=task-001
        task-004 (HIGH, PENDING)     → dep=task-002

        初始：task-001(HIGH) 和 task-002(MEDIUM) 可调度
        填满 2 槽位后无法继续
        task-001 完成后 task-003(LOW) 解锁，且有 1 个空位
        """
        master = _make_master(max_concurrent=2)
        tasks = [
            _make_task("task-001", priority=TaskPriority.HIGH),
            _make_task("task-002", priority=TaskPriority.MEDIUM),
            _make_task("task-003", dependencies=["task-001"], priority=TaskPriority.LOW),
            _make_task("task-004", dependencies=["task-002"], priority=TaskPriority.HIGH),
        ]
        master._task_json = _make_task_json(tasks)

        # 初始：task-001 + task-002 可调度
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 2
        assert dispatchable[0].id == "task-001"  # HIGH
        assert dispatchable[1].id == "task-002"  # MEDIUM

        # 填满槽位（模拟 dispatch，标记 IN_PROGRESS）
        master._active_agents["task-001"] = MagicMock(spec=SubAgent)
        master._active_agents["task-002"] = MagicMock(spec=SubAgent)
        tasks[0].status = TaskStatus.IN_PROGRESS
        tasks[1].status = TaskStatus.IN_PROGRESS
        assert master.select_next_task() is None

        # task-001 完成 → task-003 解锁
        master._active_agents.pop("task-001", None)
        tasks[0].status = TaskStatus.COMPLETED
        result = master.select_next_task()
        # task-004 (HIGH, dep=task-002未满足) 不可调度
        # task-002 仍在 IN_PROGRESS（占用槽位，不是 PENDING）
        # task-003 (LOW, dep=task-001已满足, PENDING) 可调度
        assert result.id == "task-003"

    def test_complex_scheduling_wave(self):
        """复杂调度波次

        Wave 1: task-001, task-002 (无依赖，独立)
        Wave 2: task-003 (dep=001+002), task-004 (dep=001)
        Wave 3: task-005 (dep=003+004)
        """
        master = _make_master(max_concurrent=3)
        tasks = [
            _make_task("task-001", priority=TaskPriority.HIGH),
            _make_task("task-002", priority=TaskPriority.MEDIUM),
            _make_task("task-003", dependencies=["task-001", "task-002"], priority=TaskPriority.HIGH),
            _make_task("task-004", dependencies=["task-001"], priority=TaskPriority.LOW),
            _make_task("task-005", dependencies=["task-003", "task-004"], priority=TaskPriority.MEDIUM),
        ]
        master._task_json = _make_task_json(tasks)

        # Wave 1: task-001 + task-002
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 2

        # 完成 Wave 1
        tasks[0].status = TaskStatus.COMPLETED
        tasks[1].status = TaskStatus.COMPLETED

        # Wave 2: task-004 (LOW, dep=001满足) + task-003 (HIGH, dep=001+002满足)
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 2
        assert dispatchable[0].id == "task-003"  # HIGH 优先
        assert dispatchable[1].id == "task-004"  # LOW

        # 完成 Wave 2
        tasks[2].status = TaskStatus.COMPLETED
        tasks[3].status = TaskStatus.COMPLETED

        # Wave 3: task-005
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 1
        assert dispatchable[0].id == "task-005"

    def test_retry_and_dependency_interaction(self):
        """重试 + 依赖交互

        task-001 (HIGH, retry_count=2, 超限) → FAILED
        task-002 (MEDIUM, dep=task-001)
        task-003 (LOW, 无依赖)

        task-001 超限不可重试，task-002 依赖 FAILED 任务不可调度
        只剩 task-003 可调度
        """
        master = _make_master(task_max_retries=1)
        tasks = [
            _make_task("task-001", priority=TaskPriority.HIGH, status=TaskStatus.FAILED, retry_count=2),
            _make_task("task-002", dependencies=["task-001"], status=TaskStatus.PENDING, priority=TaskPriority.MEDIUM),
            _make_task("task-003", priority=TaskPriority.LOW),
        ]
        master._task_json = _make_task_json(tasks)

        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 1
        assert dispatchable[0].id == "task-003"

    def test_concurrency_gradual_release(self):
        """并发槽位逐步释放

        max_concurrent=3, 3 个任务同时执行
        逐个完成，每完成一个就有一个新任务可调度
        """
        master = _make_master(max_concurrent=3)
        tasks = [
            _make_task("task-001", priority=TaskPriority.HIGH),
            _make_task("task-002", priority=TaskPriority.MEDIUM),
            _make_task("task-003", priority=TaskPriority.LOW),
            _make_task("task-004", priority=TaskPriority.HIGH),
            _make_task("task-005", priority=TaskPriority.MEDIUM),
        ]
        master._task_json = _make_task_json(tasks)

        # 填满 3 个槽位（模拟 dispatch）
        master._active_agents["task-001"] = MagicMock(spec=SubAgent)
        master._active_agents["task-002"] = MagicMock(spec=SubAgent)
        master._active_agents["task-003"] = MagicMock(spec=SubAgent)
        tasks[0].status = TaskStatus.IN_PROGRESS
        tasks[1].status = TaskStatus.IN_PROGRESS
        tasks[2].status = TaskStatus.IN_PROGRESS
        assert not master._can_dispatch_more()

        # 释放 task-001
        master._active_agents.pop("task-001", None)
        tasks[0].status = TaskStatus.COMPLETED
        assert master._can_dispatch_more()

        # 选最高优先级可用任务
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 2  # task-004 (HIGH) + task-005 (MEDIUM)
        assert dispatchable[0].id == "task-004"  # HIGH
        assert dispatchable[1].id == "task-005"  # MEDIUM

        # dispatch task-004
        tasks[3].status = TaskStatus.IN_PROGRESS
        master._active_agents["task-004"] = MagicMock(spec=SubAgent)

        # 再释放 task-002
        master._active_agents.pop("task-002", None)
        tasks[1].status = TaskStatus.COMPLETED

        # task-005 仍是唯一可调度的 PENDING
        result = master.select_next_task()
        assert result.id == "task-005"

    def test_all_deps_completed_allows_dispatch(self):
        """所有依赖完成时任务变为可调度

        task-001 (COMPLETED) → task-002 (COMPLETED) → task-003 (PENDING, dep=001+002)
        task-003 的依赖全部满足
        """
        master = _make_master()
        tasks = [
            _make_task("task-001", status=TaskStatus.COMPLETED),
            _make_task("task-002", status=TaskStatus.COMPLETED),
            _make_task("task-003", dependencies=["task-001", "task-002"]),
        ]
        master._task_json = _make_task_json(tasks)

        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 1
        assert dispatchable[0].id == "task-003"

    def test_skip_in_progress_dependency(self):
        """IN_PROGRESS 的依赖任务不算完成

        task-001 (IN_PROGRESS) → task-002 (PENDING, dep=task-001)
        task-002 不可调度，因为 task-001 不是 COMPLETED
        """
        master = _make_master()
        tasks = [
            _make_task("task-001", status=TaskStatus.IN_PROGRESS),
            _make_task("task-002", dependencies=["task-001"]),
        ]
        master._task_json = _make_task_json(tasks)

        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 0


# ════════════════════════════════════════════════════════════════
# 五、边界条件与异常场景
# ════════════════════════════════════════════════════════════════


class TestEdgeCases:
    """边界条件与异常场景"""

    def test_single_task_scheduling(self):
        """单任务调度"""
        master = _make_master()
        tasks = [_make_task("task-001", priority=TaskPriority.HIGH)]
        master._task_json = _make_task_json(tasks)

        result = master.select_next_task()
        assert result.id == "task-001"

    def test_empty_task_list(self):
        """空任务列表"""
        master = _make_master()
        master._task_json = _make_task_json([])

        assert master.select_next_task() is None
        assert master.get_dispatchable_tasks() == []

    def test_all_tasks_blocked(self):
        """所有任务 BLOCKED → 无可调度任务"""
        master = _make_master()
        tasks = [
            _make_task("task-001", status=TaskStatus.BLOCKED),
            _make_task("task-002", status=TaskStatus.BLOCKED),
        ]
        master._task_json = _make_task_json(tasks)

        assert master.get_dispatchable_tasks() == []
        assert master.select_next_task() is None

    def test_circular_dependency_no_dispatch(self):
        """循环依赖场景：两个任务互为依赖

        TaskJSON 构造器会拒绝循环依赖（build_dag 校验），
        此处使用 model_construct 绕过校验，测试 get_dispatchable_tasks
        对防御性数据的处理：两者依赖都不满足，无可调度任务
        """
        master = _make_master()
        tasks = [
            _make_task("task-001", dependencies=["task-002"]),
            _make_task("task-002", dependencies=["task-001"]),
        ]
        # 使用 model_construct 绕过 TaskJSON 的循环依赖校验
        master._task_json = TaskJSON.model_construct(
            project_name="test-project",
            total_tasks=2,
            tasks=tasks,
        )

        # 两者依赖都不满足
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 0

    def test_max_concurrent_one_high_volume(self):
        """max_concurrent=1 处理大量任务"""
        master = _make_master(max_concurrent=1)
        tasks = [_make_task(f"task-{i:03d}", priority=TaskPriority.MEDIUM) for i in range(1, 11)]
        master._task_json = _make_task_json(tasks)

        # 一次只能调度 1 个
        result = master.select_next_task()
        assert result is not None
        master._active_agents[result.id] = MagicMock(spec=SubAgent)
        assert master.select_next_task() is None

        # 完成后继续
        master._active_agents.clear()
        for t in tasks:
            if t.status == TaskStatus.PENDING:
                t.status = TaskStatus.COMPLETED
                break
        result = master.select_next_task()
        assert result is not None

    def test_task_with_nonexistent_dependency(self):
        """依赖不存在的任务 ID → 依赖永远不满足

        TaskJSON 构造器会校验引用有效性，此处使用 model_construct
        绕过校验，测试 get_dispatchable_tasks 对无效依赖的处理
        """
        master = _make_master()
        tasks = [
            _make_task("task-001", dependencies=["task-999"]),
            _make_task("task-002"),
        ]
        # 使用 model_construct 绕过 TaskJSON 的引用有效性校验
        master._task_json = TaskJSON.model_construct(
            project_name="test-project",
            total_tasks=2,
            tasks=tasks,
        )

        dispatchable = master.get_dispatchable_tasks()
        ids = [t.id for t in dispatchable]
        assert "task-001" not in ids  # 依赖不满足（task-999 不在 completed_ids）
        assert "task-002" in ids

    def test_state_dispatching_vs_monitoring_identical_results(self):
        """DISPATCHING 和 MONITORING 状态下调度结果一致"""
        tasks = [
            _make_task("task-001", priority=TaskPriority.HIGH),
            _make_task("task-002", priority=TaskPriority.MEDIUM),
        ]
        task_json = _make_task_json(tasks)

        master_d = _make_master(state=MasterAgentState.DISPATCHING)
        master_d._task_json = task_json

        master_m = _make_master(state=MasterAgentState.MONITORING)
        master_m._task_json = _make_task_json([
            _make_task("task-001", priority=TaskPriority.HIGH),
            _make_task("task-002", priority=TaskPriority.MEDIUM),
        ])

        result_d = master_d.select_next_task()
        result_m = master_m.select_next_task()
        assert result_d.id == result_m.id

    def test_skipped_dependency_not_counted(self):
        """SKIPPED 依赖不算完成（仅 COMPLETED 满足依赖）

        task-001 (SKIPPED) → task-002 (PENDING, dep=task-001)
        task-002 的依赖不满足
        """
        master = _make_master()
        tasks = [
            _make_task("task-001", status=TaskStatus.SKIPPED),
            _make_task("task-002", dependencies=["task-001"]),
        ]
        master._task_json = _make_task_json(tasks)

        dispatchable = master.get_dispatchable_tasks()
        ids = [t.id for t in dispatchable]
        assert "task-002" not in ids

    def test_completed_dependency_satisfies(self):
        """COMPLETED 依赖满足条件（正面验证）

        task-001 (COMPLETED) → task-002 (PENDING, dep=task-001)
        """
        master = _make_master()
        tasks = [
            _make_task("task-001", status=TaskStatus.COMPLETED),
            _make_task("task-002", dependencies=["task-001"]),
        ]
        master._task_json = _make_task_json(tasks)

        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 1
        assert dispatchable[0].id == "task-002"

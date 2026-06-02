"""
P2-016 测试 — ParallelScheduler 并行任务调度器

测试内容：
- DAG 构建与基本属性
- next_batch 基本批次划分
- 依赖解析（前置完成才进入下一批）
- 最大并发限制
- 优先级排序（HIGH > MEDIUM > LOW）
- 单任务/空任务
- 无依赖全并行
- 链式依赖串行
- mark_failed 不释放后继
- reset 状态重置
- 已完成/剩余计数
"""

import pytest

from agent_automation_system.scheduler.dag import (
    TaskDAG,
    build_dag,
)
from agent_automation_system.models.task import (
    Task,
    TaskPriority,
    TaskStatus,
)


# ── 辅助工具 ──────────────────────────────────────────────


def _make_task(
    task_id: str,
    title: str = "",
    dependencies: list[str] | None = None,
    priority: TaskPriority = TaskPriority.MEDIUM,
) -> Task:
    return Task(
        id=task_id,
        title=title or f"Task {task_id}",
        description=f"Description for {task_id}",
        dependencies=dependencies or [],
        priority=priority,
        status=TaskStatus.PENDING,
    )


def _build_dag(*tasks: Task) -> TaskDAG:
    return build_dag(list(tasks))


# ── 导入待测类 ────────────────────────────────────────────

from agent_automation_system.scheduler.parallel_scheduler import (
    ParallelScheduler,
)


# ── 基本属性 ──────────────────────────────────────────────


class TestParallelSchedulerProperties:
    """基本属性和构造"""

    def test_dag_property(self):
        """dag 属性返回注入的 DAG"""
        dag = _build_dag(_make_task("task-001"))
        sched = ParallelScheduler(dag)
        assert sched.dag is dag

    def test_max_concurrent_property(self):
        """max_concurrent 属性返回注入值"""
        dag = _build_dag(_make_task("task-001"))
        sched = ParallelScheduler(dag, max_concurrent=5)
        assert sched.max_concurrent == 5

    def test_max_concurrent_default(self):
        """默认 max_concurrent=3"""
        dag = _build_dag(_make_task("task-001"))
        sched = ParallelScheduler(dag)
        assert sched.max_concurrent == 3

    def test_max_concurrent_positive_required(self):
        """max_concurrent 必须为正数"""
        dag = _build_dag(_make_task("task-001"))
        with pytest.raises(ValueError, match="positive"):
            ParallelScheduler(dag, max_concurrent=0)

    def test_max_concurrent_negative_raises(self):
        """负 max_concurrent 抛 ValueError"""
        dag = _build_dag(_make_task("task-001"))
        with pytest.raises(ValueError, match="positive"):
            ParallelScheduler(dag, max_concurrent=-1)

    def test_empty_dag_total_tasks_zero(self):
        """空 DAG 任务总数为 0"""
        dag = build_dag([])
        sched = ParallelScheduler(dag)
        assert sched.total_tasks == 0


# ── next_batch 基本批次 ───────────────────────────────────


class TestParallelSchedulerNextBatch:
    """next_batch 批次划分"""

    def test_single_task_returns_itself(self):
        """单任务返回自身"""
        dag = _build_dag(_make_task("task-001"))
        sched = ParallelScheduler(dag)
        batch = sched.next_batch()
        assert batch == ["task-001"]

    def test_two_independent_tasks_one_batch(self):
        """两个无依赖任务在同一批"""
        dag = _build_dag(_make_task("task-001"), _make_task("task-002"))
        sched = ParallelScheduler(dag)
        batch = sched.next_batch()
        assert set(batch) == {"task-001", "task-002"}

    def test_empty_dag_returns_empty_batch(self):
        """空 DAG 返回空列表"""
        dag = build_dag([])
        sched = ParallelScheduler(dag)
        batch = sched.next_batch()
        assert batch == []

    def test_already_completed_returns_ready_tasks_only(self):
        """已完成的返回剩余的就绪任务"""
        dag = _build_dag(_make_task("task-001"), _make_task("task-002"))
        sched = ParallelScheduler(dag)
        sched.mark_completed("task-001")
        batch = sched.next_batch()
        assert batch == ["task-002"]

    def test_all_completed_returns_empty(self):
        """全部完成后返回空"""
        dag = _build_dag(_make_task("task-001"))
        sched = ParallelScheduler(dag)
        sched.mark_completed("task-001")
        batch = sched.next_batch()
        assert batch == []


# ── 依赖解析 ──────────────────────────────────────────────


class TestParallelSchedulerDependencyResolution:
    """依赖关系解析 — 前置完成才进入下一批"""

    def test_b_blocked_by_a(self):
        """B 依赖 A，第一批发 A，A 完成后发 B"""
        dag = _build_dag(
            _make_task("task-001"),
            _make_task("task-002", dependencies=["task-001"]),
        )
        sched = ParallelScheduler(dag)

        batch1 = sched.next_batch()
        assert batch1 == ["task-001"]

        sched.mark_completed("task-001")
        batch2 = sched.next_batch()
        assert batch2 == ["task-002"]

    def test_chain_three_sequential(self):
        """task-001→task-002→task-003 链式依赖，分三批"""
        dag = _build_dag(
            _make_task("task-001"),
            _make_task("task-002", dependencies=["task-001"]),
            _make_task("task-003", dependencies=["task-002"]),
        )
        sched = ParallelScheduler(dag)

        b1 = sched.next_batch()
        assert b1 == ["task-001"]
        sched.mark_completed("task-001")

        b2 = sched.next_batch()
        assert b2 == ["task-002"]
        sched.mark_completed("task-002")

        b3 = sched.next_batch()
        assert b3 == ["task-003"]

    def test_diamond_dependency(self):
        """task-001→task-002, task-001→task-003, task-002→task-004, task-003→task-004"""
        dag = _build_dag(
            _make_task("task-001"),
            _make_task("task-002", dependencies=["task-001"]),
            _make_task("task-003", dependencies=["task-001"]),
            _make_task("task-004", dependencies=["task-002", "task-003"]),
        )
        sched = ParallelScheduler(dag)

        b1 = sched.next_batch()
        assert set(b1) == {"task-001"}
        sched.mark_completed("task-001")

        b2 = sched.next_batch()
        assert set(b2) == {"task-002", "task-003"}
        sched.mark_completed("task-002")
        # task-003 未完成，task-004 还不能发
        b3 = sched.next_batch()
        assert set(b3) == {"task-003"}
        sched.mark_completed("task-003")

        b4 = sched.next_batch()
        assert set(b4) == {"task-004"}

    def test_multiple_deps_all_must_complete(self):
        """多依赖必须全部完成才就绪"""
        dag = _build_dag(
            _make_task("task-001"),
            _make_task("task-002"),
            _make_task("task-003", dependencies=["task-001", "task-002"]),
        )
        sched = ParallelScheduler(dag)

        b1 = sched.next_batch()
        assert set(b1) == {"task-001", "task-002"}
        sched.mark_completed("task-001")

        # task-002 未完成，task-003 不能发
        b2 = sched.next_batch()
        assert b2 == ["task-002"]


# ── 最大并发限制 ──────────────────────────────────────────


class TestParallelSchedulerMaxConcurrency:
    """最大并发限制约束"""

    def test_four_tasks_limit_two(self):
        """4 个无依赖任务，限并发 2，分两批"""
        dag = _build_dag(
            _make_task("task-001"), _make_task("task-002"),
            _make_task("task-003"), _make_task("task-004"),
        )
        sched = ParallelScheduler(dag, max_concurrent=2)
        b1 = sched.next_batch()
        assert len(b1) == 2

        sched.mark_completed(b1[0])
        sched.mark_completed(b1[1])
        b2 = sched.next_batch()
        assert len(b2) == 2

    def test_concurrency_fills_partial_slots(self):
        """并发未满时用就绪任务填充"""
        dag = _build_dag(
            _make_task("task-001"),
            _make_task("task-002", dependencies=["task-001"]),
            _make_task("task-003"),
        )
        sched = ParallelScheduler(dag, max_concurrent=3)
        # task-001 和 task-003 就绪，task-002 被阻塞
        b1 = sched.next_batch()
        assert set(b1) == {"task-001", "task-003"}

        sched.mark_completed("task-001")
        sched.mark_completed("task-003")
        b2 = sched.next_batch()
        assert b2 == ["task-002"]

    def test_new_tasks_fill_freed_slots(self):
        """释放的槽位由新就绪任务填补"""
        dag = _build_dag(
            _make_task("task-001"),
            _make_task("task-002", dependencies=["task-001"]),
            _make_task("task-003", dependencies=["task-001"]),
        )
        sched = ParallelScheduler(dag, max_concurrent=2)
        b1 = sched.next_batch()
        assert b1 == ["task-001"]
        sched.mark_completed("task-001")

        b2 = sched.next_batch()
        assert set(b2) == {"task-002", "task-003"}


# ── 优先级排序 ────────────────────────────────────────────


class TestParallelSchedulerPriorityOrdering:
    """批次内按优先级排序（HIGH > MEDIUM > LOW）"""

    def test_high_before_medium(self):
        """HIGH 排在 MEDIUM 前"""
        dag = _build_dag(
            _make_task("task-001", priority=TaskPriority.MEDIUM),
            _make_task("task-002", priority=TaskPriority.HIGH),
        )
        sched = ParallelScheduler(dag, max_concurrent=2)
        batch = sched.next_batch()
        assert batch == ["task-002", "task-001"]

    def test_high_before_low(self):
        """HIGH 排在 LOW 前"""
        dag = _build_dag(
            _make_task("task-001", priority=TaskPriority.LOW),
            _make_task("task-002", priority=TaskPriority.HIGH),
        )
        sched = ParallelScheduler(dag, max_concurrent=2)
        batch = sched.next_batch()
        assert batch == ["task-002", "task-001"]

    def test_medium_before_low(self):
        """MEDIUM 排在 LOW 前"""
        dag = _build_dag(
            _make_task("task-001", priority=TaskPriority.LOW),
            _make_task("task-002", priority=TaskPriority.MEDIUM),
        )
        sched = ParallelScheduler(dag, max_concurrent=2)
        batch = sched.next_batch()
        assert batch == ["task-002", "task-001"]

    def test_priority_with_concurrency_limit(self):
        """并发限制下，高优先级优先入批"""
        dag = _build_dag(
            _make_task("task-001", priority=TaskPriority.LOW),
            _make_task("task-002", priority=TaskPriority.HIGH),
            _make_task("task-003", priority=TaskPriority.MEDIUM),
        )
        sched = ParallelScheduler(dag, max_concurrent=2)
        batch = sched.next_batch()
        assert batch == ["task-002", "task-003"]  # HIGH + MEDIUM


# ── has_more ──────────────────────────────────────────────


class TestParallelSchedulerHasMore:
    """has_more 判断"""

    def test_initial_has_more(self):
        """初始状态有任务，返回 True"""
        dag = _build_dag(_make_task("task-001"))
        sched = ParallelScheduler(dag)
        assert sched.has_more() is True

    def test_after_complete_no_more(self):
        """完成后没有更多"""
        dag = _build_dag(_make_task("task-001"))
        sched = ParallelScheduler(dag)
        sched.mark_completed("task-001")
        assert sched.has_more() is False

    def test_empty_dag_no_more(self):
        """空 DAG 没有更多"""
        dag = build_dag([])
        sched = ParallelScheduler(dag)
        assert sched.has_more() is False

    def test_partial_complete_still_has_more(self):
        """部分完成仍有更多"""
        dag = _build_dag(_make_task("task-001"), _make_task("task-002"))
        sched = ParallelScheduler(dag)
        sched.mark_completed("task-001")
        assert sched.has_more() is True


# ── mark_failed ───────────────────────────────────────────


class TestParallelSchedulerMarkFailed:
    """失败任务不释放后继"""

    def test_failed_task_does_not_unblock_dependents(self):
        """task-001 失败 → task-002 永远不就绪"""
        dag = _build_dag(
            _make_task("task-001"),
            _make_task("task-002", dependencies=["task-001"]),
        )
        sched = ParallelScheduler(dag)
        b1 = sched.next_batch()
        assert b1 == ["task-001"]

        sched.mark_failed("task-001")
        b2 = sched.next_batch()
        assert b2 == []

    def test_failed_task_registered_as_completed_count(self):
        """失败任务计入已完成计数"""
        dag = _build_dag(_make_task("task-001"), _make_task("task-002"))
        sched = ParallelScheduler(dag)
        sched.mark_failed("task-001")
        assert sched.completed_count == 1
        assert sched.remaining_count == 1

    def test_mixed_complete_and_fail(self):
        """混合完成和失败"""
        dag = _build_dag(
            _make_task("task-001"),
            _make_task("task-002", dependencies=["task-001"]),
            _make_task("task-003"),
        )
        sched = ParallelScheduler(dag)
        b1 = sched.next_batch()
        assert set(b1) == {"task-001", "task-003"}

        sched.mark_failed("task-001")  # task-002 永远阻塞
        sched.mark_completed("task-003")
        b2 = sched.next_batch()
        assert b2 == []  # task-002 被阻塞


# ── reset ─────────────────────────────────────────────────


class TestParallelSchedulerReset:
    """reset 状态重置"""

    def test_reset_clears_completed(self):
        """reset 清除已完成记录"""
        dag = _build_dag(_make_task("task-001"), _make_task("task-002"))
        sched = ParallelScheduler(dag)
        sched.mark_completed("task-001")
        sched.reset()
        assert sched.completed_count == 0
        assert sched.remaining_count == 2

    def test_reset_restores_initial_batch(self):
        """reset 后 next_batch 恢复初始状态"""
        dag = _build_dag(_make_task("task-001"), _make_task("task-002"))
        sched = ParallelScheduler(dag)
        sched.mark_completed("task-001")
        sched.reset()
        batch = sched.next_batch()
        assert set(batch) == {"task-001", "task-002"}


# ── 计数 ──────────────────────────────────────────────────


class TestParallelSchedulerCounts:
    """completed_count 和 remaining_count"""

    def test_initial_counts(self):
        """初始计数"""
        dag = _build_dag(
            _make_task("task-001"), _make_task("task-002"), _make_task("task-003")
        )
        sched = ParallelScheduler(dag)
        assert sched.completed_count == 0
        assert sched.remaining_count == 3
        assert sched.total_tasks == 3

    def test_count_after_completions(self):
        """完成后计数更新"""
        dag = _build_dag(
            _make_task("task-001"), _make_task("task-002"), _make_task("task-003")
        )
        sched = ParallelScheduler(dag)
        sched.mark_completed("task-001")
        assert sched.completed_count == 1
        assert sched.remaining_count == 2

    def test_get_ready_tasks_count_matches_batch_size(self):
        """get_ready_tasks 数量等于 batch 大小（无限并发时）"""
        dag = _build_dag(
            _make_task("task-001"),
            _make_task("task-002", dependencies=["task-001"]),
            _make_task("task-003"),
            _make_task("task-004"),
        )
        sched = ParallelScheduler(dag, max_concurrent=10)
        ready = sched.get_ready_tasks()
        assert set(ready) == {"task-001", "task-003", "task-004"}


# ── 复杂场景 ──────────────────────────────────────────────


class TestParallelSchedulerComplexScenarios:
    """多任务复杂依赖场景"""

    def test_tree_structure(self):
        """树形结构"""
        dag = _build_dag(
            _make_task("task-001"),
            _make_task("task-002", dependencies=["task-001"]),
            _make_task("task-003", dependencies=["task-001"]),
            _make_task("task-004", dependencies=["task-002"]),
            _make_task("task-005", dependencies=["task-002"]),
            _make_task("task-006", dependencies=["task-003"]),
            _make_task("task-007", dependencies=["task-003"]),
        )
        sched = ParallelScheduler(dag, max_concurrent=5)

        b1 = sched.next_batch()
        assert b1 == ["task-001"]

        sched.mark_completed("task-001")
        b2 = sched.next_batch()
        assert set(b2) == {"task-002", "task-003"}

        sched.mark_completed("task-002")
        sched.mark_completed("task-003")
        b3 = sched.next_batch()
        assert set(b3) == {"task-004", "task-005", "task-006", "task-007"}

    def test_mixed_dependencies_with_priorities(self):
        """混合依赖 + 优先级"""
        dag = _build_dag(
            _make_task("task-001", priority=TaskPriority.LOW),
            _make_task("task-002", priority=TaskPriority.HIGH),
            _make_task("task-003", dependencies=["task-001"], priority=TaskPriority.HIGH),
            _make_task("task-004", dependencies=["task-002"], priority=TaskPriority.MEDIUM),
        )
        sched = ParallelScheduler(dag, max_concurrent=2)

        b1 = sched.next_batch()
        # task-002(HIGH) > task-001(LOW)
        assert b1 == ["task-002", "task-001"]

        sched.mark_completed("task-001")
        sched.mark_completed("task-002")
        b2 = sched.next_batch()
        # task-003(HIGH) > task-004(MEDIUM)
        assert b2 == ["task-003", "task-004"]

    def test_concurrent_with_multiple_dependency_levels(self):
        """多层级并发限制"""
        dag = _build_dag(
            _make_task("task-001"), _make_task("task-002"), _make_task("task-003"),
            _make_task("task-004", dependencies=["task-001"]),
            _make_task("task-005", dependencies=["task-002"]),
            _make_task("task-006", dependencies=["task-003"]),
            _make_task("task-007", dependencies=["task-004", "task-005", "task-006"]),
        )
        sched = ParallelScheduler(dag, max_concurrent=2)

        b1 = sched.next_batch()
        assert len(b1) == 2  # 3 个就绪但限 2
        for tid in b1:
            sched.mark_completed(tid)

        b2 = sched.next_batch()
        assert len(b2) == 2  # 1 剩余 + 1 新就绪
        for tid in b2:
            sched.mark_completed(tid)

        b3 = sched.next_batch()
        assert len(b3) == 2  # 2 个 task-004/task-005/task-006 就绪
        for tid in b3:
            sched.mark_completed(tid)

        b4 = sched.next_batch()
        assert len(b4) == 1  # 最后 1 个

    def test_no_ready_tasks_yet(self):
        """所有就绪任务已返回（未完成），下一批无新增"""
        dag = _build_dag(
            _make_task("task-001"),
            _make_task("task-002", dependencies=["task-001"]),
            _make_task("task-003", dependencies=["task-002"]),
        )
        sched = ParallelScheduler(dag)

        # task-001 就绪（无依赖）
        b1 = sched.next_batch()
        assert b1 == ["task-001"]

        # task-001 未完成 → task-002 仍阻塞 → 就绪任务仍是 task-001
        # 调用者应自行避免重复分发
        b2 = sched.next_batch()
        assert b2 == ["task-001"]  # 纯函数：基于 DAG + 完成状态计算

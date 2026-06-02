"""
P2-021 测试 — ParallelScheduler 单元测试补充

补充场景：2-agent 并行、3-agent 并行、依赖阻塞、批次填充、
单线程退化、max_concurrent 边界、复杂流水线等。
"""

import pytest

from agent_automation_system.scheduler.parallel_scheduler import ParallelScheduler
from agent_automation_system.scheduler.dag import build_dag
from agent_automation_system.models.task import Task, TaskPriority, TaskStatus


def _t(task_id, deps=None, priority=TaskPriority.MEDIUM):
    return Task(
        id=task_id, title=task_id, description=task_id,
        dependencies=deps or [], priority=priority, status=TaskStatus.PENDING,
    )


class TestTwoAgentParallel:
    """2-agent 并行场景"""

    def test_two_agents_four_independent_tasks(self):
        dag = build_dag([_t("task-001"), _t("task-002"), _t("task-003"), _t("task-004")])
        s = ParallelScheduler(dag, max_concurrent=2)
        b1 = s.next_batch()
        assert len(b1) == 2
        for tid in b1:
            s.mark_completed(tid)
        b2 = s.next_batch()
        assert len(b2) == 2

    def test_two_agents_with_blocked_third(self):
        dag = build_dag([
            _t("task-001"), _t("task-002"),
            _t("task-003", deps=["task-001"]),
        ])
        s = ParallelScheduler(dag, max_concurrent=2)
        b1 = s.next_batch()
        assert set(b1) == {"task-001", "task-002"}
        s.mark_completed("task-002")
        b2 = s.next_batch()
        assert b2 == ["task-001"]
        s.mark_completed("task-001")
        b3 = s.next_batch()
        assert b3 == ["task-003"]

    def test_two_agents_three_independent_one_after(self):
        dag = build_dag([
            _t("task-001"), _t("task-002"), _t("task-003"),
            _t("task-004", deps=["task-001", "task-002", "task-003"]),
        ])
        s = ParallelScheduler(dag, max_concurrent=2)
        b1 = s.next_batch()
        assert len(b1) == 2
        for tid in b1:
            s.mark_completed(tid)
        b2 = s.next_batch()
        assert len(b2) == 1
        s.mark_completed(b2[0])
        b3 = s.next_batch()
        assert b3 == ["task-004"]


class TestThreeAgentParallel:
    """3-agent 并行场景"""

    def test_three_agents_six_independent_tasks(self):
        dag = build_dag([
            _t("task-001"), _t("task-002"), _t("task-003"),
            _t("task-004"), _t("task-005"), _t("task-006"),
        ])
        s = ParallelScheduler(dag, max_concurrent=3)
        b1 = s.next_batch()
        assert len(b1) == 3
        for tid in b1:
            s.mark_completed(tid)
        b2 = s.next_batch()
        assert len(b2) == 3

    def test_three_agents_interleaved_completions(self):
        dag = build_dag([
            _t("task-001"),
            _t("task-002", deps=["task-001"]),
            _t("task-003", deps=["task-001"]),
            _t("task-004", deps=["task-002"]),
            _t("task-005", deps=["task-003"]),
            _t("task-006", deps=["task-002", "task-003"]),
        ])
        s = ParallelScheduler(dag, max_concurrent=3)
        b1 = s.next_batch()
        assert b1 == ["task-001"]
        s.mark_completed("task-001")
        b2 = s.next_batch()
        assert set(b2) == {"task-002", "task-003"}
        s.mark_completed("task-002")
        b3 = s.next_batch()
        assert set(b3) == {"task-003", "task-004"}
        s.mark_completed("task-003")
        s.mark_completed("task-004")
        b4 = s.next_batch()
        assert set(b4) == {"task-005", "task-006"}

    def test_three_agents_partial_refill(self):
        dag = build_dag([
            _t("task-001"),
            _t("task-002", deps=["task-001"]),
            _t("task-003", deps=["task-001"]),
            _t("task-004", deps=["task-001"]),
            _t("task-005", deps=["task-001"]),
        ])
        s = ParallelScheduler(dag, max_concurrent=3)
        b1 = s.next_batch()
        assert b1 == ["task-001"]
        s.mark_completed("task-001")
        b2 = s.next_batch()
        assert len(b2) == 3


class TestDependencyBlocking:
    """依赖阻塞场景"""

    def test_entire_pipeline_blocked_by_one(self):
        dag = build_dag([
            _t("task-001"),
            _t("task-002", deps=["task-001"]),
            _t("task-003", deps=["task-002"]),
            _t("task-004", deps=["task-003"]),
        ])
        s = ParallelScheduler(dag, max_concurrent=3)
        b1 = s.next_batch()
        assert b1 == ["task-001"]
        b2 = s.next_batch()
        assert b2 == ["task-001"]

    def test_branch_blocked_other_continues(self):
        dag = build_dag([
            _t("task-001"), _t("task-002"),
            _t("task-003", deps=["task-001"]),
            _t("task-004", deps=["task-002"]),
        ])
        s = ParallelScheduler(dag, max_concurrent=3)
        b1 = s.next_batch()
        assert set(b1) == {"task-001", "task-002"}
        s.mark_completed("task-001")
        b2 = s.next_batch()
        assert set(b2) == {"task-002", "task-003"}

    def test_fork_join_all_blocked_until_root_done(self):
        dag = build_dag([
            _t("task-001"),
            _t("task-002", deps=["task-001"]),
            _t("task-003", deps=["task-001"]),
            _t("task-004", deps=["task-001"]),
        ])
        s = ParallelScheduler(dag, max_concurrent=5)
        b1 = s.next_batch()
        assert b1 == ["task-001"]
        b2 = s.next_batch()
        assert b2 == ["task-001"]


class TestMaxConcurrentBoundary:
    """max_concurrent 边界"""

    def test_max_one_degraded_to_sequential(self):
        dag = build_dag([_t("task-001"), _t("task-002"), _t("task-003")])
        s = ParallelScheduler(dag, max_concurrent=1)
        b1 = s.next_batch()
        assert len(b1) == 1
        s.mark_completed(b1[0])
        b2 = s.next_batch()
        assert len(b2) == 1

    def test_max_greater_than_total_returns_all(self):
        dag = build_dag([_t("task-001"), _t("task-002"), _t("task-003")])
        s = ParallelScheduler(dag, max_concurrent=100)
        b1 = s.next_batch()
        assert len(b1) == 3

    def test_max_equals_total_returns_all(self):
        dag = build_dag([_t("task-001"), _t("task-002")])
        s = ParallelScheduler(dag, max_concurrent=2)
        b1 = s.next_batch()
        assert len(b1) == 2


class TestRepeatedNextBatch:
    """重复调用 next_batch 幂等性"""

    def test_repeated_call_without_state_change_same_result(self):
        dag = build_dag([_t("task-001"), _t("task-002")])
        s = ParallelScheduler(dag, max_concurrent=2)
        b1 = s.next_batch()
        b2 = s.next_batch()
        assert set(b1) == set(b2)

    def test_repeated_call_after_completion_differs(self):
        dag = build_dag([
            _t("task-001"),
            _t("task-002", deps=["task-001"]),
        ])
        s = ParallelScheduler(dag)
        b1 = s.next_batch()
        s.mark_completed("task-001")
        b2 = s.next_batch()
        assert b1 != b2


class TestMarkCompletedEdgeCases:
    """mark_completed/mark_failed 边界"""

    def test_mark_completed_unknown_task_no_error(self):
        dag = build_dag([_t("task-001")])
        s = ParallelScheduler(dag)
        s.mark_completed("task-999")

    def test_double_mark_completed_idempotent(self):
        dag = build_dag([_t("task-001"), _t("task-002")])
        s = ParallelScheduler(dag)
        s.mark_completed("task-001")
        s.mark_completed("task-001")
        assert s.completed_count == 1

    def test_mark_failed_unknown_task_no_error(self):
        dag = build_dag([_t("task-001")])
        s = ParallelScheduler(dag)
        s.mark_failed("task-999")

    def test_mark_failed_and_completed_conflict(self):
        dag = build_dag([_t("task-001")])
        s = ParallelScheduler(dag)
        s.mark_failed("task-001")
        s.mark_completed("task-001")
        assert s.completed_count == 1

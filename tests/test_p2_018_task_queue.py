"""
P2-018 测试 — TaskQueue 任务队列管理

测试内容：
- enqueue/dequeue 基本入队出队
- FIFO 顺序
- 优先级排序（HIGH > MEDIUM > LOW）
- 依赖过滤（前置未完成不出队）
- peek 查看队首
- remove 移除指定任务
- size / is_empty
- clear 清空
- reprioritize 重新排序
- 空队列行为
"""

import pytest

from agent_automation_system.scheduler.task_queue import TaskQueue
from agent_automation_system.models.task import (
    Task,
    TaskPriority,
    TaskStatus,
    BDDSpec,
)


def _t(task_id, priority=TaskPriority.MEDIUM, deps=None, status=TaskStatus.PENDING):
    return Task(
        id=task_id, title=task_id, description=task_id,
        dependencies=deps or [], priority=priority, status=status,
    )


class TestTaskQueueEnqueueDequeue:
    """基本入队出队"""

    def test_enqueue_and_dequeue_single(self):
        q = TaskQueue()
        t = _t("task-001")
        q.enqueue(t)
        assert q.dequeue() is t
        assert q.is_empty

    def test_fifo_order(self):
        q = TaskQueue()
        a = _t("task-001")
        b = _t("task-002")
        c = _t("task-003")
        q.enqueue(a)
        q.enqueue(b)
        q.enqueue(c)
        assert q.dequeue() is a
        assert q.dequeue() is b
        assert q.dequeue() is c

    def test_dequeue_empty_returns_none(self):
        q = TaskQueue()
        assert q.dequeue() is None

    def test_enqueue_none_raises(self):
        q = TaskQueue()
        with pytest.raises(ValueError, match="task"):
            q.enqueue(None)

    def test_enqueue_duplicate_id_raises(self):
        q = TaskQueue()
        q.enqueue(_t("task-001"))
        with pytest.raises(ValueError, match="already"):
            q.enqueue(_t("task-001"))


class TestTaskQueuePriority:
    """优先级排序"""

    def test_high_before_medium(self):
        q = TaskQueue()
        m = _t("task-001", TaskPriority.MEDIUM)
        h = _t("task-002", TaskPriority.HIGH)
        q.enqueue(m)
        q.enqueue(h)
        assert q.dequeue() is h
        assert q.dequeue() is m

    def test_high_before_low(self):
        q = TaskQueue()
        l = _t("task-001", TaskPriority.LOW)
        h = _t("task-002", TaskPriority.HIGH)
        q.enqueue(l)
        q.enqueue(h)
        assert q.dequeue() is h
        assert q.dequeue() is l

    def test_medium_before_low(self):
        q = TaskQueue()
        l = _t("task-001", TaskPriority.LOW)
        m = _t("task-002", TaskPriority.MEDIUM)
        q.enqueue(l)
        q.enqueue(m)
        assert q.dequeue() is m
        assert q.dequeue() is l

    def test_fifo_within_same_priority(self):
        q = TaskQueue()
        a = _t("task-001", TaskPriority.HIGH)
        b = _t("task-002", TaskPriority.HIGH)
        c = _t("task-003", TaskPriority.HIGH)
        q.enqueue(a)
        q.enqueue(b)
        q.enqueue(c)
        assert q.dequeue() is a
        assert q.dequeue() is b
        assert q.dequeue() is c

    def test_complex_priority_mix(self):
        q = TaskQueue()
        a = _t("task-001", TaskPriority.LOW)
        b = _t("task-002", TaskPriority.MEDIUM)
        c = _t("task-003", TaskPriority.HIGH)
        d = _t("task-004", TaskPriority.LOW)
        e = _t("task-005", TaskPriority.HIGH)
        q.enqueue(a)
        q.enqueue(b)
        q.enqueue(c)
        q.enqueue(d)
        q.enqueue(e)
        assert q.dequeue() is c
        assert q.dequeue() is e
        assert q.dequeue() is b
        assert q.dequeue() is a
        assert q.dequeue() is d


class TestTaskQueueDependencyFilter:
    """依赖过滤"""

    def test_unmet_dependency_not_dequeued(self):
        q = TaskQueue()
        a = _t("task-001", deps=["task-000"])
        b = _t("task-002")
        q.enqueue(a)
        q.enqueue(b)
        completed = {"task-002"}
        assert q.dequeue(completed) is b
        assert q.dequeue(completed) is None

    def test_met_dependency_dequeued(self):
        q = TaskQueue()
        a = _t("task-001", deps=["task-000"])
        q.enqueue(a)
        completed = {"task-000"}
        assert q.dequeue(completed) is a

    def test_partial_deps_not_dequeued(self):
        q = TaskQueue()
        a = _t("task-001", deps=["task-000", "task-099"])
        q.enqueue(a)
        completed = {"task-000"}
        assert q.dequeue(completed) is None

    def test_all_deps_met_then_dequeued(self):
        q = TaskQueue()
        a = _t("task-001", deps=["task-000", "task-099"])
        q.enqueue(a)
        completed = {"task-000", "task-099"}
        assert q.dequeue(completed) is a

    def test_no_deps_always_dequeued(self):
        q = TaskQueue()
        a = _t("task-001")
        q.enqueue(a)
        assert q.dequeue(set()) is a

    def test_dependency_filter_skips_blocked_for_next_ready(self):
        q = TaskQueue()
        a = _t("task-001", deps=["task-000"])
        b = _t("task-002")
        q.enqueue(a)
        q.enqueue(b)
        completed = set()
        assert q.dequeue(completed) is b


class TestTaskQueuePeek:
    """peek 查看队首"""

    def test_peek_returns_first_without_removing(self):
        q = TaskQueue()
        t = _t("task-001")
        q.enqueue(t)
        assert q.peek() is t
        assert q.size == 1

    def test_peek_empty_returns_none(self):
        q = TaskQueue()
        assert q.peek() is None

    def test_peek_respects_priority(self):
        q = TaskQueue()
        q.enqueue(_t("task-001", TaskPriority.LOW))
        q.enqueue(_t("task-002", TaskPriority.HIGH))
        assert q.peek().id == "task-002"

    def test_peek_respects_dependency_filter(self):
        q = TaskQueue()
        q.enqueue(_t("task-001", deps=["task-000"]))
        q.enqueue(_t("task-002"))
        assert q.peek({"task-000"}).id == "task-001"


class TestTaskQueueRemove:
    """remove 移除任务"""

    def test_remove_by_id(self):
        q = TaskQueue()
        q.enqueue(_t("task-001"))
        q.enqueue(_t("task-002"))
        assert q.remove("task-001") is True
        assert q.size == 1
        assert q.dequeue().id == "task-002"

    def test_remove_nonexistent(self):
        q = TaskQueue()
        assert q.remove("task-999") is False

    def test_remove_then_enqueue_same_id(self):
        q = TaskQueue()
        q.enqueue(_t("task-001"))
        q.remove("task-001")
        q.enqueue(_t("task-001"))


class TestTaskQueueSizeAndClear:
    """size / is_empty / clear"""

    def test_size(self):
        q = TaskQueue()
        assert q.size == 0
        q.enqueue(_t("task-001"))
        assert q.size == 1
        q.enqueue(_t("task-002"))
        assert q.size == 2
        q.dequeue()
        assert q.size == 1

    def test_is_empty(self):
        q = TaskQueue()
        assert q.is_empty is True
        q.enqueue(_t("task-001"))
        assert q.is_empty is False
        q.dequeue()
        assert q.is_empty is True

    def test_clear(self):
        q = TaskQueue()
        q.enqueue(_t("task-001"))
        q.enqueue(_t("task-002"))
        q.clear()
        assert q.is_empty
        assert q.size == 0

    def test_contains(self):
        q = TaskQueue()
        q.enqueue(_t("task-001"))
        assert q.contains("task-001") is True
        assert q.contains("task-999") is False


class TestTaskQueueReprioritize:
    """reprioritize 动态改优先级"""

    def test_reprioritize_changes_order(self):
        q = TaskQueue()
        q.enqueue(_t("task-001", TaskPriority.LOW))
        q.enqueue(_t("task-002", TaskPriority.HIGH))
        q.reprioritize("task-002", TaskPriority.LOW)
        assert q.dequeue().id == "task-001"
        assert q.dequeue().id == "task-002"

    def test_reprioritize_nonexistent_no_error(self):
        q = TaskQueue()
        q.reprioritize("task-999", TaskPriority.HIGH)

    def test_reprioritize_same_priority(self):
        q = TaskQueue()
        q.enqueue(_t("task-001", TaskPriority.HIGH))
        q.reprioritize("task-001", TaskPriority.HIGH)
        assert q.dequeue().id == "task-001"

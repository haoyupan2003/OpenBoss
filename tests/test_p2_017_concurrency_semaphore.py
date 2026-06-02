"""
P2-017 测试 — ConcurrencySemaphore 并发控制

测试内容：
- acquire/release 基本流程
- max_count 限制
- available 槽位计数
- try_acquire 非阻塞获取
- 上下文管理器（with 语句）
- 超量 acquire 拒绝
- release 过多处理
- active_count 正确性
- reset 重置
"""

import pytest

from agent_automation_system.scheduler.concurrency import (
    ConcurrencySemaphore,
)


class TestConcurrencySemaphoreBasic:
    """基本 acquire/release 流程"""

    def test_acquire_reduces_available(self):
        """acquire 减少可用槽位"""
        sem = ConcurrencySemaphore(max_count=5)
        assert sem.available == 5
        sem.acquire()
        assert sem.available == 4

    def test_release_increases_available(self):
        """release 增加可用槽位"""
        sem = ConcurrencySemaphore(max_count=5)
        sem.acquire()
        sem.release()
        assert sem.available == 5

    def test_multiple_acquire_release(self):
        """多次 acquire/release 正确追踪"""
        sem = ConcurrencySemaphore(max_count=5)
        sem.acquire()
        sem.acquire()
        sem.acquire()
        assert sem.available == 2
        sem.release()
        assert sem.available == 3
        sem.release()
        sem.release()
        assert sem.available == 5

    def test_acquire_all_then_release_all(self):
        """全部获取后全部释放"""
        sem = ConcurrencySemaphore(max_count=3)
        sem.acquire()
        sem.acquire()
        sem.acquire()
        assert sem.available == 0
        sem.release()
        sem.release()
        sem.release()
        assert sem.available == 3


class TestConcurrencySemaphoreMaxCount:
    """max_count 限制"""

    def test_default_max_count_is_three(self):
        """默认 max_count=3"""
        sem = ConcurrencySemaphore()
        assert sem.max_count == 3

    def test_custom_max_count(self):
        """自定义 max_count"""
        sem = ConcurrencySemaphore(max_count=10)
        assert sem.max_count == 10
        assert sem.available == 10

    def test_max_count_zero_raises(self):
        """max_count=0 抛 ValueError"""
        with pytest.raises(ValueError, match="positive"):
            ConcurrencySemaphore(max_count=0)

    def test_max_count_negative_raises(self):
        """负 max_count 抛 ValueError"""
        with pytest.raises(ValueError, match="positive"):
            ConcurrencySemaphore(max_count=-1)


class TestConcurrencySemaphoreTryAcquire:
    """try_acquire 非阻塞获取"""

    def test_try_acquire_returns_true_when_available(self):
        """有槽位时返回 True"""
        sem = ConcurrencySemaphore(max_count=1)
        assert sem.try_acquire() is True
        assert sem.available == 0

    def test_try_acquire_returns_false_when_full(self):
        """槽位满时返回 False"""
        sem = ConcurrencySemaphore(max_count=1)
        sem.acquire()
        assert sem.try_acquire() is False
        assert sem.available == 0

    def test_try_acquire_after_release(self):
        """释放后 try_acquire 成功"""
        sem = ConcurrencySemaphore(max_count=1)
        sem.acquire()
        sem.release()
        assert sem.try_acquire() is True


class TestConcurrencySemaphoreContextManager:
    """with 语句上下文管理器"""

    def test_context_manager_acquires_and_releases(self):
        """with 块内 acquire，退出后 release"""
        sem = ConcurrencySemaphore(max_count=3)
        with sem:
            assert sem.available == 2
        assert sem.available == 3

    def test_nested_context_managers(self):
        """嵌套 with 块各自管理槽位"""
        sem = ConcurrencySemaphore(max_count=3)
        with sem:
            assert sem.available == 2
            with sem:
                assert sem.available == 1
            assert sem.available == 2
        assert sem.available == 3

    def test_context_manager_exception_safety(self):
        """with 块内抛异常仍 release"""
        sem = ConcurrencySemaphore(max_count=3)
        try:
            with sem:
                assert sem.available == 2
                raise RuntimeError("boom")
        except RuntimeError:
            pass
        assert sem.available == 3


class TestConcurrencySemaphoreEdgeCases:
    """边界条件"""

    def test_acquire_when_full_raises(self):
        """槽位满时 acquire 阻塞/抛异常"""
        sem = ConcurrencySemaphore(max_count=2)
        sem.acquire()
        sem.acquire()
        with pytest.raises(RuntimeError, match="No available slots"):
            sem.acquire()

    def test_release_when_idle_no_error(self):
        """全部已释放时再次 release 不抛异常"""
        sem = ConcurrencySemaphore(max_count=3)
        sem.release()
        assert sem.available == 3


class TestConcurrencySemaphoreProperties:
    """属性计算正确性"""

    def test_active_count(self):
        """active_count = max_count - available"""
        sem = ConcurrencySemaphore(max_count=5)
        assert sem.active_count == 0
        sem.acquire()
        sem.acquire()
        assert sem.active_count == 2
        sem.release()
        assert sem.active_count == 1

    def test_is_full_and_is_empty(self):
        """is_full / is_empty 判断"""
        sem = ConcurrencySemaphore(max_count=2)
        assert sem.is_empty is True
        assert sem.is_full is False

        sem.acquire()
        assert sem.is_empty is False

        sem.acquire()
        assert sem.is_full is True
        assert sem.is_empty is False

    def test_available_never_negative(self):
        """available 不会变为负数"""
        sem = ConcurrencySemaphore(max_count=2)
        sem.acquire()
        sem.acquire()
        assert sem.available == 0
        sem.release()
        sem.release()
        sem.release()
        assert sem.available == 2


class TestConcurrencySemaphoreReset:
    """reset 重置"""

    def test_reset_restores_full_available(self):
        """reset 恢复满槽位"""
        sem = ConcurrencySemaphore(max_count=5)
        sem.acquire()
        sem.acquire()
        sem.acquire()
        sem.reset()
        assert sem.available == 5
        assert sem.active_count == 0

    def test_reset_then_acquire_works(self):
        """reset 后 acquire 正常"""
        sem = ConcurrencySemaphore(max_count=3)
        sem.acquire()
        sem.acquire()
        sem.acquire()
        sem.reset()
        sem.acquire()
        assert sem.available == 2


class TestConcurrencySemaphoreIntegration:
    """与 ParallelScheduler 协作模拟"""

    def test_semaphore_limits_concurrent_dispatches(self):
        """Semaphore 限制并发分发数量"""
        from agent_automation_system.scheduler.parallel_scheduler import ParallelScheduler
        from agent_automation_system.scheduler.dag import build_dag
        from agent_automation_system.models.task import Task, TaskPriority, TaskStatus

        def t(tid):
            return Task(
                id=tid, title=tid, description=tid,
                dependencies=[], priority=TaskPriority.MEDIUM,
                status=TaskStatus.PENDING,
            )

        dag = build_dag([t("task-001"), t("task-002"), t("task-003"), t("task-004")])
        sched = ParallelScheduler(dag, max_concurrent=10)
        sem = ConcurrencySemaphore(max_count=2)

        dispatched = []
        while sched.has_more():
            batch = sched.next_batch()
            for tid in batch:
                if sem.try_acquire():
                    dispatched.append(tid)
                    sched.mark_completed(tid)
                    sem.release()

        assert len(dispatched) == 4

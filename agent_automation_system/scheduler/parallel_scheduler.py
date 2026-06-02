"""
ParallelScheduler — 并行任务调度器

基于 TaskDAG 的并行批次调度器，在满足依赖约束的前提下最大化并行度。
MasterAgent 在 DISPATCHING 阶段调用，获取每轮可并行执行的任务批次。

核心算法：
    1. 扫描所有任务，找出依赖已全部满足的"就绪"任务
    2. 按优先级排序（HIGH > MEDIUM > LOW）
    3. 取前 max_concurrent 个作为当前批次
    4. 任务完成后，重新扫描就绪任务填充空余槽位

使用场景：
    - 获取初始批次 → next_batch()
    - 执行批次中的任务（并发）
    - 标记完成 → mark_completed(task_id)
    - 获取下一批次 → next_batch()
    - 重复直到 has_more() == False
"""

import logging
from collections import deque
from typing import Optional

from agent_automation_system.scheduler.dag import TaskDAG
from agent_automation_system.models.task import TaskPriority

logger = logging.getLogger(__name__)


# 优先级权重（越小优先级越高）
_PRIORITY_ORDER: dict[TaskPriority, int] = {
    TaskPriority.HIGH: 0,
    TaskPriority.MEDIUM: 1,
    TaskPriority.LOW: 2,
}


class ParallelScheduler:
    """并行任务调度器

    基于 TaskDAG 的依赖分析和优先级排序，将任务划分为
    可并行执行的批次，保证依赖约束不违反。

    Attributes:
        dag: 任务依赖图
        max_concurrent: 最大并发 Agent 数
        completed_count: 已完成（含失败）的任务数
        remaining_count: 剩余未完成的任务数
        total_tasks: DAG 中的任务总数
    """

    def __init__(
        self,
        dag: TaskDAG,
        max_concurrent: int = 3,
    ) -> None:
        """初始化并行调度器

        Args:
            dag: 任务 DAG
            max_concurrent: 最大并发任务数（必须 >= 1）

        Raises:
            ValueError: max_concurrent 非正数
        """
        if max_concurrent <= 0:
            raise ValueError(
                "max_concurrent must be positive, "
                f"got {max_concurrent}"
            )

        self._dag = dag
        self._max_concurrent = max_concurrent

        # 已完成（含失败）的任务集合
        self._completed: set[str] = set()

        # 失败任务集合（不释放后继依赖）
        self._failed: set[str] = set()

        # 每批次已完成计数（用于判断新批次需要多少次 mark_completed）
        self._batch_completed_since_last: int = 0

    # ── 属性 ──────────────────────────────────────────────

    @property
    def dag(self) -> TaskDAG:
        """任务依赖图"""
        return self._dag

    @property
    def max_concurrent(self) -> int:
        """最大并发数"""
        return self._max_concurrent

    @property
    def completed_count(self) -> int:
        """已完成（含失败）的任务数"""
        return len(self._completed)

    @property
    def remaining_count(self) -> int:
        """剩余未完成的任务数"""
        return self._dag.task_count - len(self._completed)

    @property
    def total_tasks(self) -> int:
        """DAG 中的任务总数"""
        return self._dag.task_count

    # ── 核心方法 ──────────────────────────────────────────

    def next_batch(self) -> list[str]:
        """获取下一批可并行执行的任务 ID 列表

        算法：
        1. 找出所有依赖已满足的"就绪"任务
        2. 已完成的排除
        3. 按优先级排序
        4. 取前 max_concurrent 个

        Returns:
            任务 ID 列表（可能为空）
        """
        # 1. 找出就绪任务
        ready = self.get_ready_tasks()

        # 2. 排除已完成
        pending_ready = [tid for tid in ready if tid not in self._completed]

        if not pending_ready:
            return []

        # 3. 按优先级排序
        sorted_ready = self._sort_by_priority(pending_ready)

        # 4. 截取 max_concurrent
        batch = sorted_ready[:self._max_concurrent]

        logger.debug(
            "ParallelScheduler next_batch: %d tasks (ready=%d, max=%d)",
            len(batch),
            len(pending_ready),
            self._max_concurrent,
        )

        return batch

    def get_ready_tasks(self) -> list[str]:
        """获取依赖已全部满足的就绪任务

        判断标准：
        - 根任务（入度为 0）始终就绪
        - 非根任务：所有前置依赖都在 _completed 中 且 不在 _failed 中
        - 若任一前置依赖失败（在 _failed 中），则永远不就绪

        Returns:
            就绪任务 ID 列表
        """
        ready: list[str] = []
        in_degree = self._dag.in_degree

        for task_id in self._dag.tasks:
            if task_id in self._completed:
                continue

            # 检查依赖是否已满足
            deps = self._dag.get_dependencies(task_id)

            # 若任一依赖失败，该任务阻塞
            if any(dep in self._failed for dep in deps):
                continue

            # 若所有依赖已完成，该任务就绪
            deps_completed = all(dep in self._completed for dep in deps)
            if deps_completed:
                ready.append(task_id)

        return ready

    def mark_completed(self, task_id: str) -> None:
        """标记任务为已完成

        完成后可能释放新的就绪任务（其依赖已全部满足的后继节点）。

        Args:
            task_id: 已完成的任务 ID
        """
        if task_id not in self._dag.tasks:
            logger.warning(
                "Task '%s' not in DAG, ignoring mark_completed", task_id
            )
            return

        if task_id in self._completed:
            logger.debug("Task '%s' already completed, skipping", task_id)
            return

        self._completed.add(task_id)
        logger.debug(
            "ParallelScheduler: task '%s' completed (%d/%d done)",
            task_id,
            self.completed_count,
            self.total_tasks,
        )

    def mark_failed(self, task_id: str) -> None:
        """标记任务为失败

        失败任务视为已完成（不再调度），但其后继依赖不会被释放。
        这阻止了依赖链上后续任务的执行。

        Args:
            task_id: 失败的任务 ID
        """
        if task_id not in self._dag.tasks:
            logger.warning(
                "Task '%s' not in DAG, ignoring mark_failed", task_id
            )
            return

        self._failed.add(task_id)
        self._completed.add(task_id)
        logger.debug(
            "ParallelScheduler: task '%s' failed (%d/%d done, "
            "%d in chain blocked)",
            task_id,
            self.completed_count,
            self.total_tasks,
            self._count_blocked_by_failed(),
        )

    def has_more(self) -> bool:
        """是否还有未完成的任务

        Returns:
            True 表示还有任务可调度
        """
        return self.completed_count < self.total_tasks

    def reset(self) -> None:
        """重置调度器状态

        清除所有完成和失败记录，恢复到初始状态。
        """
        self._completed.clear()
        self._failed.clear()
        logger.debug("ParallelScheduler reset")

    # ── 辅助方法 ──────────────────────────────────────────

    def _sort_by_priority(self, task_ids: list[str]) -> list[str]:
        """按优先级排序任务 ID（HIGH > MEDIUM > LOW）

        同优先级按 ID 排序以确保确定性。

        Args:
            task_ids: 待排序的任务 ID 列表

        Returns:
            排序后的任务 ID 列表
        """
        return sorted(
            task_ids,
            key=lambda tid: (
                _PRIORITY_ORDER.get(
                    self._dag.get_task(tid).priority
                    if self._dag.get_task(tid)
                    else TaskPriority.MEDIUM,
                    1,
                ),
                tid,  # 同优先级按 ID 排序（确定性的）
            ),
        )

    def _count_blocked_by_failed(self) -> int:
        """统计被失败任务阻塞的任务数"""
        count = 0
        for task_id in self._dag.tasks:
            if task_id in self._completed:
                continue
            deps = self._dag.get_dependencies(task_id)
            if any(dep in self._failed for dep in deps):
                # 检查所有非失败依赖是否完成
                remaining_deps = [
                    dep for dep in deps
                    if dep not in self._failed
                ]
                if all(dep in self._completed for dep in remaining_deps):
                    count += 1
        return count

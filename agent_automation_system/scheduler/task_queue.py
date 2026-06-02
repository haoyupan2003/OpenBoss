"""
TaskQueue — 任务队列管理

FIFO + 优先级排序 + 依赖过滤的任务队列。
MasterAgent 在 DISPATCHING 阶段使用，按优先级和依赖约束出队任务。

特性：
- 入队时按优先级 + FIFO 排序
- 出队时支持依赖过滤（前置未完成的任务被跳过）
- O(1) peek，O(n) dequeue/remove
"""

import logging
from collections import deque
from typing import Optional

from agent_automation_system.models.task import Task, TaskPriority

logger = logging.getLogger(__name__)

_PRIORITY_ORDER = {TaskPriority.HIGH: 0, TaskPriority.MEDIUM: 1, TaskPriority.LOW: 2}


class TaskQueue:
    """任务优先队列

    内部维护按优先级排序的双端队列。同优先级按入队顺序（FIFO）。
    """

    def __init__(self) -> None:
        self._tasks: deque[Task] = deque()
        self._ids: set[str] = set()

    @property
    def size(self) -> int:
        return len(self._tasks)

    @property
    def is_empty(self) -> bool:
        return len(self._tasks) == 0

    def contains(self, task_id: str) -> bool:
        return task_id in self._ids

    def enqueue(self, task: Task) -> None:
        if task is None:
            raise ValueError("task cannot be None")
        if task.id in self._ids:
            raise ValueError(f"Task '{task.id}' already in queue")
        self._insert_sorted(task)
        self._ids.add(task.id)

    def dequeue(self, completed_ids: Optional[set[str]] = None) -> Optional[Task]:
        if completed_ids is None:
            completed_ids = set()
        for i in range(len(self._tasks)):
            t = self._tasks[i]
            if all(dep in completed_ids for dep in t.dependencies):
                del self._tasks[i]
                self._ids.discard(t.id)
                return t
        return None

    def peek(self, completed_ids: Optional[set[str]] = None) -> Optional[Task]:
        if completed_ids is None:
            completed_ids = set()
        for t in self._tasks:
            if all(dep in completed_ids for dep in t.dependencies):
                return t
        return None

    def remove(self, task_id: str) -> bool:
        for i, t in enumerate(self._tasks):
            if t.id == task_id:
                del self._tasks[i]
                self._ids.discard(task_id)
                return True
        return False

    def reprioritize(self, task_id: str, new_priority: TaskPriority) -> None:
        for i, t in enumerate(self._tasks):
            if t.id == task_id:
                task = self._tasks[i]
                del self._tasks[i]
                self._ids.discard(task_id)
                task.priority = new_priority
                self._insert_sorted(task)
                self._ids.add(task_id)
                return

    def clear(self) -> None:
        self._tasks.clear()
        self._ids.clear()

    def _insert_sorted(self, task: Task) -> None:
        p = _PRIORITY_ORDER.get(task.priority, 1)
        for i, t in enumerate(self._tasks):
            tp = _PRIORITY_ORDER.get(t.priority, 1)
            if p < tp:
                self._tasks.insert(i, task)
                return
        self._tasks.append(task)

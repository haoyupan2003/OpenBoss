"""
ExecutionMonitor — Sub-Agent 并行执行监控

追踪多个 Sub-Agent 的并行执行状态，提供实时查询和汇总。
MasterAgent 在 MONITORING 阶段使用，检测超时、汇总进度。

使用方式：
    monitor = ExecutionMonitor()
    monitor.register("task-001", "senior-developer", "agent_dev_001")
    monitor.update_status("task-001", AgentRunStatus.RUNNING)
    ...
    monitor.update_status("task-001", AgentRunStatus.COMPLETED)
    print(monitor.active_count, monitor.completed_count)
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class AgentRunStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    TIMEOUT = "timeout"


@dataclass
class AgentRunInfo:
    task_id: str
    role: str
    window: str = ""
    status: AgentRunStatus = AgentRunStatus.CREATED
    start_time: float = field(default_factory=time.time)
    end_time: Optional[float] = None

    @property
    def elapsed_seconds(self) -> float:
        if self.end_time is not None:
            return self.end_time - self.start_time
        return time.time() - self.start_time


class ExecutionMonitor:
    def __init__(self) -> None:
        self._agents: dict[str, AgentRunInfo] = {}

    def register(self, task_id: str, role: str, window: str = "") -> None:
        self._agents[task_id] = AgentRunInfo(
            task_id=task_id, role=role, window=window
        )

    def update_status(self, task_id: str, status: AgentRunStatus) -> None:
        info = self._agents.get(task_id)
        if info is None:
            return
        info.status = status
        if status in (AgentRunStatus.COMPLETED, AgentRunStatus.FAILED,
                       AgentRunStatus.TIMEOUT):
            if info.end_time is None:
                info.end_time = time.time()

    def get_status(self, task_id: str) -> Optional[AgentRunInfo]:
        return self._agents.get(task_id)

    def get_all_statuses(self) -> dict[str, AgentRunInfo]:
        return dict(self._agents)

    def deregister(self, task_id: str) -> None:
        self._agents.pop(task_id, None)

    def chec_timeout(self, timeout_seconds: float) -> list[str]:
        now = time.time()
        overdue = []
        for task_id, info in self._agents.items():
            if info.status != AgentRunStatus.RUNNING:
                continue
            if info.end_time is None and (now - info.start_time) > timeout_seconds:
                overdue.append(task_id)
        return overdue

    def get_by_role(self, role: str) -> list[AgentRunInfo]:
        return [info for info in self._agents.values() if info.role == role]

    def get_active(self) -> list[AgentRunInfo]:
        return [info for info in self._agents.values()
                if info.status == AgentRunStatus.RUNNING]

    @property
    def active_count(self) -> int:
        return sum(1 for a in self._agents.values()
                   if a.status == AgentRunStatus.RUNNING)

    @property
    def completed_count(self) -> int:
        return sum(1 for a in self._agents.values()
                   if a.status == AgentRunStatus.COMPLETED)

    @property
    def failed_count(self) -> int:
        return sum(1 for a in self._agents.values()
                   if a.status in (AgentRunStatus.FAILED, AgentRunStatus.TIMEOUT))

    @property
    def total_count(self) -> int:
        return len(self._agents)

"""
RiskSorter — 高风险任务排序

根据任务标题和描述中的关键词自动识别风险等级，
将高风险任务（数据库迁移/架构变更等）延后执行。

风险等级：
- CRITICAL: data loss
- HIGH: migration, schema, database, index, alter, architecture
- MEDIUM: refactor, auth, security, api change
- LOW: 其他

排序规则：
- sort_by_risk: 低风险→中风险→高风险→极高风险，同风险保持相对顺序
- sort_by_risk_then_priority: 风险优先，同风险内按优先级 (HIGH>MEDIUM>LOW)
"""

import logging
from enum import IntEnum

from agent_automation_system.models.task import Task, TaskPriority

logger = logging.getLogger(__name__)

_PRIORITY_ORDER = {TaskPriority.HIGH: 0, TaskPriority.MEDIUM: 1, TaskPriority.LOW: 2}


class TaskRiskLevel(IntEnum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


DEFAULT_CRITICAL_KEYWORDS = {"data loss", "dataloss", "data-loss"}
DEFAULT_HIGH_KEYWORDS = {"migration", "schema", "database", "index", "alter", "architecture"}
DEFAULT_MEDIUM_KEYWORDS = {"refactor", "auth", "security", "api change"}


class RiskSorter:
    def __init__(
        self,
        critical_keywords: set[str] | None = None,
        high_keywords: set[str] | None = None,
        medium_keywords: set[str] | None = None,
    ) -> None:
        self._critical = (critical_keywords or set()) | DEFAULT_CRITICAL_KEYWORDS
        self._high = (high_keywords or set()) | DEFAULT_HIGH_KEYWORDS
        self._medium = (medium_keywords or set()) | DEFAULT_MEDIUM_KEYWORDS

    def classify_risk(self, task: Task) -> TaskRiskLevel:
        text = (task.title + " " + task.description).lower()
        for kw in self._critical:
            if kw in text:
                return TaskRiskLevel.CRITICAL
        for kw in self._high:
            if kw in text:
                return TaskRiskLevel.HIGH
        for kw in self._medium:
            if kw in text:
                return TaskRiskLevel.MEDIUM
        return TaskRiskLevel.LOW

    def sort_by_risk(self, tasks: list[Task]) -> list[Task]:
        return sorted(tasks, key=lambda t: self.classify_risk(t))

    def sort_by_risk_then_priority(self, tasks: list[Task]) -> list[Task]:
        return sorted(
            tasks,
            key=lambda t: (
                self.classify_risk(t),
                _PRIORITY_ORDER.get(t.priority, 1),
            ),
        )

    def get_high_risk_tasks(self, tasks: list[Task]) -> list[Task]:
        return [t for t in tasks
                if self.classify_risk(t) in (TaskRiskLevel.HIGH, TaskRiskLevel.CRITICAL)]

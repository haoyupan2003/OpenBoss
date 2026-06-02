"""
P2-020 测试 — RiskSorter 高风险任务排序

测试内容：
- classify_risk 根据标题/描述关键词分配风险等级
- sort_by_risk 将高风险排到末尾
- sort_by_risk_then_priority 风险优先 + 同风险内按优先级
- get_high_risk_tasks 过滤高风险任务
- 空列表 / 单任务边界
- 自定关键词
"""

import pytest

from agent_automation_system.scheduler.risk_sorter import (
    RiskSorter,
    TaskRiskLevel,
)
from agent_automation_system.models.task import Task, TaskPriority, TaskStatus


def _t(task_id, title="", description="", priority=TaskPriority.MEDIUM):
    return Task(
        id=task_id, title=title or task_id, description=description or task_id,
        dependencies=[], priority=priority, status=TaskStatus.PENDING,
    )


class TestRiskSorterClassifyRisk:
    """classify_risk 风险等级分类"""

    def test_migration_keyword_returns_high(self):
        s = RiskSorter()
        t = _t("task-001", title="Database migration v2")
        assert s.classify_risk(t) == TaskRiskLevel.HIGH

    def test_schema_keyword_returns_high(self):
        s = RiskSorter()
        t = _t("task-001", description="Update database schema")
        assert s.classify_risk(t) == TaskRiskLevel.HIGH

    def test_architecture_keyword_returns_high(self):
        s = RiskSorter()
        t = _t("task-001", title="Architecture refactor for auth")
        assert s.classify_risk(t) == TaskRiskLevel.HIGH

    def test_index_keyword_returns_high(self):
        s = RiskSorter()
        t = _t("task-001", title="Add index to users table")
        assert s.classify_risk(t) == TaskRiskLevel.HIGH

    def test_alter_keyword_returns_high(self):
        s = RiskSorter()
        t = _t("task-001", description="Alter table structure")
        assert s.classify_risk(t) == TaskRiskLevel.HIGH

    def test_data_loss_keyword_returns_critical(self):
        s = RiskSorter()
        t = _t("task-001", title="Data loss prevention", description="data loss")
        assert s.classify_risk(t) == TaskRiskLevel.CRITICAL

    def test_refactor_keyword_returns_medium(self):
        s = RiskSorter()
        t = _t("task-001", title="Refactor user service")
        assert s.classify_risk(t) == TaskRiskLevel.MEDIUM

    def test_auth_keyword_returns_medium(self):
        s = RiskSorter()
        t = _t("task-001", description="Update auth middleware")
        assert s.classify_risk(t) == TaskRiskLevel.MEDIUM

    def test_normal_task_returns_low(self):
        s = RiskSorter()
        t = _t("task-001", title="Add user avatar endpoint")
        assert s.classify_risk(t) == TaskRiskLevel.LOW

    def test_empty_title_and_description_returns_low(self):
        s = RiskSorter()
        t = _t("task-001", title="", description="")
        assert s.classify_risk(t) == TaskRiskLevel.LOW


class TestRiskSorterSortByRisk:
    """sort_by_risk 按风险重排"""

    def test_high_risk_pushed_to_end(self):
        s = RiskSorter()
        tasks = [
            _t("task-001", "Normal task"),
            _t("task-002", "Database migration"),
            _t("task-003", "Another normal"),
        ]
        result = s.sort_by_risk(tasks)
        assert result[2].id == "task-002"

    def test_critical_before_high(self):
        s = RiskSorter()
        tasks = [
            _t("task-001", "data loss fix"),
            _t("task-002", "Database migration"),
            _t("task-003", "Normal task"),
        ]
        result = s.sort_by_risk(tasks)
        ids = [t.id for t in result]
        assert ids[0] == "task-003"
        assert ids[1] == "task-002"
        assert ids[2] == "task-001"

    def test_same_risk_preserves_relative_order(self):
        s = RiskSorter()
        tasks = [
            _t("task-001", "Normal A"),
            _t("task-003", "Normal C"),
            _t("task-002", "Normal B"),
        ]
        result = s.sort_by_risk(tasks)
        ids = [t.id for t in result]
        assert ids == ["task-001", "task-003", "task-002"]

    def test_single_task_unchanged(self):
        s = RiskSorter()
        tasks = [_t("task-001", "Database migration")]
        result = s.sort_by_risk(tasks)
        assert len(result) == 1
        assert result[0].id == "task-001"

    def test_empty_list(self):
        s = RiskSorter()
        assert s.sort_by_risk([]) == []

    def test_all_high_risk_preserves_input_order(self):
        s = RiskSorter()
        tasks = [
            _t("task-001", "migration A"),
            _t("task-002", "migration B"),
        ]
        result = s.sort_by_risk(tasks)
        assert result[0].id == "task-001"
        assert result[1].id == "task-002"


class TestRiskSorterSortByRiskThenPriority:
    """sort_by_risk_then_priority 风险+优先级双排序"""

    def test_risk_first_then_priority(self):
        s = RiskSorter()
        tasks = [
            _t("task-001", "Normal low", priority=TaskPriority.LOW),
            _t("task-002", "Normal high", priority=TaskPriority.HIGH),
        ]
        result = s.sort_by_risk_then_priority(tasks)
        ids = [t.id for t in result]
        assert ids == ["task-002", "task-001"]

    def test_high_risk_low_priority_still_behind_low_risk_high_priority(self):
        s = RiskSorter()
        tasks = [
            _t("task-001", "migration", priority=TaskPriority.HIGH),
            _t("task-002", "Normal", priority=TaskPriority.LOW),
        ]
        result = s.sort_by_risk_then_priority(tasks)
        ids = [t.id for t in result]
        assert ids == ["task-002", "task-001"]


class TestRiskSorterGetHighRisk:
    """get_high_risk_tasks 过滤"""

    def test_only_returns_high_or_critical(self):
        s = RiskSorter()
        tasks = [
            _t("task-001", "Normal"),
            _t("task-002", "migration"),
            _t("task-003", "data loss"),
            _t("task-004", "refactor"),
        ]
        result = s.get_high_risk_tasks(tasks)
        ids = {t.id for t in result}
        assert ids == {"task-002", "task-003"}

    def test_empty_when_no_high_risk(self):
        s = RiskSorter()
        tasks = [_t("task-001", "Normal"), _t("task-002", "Refactor")]
        result = s.get_high_risk_tasks(tasks)
        assert result == []


class TestRiskSorterCustomKeywords:
    """自定义关键词"""

    def test_custom_high_keywords(self):
        s = RiskSorter(high_keywords={"deploy", "release"})
        t = _t("task-001", title="Production deploy")
        assert s.classify_risk(t) == TaskRiskLevel.HIGH

    def test_custom_keywords_override_defaults(self):
        s = RiskSorter(high_keywords={"avatar"})
        t = _t("task-001", title="Add avatar upload")
        assert s.classify_risk(t) == TaskRiskLevel.HIGH

    def test_default_keywords_still_work_with_partial_override(self):
        s = RiskSorter(high_keywords={"deploy"})
        t = _t("task-001", title="Database migration")
        assert s.classify_risk(t) == TaskRiskLevel.HIGH

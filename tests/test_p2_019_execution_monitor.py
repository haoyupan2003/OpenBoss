"""
P2-019 测试 — ExecutionMonitor 并行执行监控

测试内容：
- register/update_status 注册与状态更新
- get_status 查询单个 Agent 状态
- get_all_statuses 汇总所有状态
- active_count / completed_count / failed_count
- 状态枚举（CREATED/RUNNING/COMPLETED/FAILED/TIMEOUT）
- start_time / end_time 时间记录
- deregister 注销
- 超时检测
- 未注册 agent 查询
"""

import time
import pytest

from agent_automation_system.scheduler.execution_monitor import (
    ExecutionMonitor,
    AgentRunStatus,
    AgentRunInfo,
)


class TestExecutionMonitorRegister:
    """注册 Agent 执行"""

    def test_register_creates_entry(self):
        m = ExecutionMonitor()
        m.register("task-001", "senior-developer", "agent_dev_001")
        info = m.get_status("task-001")
        assert info is not None
        assert info.task_id == "task-001"
        assert info.role == "senior-developer"
        assert info.window == "agent_dev_001"
        assert info.status == AgentRunStatus.CREATED

    def test_register_sets_start_time(self):
        m = ExecutionMonitor()
        before = time.time()
        m.register("task-001", "senior-developer")
        after = time.time()
        info = m.get_status("task-001")
        assert before <= info.start_time <= after

    def test_register_duplicate_overwrites(self):
        m = ExecutionMonitor()
        m.register("task-001", "dev")
        m.register("task-001", "qa")
        assert m.get_status("task-001").role == "qa"


class TestExecutionMonitorUpdate:
    """更新 Agent 状态"""

    def test_update_to_running(self):
        m = ExecutionMonitor()
        m.register("task-001", "dev")
        m.update_status("task-001", AgentRunStatus.RUNNING)
        assert m.get_status("task-001").status == AgentRunStatus.RUNNING

    def test_update_to_completed_sets_end_time(self):
        m = ExecutionMonitor()
        m.register("task-001", "dev")
        m.update_status("task-001", AgentRunStatus.COMPLETED)
        info = m.get_status("task-001")
        assert info.status == AgentRunStatus.COMPLETED
        assert info.end_time is not None

    def test_update_to_failed_sets_end_time(self):
        m = ExecutionMonitor()
        m.register("task-001", "dev")
        m.update_status("task-001", AgentRunStatus.FAILED)
        info = m.get_status("task-001")
        assert info.end_time is not None

    def test_update_to_timeout_sets_end_time(self):
        m = ExecutionMonitor()
        m.register("task-001", "dev")
        m.update_status("task-001", AgentRunStatus.TIMEOUT)
        info = m.get_status("task-001")
        assert info.end_time is not None

    def test_update_unknown_task_no_error(self):
        m = ExecutionMonitor()
        m.update_status("task-999", AgentRunStatus.RUNNING)


class TestExecutionMonitorQuery:
    """查询 Agent 状态"""

    def test_get_status_unknown_returns_none(self):
        m = ExecutionMonitor()
        assert m.get_status("task-999") is None

    def test_get_all_statuses_empty(self):
        m = ExecutionMonitor()
        assert m.get_all_statuses() == {}

    def test_get_all_statuses_multiple(self):
        m = ExecutionMonitor()
        m.register("task-001", "dev")
        m.register("task-002", "qa")
        m.update_status("task-001", AgentRunStatus.RUNNING)
        all_statuses = m.get_all_statuses()
        assert len(all_statuses) == 2
        assert all_statuses["task-001"].status == AgentRunStatus.RUNNING
        assert all_statuses["task-002"].status == AgentRunStatus.CREATED


class TestExecutionMonitorCounts:
    """汇总计数"""

    def test_initial_counts_zero(self):
        m = ExecutionMonitor()
        assert m.active_count == 0
        assert m.completed_count == 0
        assert m.failed_count == 0
        assert m.total_count == 0

    def test_active_count_tracks_running(self):
        m = ExecutionMonitor()
        m.register("task-001", "dev")
        m.register("task-002", "qa")
        m.update_status("task-001", AgentRunStatus.RUNNING)
        m.update_status("task-002", AgentRunStatus.RUNNING)
        assert m.active_count == 2

    def test_active_excludes_completed(self):
        m = ExecutionMonitor()
        m.register("task-001", "dev")
        m.register("task-002", "qa")
        m.update_status("task-001", AgentRunStatus.RUNNING)
        m.update_status("task-002", AgentRunStatus.COMPLETED)
        assert m.active_count == 1

    def test_completed_count(self):
        m = ExecutionMonitor()
        m.register("task-001", "dev")
        m.register("task-002", "qa")
        m.update_status("task-001", AgentRunStatus.COMPLETED)
        m.update_status("task-002", AgentRunStatus.COMPLETED)
        assert m.completed_count == 2

    def test_failed_count(self):
        m = ExecutionMonitor()
        m.register("task-001", "dev")
        m.update_status("task-001", AgentRunStatus.FAILED)
        assert m.failed_count == 1

    def test_total_count(self):
        m = ExecutionMonitor()
        m.register("task-001", "dev")
        m.register("task-002", "qa")
        m.register("task-003", "api")
        assert m.total_count == 3


class TestExecutionMonitorDeregister:
    """注销 Agent"""

    def test_deregister_removes_entry(self):
        m = ExecutionMonitor()
        m.register("task-001", "dev")
        m.deregister("task-001")
        assert m.get_status("task-001") is None
        assert m.total_count == 0

    def test_deregister_unknown_no_error(self):
        m = ExecutionMonitor()
        m.deregister("task-999")


class TestExecutionMonitorTimeout:
    """超时检测"""

    def test_chec_timeout_detects_overdue(self):
        m = ExecutionMonitor()
        m.register("task-001", "dev")
        m.update_status("task-001", AgentRunStatus.RUNNING)
        overdue = m.chec_timeout(timeout_seconds=-1)
        assert "task-001" in overdue

    def test_chec_timeout_ignores_completed(self):
        m = ExecutionMonitor()
        m.register("task-001", "dev")
        m.update_status("task-001", AgentRunStatus.COMPLETED)
        overdue = m.chec_timeout(timeout_seconds=-1)
        assert "task-001" not in overdue

    def test_chec_timeout_no_running_returns_empty(self):
        m = ExecutionMonitor()
        m.register("task-001", "dev")
        overdue = m.chec_timeout(timeout_seconds=3600)
        assert overdue == []


class TestExecutionMonitorGetByRole:
    """按角色过滤"""

    def test_get_by_role_filters_correctly(self):
        m = ExecutionMonitor()
        m.register("task-001", "senior-developer")
        m.register("task-002", "test-engineer")
        m.register("task-003", "senior-developer")
        devs = m.get_by_role("senior-developer")
        assert {r.task_id for r in devs} == {"task-001", "task-003"}

    def test_get_by_role_none_found(self):
        m = ExecutionMonitor()
        assert m.get_by_role("unknown") == []


class TestExecutionMonitorGetActive:
    """获取活跃任务"""

    def test_get_active_returns_running_only(self):
        m = ExecutionMonitor()
        m.register("task-001", "dev")
        m.register("task-002", "qa")
        m.update_status("task-001", AgentRunStatus.RUNNING)
        active = m.get_active()
        assert len(active) == 1
        assert active[0].task_id == "task-001"

    def test_get_active_excludes_completed_and_failed(self):
        m = ExecutionMonitor()
        m.register("task-001", "dev")
        m.register("task-002", "qa")
        m.register("task-003", "api")
        m.update_status("task-001", AgentRunStatus.RUNNING)
        m.update_status("task-002", AgentRunStatus.COMPLETED)
        m.update_status("task-003", AgentRunStatus.FAILED)
        active = m.get_active()
        assert len(active) == 1

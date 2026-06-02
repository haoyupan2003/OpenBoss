"""
P1-044: MasterAgent 类设计 — 单元测试

覆盖范围：
- MasterAgentState 枚举 (3)
- 构造函数与参数校验 (7)
- 状态转换 _transition_to (8)
- receive_requirement (4)
- create_pm_agent (5)
- load_task_json / set_task_json (6)
- get_dispatchable_tasks (8)
- create_sub_agent (5)
- record_result (6)
- 终态检查 (5)
- get_progress_summary (3)
- reset (3)
- _map_result_status (5)
- 属性 (4)
合计: 72 项
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_automation_system.master_agent.master_agent import (
    MasterAgent,
    MasterAgentState,
    _VALID_STATE_TRANSITIONS,
    _default_agent_factory,
)
from agent_automation_system.models.task import Task, TaskPriority, TaskStatus
from agent_automation_system.models.task_json import TaskJSON
from agent_automation_system.sub_agent.sub_agent import (
    AgentPhase,
    SubAgent,
    SubAgentResult,
    SubAgentResultStatus,
)


# ── 测试辅助 ──────────────────────────────────────────────


def _make_sub_agent(role_name: str = "dev") -> MagicMock:
    """创建 Mock SubAgent"""
    agent = MagicMock(spec=SubAgent)
    agent.role_name = role_name
    return agent


def _make_factory(roles: dict[str, MagicMock] | None = None):
    """创建 Mock AgentFactory"""
    default = _make_sub_agent()
    agents = roles or {}

    def factory(role_name: str) -> SubAgent:
        return agents.get(role_name, default)

    return factory


def _make_task(
    task_id: str = "task-001",
    title: str = "Test Task",
    deps: list[str] | None = None,
    status: TaskStatus = TaskStatus.PENDING,
    role: str = "senior-developer",
    priority: TaskPriority = TaskPriority.MEDIUM,
) -> Task:
    """创建测试 Task"""
    return Task(
        id=task_id,
        title=title,
        description=f"Description for {title}",
        dependencies=deps or [],
        suggested_role=role,
        priority=priority,
        status=status,
    )


def _make_task_json(tasks: list[Task] | None = None) -> TaskJSON:
    """创建测试 TaskJSON"""
    task_list = tasks or [_make_task()]
    return TaskJSON(
        project_name="TestProject",
        description="Test project",
        total_tasks=len(task_list),
        tasks=task_list,
    )


def _make_master(**kwargs) -> MasterAgent:
    """创建测试 MasterAgent"""
    defaults = {
        "agent_factory": _make_factory(),
    }
    defaults.update(kwargs)
    return MasterAgent(**defaults)


def _prepare_master_with_tasks(
    tasks: list[Task] | None = None,
) -> MasterAgent:
    """创建已设置 task_json 的 MasterAgent"""
    master = _make_master()
    master.receive_requirement("测试需求")
    task_json = _make_task_json(tasks)
    master.set_task_json(task_json)
    return master


# ── MasterAgentState 枚举 ─────────────────────────────────


class TestMasterAgentState:
    """MasterAgentState 枚举测试"""

    def test_state_values(self):
        """所有状态值正确"""
        assert MasterAgentState.IDLE == "idle"
        assert MasterAgentState.ANALYZING == "analyzing"
        assert MasterAgentState.PLANNING == "planning"
        assert MasterAgentState.DISPATCHING == "dispatching"
        assert MasterAgentState.MONITORING == "monitoring"
        assert MasterAgentState.COMPLETED == "completed"
        assert MasterAgentState.FAILED == "failed"
        assert MasterAgentState.PAUSED == "paused"

    def test_state_count(self):
        """状态总数为 8"""
        assert len(MasterAgentState) == 8

    def test_state_is_str_enum(self):
        """状态是 str 枚举"""
        assert isinstance(MasterAgentState.IDLE, str)


# ── 构造函数与参数校验 ────────────────────────────────────


class TestConstructor:
    """MasterAgent 构造函数测试"""

    def test_default_values(self):
        """默认配置值"""
        master = MasterAgent()
        assert master.state == MasterAgentState.IDLE
        assert master.session_name == "openboss"
        assert master.max_concurrent_agents == 3
        assert master.agent_timeout == 1800
        assert master.task_max_retries == 1
        assert master.poll_interval == 10.0

    def test_custom_values(self):
        """自定义配置值"""
        master = MasterAgent(
            session_name="custom-session",
            max_concurrent_agents=5,
            agent_timeout=3600,
            task_max_retries=3,
            poll_interval=5.0,
        )
        assert master.session_name == "custom-session"
        assert master.max_concurrent_agents == 5
        assert master.agent_timeout == 3600
        assert master.task_max_retries == 3
        assert master.poll_interval == 5.0

    def test_invalid_max_concurrent_agents(self):
        """max_concurrent_agents <= 0 抛异常"""
        with pytest.raises(ValueError, match="max_concurrent_agents"):
            MasterAgent(max_concurrent_agents=0)

    def test_invalid_agent_timeout(self):
        """agent_timeout <= 0 抛异常"""
        with pytest.raises(ValueError, match="agent_timeout"):
            MasterAgent(agent_timeout=-1)

    def test_invalid_task_max_retries(self):
        """task_max_retries < 0 抛异常"""
        with pytest.raises(ValueError, match="task_max_retries"):
            MasterAgent(task_max_retries=-1)

    def test_invalid_poll_interval(self):
        """poll_interval <= 0 抛异常"""
        with pytest.raises(ValueError, match="poll_interval"):
            MasterAgent(poll_interval=0)

    def test_initial_runtime_state(self):
        """初始运行时状态为空"""
        master = MasterAgent()
        assert master.requirement is None
        assert master.task_json is None
        assert master.pm_agent is None
        assert master.active_agents == {}
        assert master.execution_results == {}


# ── 状态转换 ──────────────────────────────────────────────


class TestStateTransition:
    """_transition_to 状态转换测试"""

    def test_valid_idle_to_analyzing(self):
        """IDLE → ANALYZING 合法"""
        master = _make_master()
        master._transition_to(MasterAgentState.ANALYZING)
        assert master.state == MasterAgentState.ANALYZING

    def test_valid_analyzing_to_planning(self):
        """ANALYZING → PLANNING 合法"""
        master = _make_master()
        master._state = MasterAgentState.ANALYZING
        master._transition_to(MasterAgentState.PLANNING)
        assert master.state == MasterAgentState.PLANNING

    def test_valid_planning_to_dispatching(self):
        """PLANNING → DISPATCHING 合法"""
        master = _make_master()
        master._state = MasterAgentState.PLANNING
        master._transition_to(MasterAgentState.DISPATCHING)
        assert master.state == MasterAgentState.DISPATCHING

    def test_valid_dispatching_to_monitoring(self):
        """DISPATCHING → MONITORING 合法"""
        master = _make_master()
        master._state = MasterAgentState.DISPATCHING
        master._transition_to(MasterAgentState.MONITORING)
        assert master.state == MasterAgentState.MONITORING

    def test_valid_monitoring_to_dispatching(self):
        """MONITORING → DISPATCHING 合法（循环调度）"""
        master = _make_master()
        master._state = MasterAgentState.MONITORING
        master._transition_to(MasterAgentState.DISPATCHING)
        assert master.state == MasterAgentState.DISPATCHING

    def test_invalid_idle_to_completed(self):
        """IDLE → COMPLETED 非法"""
        master = _make_master()
        with pytest.raises(RuntimeError, match="Invalid state transition"):
            master._transition_to(MasterAgentState.COMPLETED)

    def test_invalid_completed_to_idle(self):
        """COMPLETED 是终态，不可转换"""
        master = _make_master()
        master._state = MasterAgentState.COMPLETED
        with pytest.raises(RuntimeError, match="Invalid state transition"):
            master._transition_to(MasterAgentState.IDLE)

    def test_invalid_failed_to_idle(self):
        """FAILED 是终态，不可转换"""
        master = _make_master()
        master._state = MasterAgentState.FAILED
        with pytest.raises(RuntimeError, match="Invalid state transition"):
            master._transition_to(MasterAgentState.IDLE)


# ── receive_requirement ───────────────────────────────────


class TestReceiveRequirement:
    """receive_requirement 测试"""

    def test_receive_valid_requirement(self):
        """接收有效需求"""
        master = _make_master()
        master.receive_requirement("实现用户登录功能")
        assert master.requirement == "实现用户登录功能"
        assert master.state == MasterAgentState.ANALYZING

    def test_receive_empty_requirement(self):
        """空需求抛异常"""
        master = _make_master()
        with pytest.raises(ValueError, match="requirement cannot be empty"):
            master.receive_requirement("")

    def test_receive_whitespace_requirement(self):
        """纯空格需求抛异常"""
        master = _make_master()
        with pytest.raises(ValueError, match="requirement cannot be empty"):
            master.receive_requirement("   ")

    def test_receive_requirement_strips_whitespace(self):
        """需求自动去除前后空格"""
        master = _make_master()
        master.receive_requirement("  实现登录  ")
        assert master.requirement == "实现登录"


# ── create_pm_agent ───────────────────────────────────────


class TestCreatePmAgent:
    """create_pm_agent 测试"""

    def test_create_with_stored_requirement(self):
        """使用已存储需求创建 PM Agent"""
        pm_mock = _make_sub_agent("product-manager")
        master = _make_master(
            agent_factory=_make_factory({"product-manager": pm_mock})
        )
        master.receive_requirement("实现登录")
        agent = master.create_pm_agent()

        assert agent is pm_mock
        assert master.pm_agent is pm_mock
        assert agent.role_name == "product-manager"

    def test_create_with_explicit_requirement(self):
        """传入显式需求创建 PM Agent"""
        pm_mock = _make_sub_agent("product-manager")
        master = _make_master(
            agent_factory=_make_factory({"product-manager": pm_mock})
        )
        agent = master.create_pm_agent("实现登录")

        assert agent is pm_mock
        assert master.requirement == "实现登录"

    def test_create_without_requirement_raises(self):
        """无需求时创建 PM Agent 抛异常"""
        master = _make_master()
        with pytest.raises(ValueError, match="No requirement available"):
            master.create_pm_agent()

    def test_create_from_idle_auto_transitions(self):
        """从 IDLE 创建 PM Agent 自动转换状态"""
        pm_mock = _make_sub_agent("product-manager")
        master = _make_master(
            agent_factory=_make_factory({"product-manager": pm_mock})
        )
        master.create_pm_agent("实现登录")
        assert master.state == MasterAgentState.ANALYZING

    def test_create_calls_factory_with_role(self):
        """factory 被正确调用"""
        factory_mock = MagicMock(return_value=_make_sub_agent("product-manager"))
        master = _make_master(agent_factory=factory_mock)
        master.receive_requirement("需求")
        master.create_pm_agent()

        factory_mock.assert_called_with("product-manager")


# ── load_task_json / set_task_json ────────────────────────


class TestTaskJsonLoading:
    """task.json 加载测试"""

    def test_set_task_json(self):
        """直接设置 TaskJSON"""
        master = _make_master()
        master.receive_requirement("需求")
        task_json = _make_task_json()
        master.set_task_json(task_json)

        assert master.task_json is task_json
        assert master.state == MasterAgentState.DISPATCHING

    def test_set_task_json_from_analyzing(self):
        """从 ANALYZING 设置 TaskJSON 自动经过 PLANNING"""
        master = _make_master()
        master.receive_requirement("需求")
        assert master.state == MasterAgentState.ANALYZING

        master.set_task_json(_make_task_json())
        assert master.state == MasterAgentState.DISPATCHING

    def test_set_task_json_none_raises(self):
        """设置 None 抛异常"""
        master = _make_master()
        master.receive_requirement("需求")
        with pytest.raises(ValueError, match="task_json cannot be None"):
            master.set_task_json(None)

    def test_load_task_json_from_file(self):
        """从文件加载 task.json"""
        task_data = {
            "project_name": "TestProject",
            "total_tasks": 1,
            "tasks": [
                {
                    "id": "task-001",
                    "title": "Test",
                    "description": "Desc",
                    "suggested_role": "dev",
                }
            ],
        }

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            json.dump(task_data, f)
            temp_path = f.name

        try:
            master = _make_master()
            master.receive_requirement("需求")
            result = master.load_task_json(temp_path)

            assert result.project_name == "TestProject"
            assert len(result.tasks) == 1
            assert master.task_json is result
            assert master.state == MasterAgentState.DISPATCHING
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_load_nonexistent_file_raises(self):
        """加载不存在的文件抛异常"""
        master = _make_master()
        master.receive_requirement("需求")
        with pytest.raises(FileNotFoundError):
            master.load_task_json("/nonexistent/task.json")

    def test_set_task_json_from_idle_raises(self):
        """从 IDLE 状态设置 TaskJSON 抛异常（需先接收需求）"""
        master = _make_master()
        with pytest.raises(RuntimeError, match="Cannot set task_json"):
            master.set_task_json(_make_task_json())


# ── get_dispatchable_tasks ────────────────────────────────


class TestGetDispatchableTasks:
    """get_dispatchable_tasks 测试"""

    def test_no_deps_all_dispatchable(self):
        """无依赖的任务全部可调度"""
        tasks = [
            _make_task("task-001", role="dev"),
            _make_task("task-002", role="qa"),
        ]
        master = _prepare_master_with_tasks(tasks)
        result = master.get_dispatchable_tasks()

        assert len(result) == 2
        assert result[0].id == "task-001"
        assert result[1].id == "task-002"

    def test_deps_not_met(self):
        """依赖未完成的任务不可调度"""
        tasks = [
            _make_task("task-001", status=TaskStatus.PENDING),
            _make_task("task-002", deps=["task-001"], status=TaskStatus.PENDING),
        ]
        master = _prepare_master_with_tasks(tasks)
        result = master.get_dispatchable_tasks()

        assert len(result) == 1
        assert result[0].id == "task-001"

    def test_deps_met(self):
        """依赖已完成的任务可调度"""
        tasks = [
            _make_task("task-001", status=TaskStatus.COMPLETED),
            _make_task("task-002", deps=["task-001"], status=TaskStatus.PENDING),
        ]
        master = _prepare_master_with_tasks(tasks)
        result = master.get_dispatchable_tasks()

        assert len(result) == 1
        assert result[0].id == "task-002"

    def test_priority_sorting(self):
        """按优先级排序（HIGH > MEDIUM > LOW）"""
        tasks = [
            _make_task("task-003", priority=TaskPriority.LOW),
            _make_task("task-001", priority=TaskPriority.HIGH),
            _make_task("task-002", priority=TaskPriority.MEDIUM),
        ]
        master = _prepare_master_with_tasks(tasks)
        result = master.get_dispatchable_tasks()

        assert result[0].id == "task-001"  # HIGH
        assert result[1].id == "task-002"  # MEDIUM
        assert result[2].id == "task-003"  # LOW

    def test_skip_non_pending(self):
        """非 PENDING 状态的任务不可调度"""
        tasks = [
            _make_task("task-001", status=TaskStatus.COMPLETED),
            _make_task("task-002", status=TaskStatus.FAILED),
            _make_task("task-003", status=TaskStatus.IN_PROGRESS),
            _make_task("task-004", status=TaskStatus.PENDING),
        ]
        master = _prepare_master_with_tasks(tasks)
        result = master.get_dispatchable_tasks()

        assert len(result) == 1
        assert result[0].id == "task-004"

    def test_empty_task_json(self):
        """无 task_json 返回空列表"""
        master = _make_master()
        master._state = MasterAgentState.DISPATCHING
        result = master.get_dispatchable_tasks()
        assert result == []

    def test_wrong_state_raises(self):
        """在错误状态下调用抛异常"""
        master = _make_master()
        with pytest.raises(RuntimeError, match="Cannot get dispatchable tasks"):
            master.get_dispatchable_tasks()

    def test_chain_dependencies(self):
        """链式依赖：A→B→C，A 完成后 B 可调度"""
        tasks = [
            _make_task("task-001", status=TaskStatus.COMPLETED),
            _make_task("task-002", deps=["task-001"], status=TaskStatus.PENDING),
            _make_task("task-003", deps=["task-002"], status=TaskStatus.PENDING),
        ]
        master = _prepare_master_with_tasks(tasks)
        result = master.get_dispatchable_tasks()

        # task-002 可调度，task-003 依赖 task-002 不可调度
        assert len(result) == 1
        assert result[0].id == "task-002"


# ── create_sub_agent ──────────────────────────────────────


class TestCreateSubAgent:
    """create_sub_agent 测试"""

    def test_create_agent_for_task(self):
        """为任务创建 Sub-Agent"""
        dev_mock = _make_sub_agent("senior-developer")
        factory = _make_factory({"senior-developer": dev_mock})
        master = _make_master(agent_factory=factory)
        task = _make_task(role="senior-developer")
        master.receive_requirement("需求")
        master.set_task_json(_make_task_json([task]))

        agent = master.create_sub_agent(task)
        assert agent is dev_mock
        assert task.id in master.active_agents

    def test_create_agent_none_task_raises(self):
        """task 为 None 抛异常"""
        master = _make_master()
        master._state = MasterAgentState.DISPATCHING
        with pytest.raises(ValueError, match="task cannot be None"):
            master.create_sub_agent(None)

    def test_create_agent_wrong_state_raises(self):
        """在错误状态下创建抛异常"""
        master = _make_master()
        task = _make_task()
        with pytest.raises(RuntimeError, match="Cannot create sub-agent"):
            master.create_sub_agent(task)

    def test_create_agent_from_monitoring(self):
        """从 MONITORING 状态可以创建"""
        dev_mock = _make_sub_agent("dev")
        factory = _make_factory({"dev": dev_mock})
        master = _make_master(agent_factory=factory)
        task = _make_task(role="dev")
        master.receive_requirement("需求")
        master.set_task_json(_make_task_json([task]))
        master._state = MasterAgentState.MONITORING

        agent = master.create_sub_agent(task)
        assert agent is dev_mock

    def test_create_agent_registers_in_active(self):
        """创建的 Agent 注册到活跃列表"""
        dev_mock = _make_sub_agent("dev")
        factory = _make_factory({"dev": dev_mock})
        master = _make_master(agent_factory=factory)
        task = _make_task("task-042", role="dev")
        master.receive_requirement("需求")
        master.set_task_json(_make_task_json([task]))

        master.create_sub_agent(task)
        assert "task-042" in master.active_agents
        assert master.active_agents["task-042"] is dev_mock


# ── record_result ─────────────────────────────────────────


class TestRecordResult:
    """record_result 测试"""

    def test_record_success_result(self):
        """记录成功结果"""
        master = _prepare_master_with_tasks()
        task_id = master.task_json.tasks[0].id

        result = SubAgentResult(
            task_id=task_id,
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.COMPLETED,
            role="dev",
        )
        master.record_result(task_id, result)

        assert task_id in master.execution_results
        assert master.execution_results[task_id] is result

    def test_record_updates_task_status(self):
        """记录结果后更新 task_json 中任务状态"""
        master = _prepare_master_with_tasks()
        task_id = master.task_json.tasks[0].id

        result = SubAgentResult(
            task_id=task_id,
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.COMPLETED,
            role="dev",
        )
        master.record_result(task_id, result)

        assert master.task_json.tasks[0].status == TaskStatus.COMPLETED

    def test_record_failed_result_updates_status(self):
        """记录失败结果后任务状态为 FAILED"""
        master = _prepare_master_with_tasks()
        task_id = master.task_json.tasks[0].id

        result = SubAgentResult(
            task_id=task_id,
            status=SubAgentResultStatus.FAILED,
            phase=AgentPhase.FAILED,
            role="dev",
            error="Something went wrong",
        )
        master.record_result(task_id, result)

        assert master.task_json.tasks[0].status == TaskStatus.FAILED
        assert master.task_json.tasks[0].error_message == "Something went wrong"

    def test_record_removes_from_active(self):
        """记录结果后从活跃列表移除"""
        master = _prepare_master_with_tasks()
        task = master.task_json.tasks[0]

        dev_mock = _make_sub_agent("dev")
        master._active_agents[task.id] = dev_mock
        assert task.id in master.active_agents

        result = SubAgentResult(
            task_id=task.id,
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.COMPLETED,
            role="dev",
        )
        master.record_result(task.id, result)

        assert task.id not in master.active_agents

    def test_record_empty_task_id_raises(self):
        """空 task_id 抛异常"""
        master = _prepare_master_with_tasks()
        result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.COMPLETED,
            role="dev",
        )
        with pytest.raises(ValueError, match="task_id cannot be empty"):
            master.record_result("", result)

    def test_record_none_result_raises(self):
        """result 为 None 抛异常"""
        master = _prepare_master_with_tasks()
        with pytest.raises(ValueError, match="result cannot be None"):
            master.record_result("task-001", None)


# ── 终态检查 ──────────────────────────────────────────────


class TestTerminalChecks:
    """is_all_completed / is_any_failed / is_any_blocked 测试"""

    def test_all_completed(self):
        """所有任务完成"""
        tasks = [
            _make_task("task-001", status=TaskStatus.COMPLETED),
            _make_task("task-002", status=TaskStatus.COMPLETED),
        ]
        master = _prepare_master_with_tasks(tasks)
        assert master.is_all_completed() is True

    def test_not_all_completed(self):
        """并非所有任务完成"""
        tasks = [
            _make_task("task-001", status=TaskStatus.COMPLETED),
            _make_task("task-002", status=TaskStatus.PENDING),
        ]
        master = _prepare_master_with_tasks(tasks)
        assert master.is_all_completed() is False

    def test_any_failed_true(self):
        """存在失败任务"""
        tasks = [
            _make_task("task-001", status=TaskStatus.COMPLETED),
            _make_task("task-002", status=TaskStatus.FAILED),
        ]
        master = _prepare_master_with_tasks(tasks)
        assert master.is_any_failed() is True

    def test_any_blocked_true(self):
        """存在阻塞任务"""
        tasks = [
            _make_task("task-001", status=TaskStatus.BLOCKED),
            _make_task("task-002", status=TaskStatus.PENDING),
        ]
        master = _prepare_master_with_tasks(tasks)
        assert master.is_any_blocked() is True

    def test_no_task_json_returns_false(self):
        """无 task_json 时检查均返回 False"""
        master = _make_master()
        assert master.is_all_completed() is False
        assert master.is_any_failed() is False
        assert master.is_any_blocked() is False


# ── get_progress_summary ─────────────────────────────────


class TestProgressSummary:
    """get_progress_summary 测试"""

    def test_summary_with_tasks(self):
        """有任务时的进度摘要"""
        tasks = [
            _make_task("task-001", status=TaskStatus.COMPLETED),
            _make_task("task-002", status=TaskStatus.FAILED),
            _make_task("task-003", status=TaskStatus.PENDING),
            _make_task("task-004", status=TaskStatus.IN_PROGRESS),
        ]
        master = _prepare_master_with_tasks(tasks)
        summary = master.get_progress_summary()

        assert summary["total"] == 4
        assert summary["completed"] == 1
        assert summary["failed"] == 1
        assert summary["pending"] == 1
        assert summary["in_progress"] == 1
        assert summary["progress_pct"] == 25.0

    def test_summary_no_tasks(self):
        """无 task_json 时的进度摘要"""
        master = _make_master()
        summary = master.get_progress_summary()

        assert summary["total"] == 0
        assert summary["completed"] == 0
        assert summary["progress_pct"] == 0.0
        assert summary["state"] == "idle"

    def test_summary_all_completed(self):
        """全部完成的进度摘要"""
        tasks = [
            _make_task("task-001", status=TaskStatus.COMPLETED),
            _make_task("task-002", status=TaskStatus.COMPLETED),
        ]
        master = _prepare_master_with_tasks(tasks)
        summary = master.get_progress_summary()

        assert summary["progress_pct"] == 100.0


# ── reset ─────────────────────────────────────────────────


class TestReset:
    """reset 测试"""

    def test_reset_from_completed(self):
        """从 COMPLETED 重置"""
        master = _prepare_master_with_tasks()
        master._state = MasterAgentState.COMPLETED
        master.reset()

        assert master.state == MasterAgentState.IDLE
        assert master.requirement is None
        assert master.task_json is None
        assert master.active_agents == {}
        assert master.execution_results == {}

    def test_reset_from_failed(self):
        """从 FAILED 重置"""
        master = _prepare_master_with_tasks()
        master._state = MasterAgentState.FAILED
        master.reset()

        assert master.state == MasterAgentState.IDLE

    def test_reset_from_idle(self):
        """从 IDLE 重置（空操作）"""
        master = _make_master()
        master.reset()
        assert master.state == MasterAgentState.IDLE


# ── _map_result_status ───────────────────────────────────


class TestMapResultStatus:
    """_map_result_status 映射测试"""

    def test_success_to_completed(self):
        assert MasterAgent._map_result_status(
            SubAgentResultStatus.SUCCESS
        ) == TaskStatus.COMPLETED

    def test_failed_to_failed(self):
        assert MasterAgent._map_result_status(
            SubAgentResultStatus.FAILED
        ) == TaskStatus.FAILED

    def test_blocked_to_blocked(self):
        assert MasterAgent._map_result_status(
            SubAgentResultStatus.BLOCKED
        ) == TaskStatus.BLOCKED

    def test_timeout_to_failed(self):
        assert MasterAgent._map_result_status(
            SubAgentResultStatus.TIMEOUT
        ) == TaskStatus.FAILED

    def test_retry_to_pending(self):
        assert MasterAgent._map_result_status(
            SubAgentResultStatus.RETRY
        ) == TaskStatus.PENDING


# ── 属性 ─────────────────────────────────────────────────


class TestProperties:
    """属性只读测试"""

    def test_active_agents_is_copy(self):
        """active_agents 返回副本"""
        master = _make_master()
        agents = master.active_agents
        agents["task-999"] = _make_sub_agent()
        assert "task-999" not in master.active_agents

    def test_execution_results_is_copy(self):
        """execution_results 返回副本"""
        master = _make_master()
        results = master.execution_results
        results["task-999"] = MagicMock()
        assert "task-999" not in master.execution_results

    def test_default_agent_factory_raises(self):
        """默认 agent_factory 抛 NotImplementedError"""
        with pytest.raises(NotImplementedError, match="No agent factory"):
            _default_agent_factory("dev")

    def test_transition_table_terminal_states(self):
        """终态转换表为空集"""
        assert _VALID_STATE_TRANSITIONS[MasterAgentState.COMPLETED] == set()
        assert _VALID_STATE_TRANSITIONS[MasterAgentState.FAILED] == set()

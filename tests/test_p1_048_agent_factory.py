"""
P1-048 测试 — Agent Factory（Sub-Agent 创建与委派）

测试内容：
- SubAgentFactory: 角色映射、窗口分配、Agent 创建
- EphemeralSubAgent: 初始化、执行、验证、提交、清理
- MasterAgent.dispatch_task(): 委派流程
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock

from agent_automation_system.master_agent.agent_factory import (
    EphemeralSubAgent,
    SubAgentFactory,
    _ROLE_SHORT_NAMES,
    _DEFAULT_ROLE_SHORT,
)
from agent_automation_system.master_agent.master_agent import (
    MasterAgent,
    MasterAgentState,
)
from agent_automation_system.models.task import (
    Task,
    TaskPriority,
    TaskStatus,
    BDDSpec,
)
from agent_automation_system.models.task_json import TaskJSON
from agent_automation_system.sub_agent.sub_agent import (
    SubAgent,
    SubAgentResult,
    SubAgentResultStatus,
    AgentPhase,
)


# ── 辅助工具 ──────────────────────────────────────────────


def _make_task(
    task_id: str = "task-001",
    title: str = "Test task",
    priority: TaskPriority = TaskPriority.MEDIUM,
    status: TaskStatus = TaskStatus.PENDING,
    dependencies: list[str] | None = None,
    retry_count: int = 0,
    suggested_role: str = "senior-developer",
) -> Task:
    """创建测试用 Task"""
    return Task(
        id=task_id,
        title=title,
        description=f"Description for {title}",
        bdd=BDDSpec(given="context", when="action", then="result"),
        dependencies=dependencies or [],
        priority=priority,
        status=status,
        retry_count=retry_count,
        suggested_role=suggested_role,
    )


def _make_task_json(tasks: list[Task]) -> TaskJSON:
    """创建测试用 TaskJSON"""
    return TaskJSON(
        project_name="test-project",
        total_tasks=len(tasks),
        tasks=tasks,
    )


def _make_mock_tmux() -> MagicMock:
    """创建 mock TmuxManager"""
    tmux = MagicMock()
    tmux.session_exists.return_value = True
    tmux.window_exists.return_value = False
    return tmux


def _make_mock_cli() -> MagicMock:
    """创建 mock ClaudeCodeCLI"""
    cli = MagicMock()
    cli.start_cli.return_value = MagicMock()
    return cli


# ── SubAgentFactory: 角色映射 ────────────────────────────


class TestSubAgentFactoryRoleMapping:
    """角色名称 → 角色简称映射"""

    def test_known_role_short_names(self):
        """内置角色有正确的简称映射"""
        assert _ROLE_SHORT_NAMES["senior-developer"] == "dev"
        assert _ROLE_SHORT_NAMES["test-engineer"] == "qa"
        assert _ROLE_SHORT_NAMES["product-manager"] == "pm"
        assert _ROLE_SHORT_NAMES["validator"] == "val"

    def test_unknown_role_uses_default(self):
        """未知角色使用默认简称"""
        assert _ROLE_SHORT_NAMES.get("custom-role", _DEFAULT_ROLE_SHORT) == "agent"

    def test_all_built_in_roles_mapped(self):
        """所有内置角色模板都有简称"""
        factory = SubAgentFactory()
        # 验证工厂内置的映射不为空
        assert len(_ROLE_SHORT_NAMES) >= 8


# ── SubAgentFactory: 窗口分配 ────────────────────────────


class TestSubAgentFactoryWindowAllocation:
    """窗口名称分配和计数"""

    def test_first_dev_agent_gets_001(self):
        """第一个 dev 角色分配序号 001"""
        factory = SubAgentFactory()
        name = factory._allocate_window_name("senior-developer")
        assert name == "agent_dev_001"

    def test_second_dev_agent_gets_002(self):
        """第二个 dev 角色分配序号 002"""
        factory = SubAgentFactory()
        factory._allocate_window_name("senior-developer")
        name = factory._allocate_window_name("senior-developer")
        assert name == "agent_dev_002"

    def test_different_roles_independent_counters(self):
        """不同角色的计数器独立"""
        factory = SubAgentFactory()
        name1 = factory._allocate_window_name("senior-developer")
        name2 = factory._allocate_window_name("test-engineer")
        name3 = factory._allocate_window_name("senior-developer")
        assert name1 == "agent_dev_001"
        assert name2 == "agent_qa_001"
        assert name3 == "agent_dev_002"

    def test_unknown_role_uses_default_short(self):
        """未知角色使用默认简称 'agent'"""
        factory = SubAgentFactory()
        name = factory._allocate_window_name("custom-agent")
        assert name == "agent_agent_001"

    def test_reset_counters(self):
        """重置计数器后序号重新开始"""
        factory = SubAgentFactory()
        factory._allocate_window_name("senior-developer")
        factory._allocate_window_name("senior-developer")
        factory.reset_counters()
        name = factory._allocate_window_name("senior-developer")
        assert name == "agent_dev_001"

    def test_get_role_counter(self):
        """获取角色已创建数量"""
        factory = SubAgentFactory()
        assert factory.get_role_counter("senior-developer") == 0
        factory.create("senior-developer")
        assert factory.get_role_counter("senior-developer") == 1


# ── SubAgentFactory: 创建 Agent ──────────────────────────


class TestSubAgentFactoryCreate:
    """SubAgentFactory.create() 核心创建逻辑"""

    def test_creates_ephemeral_sub_agent(self):
        """创建 EphemeralSubAgent 实例"""
        factory = SubAgentFactory()
        agent = factory.create("senior-developer")
        assert isinstance(agent, EphemeralSubAgent)
        assert isinstance(agent, SubAgent)

    def test_agent_has_correct_role_name(self):
        """Agent 具有正确的角色名称"""
        factory = SubAgentFactory()
        agent = factory.create("test-engineer")
        assert agent.role_name == "test-engineer"

    def test_agent_has_window_name(self):
        """Agent 被分配了窗口名称"""
        factory = SubAgentFactory()
        agent = factory.create("senior-developer")
        assert agent.window_name is not None
        assert "dev" in agent.window_name

    def test_empty_role_name_raises(self):
        """空角色名称抛 ValueError"""
        factory = SubAgentFactory()
        with pytest.raises(ValueError, match="role_name cannot be empty"):
            factory.create("")

    def test_whitespace_role_name_raises(self):
        """纯空格角色名称抛 ValueError"""
        factory = SubAgentFactory()
        with pytest.raises(ValueError, match="role_name cannot be empty"):
            factory.create("   ")

    def test_auto_create_window(self):
        """自动创建 tmux 窗口"""
        tmux = _make_mock_tmux()
        factory = SubAgentFactory(tmux_manager=tmux, auto_create_window=True)
        factory.create("senior-developer")
        tmux.create_window.assert_called_once()

    def test_no_auto_create_window(self):
        """禁用自动创建窗口"""
        tmux = _make_mock_tmux()
        factory = SubAgentFactory(tmux_manager=tmux, auto_create_window=False)
        factory.create("senior-developer")
        tmux.create_window.assert_not_called()

    def test_session_not_exists_raises(self):
        """会话不存在时抛 RuntimeError"""
        tmux = _make_mock_tmux()
        tmux.session_exists.return_value = False
        factory = SubAgentFactory(tmux_manager=tmux, auto_create_window=True)
        with pytest.raises(RuntimeError, match="does not exist"):
            factory.create("senior-developer")

    def test_window_already_exists_reuses(self):
        """窗口已存在时复用"""
        tmux = _make_mock_tmux()
        tmux.window_exists.return_value = True
        factory = SubAgentFactory(tmux_manager=tmux, auto_create_window=True)
        factory.create("senior-developer")
        tmux.create_window.assert_not_called()

    def test_without_tmux_manager(self):
        """无 TmuxManager 时不创建窗口"""
        factory = SubAgentFactory(tmux_manager=None)
        agent = factory.create("senior-developer")
        assert agent is not None
        assert isinstance(agent, EphemeralSubAgent)


# ── SubAgentFactory: __call__ 协议 ───────────────────────


class TestSubAgentFactoryCallable:
    """__call__ 兼容 AgentFactory 协议"""

    def test_callable_creates_agent(self):
        """可调用创建 Agent"""
        factory = SubAgentFactory()
        agent = factory("senior-developer")
        assert isinstance(agent, SubAgent)

    def test_callable_same_as_create(self):
        """__call__ 和 create() 结果一致"""
        factory = SubAgentFactory()
        agent1 = factory.create("test-engineer")
        agent2 = factory("test-engineer")
        assert type(agent1) == type(agent2)
        assert agent1.role_name == agent2.role_name

    def test_compatible_with_master_agent(self):
        """兼容 MasterAgent 的 agent_factory 协议"""
        factory = SubAgentFactory()
        master = MasterAgent(agent_factory=factory)
        # MasterAgent 内部调用 _agent_factory("product-manager")
        agent = master._agent_factory("product-manager")
        assert isinstance(agent, SubAgent)


# ── EphemeralSubAgent: 生命周期 ──────────────────────────


class TestEphemeralSubAgentLifecycle:
    """EphemeralSubAgent 生命周期方法"""

    def test_initialize_success(self):
        """初始化成功"""
        tmux = _make_mock_tmux()
        tmux.window_exists.return_value = True  # 窗口已存在
        agent = EphemeralSubAgent(
            role_name="senior-developer",
            tmux_manager=tmux,
            session_name="openboss",
            window_name="agent_dev_001",
        )
        agent.initialize()  # 不应抛异常

    def test_initialize_session_not_found(self):
        """tmux 会话不存在时初始化失败"""
        tmux = _make_mock_tmux()
        tmux.session_exists.return_value = False
        agent = EphemeralSubAgent(
            role_name="senior-developer",
            tmux_manager=tmux,
            session_name="openboss",
            window_name="agent_dev_001",
        )
        with pytest.raises(RuntimeError, match="not found"):
            agent.initialize()

    def test_initialize_window_not_found(self):
        """tmux 窗口不存在时初始化失败"""
        tmux = _make_mock_tmux()
        tmux.window_exists.return_value = False
        agent = EphemeralSubAgent(
            role_name="senior-developer",
            tmux_manager=tmux,
            session_name="openboss",
            window_name="agent_dev_001",
        )
        with pytest.raises(RuntimeError, match="not found"):
            agent.initialize()

    def test_initialize_without_tmux(self):
        """无 TmuxManager 时初始化通过"""
        agent = EphemeralSubAgent(role_name="senior-developer")
        agent.initialize()  # 不应抛异常

    def test_execute_returns_result(self):
        """execute 返回 SubAgentResult"""
        agent = EphemeralSubAgent(role_name="senior-developer")
        agent._task = _make_task()
        result = agent.execute(agent._task)
        assert isinstance(result, SubAgentResult)

    def test_verify_returns_success(self):
        """verify 返回成功结果"""
        agent = EphemeralSubAgent(role_name="senior-developer")
        agent._task = _make_task()
        result = agent.verify()
        assert result.status == SubAgentResultStatus.SUCCESS

    def test_commit_returns_success(self):
        """commit 返回成功结果"""
        agent = EphemeralSubAgent(role_name="senior-developer")
        agent._task = _make_task()
        result = agent.commit()
        assert result.status == SubAgentResultStatus.SUCCESS

    def test_cleanup_no_error(self):
        """cleanup 不抛异常"""
        agent = EphemeralSubAgent(role_name="senior-developer")
        agent.cleanup()  # 不应抛异常

    def test_full_lifecycle_via_run(self):
        """通过 run() 完成完整生命周期"""
        tmux = _make_mock_tmux()
        cli = _make_mock_cli()
        agent = EphemeralSubAgent(
            role_name="senior-developer",
            tmux_manager=tmux,
            cli=cli,
            session_name="openboss",
            window_name="agent_dev_001",
        )
        task = _make_task()
        result = agent.run(task)

        assert isinstance(result, SubAgentResult)
        assert result.task_id == "task-001"
        assert result.role == "senior-developer"
        assert agent.phase == AgentPhase.CLEANED_UP

    def test_execute_cli_failure(self):
        """CLI 执行失败时返回 FAILED"""
        cli = _make_mock_cli()
        cli.start_cli.side_effect = RuntimeError("CLI crashed")
        agent = EphemeralSubAgent(
            role_name="senior-developer",
            cli=cli,
            session_name="openboss",
            window_name="agent_dev_001",
        )
        agent._task = _make_task()
        result = agent.execute(agent._task)
        assert result.status == SubAgentResultStatus.FAILED
        assert "CLI execution failed" in result.error


# ── EphemeralSubAgent: 属性 ─────────────────────────────


class TestEphemeralSubAgentProperties:
    """EphemeralSubAgent 属性"""

    def test_window_name(self):
        """窗口名称属性"""
        agent = EphemeralSubAgent(
            role_name="dev",
            window_name="agent_dev_001",
        )
        assert agent.window_name == "agent_dev_001"

    def test_session_name(self):
        """会话名称属性"""
        agent = EphemeralSubAgent(
            role_name="dev",
            session_name="my-session",
        )
        assert agent.session_name == "my-session"

    def test_role_name_inherited(self):
        """角色名称从 SubAgent 继承"""
        agent = EphemeralSubAgent(role_name="test-engineer")
        assert agent.role_name == "test-engineer"


# ── EphemeralSubAgent: 任务描述构建 ──────────────────────


class TestEphemeralSubAgentTaskDescription:
    """_build_task_description 构建逻辑"""

    def test_includes_title_and_id(self):
        """包含标题和 ID"""
        agent = EphemeralSubAgent(role_name="dev")
        task = _make_task(task_id="task-042", title="Implement feature X")
        desc = agent._build_task_description(task)
        assert "task-042" in desc
        assert "Implement feature X" in desc

    def test_includes_bdd_spec(self):
        """包含 BDD 规格"""
        agent = EphemeralSubAgent(role_name="dev")
        task = _make_task()
        desc = agent._build_task_description(task)
        assert "Given" in desc
        assert "When" in desc
        assert "Then" in desc

    def test_includes_test_script(self):
        """包含测试脚本路径"""
        agent = EphemeralSubAgent(role_name="dev")
        task = _make_task()
        task.test_script = "tests/test_login.py"
        desc = agent._build_task_description(task)
        assert "tests/test_login.py" in desc


# ── MasterAgent.dispatch_task ───────────────────────────


class TestMasterAgentDispatchTask:
    """MasterAgent.dispatch_task() 委派流程"""

    def _make_dispatching_master(
        self,
        tasks: list[Task],
        max_concurrent: int = 3,
    ) -> MasterAgent:
        """创建 DISPATCHING 状态的 MasterAgent"""
        master = MasterAgent(max_concurrent_agents=max_concurrent)
        master._state = MasterAgentState.DISPATCHING
        master._task_json = _make_task_json(tasks)
        return master

    def test_dispatch_auto_selects_task(self):
        """自动选择任务并执行"""
        mock_agent = MagicMock(spec=SubAgent)
        mock_agent.role_name = "senior-developer"
        mock_result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.COMPLETED,
            role="senior-developer",
        )
        mock_agent.run.return_value = mock_result

        factory = MagicMock(return_value=mock_agent)
        master = self._make_dispatching_master(
            [_make_task("task-001", priority=TaskPriority.HIGH)]
        )
        master._agent_factory = factory

        result = master.dispatch_task()
        assert result is not None
        assert result.is_success
        mock_agent.run.assert_called_once()

    def test_dispatch_specific_task(self):
        """指定任务执行"""
        mock_agent = MagicMock(spec=SubAgent)
        mock_agent.role_name = "senior-developer"
        mock_result = SubAgentResult(
            task_id="task-002",
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.COMPLETED,
            role="senior-developer",
        )
        mock_agent.run.return_value = mock_result

        factory = MagicMock(return_value=mock_agent)
        task = _make_task("task-002")
        master = self._make_dispatching_master([task])
        master._agent_factory = factory

        result = master.dispatch_task(task=task)
        assert result is not None
        assert result.task_id == "task-002"

    def test_dispatch_no_available_tasks(self):
        """无可用任务时返回 None"""
        mock_agent = MagicMock(spec=SubAgent)
        factory = MagicMock(return_value=mock_agent)
        master = self._make_dispatching_master(
            [_make_task("task-001", status=TaskStatus.COMPLETED)]
        )
        master._agent_factory = factory

        result = master.dispatch_task()
        assert result is None
        factory.assert_not_called()

    def test_dispatch_records_result(self):
        """委派后记录结果"""
        mock_agent = MagicMock(spec=SubAgent)
        mock_agent.role_name = "senior-developer"
        mock_result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.COMPLETED,
            role="senior-developer",
        )
        mock_agent.run.return_value = mock_result

        factory = MagicMock(return_value=mock_agent)
        master = self._make_dispatching_master([_make_task("task-001")])
        master._agent_factory = factory

        master.dispatch_task()
        assert "task-001" in master.execution_results

    def test_dispatch_failed_task(self):
        """失败任务正确记录"""
        mock_agent = MagicMock(spec=SubAgent)
        mock_agent.role_name = "senior-developer"
        mock_result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.FAILED,
            phase=AgentPhase.FAILED,
            role="senior-developer",
            error="Build failed",
        )
        mock_agent.run.return_value = mock_result

        factory = MagicMock(return_value=mock_agent)
        master = self._make_dispatching_master([_make_task("task-001")])
        master._agent_factory = factory

        result = master.dispatch_task()
        assert result.status == SubAgentResultStatus.FAILED
        assert master._task_json.tasks[0].status == TaskStatus.FAILED

    def test_dispatch_state_validation(self):
        """非 DISPATCHING/MONITORING 状态抛 RuntimeError"""
        master = MasterAgent()
        master._state = MasterAgentState.IDLE

        with pytest.raises(RuntimeError, match="Cannot dispatch task"):
            master.dispatch_task()

    def test_dispatch_in_monitoring_state(self):
        """MONITORING 状态下也可委派"""
        mock_agent = MagicMock(spec=SubAgent)
        mock_agent.role_name = "senior-developer"
        mock_result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.COMPLETED,
            role="senior-developer",
        )
        mock_agent.run.return_value = mock_result

        factory = MagicMock(return_value=mock_agent)
        master = MasterAgent()
        master._state = MasterAgentState.MONITORING
        master._task_json = _make_task_json([_make_task("task-001")])
        master._agent_factory = factory

        result = master.dispatch_task()
        assert result is not None

    def test_dispatch_concurrency_limit_respected(self):
        """委派受并发限制"""
        mock_agent = MagicMock(spec=SubAgent)
        mock_agent.role_name = "senior-developer"
        factory = MagicMock(return_value=mock_agent)

        master = self._make_dispatching_master(
            [_make_task("task-001"), _make_task("task-002")],
            max_concurrent=1,
        )
        master._agent_factory = factory

        # 第一次委派
        mock_result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.COMPLETED,
            role="senior-developer",
        )
        mock_agent.run.return_value = mock_result
        master.dispatch_task()

        # 此时 task-001 已完成并从 active_agents 移除
        # 但我们手动模拟一个正在运行的 agent
        master._active_agents["task-099"] = MagicMock(spec=SubAgent)

        result = master.dispatch_task()
        assert result is None  # 受并发限制


# ── SubAgentFactory + MasterAgent 集成 ───────────────────


class TestSubAgentFactoryMasterAgentIntegration:
    """SubAgentFactory 与 MasterAgent 集成"""

    def test_factory_as_agent_factory(self):
        """SubAgentFactory 可直接作为 agent_factory 使用"""
        tmux = _make_mock_tmux()
        factory = SubAgentFactory(tmux_manager=tmux)
        master = MasterAgent(
            agent_factory=factory,
            tmux_manager=tmux,
        )
        assert master._agent_factory is factory

    def test_create_pm_agent_with_factory(self):
        """通过工厂创建 PM Agent"""
        factory = SubAgentFactory()
        master = MasterAgent(agent_factory=factory)
        master.receive_requirement("Test requirement")
        pm = master.create_pm_agent()
        assert isinstance(pm, SubAgent)
        assert pm.role_name == "product-manager"

    def test_create_sub_agent_with_factory(self):
        """通过工厂创建任务 Agent"""
        factory = SubAgentFactory()
        master = MasterAgent(agent_factory=factory)
        master._state = MasterAgentState.DISPATCHING
        task = _make_task(suggested_role="senior-developer")
        agent = master.create_sub_agent(task)
        assert isinstance(agent, EphemeralSubAgent)
        assert agent.role_name == "senior-developer"

    def test_full_dispatch_flow(self):
        """完整委派流程"""
        tmux = _make_mock_tmux()
        cli = _make_mock_cli()

        # 窗口创建后 window_exists 应返回 True（模拟创建成功）
        def window_exists_side_effect(session, window):
            return True
        tmux.window_exists.side_effect = window_exists_side_effect

        factory = SubAgentFactory(tmux_manager=tmux, cli=cli)

        master = MasterAgent(
            agent_factory=factory,
            tmux_manager=tmux,
        )
        master._state = MasterAgentState.DISPATCHING
        task = _make_task("task-001", priority=TaskPriority.HIGH)
        master._task_json = _make_task_json([task])

        result = master.dispatch_task()
        assert result is not None
        assert result.is_success

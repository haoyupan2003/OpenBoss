"""
P2-014 测试 — AgentFactory.create(role_name) 角色映射与 SubAgent 创建

设计原则：
- **所有** Sub-Agent 统一通过 EphemeralSubAgent + tmux 窗口 + Claude CLI 创建
- ProductManagerAgent / SeniorDeveloperAgent / APIRequestAgent 是业务逻辑类，
  不是 EphemeralSubAgent 的替代品 — 它们定义角色行为和 harness 约束
- MasterAgent 是唯一持久存在的 Agent，它通过工厂创建临时 Sub-Agent
- 每个 Sub-Agent：分配 tmux 窗口 → 注入角色 prompt → 执行 task → 关闭窗口

测试内容：
- 所有已知角色都创建 EphemeralSubAgent 实例（统一架构）
- 角色名称、窗口分配、tmux 窗口创建
- 角色计数器、__call__ 协议兼容
- MasterAgent 集成
"""

import pytest
from unittest.mock import MagicMock

from agent_automation_system.master_agent.agent_factory import (
    EphemeralSubAgent,
    SubAgentFactory,
    _ROLE_SHORT_NAMES,
    _DEFAULT_ROLE_SHORT,
)
from agent_automation_system.sub_agent.sub_agent import SubAgent
from agent_automation_system.sub_agent.role_injector import RoleInjector
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


# ── 辅助工具 ──────────────────────────────────────────────


def _make_mock_tmux() -> MagicMock:
    tmux = MagicMock()
    tmux.session_exists.return_value = True
    tmux.window_exists.return_value = False
    return tmux


def _make_task(
    task_id: str = "task-001",
    title: str = "Test task",
    priority: TaskPriority = TaskPriority.MEDIUM,
    status: TaskStatus = TaskStatus.PENDING,
    suggested_role: str = "senior-developer",
) -> Task:
    return Task(
        id=task_id,
        title=title,
        description=f"Description for {title}",
        bdd=BDDSpec(given="context", when="action", then="result"),
        dependencies=[],
        priority=priority,
        status=status,
        suggested_role=suggested_role,
    )


def _make_task_json(tasks: list[Task]) -> TaskJSON:
    return TaskJSON(
        project_name="test-project",
        total_tasks=len(tasks),
        tasks=tasks,
    )


# ── 角色 → Agent 实例类型统一验证 ─────────────────────────


class TestAgentFactoryCreateUnified:
    """所有角色统一创建 EphemeralSubAgent 实例"""

    def test_senior_developer_creates_ephemeral(self):
        """'senior-developer' → EphemeralSubAgent（通过 tmux + CLI 执行）"""
        factory = SubAgentFactory()
        agent = factory.create("senior-developer")
        assert isinstance(agent, EphemeralSubAgent)
        assert isinstance(agent, SubAgent)
        assert agent.role_name == "senior-developer"

    def test_product_manager_creates_ephemeral(self):
        """'product-manager' → EphemeralSubAgent（通过 tmux + CLI 执行）"""
        factory = SubAgentFactory()
        agent = factory.create("product-manager")
        assert isinstance(agent, EphemeralSubAgent)
        assert agent.role_name == "product-manager"

    def test_api_request_creates_ephemeral(self):
        """'api-request' → EphemeralSubAgent（通过 tmux + CLI 执行）"""
        factory = SubAgentFactory()
        agent = factory.create("api-request")
        assert isinstance(agent, EphemeralSubAgent)
        assert agent.role_name == "api-request"

    def test_test_engineer_creates_ephemeral(self):
        """'test-engineer' → EphemeralSubAgent"""
        factory = SubAgentFactory()
        agent = factory.create("test-engineer")
        assert isinstance(agent, EphemeralSubAgent)
        assert agent.role_name == "test-engineer"

    def test_browser_task_creates_ephemeral(self):
        """'browser-task' → EphemeralSubAgent"""
        factory = SubAgentFactory()
        agent = factory.create("browser-task")
        assert isinstance(agent, EphemeralSubAgent)
        assert agent.role_name == "browser-task"

    def test_custom_role_creates_ephemeral(self):
        """未知角色 → EphemeralSubAgent"""
        factory = SubAgentFactory()
        agent = factory.create("custom-bot")
        assert isinstance(agent, EphemeralSubAgent)
        assert agent.role_name == "custom-bot"


# ── 角色名称匹配 ──────────────────────────────────────────


class TestAgentFactoryCreateRoleName:
    """创建的 Agent role_name 与传入参数一致"""

    def test_role_name_preserved_pm(self):
        """PM 角色名一致"""
        factory = SubAgentFactory()
        agent = factory.create("product-manager")
        assert agent.role_name == "product-manager"

    def test_role_name_preserved_dev(self):
        """Dev 角色名一致"""
        factory = SubAgentFactory()
        agent = factory.create("senior-developer")
        assert agent.role_name == "senior-developer"

    def test_role_name_preserved_api(self):
        """API 角色名一致"""
        factory = SubAgentFactory()
        agent = factory.create("api-request")
        assert agent.role_name == "api-request"

    def test_role_name_preserved_custom(self):
        """自定义角色名一致"""
        factory = SubAgentFactory()
        agent = factory.create("my-custom-agent")
        assert agent.role_name == "my-custom-agent"


# ── 窗口分配 ──────────────────────────────────────────────


class TestAgentFactoryCreateWindowAllocation:
    """所有角色都分配 tmux 窗口名称"""

    def test_dev_agent_has_window_name(self):
        """Dev Agent 分配窗口"""
        factory = SubAgentFactory()
        agent = factory.create("senior-developer")
        assert agent.window_name is not None
        assert "dev" in agent.window_name

    def test_pm_agent_has_window_name(self):
        """PM Agent 分配窗口"""
        factory = SubAgentFactory()
        agent = factory.create("product-manager")
        assert agent.window_name is not None
        assert "pm" in agent.window_name

    def test_api_agent_has_window_name(self):
        """API Agent 分配窗口"""
        factory = SubAgentFactory()
        agent = factory.create("api-request")
        assert agent.window_name is not None
        assert "api" in agent.window_name

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


# ── tmux 窗口创建 ─────────────────────────────────────────


class TestAgentFactoryCreateTmuxWindow:
    """tmux 窗口创建行为（所有角色统一）"""

    def test_dev_agent_creates_window(self):
        """Dev Agent 创建 tmux 窗口"""
        tmux = _make_mock_tmux()
        factory = SubAgentFactory(tmux_manager=tmux, auto_create_window=True)
        factory.create("senior-developer")
        tmux.create_window.assert_called_once()

    def test_pm_agent_creates_window(self):
        """PM Agent 创建 tmux 窗口"""
        tmux = _make_mock_tmux()
        factory = SubAgentFactory(tmux_manager=tmux, auto_create_window=True)
        factory.create("product-manager")
        tmux.create_window.assert_called_once()

    def test_api_agent_creates_window(self):
        """API Agent 创建 tmux 窗口"""
        tmux = _make_mock_tmux()
        factory = SubAgentFactory(tmux_manager=tmux, auto_create_window=True)
        factory.create("api-request")
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


# ── 错误处理 ──────────────────────────────────────────────


class TestAgentFactoryCreateErrorHandling:
    """create() 错误条件"""

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


# ── __call__ 协议兼容 ────────────────────────────────────


class TestAgentFactoryCreateCallable:
    """__call__ 兼容 MasterAgent 的 agent_factory 协议"""

    def test_callable_creates_ephemeral(self):
        """__call__ 创建 EphemeralSubAgent"""
        factory = SubAgentFactory()
        agent = factory("senior-developer")
        assert isinstance(agent, EphemeralSubAgent)
        assert agent.role_name == "senior-developer"

    def test_callable_same_as_create(self):
        """__call__ 和 create() 返回相同类型"""
        factory = SubAgentFactory()
        agent1 = factory.create("senior-developer")
        agent2 = factory("senior-developer")
        assert type(agent1) == type(agent2)
        assert agent1.role_name == agent2.role_name

    def test_callable_compatible_with_master(self):
        """兼容 MasterAgent 的 agent_factory 协议"""
        factory = SubAgentFactory()
        master = MasterAgent(agent_factory=factory)
        agent = master._agent_factory("product-manager")
        assert isinstance(agent, SubAgent)
        assert agent.role_name == "product-manager"


# ── 角色计数器 ────────────────────────────────────────────


class TestAgentFactoryCreateCounters:
    """所有角色的计数器行为统一"""

    def test_counter_increments_for_dev(self):
        """Dev 角色计数器递增"""
        factory = SubAgentFactory()
        assert factory.get_role_counter("senior-developer") == 0
        factory.create("senior-developer")
        assert factory.get_role_counter("senior-developer") == 1

    def test_counter_independent_for_mixed_roles(self):
        """混合角色计数器独立"""
        factory = SubAgentFactory()
        factory.create("senior-developer")
        factory.create("senior-developer")
        factory.create("product-manager")
        factory.create("test-engineer")

        assert factory.get_role_counter("senior-developer") == 2
        assert factory.get_role_counter("product-manager") == 1
        assert factory.get_role_counter("test-engineer") == 1

    def test_reset_clears_all_counters(self):
        """重置清空所有计数器"""
        factory = SubAgentFactory()
        factory.create("senior-developer")
        factory.create("test-engineer")
        factory.reset_counters()
        assert factory.get_role_counter("senior-developer") == 0
        assert factory.get_role_counter("test-engineer") == 0


# ── MasterAgent 集成 ─────────────────────────────────────


class TestAgentFactoryMasterAgentIntegration:
    """工厂与 MasterAgent 集成确认"""

    def test_factory_as_agent_factory(self):
        """SubAgentFactory 可直接作为 agent_factory 使用"""
        tmux = _make_mock_tmux()
        factory = SubAgentFactory(tmux_manager=tmux)
        master = MasterAgent(agent_factory=factory, tmux_manager=tmux)
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
        """通过工厂创建任务 Sub-Agent"""
        factory = SubAgentFactory()
        master = MasterAgent(agent_factory=factory)
        master._state = MasterAgentState.DISPATCHING
        task = _make_task(suggested_role="senior-developer")
        agent = master.create_sub_agent(task)
        assert isinstance(agent, EphemeralSubAgent)
        assert agent.role_name == "senior-developer"

    def test_create_sub_agent_custom_role(self):
        """通过工厂创建自定义角色 Sub-Agent"""
        factory = SubAgentFactory()
        master = MasterAgent(agent_factory=factory)
        master._state = MasterAgentState.DISPATCHING
        task = _make_task(suggested_role="data-analyst")
        agent = master.create_sub_agent(task)
        assert isinstance(agent, EphemeralSubAgent)
        assert agent.role_name == "data-analyst"

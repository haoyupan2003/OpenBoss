"""
P2-015 测试 — AgentFactory 单元测试补充

填补 P1-048 和 P2-014 未覆盖的场景：
- 工厂属性访问（properties）
- get_role_counter 边界条件
- 多工厂隔离
- reset_counters 后创建行为
- None role_name 处理
- 特殊 role_name 格式
- 会话名称定制
- 8 种角色简称全覆盖
"""

import pytest
from unittest.mock import MagicMock

from agent_automation_system.master_agent.agent_factory import (
    EphemeralSubAgent,
    SubAgentFactory,
    _ROLE_SHORT_NAMES,
    _DEFAULT_ROLE_SHORT,
    _DEFAULT_SESSION_NAME,
)
from agent_automation_system.sub_agent.sub_agent import SubAgent
from agent_automation_system.sub_agent.role_injector import RoleInjector


# ── 辅助工具 ──────────────────────────────────────────────

def _make_mock_tmux() -> MagicMock:
    tmux = MagicMock()
    tmux.session_exists.return_value = True
    tmux.window_exists.return_value = False
    return tmux


# ── 工厂属性访问 ──────────────────────────────────────────


class TestSubAgentFactoryProperties:
    """工厂构造函数注入的属性可正常访问"""

    def test_tmux_manager_property(self):
        """tmux_manager 属性返回注入的实例"""
        tmux = _make_mock_tmux()
        factory = SubAgentFactory(tmux_manager=tmux)
        assert factory.tmux_manager is tmux

    def test_tmux_manager_none_by_default(self):
        """默认不传 tmux_manager 时属性为 None"""
        factory = SubAgentFactory()
        assert factory.tmux_manager is None

    def test_cli_property(self):
        """cli 属性返回注入的实例"""
        mock_cli = MagicMock()
        factory = SubAgentFactory(cli=mock_cli)
        assert factory.cli is mock_cli

    def test_cli_none_by_default(self):
        """默认不传 cli 时属性为 None"""
        factory = SubAgentFactory()
        assert factory.cli is None

    def test_role_injector_property(self):
        """role_injector 属性返回注入的实例"""
        custom = MagicMock(spec=RoleInjector)
        factory = SubAgentFactory(role_injector=custom)
        assert factory.role_injector is custom

    def test_role_injector_default_created(self):
        """不传 role_injector 时自动创建"""
        factory = SubAgentFactory()
        assert isinstance(factory.role_injector, RoleInjector)

    def test_session_name_property(self):
        """session_name 属性返回传入值"""
        factory = SubAgentFactory(session_name="my-session")
        assert factory.session_name == "my-session"

    def test_session_name_default(self):
        """不传 session_name 时使用默认值"""
        factory = SubAgentFactory()
        assert factory.session_name == _DEFAULT_SESSION_NAME

    def test_auto_create_window_property(self):
        """auto_create_window 属性返回传入值"""
        factory = SubAgentFactory(auto_create_window=False)
        assert factory.auto_create_window is False

    def test_auto_create_window_default(self):
        """默认 auto_create_window 为 True"""
        factory = SubAgentFactory()
        assert factory.auto_create_window is True


# ── get_role_counter 边界 ────────────────────────────────


class TestSubAgentFactoryGetRoleCounter:
    """get_role_counter 边界条件"""

    def test_never_created_role_returns_zero(self):
        """从未创建过的角色返回 0"""
        factory = SubAgentFactory()
        assert factory.get_role_counter("senior-developer") == 0

    def test_unknown_role_returns_zero(self):
        """未知角色返回 0"""
        factory = SubAgentFactory()
        assert factory.get_role_counter("non-existent-role") == 0

    def test_created_once_returns_one(self):
        """创建一次后返回 1"""
        factory = SubAgentFactory()
        factory.create("test-engineer")
        assert factory.get_role_counter("test-engineer") == 1

    def test_created_thrice_returns_three(self):
        """创建三次后返回 3"""
        factory = SubAgentFactory()
        for _ in range(3):
            factory.create("test-engineer")
        assert factory.get_role_counter("test-engineer") == 3

    def test_after_reset_returns_zero(self):
        """reset 后返回 0"""
        factory = SubAgentFactory()
        factory.create("senior-developer")
        factory.create("senior-developer")
        factory.reset_counters()
        assert factory.get_role_counter("senior-developer") == 0


# ── 多工厂隔离 ────────────────────────────────────────────


class TestSubAgentFactoryIsolation:
    """多个工厂实例的计数器互不干扰"""

    def test_counters_isolated_between_factories(self):
        """两个工厂各自维护独立计数器"""
        f1 = SubAgentFactory()
        f2 = SubAgentFactory()

        f1.create("senior-developer")
        f1.create("senior-developer")
        f2.create("senior-developer")

        assert f1.get_role_counter("senior-developer") == 2
        assert f2.get_role_counter("senior-developer") == 1

    def test_write_to_one_does_not_affect_other(self):
        """对 f1 创建不影响 f2 的同名角色计数"""
        f1 = SubAgentFactory()
        f2 = SubAgentFactory()

        f1.create("test-engineer")
        assert f2.get_role_counter("test-engineer") == 0


# ── reset_counters 后创建 ─────────────────────────────────


class TestSubAgentFactoryResetAndCreate:
    """reset_counters 后重新创建的序列号行为"""

    def test_window_name_restarts_after_reset(self):
        """reset 后窗口序号重新从 001 开始"""
        factory = SubAgentFactory()
        factory.create("senior-developer")  # agent_dev_001
        factory.create("senior-developer")  # agent_dev_002
        factory.reset_counters()
        agent = factory.create("senior-developer")
        assert "agent_dev_001" in agent.window_name

    def test_counter_restarts_after_reset(self):
        """reset 后计数器归零再递增"""
        factory = SubAgentFactory()
        factory.create("product-manager")
        factory.create("product-manager")
        factory.create("product-manager")
        factory.reset_counters()
        assert factory.get_role_counter("product-manager") == 0
        factory.create("product-manager")
        assert factory.get_role_counter("product-manager") == 1

    def test_double_reset_idempotent(self):
        """连续两次 reset 不影响后续创建"""
        factory = SubAgentFactory()
        factory.create("senior-developer")
        factory.reset_counters()
        factory.reset_counters()
        agent = factory.create("senior-developer")
        assert "agent_dev_001" in agent.window_name


# ── 窗口名称格式 ──────────────────────────────────────────


class TestSubAgentFactoryWindowNameFormat:
    """窗口名称格式验证"""

    def test_window_name_format_pattern(self):
        """窗口名称格式为 agent_{short}_{seq:03d}"""
        factory = SubAgentFactory()
        factory.create("senior-developer")  # agent_dev_001
        factory.create("senior-developer")  # agent_dev_002
        agent = factory.create("senior-developer")  # agent_dev_003
        assert agent.window_name == "agent_dev_003"

    def test_default_short_window_name(self):
        """未知角色使用默认简称 agent"""
        factory = SubAgentFactory()
        agent = factory.create("my-bot")
        assert agent.window_name.startswith("agent_agent_")
        assert agent.window_name == "agent_agent_001"

    def test_role_with_leading_trailing_whitespace_stripped(self):
        """带前后空格的角色名被 trim 后正常分配窗口"""
        factory = SubAgentFactory()
        agent = factory.create("  senior-developer  ")
        assert "agent_dev_001" in agent.window_name
        assert agent.role_name == "senior-developer"


# ── None role_name ────────────────────────────────────────


class TestSubAgentFactoryNoneRoleName:
    """None 角色名处理"""

    def test_none_role_name_raises_value_error(self):
        """传入 None 抛 ValueError"""
        factory = SubAgentFactory()
        with pytest.raises(ValueError):
            factory.create(None)


# ── 完整角色简称映射覆盖 ──────────────────────────────────


class TestSubAgentFactoryRoleShortNames:
    """所有 8 种内置角色简称验证"""

    def test_senior_developer_short_is_dev(self):
        assert _ROLE_SHORT_NAMES["senior-developer"] == "dev"

    def test_test_engineer_short_is_qa(self):
        assert _ROLE_SHORT_NAMES["test-engineer"] == "qa"

    def test_product_manager_short_is_pm(self):
        assert _ROLE_SHORT_NAMES["product-manager"] == "pm"

    def test_validator_short_is_val(self):
        assert _ROLE_SHORT_NAMES["validator"] == "val"

    def test_senior_screenwriter_short_is_sw(self):
        assert _ROLE_SHORT_NAMES["senior-screenwriter"] == "sw"

    def test_data_analyst_short_is_da(self):
        assert _ROLE_SHORT_NAMES["data-analyst"] == "da"

    def test_browser_task_short_is_bt(self):
        assert _ROLE_SHORT_NAMES["browser-task"] == "bt"

    def test_api_request_short_is_api(self):
        assert _ROLE_SHORT_NAMES["api-request"] == "api"

    def test_total_eight_roles_mapped(self):
        """共 8 个内置角色有简称映射"""
        assert len(_ROLE_SHORT_NAMES) == 8


# ── 会话名称定制 ──────────────────────────────────────────


class TestSubAgentFactoryCustomSession:
    """自定义 session_name 的工厂行为"""

    def test_custom_session_name_on_agent(self):
        """自定义 session_name 传递给 Agent"""
        factory = SubAgentFactory(session_name="prod-session")
        agent = factory.create("senior-developer")
        assert agent.session_name == "prod-session"

    def test_default_session_name_on_agent(self):
        """默认 session_name = 'openboss'"""
        factory = SubAgentFactory()
        agent = factory.create("senior-developer")
        assert agent.session_name == "openboss"


# ── __call__ 错误传播 ─────────────────────────────────────


class TestSubAgentFactoryCallableErrors:
    """__call__ 应正确传播 create() 的错误"""

    def test_callable_raises_on_empty_role(self):
        """__call__ 空角色抛异常"""
        factory = SubAgentFactory()
        with pytest.raises(ValueError, match="role_name cannot be empty"):
            factory("")

    def test_callable_raises_on_whitespace_role(self):
        """__call__ 纯空格抛异常"""
        factory = SubAgentFactory()
        with pytest.raises(ValueError, match="role_name cannot be empty"):
            factory("   ")

    def test_callable_raises_on_none_role(self):
        """__call__ None 角色抛异常"""
        factory = SubAgentFactory()
        with pytest.raises(ValueError):
            factory(None)

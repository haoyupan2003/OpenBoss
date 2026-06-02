"""
P1-045: Master Agent 启动流程 — 单元测试

覆盖范围：
- startup() 主流程 (6)
- _load_main_rules (7)
- _init_tmux_session (6)
- _start_main_cli (6)
- _build_main_prompt (4)
- 新属性 (6)
- reset 清理启动状态 (2)
- 与原有功能兼容性 (3)
合计: 40 项
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from agent_automation_system.master_agent.master_agent import (
    MasterAgent,
    MasterAgentState,
    _MAIN_WINDOW_NAME,
)
from agent_automation_system.sub_agent.sub_agent import SubAgent


# ── 测试辅助 ──────────────────────────────────────────────


def _make_sub_agent(role_name: str = "dev") -> MagicMock:
    """创建 Mock SubAgent"""
    agent = MagicMock(spec=SubAgent)
    agent.role_name = role_name
    return agent


def _make_agent_factory(role_name_to_agent: dict[str, MagicMock] | None = None):
    """创建 Mock Agent Factory"""
    if role_name_to_agent is None:
        role_name_to_agent = {}

    def factory(role_name: str) -> MagicMock:
        if role_name in role_name_to_agent:
            return role_name_to_agent[role_name]
        return _make_sub_agent(role_name)

    return factory


def _make_mock_tmux() -> MagicMock:
    """创建 Mock TmuxManager"""
    tmux = MagicMock()
    tmux.is_available.return_value = True
    tmux.session_exists.return_value = False
    tmux.window_exists.return_value = False
    return tmux


def _make_mock_cli() -> MagicMock:
    """创建 Mock ClaudeCodeCLI"""
    cli = MagicMock()
    return cli


def _create_main_rules_file(content: str | None = None) -> str:
    """创建临时 main-rules.md 文件，返回路径"""
    if content is None:
        content = (
            "# Master Agent Rules\n\n"
            "## DO\n"
            "- Always review task.json before dispatching\n"
            "- Monitor Sub-Agent progress actively\n\n"
            "## DON'T\n"
            "- Never skip dependency checks\n\n"
        )
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, prefix="main-rules-"
    )
    f.write(content)
    f.close()
    return f.name


# ── startup() 主流程 ──────────────────────────────────────


class TestStartup:
    """startup() 主流程测试"""

    def test_startup_basic_success(self):
        """基本启动流程：无 tmux/cli，仅加载 main-rules"""
        rules_path = _create_main_rules_file()
        try:
            master = MasterAgent(
                main_rules_path=rules_path,
                agent_factory=_make_agent_factory(),
            )
            master.startup()
            assert master.is_started is True
            assert master.main_rules_content is not None
            assert "Always review" in master.main_rules_content
        finally:
            Path(rules_path).unlink(missing_ok=True)

    def test_startup_with_all_dependencies(self):
        """完整启动流程：tmux + cli + main-rules"""
        rules_path = _create_main_rules_file()
        tmux = _make_mock_tmux()
        cli = _make_mock_cli()
        try:
            master = MasterAgent(
                tmux_manager=tmux,
                cli=cli,
                main_rules_path=rules_path,
                agent_factory=_make_agent_factory(),
            )
            # 模拟 _init_tmux_session 创建会话后 session/window 存在
            tmux.session_exists.side_effect = lambda name: True
            tmux.window_exists.side_effect = lambda s, w: True

            master.startup()
            assert master.is_started is True
            # 验证 tmux 会话创建（已存在时不会调用，因为 side_effect 返回 True）
            # 验证 CLI 启动
            cli.start_cli.assert_called_once()
            call_kwargs = cli.start_cli.call_args
            assert call_kwargs.kwargs["session"] == "openboss"
            assert call_kwargs.kwargs["window"] == _MAIN_WINDOW_NAME
        finally:
            Path(rules_path).unlink(missing_ok=True)

    def test_startup_no_rules_path_no_tmux_no_cli(self):
        """无规则路径、无 tmux、无 CLI — 启动仍成功"""
        master = MasterAgent(agent_factory=_make_agent_factory())
        master.startup()
        assert master.is_started is True
        assert master.main_rules_content is None

    def test_startup_raises_on_duplicate(self):
        """重复启动抛出 RuntimeError"""
        master = MasterAgent(agent_factory=_make_agent_factory())
        master.startup()
        with pytest.raises(RuntimeError, match="already started"):
            master.startup()

    def test_startup_with_runtime_main_rules_path(self):
        """通过 startup() 参数覆盖 main_rules_path"""
        rules_path = _create_main_rules_file()
        try:
            master = MasterAgent(agent_factory=_make_agent_factory())
            master.startup(main_rules_path=rules_path)
            assert master.is_started is True
            assert master.main_rules_content is not None
            assert master.main_rules_path == rules_path
        finally:
            Path(rules_path).unlink(missing_ok=True)

    def test_startup_tmux_unavailable_raises(self):
        """tmux 不可用时启动抛出 RuntimeError"""
        tmux = _make_mock_tmux()
        tmux.is_available.return_value = False
        master = MasterAgent(
            tmux_manager=tmux,
            agent_factory=_make_agent_factory(),
        )
        with pytest.raises(RuntimeError, match="tmux is not available"):
            master.startup()


# ── _load_main_rules ─────────────────────────────────────


class TestLoadMainRules:
    """_load_main_rules() 测试"""

    def test_load_valid_rules_file(self):
        """加载有效的 main-rules.md 文件"""
        rules_path = _create_main_rules_file()
        try:
            master = MasterAgent(agent_factory=_make_agent_factory())
            master._load_main_rules(rules_path)
            assert master.main_rules_content is not None
            assert "Always review" in master.main_rules_content
            assert master.main_rules_path == rules_path
        finally:
            Path(rules_path).unlink(missing_ok=True)

    def test_load_nonexistent_file_raises(self):
        """加载不存在的文件抛出 FileNotFoundError"""
        master = MasterAgent(agent_factory=_make_agent_factory())
        with pytest.raises(FileNotFoundError, match="main-rules.md not found"):
            master._load_main_rules("/nonexistent/main-rules.md")

    def test_skip_when_no_path(self):
        """无路径时跳过加载"""
        master = MasterAgent(agent_factory=_make_agent_factory())
        master._load_main_rules(None)
        assert master.main_rules_content is None

    def test_skip_when_empty_path(self):
        """空路径时跳过加载"""
        master = MasterAgent(agent_factory=_make_agent_factory())
        master._load_main_rules("")
        assert master.main_rules_content is None

    def test_lazy_create_harness_loader(self):
        """无 harness_loader 时懒创建"""
        rules_path = _create_main_rules_file()
        try:
            master = MasterAgent(agent_factory=_make_agent_factory())
            assert master._harness_loader is None
            master._load_main_rules(rules_path)
            assert master._harness_loader is not None
        finally:
            Path(rules_path).unlink(missing_ok=True)

    def test_reuse_existing_harness_loader(self):
        """复用已有的 harness_loader"""
        rules_path = _create_main_rules_file()
        try:
            mock_loader = MagicMock()
            mock_harness = MagicMock()
            mock_harness.to_prompt_text.return_value = "mock rules"
            mock_harness.name = "Mock Rules"
            mock_harness.rules = []
            mock_loader.load_harness.return_value = mock_harness

            master = MasterAgent(
                agent_factory=_make_agent_factory(),
                harness_loader=mock_loader,
            )
            master._load_main_rules(rules_path)
            mock_loader.load_harness.assert_called_once_with(rules_path)
            assert master.main_rules_content == "mock rules"
        finally:
            Path(rules_path).unlink(missing_ok=True)

    def test_load_preserves_harness_structure(self):
        """加载后保留 harness 结构化内容"""
        content = (
            "# Test Rules\n\n"
            "## DO\n"
            "- Rule A\n"
            "- Rule B\n\n"
            "## DON'T\n"
            "- Bad thing\n\n"
            "## Constraints\n"
            "- Max 3 agents\n\n"
        )
        rules_path = _create_main_rules_file(content)
        try:
            master = MasterAgent(agent_factory=_make_agent_factory())
            master._load_main_rules(rules_path)
            assert "Rule A" in master.main_rules_content
            assert "Bad thing" in master.main_rules_content
            assert "Max 3 agents" in master.main_rules_content
        finally:
            Path(rules_path).unlink(missing_ok=True)


# ── _init_tmux_session ───────────────────────────────────


class TestInitTmuxSession:
    """_init_tmux_session() 测试"""

    def test_create_new_session(self):
        """创建新 tmux 会话"""
        tmux = _make_mock_tmux()
        master = MasterAgent(
            tmux_manager=tmux,
            agent_factory=_make_agent_factory(),
        )
        master._init_tmux_session()
        tmux.create_session.assert_called_once_with(
            name="openboss",
            window_name=_MAIN_WINDOW_NAME,
        )

    def test_reuse_existing_session(self):
        """复用已有 tmux 会话"""
        tmux = _make_mock_tmux()
        tmux.session_exists.return_value = True
        tmux.window_exists.return_value = True

        master = MasterAgent(
            tmux_manager=tmux,
            agent_factory=_make_agent_factory(),
        )
        master._init_tmux_session()
        tmux.create_session.assert_not_called()
        tmux.create_window.assert_not_called()

    def test_reuse_session_create_missing_main_window(self):
        """复用会话但创建缺失的 main 窗口"""
        tmux = _make_mock_tmux()
        tmux.session_exists.return_value = True
        tmux.window_exists.return_value = False

        master = MasterAgent(
            tmux_manager=tmux,
            agent_factory=_make_agent_factory(),
        )
        master._init_tmux_session()
        tmux.create_session.assert_not_called()
        tmux.create_window.assert_called_once_with(
            session="openboss",
            name=_MAIN_WINDOW_NAME,
        )

    def test_skip_when_no_tmux_manager(self):
        """无 tmux_manager 时跳过"""
        master = MasterAgent(agent_factory=_make_agent_factory())
        master._init_tmux_session()  # 不应抛异常

    def test_tmux_unavailable_raises(self):
        """tmux 不可用时抛出 RuntimeError"""
        tmux = _make_mock_tmux()
        tmux.is_available.return_value = False
        master = MasterAgent(
            tmux_manager=tmux,
            agent_factory=_make_agent_factory(),
        )
        with pytest.raises(RuntimeError, match="tmux is not available"):
            master._init_tmux_session()

    def test_custom_session_name(self):
        """自定义会话名称"""
        tmux = _make_mock_tmux()
        master = MasterAgent(
            tmux_manager=tmux,
            agent_factory=_make_agent_factory(),
            session_name="my-project",
        )
        master._init_tmux_session()
        tmux.create_session.assert_called_once_with(
            name="my-project",
            window_name=_MAIN_WINDOW_NAME,
        )


# ── _start_main_cli ──────────────────────────────────────


class TestStartMainCli:
    """_start_main_cli() 测试"""

    def test_start_cli_with_rules_prompt(self):
        """启动 CLI 并注入 main-rules prompt"""
        tmux = _make_mock_tmux()
        tmux.session_exists.return_value = True
        tmux.window_exists.return_value = True
        cli = _make_mock_cli()
        rules_path = _create_main_rules_file()

        try:
            master = MasterAgent(
                tmux_manager=tmux,
                cli=cli,
                main_rules_path=rules_path,
                agent_factory=_make_agent_factory(),
            )
            # 先完成前两步
            master._load_main_rules(rules_path)
            master._init_tmux_session()
            master._start_main_cli()

            cli.start_cli.assert_called_once()
            call_kwargs = cli.start_cli.call_args.kwargs
            assert call_kwargs["session"] == "openboss"
            assert call_kwargs["window"] == _MAIN_WINDOW_NAME
            assert call_kwargs["prompt"] is not None
            assert "Master Agent" in call_kwargs["prompt"]
        finally:
            Path(rules_path).unlink(missing_ok=True)

    def test_start_cli_without_rules(self):
        """无 main-rules 时仍能启动 CLI（仅注入角色身份）"""
        tmux = _make_mock_tmux()
        tmux.session_exists.return_value = True
        tmux.window_exists.return_value = True
        cli = _make_mock_cli()

        master = MasterAgent(
            tmux_manager=tmux,
            cli=cli,
            agent_factory=_make_agent_factory(),
        )
        master._init_tmux_session()
        master._start_main_cli()

        cli.start_cli.assert_called_once()
        call_kwargs = cli.start_cli.call_args.kwargs
        # 仍有角色身份 prompt
        assert call_kwargs["prompt"] is not None
        assert "Master Agent" in call_kwargs["prompt"]

    def test_skip_when_no_cli(self):
        """无 CLI 时跳过启动"""
        master = MasterAgent(agent_factory=_make_agent_factory())
        master._start_main_cli()  # 不应抛异常

    def test_session_not_initialized_raises(self):
        """tmux 会话未初始化时启动 CLI 抛出 RuntimeError"""
        tmux = _make_mock_tmux()
        tmux.session_exists.return_value = False
        cli = _make_mock_cli()

        master = MasterAgent(
            tmux_manager=tmux,
            cli=cli,
            agent_factory=_make_agent_factory(),
        )
        with pytest.raises(RuntimeError, match="not initialized"):
            master._start_main_cli()

    def test_window_not_found_raises(self):
        """tmux main 窗口不存在时抛出 RuntimeError"""
        tmux = _make_mock_tmux()
        tmux.session_exists.return_value = True
        tmux.window_exists.return_value = False
        cli = _make_mock_cli()

        master = MasterAgent(
            tmux_manager=tmux,
            cli=cli,
            agent_factory=_make_agent_factory(),
        )
        with pytest.raises(RuntimeError, match="main window not found"):
            master._start_main_cli()

    def test_start_cli_without_tmux_manager(self):
        """无 tmux_manager 时直接启动 CLI（跳过会话校验）"""
        cli = _make_mock_cli()
        master = MasterAgent(
            cli=cli,
            agent_factory=_make_agent_factory(),
        )
        master._start_main_cli()
        cli.start_cli.assert_called_once()


# ── _build_main_prompt ───────────────────────────────────


class TestBuildMainPrompt:
    """_build_main_prompt() 测试"""

    def test_prompt_contains_role_identity(self):
        """prompt 包含 Master Agent 角色身份"""
        master = MasterAgent(agent_factory=_make_agent_factory())
        prompt = master._build_main_prompt()
        assert "Master Agent" in prompt
        assert "角色身份" in prompt

    def test_prompt_contains_rules_when_loaded(self):
        """已加载 main-rules 时 prompt 包含约束规则"""
        rules_path = _create_main_rules_file()
        try:
            master = MasterAgent(agent_factory=_make_agent_factory())
            master._load_main_rules(rules_path)
            prompt = master._build_main_prompt()
            assert "约束规则" in prompt
            assert "Always review" in prompt
        finally:
            Path(rules_path).unlink(missing_ok=True)

    def test_prompt_no_rules_when_not_loaded(self):
        """未加载 main-rules 时 prompt 不含约束规则段"""
        master = MasterAgent(agent_factory=_make_agent_factory())
        prompt = master._build_main_prompt()
        assert "约束规则" not in prompt

    def test_prompt_lazy_creates_role_injector(self):
        """构建 prompt 时懒创建 RoleInjector"""
        master = MasterAgent(agent_factory=_make_agent_factory())
        assert master._role_injector is None
        prompt = master._build_main_prompt()
        assert master._role_injector is not None
        assert len(prompt) > 0


# ── 新属性 ────────────────────────────────────────────────


class TestNewProperties:
    """P1-045 新增属性测试"""

    def test_is_started_default_false(self):
        """is_started 默认为 False"""
        master = MasterAgent(agent_factory=_make_agent_factory())
        assert master.is_started is False

    def test_main_rules_content_default_none(self):
        """main_rules_content 默认为 None"""
        master = MasterAgent(agent_factory=_make_agent_factory())
        assert master.main_rules_content is None

    def test_tmux_manager_property(self):
        """tmux_manager 属性"""
        tmux = _make_mock_tmux()
        master = MasterAgent(
            tmux_manager=tmux,
            agent_factory=_make_agent_factory(),
        )
        assert master.tmux_manager is tmux

    def test_cli_property(self):
        """cli 属性"""
        cli = _make_mock_cli()
        master = MasterAgent(
            cli=cli,
            agent_factory=_make_agent_factory(),
        )
        assert master.cli is cli

    def test_main_rules_path_default_none(self):
        """main_rules_path 默认为 None"""
        master = MasterAgent(agent_factory=_make_agent_factory())
        assert master.main_rules_path is None

    def test_main_rules_path_set_via_constructor(self):
        """通过构造函数设置 main_rules_path"""
        master = MasterAgent(
            main_rules_path="/some/path/main-rules.md",
            agent_factory=_make_agent_factory(),
        )
        assert master.main_rules_path == "/some/path/main-rules.md"


# ── reset 清理启动状态 ────────────────────────────────────


class TestResetStartupState:
    """reset() 是否正确清理启动状态"""

    def test_reset_clears_is_started(self):
        """reset 后 is_started 变为 False"""
        master = MasterAgent(agent_factory=_make_agent_factory())
        master.startup()
        assert master.is_started is True
        master.reset()
        assert master.is_started is False

    def test_reset_clears_main_rules_content(self):
        """reset 后 main_rules_content 变为 None"""
        rules_path = _create_main_rules_file()
        try:
            master = MasterAgent(
                main_rules_path=rules_path,
                agent_factory=_make_agent_factory(),
            )
            master.startup()
            assert master.main_rules_content is not None
            master.reset()
            assert master.main_rules_content is None
        finally:
            Path(rules_path).unlink(missing_ok=True)


# ── 与原有功能兼容性 ──────────────────────────────────────


class TestBackwardCompatibility:
    """确保 P1-045 变更不破坏原有功能"""

    def test_receive_requirement_still_works(self):
        """receive_requirement 仍正常工作"""
        master = MasterAgent(agent_factory=_make_agent_factory())
        master.receive_requirement("实现登录功能")
        assert master.state == MasterAgentState.ANALYZING
        assert master.requirement == "实现登录功能"

    def test_constructor_backward_compatible(self):
        """构造函数向后兼容 — 旧参数仍可用"""
        master = MasterAgent(
            agent_factory=_make_agent_factory(),
            session_name="test",
            max_concurrent_agents=5,
        )
        assert master.session_name == "test"
        assert master.max_concurrent_agents == 5
        assert master.tmux_manager is None
        assert master.cli is None

    def test_full_workflow_with_startup(self):
        """完整工作流：startup → receive_requirement → set_task_json"""
        from agent_automation_system.models.task import Task, TaskPriority, TaskStatus
        from agent_automation_system.models.task_json import TaskJSON

        master = MasterAgent(agent_factory=_make_agent_factory())
        master.startup()

        master.receive_requirement("实现用户系统")
        assert master.state == MasterAgentState.ANALYZING

        task = Task(
            id="task-001",
            title="实现登录",
            description="登录功能",
            priority=TaskPriority.HIGH,
            status=TaskStatus.PENDING,
        )
        task_json = TaskJSON(
            project_name="test-project",
            total_tasks=1,
            tasks=[task],
        )
        master.set_task_json(task_json)
        assert master.state == MasterAgentState.DISPATCHING

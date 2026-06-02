"""
P1-062: 集成测试 — tmux 会话创建/销毁 + CLI 启动/关闭 完整流程

验证 TmuxManager 与 ClaudeCodeCLI 协同工作的集成场景：
  1. tmux 会话生命周期（创建 → 窗口管理 → 销毁）
  2. CLI 启动与 tmux 窗口交互（启动 → 就绪检测 → prompt 注入 → 停止）
  3. 完整工作流：创建会话 → 创建窗口 → 启动 CLI → 交互 → 停止 CLI → 销毁会话
  4. 异常恢复场景
  5. 多会话/多窗口并发管理

使用 mock 隔离 libtmux/Claude Code CLI 外部依赖，验证两个模块间的协作逻辑。
"""

import pytest
from unittest.mock import MagicMock, patch

from agent_automation_system.cli.claude_code_cli import (
    CLIStatus,
    ClaudeCodeCLI,
    _CLI_READY_PATTERNS,
    _DEFAULT_CLI_COMMAND,
)
from agent_automation_system.tmux_manager.tmux_manager import TmuxManager


# ── Fixtures ────────────────────────────────────────────────

@pytest.fixture
def mock_server():
    """创建 mock libtmux.Server"""
    server = MagicMock()
    server.is_alive.return_value = True
    server.has_session.return_value = False

    # mock sessions 集合（支持 .filter()）
    mock_sessions = MagicMock()
    mock_sessions.filter.return_value = []
    server.sessions = mock_sessions

    # mock new_session 返回值
    mock_session = MagicMock()
    mock_session.name = "test_session"
    server.new_session.return_value = mock_session

    return server


@pytest.fixture
def available_tmux(mock_server):
    """创建可用的 TmuxManager 实例（注入 mock server）"""
    mgr = TmuxManager()
    mgr._available = True
    mgr._server = mock_server
    return mgr


@pytest.fixture
def cli(available_tmux):
    """创建基于 available_tmux 的 ClaudeCodeCLI 实例"""
    return ClaudeCodeCLI(
        tmux_manager=available_tmux,
        startup_timeout=1.0,
        ready_check_interval=0.1,
    )


def _make_mock_session(name: str) -> MagicMock:
    """创建 mock libtmux.Session（windows 用 MagicMock 支持 .filter()）"""
    session = MagicMock()
    session.name = name

    # 关键：windows 必须是 MagicMock 以支持 .filter()
    mock_windows = MagicMock()
    mock_windows.filter.return_value = []
    session.windows = mock_windows

    session.new_window = MagicMock()
    session.kill_window = MagicMock()
    return session


def _make_mock_window(name: str) -> MagicMock:
    """创建 mock libtmux.Window"""
    window = MagicMock()
    window.name = name
    window.window_name = name
    pane = MagicMock()
    pane.capture_pane.return_value = []
    window.active_pane = pane
    return window


def _setup_session_and_window(available_tmux, session_name, window_name):
    """
    辅助：设置完整的 session + window mock 链路。
    配置 server.sessions.filter → [session]，session.windows.filter → [window]
    使 session_exists / window_exists / _get_session / _get_window 全部通过。
    """
    mock_server = available_tmux._server
    mock_session = _make_mock_session(session_name)
    mock_window = _make_mock_window(window_name)

    # session 存在
    mock_server.has_session.return_value = True

    # server.sessions.filter → [session]
    def filter_sessions(**kwargs):
        if kwargs.get("session_name") == session_name:
            return [mock_session]
        return []
    mock_server.sessions.filter.side_effect = filter_sessions

    # window 存在：session.windows.filter → [window]
    def filter_windows(**kwargs):
        if kwargs.get("window_name") == window_name:
            return [mock_window]
        return []
    mock_session.windows.filter.side_effect = filter_windows

    # list_windows 遍历需要 .windows 迭代
    # 通过 __iter__ 让 for w in session.windows 返回 [mock_window]
    mock_session.windows.__iter__.return_value = [mock_window]

    return mock_session, mock_window


# ══════════════════════════════════════════════════════════
# 1. tmux 会话生命周期集成
# ══════════════════════════════════════════════════════════
class TestTmuxSessionLifecycle:
    """tmux 会话创建 → 窗口管理 → 销毁完整生命周期"""

    def test_create_session_and_verify_exists(self, available_tmux, mock_server):
        """创建会话后 session_exists 返回 True"""
        assert not available_tmux.session_exists("boss")

        session = available_tmux.create_session("boss")
        assert session is not None

        mock_server.has_session.return_value = True
        assert available_tmux.session_exists("boss")

    def test_create_session_with_window(self, available_tmux, mock_server):
        """创建会话并指定初始窗口名"""
        session = available_tmux.create_session("boss", window_name="main")
        assert session is not None
        mock_server.new_session.assert_called_once_with(
            session_name="boss", detach=True, window_name="main"
        )

    def test_create_session_with_start_directory(self, available_tmux, mock_server):
        """创建会话并指定工作目录"""
        available_tmux.create_session("boss", start_directory="/tmp/project")
        mock_server.new_session.assert_called_once_with(
            session_name="boss", detach=True, start_directory="/tmp/project"
        )

    def test_create_multiple_sessions(self, available_tmux, mock_server):
        """创建多个会话并列出"""
        s1 = _make_mock_session("boss")
        s2 = _make_mock_session("agent_dev_001")
        mock_server.sessions.__iter__.return_value = [s1, s2]

        sessions = available_tmux.list_sessions()
        assert "boss" in sessions
        assert "agent_dev_001" in sessions

    def test_kill_session_removes_from_list(self, available_tmux, mock_server):
        """销毁会话后不再出现在列表中"""
        available_tmux.create_session("boss")
        mock_server.has_session.return_value = True

        result = available_tmux.kill_session("boss")
        assert result is True
        mock_server.kill_session.assert_called_once_with("boss")

    def test_kill_nonexistent_session_returns_false(self, available_tmux, mock_server):
        """销毁不存在的会话返回 False"""
        mock_server.has_session.return_value = False
        result = available_tmux.kill_session("nonexistent")
        assert result is False

    def test_create_kill_create_session(self, available_tmux, mock_server):
        """创建 → 销毁 → 重新创建会话"""
        # Step 1: 创建
        available_tmux.create_session("boss")
        mock_server.has_session.return_value = True

        # Step 2: 销毁
        available_tmux.kill_session("boss")
        mock_server.has_session.return_value = False

        # Step 3: 重新创建
        available_tmux.create_session("boss")
        mock_server.new_session.assert_called_with(
            session_name="boss", detach=True
        )

    def test_create_session_with_agent_naming_convention(self, available_tmux, mock_server):
        """使用 agent_{role}_{seq} 命名规范创建会话"""
        name = available_tmux.format_agent_window_name("senior-dev", 1)
        assert name == "agent_senior-dev_001"

        available_tmux.create_session(name)
        mock_server.new_session.assert_called_once_with(
            session_name="agent_senior-dev_001", detach=True
        )


# ══════════════════════════════════════════════════════════
# 2. tmux 窗口管理集成
# ══════════════════════════════════════════════════════════
class TestTmuxWindowManagement:
    """在会话中创建/管理/销毁窗口"""

    def test_create_window_in_session(self, available_tmux, mock_server):
        """在会话中创建窗口"""
        mock_session, _ = _setup_session_and_window(
            available_tmux, "boss", "main"
        )
        new_window = _make_mock_window("agent_dev_001")
        mock_session.new_window.return_value = new_window

        window = available_tmux.create_window("boss", "agent_dev_001")
        assert window is not None
        mock_session.new_window.assert_called_once_with(
            window_name="agent_dev_001", attach=False
        )

    def test_create_window_with_command(self, available_tmux, mock_server):
        """创建带启动命令的窗口"""
        mock_session, _ = _setup_session_and_window(
            available_tmux, "boss", "main"
        )
        new_window = _make_mock_window("agent_dev_001")
        mock_session.new_window.return_value = new_window

        available_tmux.create_window("boss", "agent_dev_001", cmd="claude")
        mock_session.new_window.assert_called_once_with(
            window_name="agent_dev_001", attach=False, window_shell="claude"
        )

    def test_create_window_with_start_directory(self, available_tmux, mock_server):
        """创建指定工作目录的窗口"""
        mock_session, _ = _setup_session_and_window(
            available_tmux, "boss", "main"
        )
        new_window = _make_mock_window("agent_dev_001")
        mock_session.new_window.return_value = new_window

        available_tmux.create_window(
            "boss", "agent_dev_001", start_directory="/tmp/project"
        )
        mock_session.new_window.assert_called_once_with(
            window_name="agent_dev_001",
            attach=False,
            start_directory="/tmp/project",
        )

    def test_list_windows_in_session(self, available_tmux, mock_server):
        """列出会话中的窗口"""
        mock_session, _ = _setup_session_and_window(
            available_tmux, "boss", "main"
        )
        w1 = _make_mock_window("main")
        w2 = _make_mock_window("agent_dev_001")
        mock_session.windows.__iter__.return_value = [w1, w2]

        windows = available_tmux.list_windows("boss")
        assert "main" in windows
        assert "agent_dev_001" in windows

    def test_kill_window_in_session(self, available_tmux, mock_server):
        """销毁会话中的窗口"""
        mock_session, mock_window = _setup_session_and_window(
            available_tmux, "boss", "agent_dev_001"
        )

        result = available_tmux.kill_window("boss", "agent_dev_001")
        assert result is True
        mock_session.kill_window.assert_called_once_with("agent_dev_001")

    def test_window_exists_check(self, available_tmux, mock_server):
        """检查窗口是否存在"""
        mock_session, _ = _setup_session_and_window(
            available_tmux, "boss", "main"
        )
        w1 = _make_mock_window("main")
        w2 = _make_mock_window("agent_dev_001")
        mock_session.windows.__iter__.return_value = [w1, w2]

        assert available_tmux.window_exists("boss", "main")
        assert available_tmux.window_exists("boss", "agent_dev_001")
        assert not available_tmux.window_exists("boss", "nonexistent")

    def test_create_window_in_nonexistent_session_raises(self, available_tmux, mock_server):
        """在不存在的会话中创建窗口抛 ValueError"""
        mock_server.has_session.return_value = False
        with pytest.raises(ValueError, match="会话不存在"):
            available_tmux.create_window("nonexistent", "window1")


# ══════════════════════════════════════════════════════════
# 3. CLI 启动与 tmux 集成
# ══════════════════════════════════════════════════════════
class TestCLIStartWithTmux:
    """CLI 启动与 tmux 窗口交互"""

    def test_start_cli_checks_session_exists(self, cli, available_tmux, mock_server):
        """启动 CLI 前检查会话存在"""
        mock_server.has_session.return_value = False
        with pytest.raises(ValueError, match="Session does not exist"):
            cli.start_cli("nonexistent", "window1")

    def test_start_cli_checks_window_exists(self, cli, available_tmux, mock_server):
        """启动 CLI 前检查窗口存在"""
        _setup_session_and_window(available_tmux, "boss", "main")
        # 窗口 "nonexistent_window" 不在 filter 结果中
        with pytest.raises(ValueError, match="Window does not exist"):
            cli.start_cli("boss", "nonexistent_window")

    def test_start_cli_sends_command_via_tmux(self, cli, available_tmux, mock_server):
        """启动 CLI 通过 tmux send_command 发送启动命令"""
        mock_session, mock_window = _setup_session_and_window(
            available_tmux, "boss", "agent_dev_001"
        )
        # 模拟 CLI 就绪输出
        mock_window.active_pane.capture_pane.return_value = ["claude>"]

        status = cli.start_cli("boss", "agent_dev_001")
        assert status == CLIStatus.READY

    def test_start_cli_with_prompt_injects(self, cli, available_tmux, mock_server):
        """启动 CLI 并注入 prompt"""
        mock_session, mock_window = _setup_session_and_window(
            available_tmux, "boss", "agent_dev_001"
        )
        mock_window.active_pane.capture_pane.return_value = ["claude>"]

        status = cli.start_cli(
            "boss", "agent_dev_001", prompt="请实现登录功能"
        )
        assert status == CLIStatus.RUNNING

    def test_start_cli_timeout_raises(self, available_tmux, mock_server):
        """CLI 启动超时抛 RuntimeError"""
        cli = ClaudeCodeCLI(
            tmux_manager=available_tmux,
            startup_timeout=0.2,
            ready_check_interval=0.05,
        )
        mock_session, mock_window = _setup_session_and_window(
            available_tmux, "boss", "agent_dev_001"
        )
        # 模拟永远不就绪
        mock_window.active_pane.capture_pane.return_value = ["$"]

        with pytest.raises(RuntimeError, match="startup timed out"):
            cli.start_cli("boss", "agent_dev_001")

    def test_start_cli_with_working_directory(self, cli, available_tmux, mock_server):
        """启动 CLI 时切换工作目录"""
        mock_session, mock_window = _setup_session_and_window(
            available_tmux, "boss", "agent_dev_001"
        )
        mock_window.active_pane.capture_pane.return_value = ["claude>"]

        # mock send_command 以追踪调用
        with patch.object(available_tmux, 'send_command') as mock_send_cmd:
            mock_send_cmd.return_value = None
            cli.start_cli(
                "boss", "agent_dev_001", working_directory="/tmp/project"
            )

            # 验证 cd 命令被发送
            cd_calls = [c for c in mock_send_cmd.call_args_list if "cd" in str(c)]
            assert len(cd_calls) > 0

    def test_start_cli_status_tracking(self, cli, available_tmux, mock_server):
        """CLI 启动后状态正确跟踪"""
        mock_session, mock_window = _setup_session_and_window(
            available_tmux, "boss", "agent_dev_001"
        )
        mock_window.active_pane.capture_pane.return_value = ["claude>"]

        # 启动前
        assert cli.get_status("boss", "agent_dev_001") == CLIStatus.NOT_STARTED

        # 启动后
        cli.start_cli("boss", "agent_dev_001")
        assert cli.get_status("boss", "agent_dev_001") == CLIStatus.READY

    def test_start_cli_duplicate_returns_current_status(self, cli, available_tmux, mock_server):
        """重复启动 CLI 返回当前状态"""
        mock_session, mock_window = _setup_session_and_window(
            available_tmux, "boss", "agent_dev_001"
        )
        mock_window.active_pane.capture_pane.return_value = ["claude>"]

        status1 = cli.start_cli("boss", "agent_dev_001")
        assert status1 == CLIStatus.READY

        status2 = cli.start_cli("boss", "agent_dev_001")
        assert status2 == CLIStatus.READY

    def test_start_cli_with_extra_args(self, available_tmux, mock_server):
        """使用额外参数启动 CLI"""
        cli = ClaudeCodeCLI(
            tmux_manager=available_tmux,
            extra_args=["--model", "opus"],
            startup_timeout=1.0,
            ready_check_interval=0.1,
        )
        mock_session, mock_window = _setup_session_and_window(
            available_tmux, "boss", "agent_dev_001"
        )
        mock_window.active_pane.capture_pane.return_value = ["claude>"]

        cli.start_cli("boss", "agent_dev_001")

        cmd = cli._build_cli_command()
        assert "--model opus" in cmd


# ══════════════════════════════════════════════════════════
# 4. CLI 停止与 tmux 集成
# ══════════════════════════════════════════════════════════
class TestCLIStopWithTmux:
    """CLI 停止与 tmux 窗口交互"""

    def _start_cli(self, cli, available_tmux, mock_server):
        """辅助：启动 CLI 使其进入 READY 状态"""
        mock_session, mock_window = _setup_session_and_window(
            available_tmux, "boss", "agent_dev_001"
        )
        mock_window.active_pane.capture_pane.return_value = ["claude>"]
        cli.start_cli("boss", "agent_dev_001")
        return mock_session, mock_window

    def test_stop_cli_sends_exit_command(self, cli, available_tmux, mock_server):
        """停止 CLI 时发送 /exit 命令"""
        mock_session, mock_window = self._start_cli(cli, available_tmux, mock_server)
        mock_window.active_pane.capture_pane.return_value = ["user@host:~$"]

        status = cli.stop_cli("boss", "agent_dev_001")
        assert status == CLIStatus.STOPPED

    def test_stop_cli_not_started_returns_not_started(self, cli, available_tmux, mock_server):
        """停止未启动的 CLI 返回 NOT_STARTED"""
        status = cli.stop_cli("boss", "agent_dev_001")
        assert status == CLIStatus.NOT_STARTED

    def test_stop_cli_already_stopped(self, cli, available_tmux, mock_server):
        """停止已停止的 CLI 返回 STOPPED"""
        mock_session, mock_window = self._start_cli(cli, available_tmux, mock_server)
        mock_window.active_pane.capture_pane.return_value = ["user@host:~$"]

        cli.stop_cli("boss", "agent_dev_001")
        status = cli.stop_cli("boss", "agent_dev_001")
        assert status == CLIStatus.STOPPED

    def test_stop_cli_fallback_to_sigint(self, cli, available_tmux, mock_server):
        """/exit 失败后回退到 C-c"""
        mock_session, mock_window = self._start_cli(cli, available_tmux, mock_server)

        # /exit 后未退出 → C-c 后退出
        mock_window.active_pane.capture_pane.side_effect = [
            ["claude>"],  # /exit 后
            ["claude>"],
            ["claude>"],
            ["user@host:~$"],  # C-c 后
        ]

        # mock send_keys 和 send_command 以追踪调用
        with patch.object(available_tmux, 'send_keys') as mock_send_keys, \
             patch.object(available_tmux, 'send_command') as mock_send_cmd:
            mock_send_keys.return_value = None
            mock_send_cmd.return_value = None

            status = cli.stop_cli("boss", "agent_dev_001", timeout=0.5)
            assert status == CLIStatus.STOPPED

            # 验证 send_keys 被调用发送 C-c
            cc_calls = [c for c in mock_send_keys.call_args_list if "C-c" in str(c)]
            assert len(cc_calls) > 0

    def test_stop_cli_updates_status_map(self, cli, available_tmux, mock_server):
        """停止 CLI 后更新状态映射"""
        mock_session, mock_window = self._start_cli(cli, available_tmux, mock_server)
        mock_window.active_pane.capture_pane.return_value = ["user@host:~$"]

        cli.stop_cli("boss", "agent_dev_001")
        assert cli.get_status("boss", "agent_dev_001") == CLIStatus.STOPPED


# ══════════════════════════════════════════════════════════
# 5. 完整工作流集成
# ══════════════════════════════════════════════════════════
class TestFullTmuxCLIWorkflow:
    """完整工作流：创建会话 → 创建窗口 → 启动 CLI → 交互 → 停止 → 销毁"""

    def test_full_workflow_single_agent(self, available_tmux, mock_server):
        """单 Agent 完整工作流"""
        # Step 1: 创建 tmux 会话
        session = available_tmux.create_session("boss")
        mock_server.has_session.return_value = True
        assert available_tmux.session_exists("boss")

        # Step 2: 设置 session + window
        mock_session, mock_window = _setup_session_and_window(
            available_tmux, "boss", "agent_dev_001"
        )

        # Step 3: 创建 CLI 并启动
        cli = ClaudeCodeCLI(
            tmux_manager=available_tmux,
            startup_timeout=1.0,
            ready_check_interval=0.1,
        )
        mock_window.active_pane.capture_pane.return_value = ["claude>"]

        status = cli.start_cli("boss", "agent_dev_001", prompt="实现 Hello World")
        assert status == CLIStatus.RUNNING
        assert cli.get_status("boss", "agent_dev_001") == CLIStatus.RUNNING

        # Step 4: 发送额外 prompt
        status = cli.send_prompt("boss", "agent_dev_001", "运行测试")
        assert status == CLIStatus.RUNNING

        # Step 5: 停止 CLI
        mock_window.active_pane.capture_pane.return_value = ["user@host:~$"]
        stop_status = cli.stop_cli("boss", "agent_dev_001")
        assert stop_status == CLIStatus.STOPPED

        # Step 6: 销毁窗口
        result = available_tmux.kill_window("boss", "agent_dev_001")
        assert result is True

        # Step 7: 销毁会话
        result = available_tmux.kill_session("boss")
        assert result is True
        mock_server.has_session.return_value = False

    def test_full_workflow_multiple_agents(self, available_tmux, mock_server):
        """多 Agent 并发工作流"""
        # 创建会话
        available_tmux.create_session("boss")
        mock_server.has_session.return_value = True

        mock_session = _make_mock_session("boss")

        # 多窗口
        w1 = _make_mock_window("agent_dev_001")
        w2 = _make_mock_window("agent_qa_001")

        def filter_windows(**kwargs):
            name = kwargs.get("window_name")
            if name == "agent_dev_001":
                return [w1]
            elif name == "agent_qa_001":
                return [w2]
            return []
        mock_session.windows.filter.side_effect = filter_windows
        mock_session.windows.__iter__.return_value = [w1, w2]

        def filter_sessions(**kwargs):
            if kwargs.get("session_name") == "boss":
                return [mock_session]
            return []
        mock_server.sessions.filter.side_effect = filter_sessions

        cli = ClaudeCodeCLI(
            tmux_manager=available_tmux,
            startup_timeout=1.0,
            ready_check_interval=0.1,
        )

        # 启动 dev agent CLI
        w1.active_pane.capture_pane.return_value = ["claude>"]
        status1 = cli.start_cli("boss", "agent_dev_001", prompt="实现代码")
        assert status1 == CLIStatus.RUNNING

        # 启动 qa agent CLI
        w2.active_pane.capture_pane.return_value = ["claude>"]
        status2 = cli.start_cli("boss", "agent_qa_001", prompt="编写测试")
        assert status2 == CLIStatus.RUNNING

        # 独立状态跟踪
        assert cli.get_status("boss", "agent_dev_001") == CLIStatus.RUNNING
        assert cli.get_status("boss", "agent_qa_001") == CLIStatus.RUNNING

        # 停止 dev agent CLI
        w1.active_pane.capture_pane.return_value = ["user@host:~$"]
        cli.stop_cli("boss", "agent_dev_001")
        assert cli.get_status("boss", "agent_dev_001") == CLIStatus.STOPPED
        assert cli.get_status("boss", "agent_qa_001") == CLIStatus.RUNNING

    def test_workflow_with_send_keys_and_capture(self, available_tmux, mock_server):
        """CLI 启动后通过 send_keys/capture_pane 交互"""
        mock_session, mock_window = _setup_session_and_window(
            available_tmux, "boss", "agent_dev_001"
        )

        cli = ClaudeCodeCLI(
            tmux_manager=available_tmux,
            startup_timeout=1.0,
            ready_check_interval=0.1,
        )

        mock_window.active_pane.capture_pane.return_value = ["claude>"]
        cli.start_cli("boss", "agent_dev_001")

        # 通过 capture_pane 检查输出
        output = available_tmux.capture_pane("boss", "agent_dev_001")
        assert isinstance(output, list)

        # 通过 send_command 发送命令
        available_tmux.send_command("boss", "agent_dev_001", "echo hello")

    def test_workflow_reuse_window_after_cli_stop(self, available_tmux, mock_server):
        """CLI 停止后窗口可复用"""
        mock_session, mock_window = _setup_session_and_window(
            available_tmux, "boss", "agent_dev_001"
        )

        cli = ClaudeCodeCLI(
            tmux_manager=available_tmux,
            startup_timeout=1.0,
            ready_check_interval=0.1,
        )

        # 第一次启动
        mock_window.active_pane.capture_pane.return_value = ["claude>"]
        cli.start_cli("boss", "agent_dev_001")

        # 停止
        mock_window.active_pane.capture_pane.return_value = ["user@host:~$"]
        cli.stop_cli("boss", "agent_dev_001")
        assert cli.get_status("boss", "agent_dev_001") == CLIStatus.STOPPED

        # 再次启动（同一个窗口）
        mock_window.active_pane.capture_pane.return_value = ["claude>"]
        status = cli.start_cli("boss", "agent_dev_001")
        assert status == CLIStatus.READY

    def test_workflow_with_working_directory_change(self, available_tmux, mock_server):
        """完整工作流含工作目录切换"""
        mock_session, mock_window = _setup_session_and_window(
            available_tmux, "boss", "agent_dev_001"
        )

        cli = ClaudeCodeCLI(
            tmux_manager=available_tmux,
            startup_timeout=1.0,
            ready_check_interval=0.1,
        )

        mock_window.active_pane.capture_pane.return_value = ["claude>"]

        cli.start_cli(
            "boss", "agent_dev_001",
            working_directory="/home/user/project",
            prompt="开始工作",
        )
        assert cli.get_status("boss", "agent_dev_001") == CLIStatus.RUNNING


# ══════════════════════════════════════════════════════════
# 6. 异常恢复场景
# ══════════════════════════════════════════════════════════
class TestErrorRecoveryWorkflow:
    """异常场景下的集成恢复"""

    def test_start_cli_on_killed_session_raises(self, cli, available_tmux, mock_server):
        """在已销毁的会话上启动 CLI 抛异常"""
        mock_server.has_session.return_value = False
        with pytest.raises(ValueError, match="Session does not exist"):
            cli.start_cli("killed_session", "agent_dev_001")

    def test_start_cli_on_killed_window_raises(self, cli, available_tmux, mock_server):
        """在已销毁的窗口上启动 CLI 抛异常"""
        _setup_session_and_window(available_tmux, "boss", "main")
        with pytest.raises(ValueError, match="Window does not exist"):
            cli.start_cli("boss", "killed_window")

    def test_send_prompt_to_not_started_cli_raises(self, cli, available_tmux, mock_server):
        """向未启动的 CLI 发送 prompt 抛 ValueError"""
        with pytest.raises(ValueError, match="CLI is not ready"):
            cli.send_prompt("boss", "agent_dev_001", "hello")

    def test_send_prompt_to_stopped_cli_raises(self, cli, available_tmux, mock_server):
        """向已停止的 CLI 发送 prompt 抛 ValueError"""
        mock_session, mock_window = _setup_session_and_window(
            available_tmux, "boss", "agent_dev_001"
        )
        mock_window.active_pane.capture_pane.return_value = ["claude>"]
        cli.start_cli("boss", "agent_dev_001")

        mock_window.active_pane.capture_pane.return_value = ["user@host:~$"]
        cli.stop_cli("boss", "agent_dev_001")

        with pytest.raises(ValueError, match="CLI is not ready"):
            cli.send_prompt("boss", "agent_dev_001", "hello")

    def test_send_empty_prompt_raises(self, cli, available_tmux, mock_server):
        """发送空 prompt 抛 ValueError"""
        mock_session, mock_window = _setup_session_and_window(
            available_tmux, "boss", "agent_dev_001"
        )
        mock_window.active_pane.capture_pane.return_value = ["claude>"]
        cli.start_cli("boss", "agent_dev_001")

        with pytest.raises(ValueError, match="prompt cannot be empty"):
            cli.send_prompt("boss", "agent_dev_001", "")

    def test_cli_start_after_error_can_retry(self, available_tmux, mock_server):
        """CLI 启动失败后可以重试"""
        cli = ClaudeCodeCLI(
            tmux_manager=available_tmux,
            startup_timeout=0.2,
            ready_check_interval=0.05,
        )

        mock_session, mock_window = _setup_session_and_window(
            available_tmux, "boss", "agent_dev_001"
        )

        # 第一次：超时
        mock_window.active_pane.capture_pane.return_value = ["$"]
        with pytest.raises(RuntimeError, match="startup timed out"):
            cli.start_cli("boss", "agent_dev_001")

        assert cli.get_status("boss", "agent_dev_001") == CLIStatus.ERROR

        # 第二次：成功
        mock_window.active_pane.capture_pane.return_value = ["claude>"]
        status = cli.start_cli("boss", "agent_dev_001")
        assert status == CLIStatus.READY

    def test_tmux_unavailable_prevents_cli_start(self):
        """tmux 不可用时阻止 CLI 启动"""
        mgr = TmuxManager()
        mgr._available = False

        cli = ClaudeCodeCLI(tmux_manager=mgr)

        with pytest.raises(ValueError, match="Session does not exist"):
            cli.start_cli("boss", "agent_dev_001")

    def test_cli_none_tmux_manager_raises(self):
        """tmux_manager 为 None 时构造抛 ValueError"""
        with pytest.raises(ValueError, match="tmux_manager cannot be None"):
            ClaudeCodeCLI(tmux_manager=None)


# ══════════════════════════════════════════════════════════
# 7. 多会话并发管理
# ══════════════════════════════════════════════════════════
class TestConcurrentSessionManagement:
    """多会话/多窗口并发管理"""

    def test_multiple_sessions_with_clis(self, available_tmux, mock_server):
        """多个会话各自运行 CLI"""
        # 两个会话
        s1 = _make_mock_session("boss_1")
        s2 = _make_mock_session("boss_2")

        # 会话 1 窗口
        w1 = _make_mock_window("agent_dev_001")
        w1.active_pane.capture_pane.return_value = ["claude>"]
        s1.windows.filter.side_effect = lambda **kw: [w1] if kw.get("window_name") == "agent_dev_001" else []
        s1.windows.__iter__.return_value = [w1]

        # 会话 2 窗口
        w2 = _make_mock_window("agent_qa_001")
        w2.active_pane.capture_pane.return_value = ["claude>"]
        s2.windows.filter.side_effect = lambda **kw: [w2] if kw.get("window_name") == "agent_qa_001" else []
        s2.windows.__iter__.return_value = [w2]

        mock_server.has_session.return_value = True

        def filter_sessions(**kwargs):
            name = kwargs.get("session_name")
            if name == "boss_1":
                return [s1]
            elif name == "boss_2":
                return [s2]
            return []
        mock_server.sessions.filter.side_effect = filter_sessions

        cli = ClaudeCodeCLI(
            tmux_manager=available_tmux,
            startup_timeout=1.0,
            ready_check_interval=0.1,
        )

        status1 = cli.start_cli("boss_1", "agent_dev_001")
        status2 = cli.start_cli("boss_2", "agent_qa_001")

        assert status1 == CLIStatus.READY
        assert status2 == CLIStatus.READY

        # 独立停止
        w1.active_pane.capture_pane.return_value = ["user@host:~$"]
        cli.stop_cli("boss_1", "agent_dev_001")
        assert cli.get_status("boss_1", "agent_dev_001") == CLIStatus.STOPPED
        assert cli.get_status("boss_2", "agent_qa_001") == CLIStatus.READY

    def test_agent_naming_convention_in_workflow(self, available_tmux, mock_server):
        """使用 agent 命名规范的多窗口工作流"""
        available_tmux.create_session("boss")
        mock_server.has_session.return_value = True

        mock_session = _make_mock_session("boss")

        # 创建多个命名规范的窗口
        windows = []
        for role, seq in [("dev", 1), ("dev", 2), ("qa", 1)]:
            name = available_tmux.format_agent_window_name(role, seq)
            w = _make_mock_window(name)
            w.active_pane.capture_pane.return_value = ["claude>"]
            windows.append(w)

        mock_session.windows.__iter__.return_value = windows

        def filter_sessions(**kwargs):
            if kwargs.get("session_name") == "boss":
                return [mock_session]
            return []
        mock_server.sessions.filter.side_effect = filter_sessions

        # 验证命名
        assert windows[0].name == "agent_dev_001"
        assert windows[1].name == "agent_dev_002"
        assert windows[2].name == "agent_qa_001"

        # 解析命名
        role, seq = available_tmux.parse_agent_window_name("agent_dev_001")
        assert role == "dev"
        assert seq == 1

    def test_create_destroy_create_session_with_cli(self, available_tmux, mock_server):
        """会话销毁后重建并重新启动 CLI"""
        # 第一次创建
        available_tmux.create_session("boss")
        mock_server.has_session.return_value = True

        mock_session, mock_window = _setup_session_and_window(
            available_tmux, "boss", "agent_dev_001"
        )
        mock_window.active_pane.capture_pane.return_value = ["claude>"]

        cli = ClaudeCodeCLI(
            tmux_manager=available_tmux,
            startup_timeout=1.0,
            ready_check_interval=0.1,
        )
        cli.start_cli("boss", "agent_dev_001")
        assert cli.get_status("boss", "agent_dev_001") == CLIStatus.READY

        # 停止 CLI 并销毁会话
        mock_window.active_pane.capture_pane.return_value = ["user@host:~$"]
        cli.stop_cli("boss", "agent_dev_001")
        available_tmux.kill_session("boss")
        mock_server.has_session.return_value = False

        # 重建会话
        available_tmux.create_session("boss")
        mock_server.has_session.return_value = True

        # 重新设置窗口
        mock_session2, mock_window2 = _setup_session_and_window(
            available_tmux, "boss", "agent_dev_001"
        )
        mock_window2.active_pane.capture_pane.return_value = ["claude>"]

        # 重新启动 CLI
        status = cli.start_cli("boss", "agent_dev_001")
        assert status == CLIStatus.READY


# ══════════════════════════════════════════════════════════
# 8. CLI 就绪检测集成
# ══════════════════════════════════════════════════════════
class TestCLIReadyDetection:
    """CLI 就绪检测与 tmux 输出捕获集成"""

    def test_default_ready_patterns(self):
        """默认就绪模式列表包含标准提示符"""
        assert "claude>" in _CLI_READY_PATTERNS
        assert "claude >" in _CLI_READY_PATTERNS
        assert ">" in _CLI_READY_PATTERNS

    def test_custom_ready_patterns(self, available_tmux):
        """自定义就绪检测模式"""
        cli = ClaudeCodeCLI(
            tmux_manager=available_tmux,
            ready_patterns=[">>>", "READY>"],
        )
        assert ">>>" in cli.ready_patterns
        assert "READY>" in cli.ready_patterns

    def test_is_cli_ready_with_captured_output(self, cli, available_tmux, mock_server):
        """通过 capture_pane_history 检测 CLI 就绪"""
        mock_session, mock_window = _setup_session_and_window(
            available_tmux, "boss", "agent_dev_001"
        )
        mock_window.active_pane.capture_pane.return_value = [
            "Welcome to Claude Code",
            "Version 1.0",
            "claude>",
        ]

        ready = cli.is_cli_ready("boss", "agent_dev_001")
        assert ready is True

    def test_is_cli_ready_without_ready_pattern(self, cli, available_tmux, mock_server):
        """输出不包含就绪标志时返回 False"""
        mock_session, mock_window = _setup_session_and_window(
            available_tmux, "boss", "agent_dev_001"
        )
        mock_window.active_pane.capture_pane.return_value = [
            "Starting...",
            "Loading modules...",
        ]

        ready = cli.is_cli_ready("boss", "agent_dev_001")
        assert ready is False

    def test_is_cli_ready_on_error_returns_false(self, cli, available_tmux, mock_server):
        """tmux 捕获异常时返回 False"""
        mock_server.has_session.return_value = False

        ready = cli.is_cli_ready("nonexistent", "window")
        assert ready is False

    def test_check_ready_output_method(self):
        """_check_ready_output 方法正确匹配模式"""
        cli = ClaudeCodeCLI.__new__(ClaudeCodeCLI)
        cli._ready_patterns = ["claude>", ">"]

        assert cli._check_ready_output("some text\nclaude>") is True
        assert cli._check_ready_output("some text\n>") is True
        assert cli._check_ready_output("no prompt here") is False


# ══════════════════════════════════════════════════════════
# 9. CLI 命令构建与 prompt 处理
# ══════════════════════════════════════════════════════════
class TestCLICommandAndPrompt:
    """CLI 命令构建与 prompt 注入逻辑"""

    def test_build_cli_command_default(self, available_tmux):
        """默认命令为 'claude'"""
        cli = ClaudeCodeCLI(tmux_manager=available_tmux)
        assert cli._build_cli_command() == "claude"

    def test_build_cli_command_with_extra_args(self, available_tmux):
        """命令包含额外参数"""
        cli = ClaudeCodeCLI(
            tmux_manager=available_tmux,
            extra_args=["--model", "opus", "--verbose"],
        )
        assert cli._build_cli_command() == "claude --model opus --verbose"

    def test_split_prompt_short(self):
        """短 prompt 不分割"""
        result = ClaudeCodeCLI._split_prompt("hello world", chunk_size=500)
        assert len(result) == 1
        assert result[0] == "hello world"

    def test_split_prompt_long(self):
        """长 prompt 按 chunk_size 分割"""
        text = "line\n" * 200  # 1000 字符
        result = ClaudeCodeCLI._split_prompt(text, chunk_size=500)
        assert len(result) > 1
        assert "".join(result) == text

    def test_split_prompt_no_newlines(self):
        """无换行符时强制分割"""
        text = "a" * 1000
        result = ClaudeCodeCLI._split_prompt(text, chunk_size=500)
        assert len(result) == 2
        assert result[0] == "a" * 500
        assert result[1] == "a" * 500

    def test_inject_short_prompt(self, cli, available_tmux, mock_server):
        """短 prompt 通过 send_keys 发送"""
        mock_session, mock_window = _setup_session_and_window(
            available_tmux, "boss", "agent_dev_001"
        )
        mock_window.active_pane.capture_pane.return_value = ["claude>"]

        # mock send_keys 以追踪调用
        with patch.object(available_tmux, 'send_keys') as mock_send_keys, \
             patch.object(available_tmux, 'send_command') as mock_send_cmd:
            mock_send_keys.return_value = None
            mock_send_cmd.return_value = None

            cli.start_cli("boss", "agent_dev_001", prompt="hello")

            # send_keys 应被调用（注入 prompt）
            assert mock_send_keys.call_count > 0

    def test_make_key_format(self):
        """_make_key 生成 'session:window' 格式"""
        assert ClaudeCodeCLI._make_key("boss", "agent_dev_001") == "boss:agent_dev_001"

    def test_cli_properties(self, available_tmux):
        """CLI 属性只读访问"""
        cli = ClaudeCodeCLI(
            tmux_manager=available_tmux,
            cli_command="/usr/local/bin/claude",
            startup_timeout=60.0,
            ready_check_interval=1.0,
            ready_patterns=["custom>"],
            extra_args=["--model", "sonnet"],
        )

        assert cli.tmux_manager is available_tmux
        assert cli.cli_command == "/usr/local/bin/claude"
        assert cli.startup_timeout == 60.0
        assert cli.ready_check_interval == 1.0
        assert "custom>" in cli.ready_patterns
        assert "--model" in cli.extra_args

        # 只读副本
        cli.ready_patterns.append("extra>")
        assert "extra>" not in cli.ready_patterns

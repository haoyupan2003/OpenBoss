"""
TmuxManager 命令发送和输出捕获单元测试

使用 mock 隔离 libtmux 依赖，覆盖命令发送和输出捕获的所有方法：
- send_keys: 基本发送 / enter / literal / reset / 会话或窗口不存在
- send_command: 基本发送 / enter 默认 True / suppress_history / 自定义参数
- capture_pane: 正常捕获 / None 降级空列表 / 会话或窗口不存在
- capture_pane_history: 正常回溯 / lines=0 等同 capture_pane / lines<0 抛 ValueError / None 降级
- 综合场景: 发送命令→捕获输出流程
"""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from agent_automation_system.tmux_manager import TmuxManager


# ─── Fixtures ──────────────────────────────────────


@pytest.fixture
def mock_server():
    """创建 mock libtmux.Server"""
    server = MagicMock()
    server.is_alive.return_value = True
    server.has_session.return_value = True
    return server


@pytest.fixture
def mock_tmux_session():
    """创建 mock libtmux.Session"""
    session = MagicMock()
    session.name = "agent_dev_001"
    return session


@pytest.fixture
def mock_pane():
    """创建 mock libtmux.Pane"""
    pane = MagicMock()
    pane.capture_pane.return_value = ["$ ls", "file1.txt", "file2.txt", "$"]
    return pane


@pytest.fixture
def mock_window(mock_pane):
    """创建 mock libtmux.Window（含 active_pane）"""
    window = MagicMock()
    window.name = "main"
    window.active_pane = mock_pane
    return window


@pytest.fixture
def available_mgr(mock_server):
    """创建已标记为可用的 TmuxManager，注入 mock server"""
    mgr = TmuxManager()
    mgr._available = True
    mgr._server = mock_server
    return mgr


@pytest.fixture
def mgr_with_pane(available_mgr, mock_server, mock_tmux_session, mock_window):
    """创建带完整 mock 链的 TmuxManager（server→session→window→pane）"""
    mock_sessions = MagicMock()
    mock_sessions.filter.return_value = [mock_tmux_session]
    mock_server.sessions = mock_sessions

    mock_windows = MagicMock()
    mock_windows.filter.return_value = [mock_window]
    mock_tmux_session.windows = mock_windows

    return available_mgr


# ─── send_keys 测试 ────────────────────────────────


class TestSendKeys:
    """send_keys() 方法测试"""

    def test_send_basic(self, mgr_with_pane, mock_pane):
        """基本发送按键"""
        mgr_with_pane.send_keys("agent_dev_001", "main", "ls")
        mock_pane.send_keys.assert_called_once_with("ls", enter=False)

    def test_send_with_enter(self, mgr_with_pane, mock_pane):
        """发送按键并回车"""
        mgr_with_pane.send_keys("agent_dev_001", "main", "ls", enter=True)
        mock_pane.send_keys.assert_called_once_with("ls", enter=True)

    def test_send_with_literal(self, mgr_with_pane, mock_pane):
        """字面发送（不解释特殊按键）"""
        mgr_with_pane.send_keys("agent_dev_001", "main", "test$", literal=True)
        mock_pane.send_keys.assert_called_once_with(
            "test$", enter=False, literal=True
        )

    def test_send_with_reset(self, mgr_with_pane, mock_pane):
        """发送前重置终端"""
        mgr_with_pane.send_keys("agent_dev_001", "main", "ls", reset=True)
        mock_pane.send_keys.assert_called_once_with(
            "ls", enter=False, reset=True
        )

    def test_send_with_literal_and_reset(self, mgr_with_pane, mock_pane):
        """同时 literal 和 reset"""
        mgr_with_pane.send_keys(
            "agent_dev_001", "main", "test$", enter=True, literal=True, reset=True
        )
        mock_pane.send_keys.assert_called_once_with(
            "test$", enter=True, literal=True, reset=True
        )

    def test_send_special_keys(self, mgr_with_pane, mock_pane):
        """发送特殊按键（如 C-c）"""
        mgr_with_pane.send_keys("agent_dev_001", "main", "C-c")
        mock_pane.send_keys.assert_called_once_with("C-c", enter=False)

    def test_send_enter_false_by_default(self, mgr_with_pane, mock_pane):
        """enter 默认为 False"""
        mgr_with_pane.send_keys("agent_dev_001", "main", "hello")
        call_kwargs = mock_pane.send_keys.call_args
        assert call_kwargs[1]["enter"] is False

    def test_send_no_extra_kwargs_by_default(self, mgr_with_pane, mock_pane):
        """默认不传 literal 和 reset"""
        mgr_with_pane.send_keys("agent_dev_001", "main", "hello")
        call_args = mock_pane.send_keys.call_args
        # 只应有 keys 和 enter，不应有 literal/reset
        assert "literal" not in call_args[1]
        assert "reset" not in call_args[1]

    def test_send_session_not_exists(self, available_mgr, mock_server):
        """会话不存在抛 ValueError"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = []
        mock_server.sessions = mock_sessions
        with pytest.raises(ValueError, match="会话不存在"):
            available_mgr.send_keys("nonexistent", "main", "ls")

    def test_send_window_not_exists(
        self, available_mgr, mock_server, mock_tmux_session
    ):
        """窗口不存在抛 ValueError"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = [mock_tmux_session]
        mock_server.sessions = mock_sessions

        mock_windows = MagicMock()
        mock_windows.filter.return_value = []
        mock_tmux_session.windows = mock_windows

        with pytest.raises(ValueError, match="窗口不存在"):
            available_mgr.send_keys("agent_dev_001", "nonexistent", "ls")


# ─── send_command 测试 ─────────────────────────────


class TestSendCommand:
    """send_command() 方法测试"""

    def test_send_basic(self, mgr_with_pane, mock_pane):
        """基本发送命令"""
        mgr_with_pane.send_command("agent_dev_001", "main", "ls -la")
        mock_pane.send_keys.assert_called_once_with(
            "ls -la", enter=True, suppress_history=True
        )

    def test_send_enter_default_true(self, mgr_with_pane, mock_pane):
        """enter 默认为 True"""
        mgr_with_pane.send_command("agent_dev_001", "main", "echo hello")
        call_kwargs = mock_pane.send_keys.call_args[1]
        assert call_kwargs["enter"] is True

    def test_send_enter_false(self, mgr_with_pane, mock_pane):
        """禁用自动回车"""
        mgr_with_pane.send_command(
            "agent_dev_001", "main", "echo hello", enter=False
        )
        call_kwargs = mock_pane.send_keys.call_args[1]
        assert call_kwargs["enter"] is False

    def test_send_suppress_history_default_true(self, mgr_with_pane, mock_pane):
        """suppress_history 默认为 True"""
        mgr_with_pane.send_command("agent_dev_001", "main", "echo hi")
        call_kwargs = mock_pane.send_keys.call_args[1]
        assert call_kwargs["suppress_history"] is True

    def test_send_suppress_history_false(self, mgr_with_pane, mock_pane):
        """禁用 suppress_history"""
        mgr_with_pane.send_command(
            "agent_dev_001", "main", "echo hi", suppress_history=False
        )
        call_kwargs = mock_pane.send_keys.call_args[1]
        assert call_kwargs["suppress_history"] is False

    def test_send_session_not_exists(self, available_mgr, mock_server):
        """会话不存在抛 ValueError"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = []
        mock_server.sessions = mock_sessions
        with pytest.raises(ValueError, match="会话不存在"):
            available_mgr.send_command("nonexistent", "main", "ls")

    def test_send_window_not_exists(
        self, available_mgr, mock_server, mock_tmux_session
    ):
        """窗口不存在抛 ValueError"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = [mock_tmux_session]
        mock_server.sessions = mock_sessions

        mock_windows = MagicMock()
        mock_windows.filter.return_value = []
        mock_tmux_session.windows = mock_windows

        with pytest.raises(ValueError, match="窗口不存在"):
            available_mgr.send_command("agent_dev_001", "nonexistent", "ls")

    def test_send_long_command(self, mgr_with_pane, mock_pane):
        """发送长命令"""
        long_cmd = "python3 -m pytest tests/ -v --tb=short -x"
        mgr_with_pane.send_command("agent_dev_001", "main", long_cmd)
        mock_pane.send_keys.assert_called_once_with(
            long_cmd, enter=True, suppress_history=True
        )


# ─── capture_pane 测试 ─────────────────────────────


class TestCapturePane:
    """capture_pane() 方法测试"""

    def test_capture_basic(self, mgr_with_pane, mock_pane):
        """基本捕获输出"""
        result = mgr_with_pane.capture_pane("agent_dev_001", "main")
        assert result == ["$ ls", "file1.txt", "file2.txt", "$"]
        mock_pane.capture_pane.assert_called_once_with()

    def test_capture_none_returns_empty(self, mgr_with_pane, mock_pane):
        """capture_pane 返回 None 时降级为空列表"""
        mock_pane.capture_pane.return_value = None
        result = mgr_with_pane.capture_pane("agent_dev_001", "main")
        assert result == []

    def test_capture_empty_output(self, mgr_with_pane, mock_pane):
        """空终端输出"""
        mock_pane.capture_pane.return_value = []
        result = mgr_with_pane.capture_pane("agent_dev_001", "main")
        assert result == []

    def test_capture_session_not_exists(self, available_mgr, mock_server):
        """会话不存在抛 ValueError"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = []
        mock_server.sessions = mock_sessions
        with pytest.raises(ValueError, match="会话不存在"):
            available_mgr.capture_pane("nonexistent", "main")

    def test_capture_window_not_exists(
        self, available_mgr, mock_server, mock_tmux_session
    ):
        """窗口不存在抛 ValueError"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = [mock_tmux_session]
        mock_server.sessions = mock_sessions

        mock_windows = MagicMock()
        mock_windows.filter.return_value = []
        mock_tmux_session.windows = mock_windows

        with pytest.raises(ValueError, match="窗口不存在"):
            available_mgr.capture_pane("agent_dev_001", "nonexistent")

    def test_capture_returns_list_of_strings(self, mgr_with_pane, mock_pane):
        """返回字符串列表"""
        mock_pane.capture_pane.return_value = ["line1", "line2", "line3"]
        result = mgr_with_pane.capture_pane("agent_dev_001", "main")
        assert isinstance(result, list)
        assert all(isinstance(line, str) for line in result)


# ─── capture_pane_history 测试 ──────────────────────


class TestCapturePaneHistory:
    """capture_pane_history() 方法测试"""

    def test_capture_history_basic(self, mgr_with_pane, mock_pane):
        """基本历史捕获"""
        mock_pane.capture_pane.return_value = ["old_line", "$ ls", "output", "$"]
        result = mgr_with_pane.capture_pane_history(
            "agent_dev_001", "main", lines=50
        )
        assert result == ["old_line", "$ ls", "output", "$"]
        mock_pane.capture_pane.assert_called_once_with(start=-50)

    def test_capture_history_default_100(self, mgr_with_pane, mock_pane):
        """默认回溯 100 行"""
        mock_pane.capture_pane.return_value = []
        mgr_with_pane.capture_pane_history("agent_dev_001", "main")
        mock_pane.capture_pane.assert_called_once_with(start=-100)

    def test_capture_history_lines_0_delegates(
        self, mgr_with_pane, mock_pane
    ):
        """lines=0 等同于 capture_pane"""
        mock_pane.capture_pane.return_value = ["$"]
        result = mgr_with_pane.capture_pane_history(
            "agent_dev_001", "main", lines=0
        )
        assert result == ["$"]
        # 应该调用 capture_pane() 无参数（走 capture_pane 方法）
        mock_pane.capture_pane.assert_called_once_with()

    def test_capture_history_negative_raises(self, mgr_with_pane):
        """lines 为负数抛 ValueError"""
        with pytest.raises(ValueError, match="历史行数不能为负数"):
            mgr_with_pane.capture_pane_history(
                "agent_dev_001", "main", lines=-1
            )

    def test_capture_history_negative_various(self, mgr_with_pane):
        """各种负数 lines 都抛 ValueError"""
        for lines in [-1, -10, -100]:
            with pytest.raises(ValueError, match="历史行数不能为负数"):
                mgr_with_pane.capture_pane_history(
                    "agent_dev_001", "main", lines=lines
                )

    def test_capture_history_none_returns_empty(self, mgr_with_pane, mock_pane):
        """capture_pane 返回 None 时降级为空列表"""
        mock_pane.capture_pane.return_value = None
        result = mgr_with_pane.capture_pane_history(
            "agent_dev_001", "main", lines=50
        )
        assert result == []

    def test_capture_history_empty_output(self, mgr_with_pane, mock_pane):
        """空历史输出"""
        mock_pane.capture_pane.return_value = []
        result = mgr_with_pane.capture_pane_history(
            "agent_dev_001", "main", lines=50
        )
        assert result == []

    def test_capture_history_session_not_exists(self, available_mgr, mock_server):
        """会话不存在抛 ValueError"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = []
        mock_server.sessions = mock_sessions
        with pytest.raises(ValueError, match="会话不存在"):
            available_mgr.capture_pane_history("nonexistent", "main", lines=50)

    def test_capture_history_window_not_exists(
        self, available_mgr, mock_server, mock_tmux_session
    ):
        """窗口不存在抛 ValueError"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = [mock_tmux_session]
        mock_server.sessions = mock_sessions

        mock_windows = MagicMock()
        mock_windows.filter.return_value = []
        mock_tmux_session.windows = mock_windows

        with pytest.raises(ValueError, match="窗口不存在"):
            available_mgr.capture_pane_history(
                "agent_dev_001", "nonexistent", lines=50
            )

    def test_capture_history_lines_1(self, mgr_with_pane, mock_pane):
        """lines=1 回溯 1 行"""
        mock_pane.capture_pane.return_value = ["$"]
        result = mgr_with_pane.capture_pane_history(
            "agent_dev_001", "main", lines=1
        )
        mock_pane.capture_pane.assert_called_once_with(start=-1)

    def test_capture_history_large_lines(self, mgr_with_pane, mock_pane):
        """大行数回溯"""
        mock_pane.capture_pane.return_value = ["line"] * 500
        result = mgr_with_pane.capture_pane_history(
            "agent_dev_001", "main", lines=500
        )
        mock_pane.capture_pane.assert_called_once_with(start=-500)
        assert len(result) == 500


# ─── 综合场景 ──────────────────────────────────────


class TestCommandCaptureRoundTrip:
    """命令发送 + 输出捕获综合场景测试"""

    def test_send_command_then_capture(
        self, mgr_with_pane, mock_pane
    ):
        """发送命令后捕获输出"""
        # 发送命令
        mgr_with_pane.send_command("agent_dev_001", "main", "echo hello")
        mock_pane.send_keys.assert_called_once_with(
            "echo hello", enter=True, suppress_history=True
        )

        # 捕获输出
        mock_pane.capture_pane.return_value = [
            "$ echo hello",
            "hello",
            "$",
        ]
        result = mgr_with_pane.capture_pane("agent_dev_001", "main")
        assert "hello" in result
        assert len(result) == 3

    def test_send_keys_then_capture_history(
        self, mgr_with_pane, mock_pane
    ):
        """发送按键后捕获历史"""
        # 发送多个命令
        mgr_with_pane.send_command("agent_dev_001", "main", "make build")
        mgr_with_pane.send_command("agent_dev_001", "main", "make test")

        # 捕获历史输出
        mock_pane.capture_pane.return_value = [
            "Building...",
            "Build complete",
            "Running tests...",
            "All tests passed",
            "$",
        ]
        result = mgr_with_pane.capture_pane_history(
            "agent_dev_001", "main", lines=200
        )
        assert "Building..." in result
        assert "All tests passed" in result

    def test_send_special_keys_and_capture(
        self, mgr_with_pane, mock_pane
    ):
        """发送特殊按键（如 C-c）后捕获"""
        mgr_with_pane.send_keys("agent_dev_001", "main", "C-c")
        mock_pane.send_keys.assert_called_once_with("C-c", enter=False)

        mock_pane.capture_pane.return_value = ["$"]
        result = mgr_with_pane.capture_pane("agent_dev_001", "main")
        assert result == ["$"]

    def test_send_literal_text_and_capture(
        self, mgr_with_pane, mock_pane
    ):
        """发送字面文本后捕获"""
        mgr_with_pane.send_keys(
            "agent_dev_001", "main", "hello$world", literal=True
        )
        mock_pane.send_keys.assert_called_once_with(
            "hello$world", enter=False, literal=True
        )

    def test_capture_pane_then_history(
        self, mgr_with_pane, mock_pane
    ):
        """先捕获当前再捕获历史"""
        # 捕获当前
        mock_pane.capture_pane.return_value = ["$ ls", "$"]
        current = mgr_with_pane.capture_pane("agent_dev_001", "main")
        assert len(current) == 2

        # 重置 mock
        mock_pane.capture_pane.reset_mock()

        # 捕获历史
        mock_pane.capture_pane.return_value = [
            "old command",
            "$ ls",
            "$",
        ]
        history = mgr_with_pane.capture_pane_history(
            "agent_dev_001", "main", lines=50
        )
        assert len(history) == 3
        mock_pane.capture_pane.assert_called_once_with(start=-50)

    def test_suppress_history_on_off(
        self, mgr_with_pane, mock_pane
    ):
        """suppress_history 开关控制"""
        # 默认开启
        mgr_with_pane.send_command("agent_dev_001", "main", "secret_cmd")
        call1 = mock_pane.send_keys.call_args[1]
        assert call1["suppress_history"] is True

        # 显式关闭
        mgr_with_pane.send_command(
            "agent_dev_001", "main", "public_cmd", suppress_history=False
        )
        call2 = mock_pane.send_keys.call_args[1]
        assert call2["suppress_history"] is False

    def test_capture_none_fallback_flow(self, mgr_with_pane, mock_pane):
        """capture_pane 返回 None 时正确降级"""
        # capture_pane 返回 None
        mock_pane.capture_pane.return_value = None
        result = mgr_with_pane.capture_pane("agent_dev_001", "main")
        assert result == []

        # capture_pane_history 返回 None
        mock_pane.capture_pane.reset_mock()
        mock_pane.capture_pane.return_value = None
        result = mgr_with_pane.capture_pane_history(
            "agent_dev_001", "main", lines=50
        )
        assert result == []

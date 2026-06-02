"""
TmuxManager 窗口管理单元测试

使用 mock 隔离 libtmux 依赖，覆盖窗口管理的所有公共和内部方法：
- create_window: 正常创建、参数传递、空名称校验、会话不存在
- kill_window: 正常销毁、会话/窗口不存在返回 False
- list_windows: 正常列出、tmux 不可用、会话不存在、过滤 None
- window_exists: 存在/不存在、tmux 不可用、会话不存在
- _get_window: 获取存在的窗口、窗口不存在抛 ValueError
- _get_active_pane: 获取活跃 pane
- 命名规范: format / parse / validate 综合场景
"""

from unittest.mock import MagicMock, PropertyMock

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
    # 默认有 windows 的 filter 方法
    mock_windows = MagicMock()
    session.windows = mock_windows
    return session


@pytest.fixture
def mock_window():
    """创建 mock libtmux.Window"""
    window = MagicMock()
    window.name = "main"
    mock_pane = MagicMock()
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
def mgr_with_session(available_mgr, mock_server, mock_tmux_session):
    """创建带有 mock session 的 TmuxManager"""
    mock_sessions = MagicMock()
    mock_sessions.filter.return_value = [mock_tmux_session]
    mock_server.sessions = mock_sessions
    return available_mgr


# ─── create_window 测试 ────────────────────────────


class TestCreateWindow:
    """create_window() 方法测试"""

    def test_create_basic(self, mgr_with_session, mock_tmux_session, mock_window):
        """基本创建窗口"""
        mock_tmux_session.new_window.return_value = mock_window
        result = mgr_with_session.create_window("agent_dev_001", "main")
        assert result is mock_window
        mock_tmux_session.new_window.assert_called_once_with(
            window_name="main", attach=False
        )

    def test_create_with_cmd(self, mgr_with_session, mock_tmux_session, mock_window):
        """指定 cmd 创建窗口"""
        mock_tmux_session.new_window.return_value = mock_window
        mgr_with_session.create_window("agent_dev_001", "shell", cmd="bash")
        mock_tmux_session.new_window.assert_called_once_with(
            window_name="shell", attach=False, window_shell="bash"
        )

    def test_create_with_start_directory(
        self, mgr_with_session, mock_tmux_session, mock_window
    ):
        """指定 start_directory 创建窗口"""
        mock_tmux_session.new_window.return_value = mock_window
        mgr_with_session.create_window(
            "agent_dev_001", "main", start_directory="/tmp/project"
        )
        mock_tmux_session.new_window.assert_called_once_with(
            window_name="main", attach=False, start_directory="/tmp/project"
        )

    def test_create_with_all_options(
        self, mgr_with_session, mock_tmux_session, mock_window
    ):
        """指定所有选项创建窗口"""
        mock_tmux_session.new_window.return_value = mock_window
        mgr_with_session.create_window(
            "agent_dev_001", "shell", cmd="zsh", start_directory="/home"
        )
        mock_tmux_session.new_window.assert_called_once_with(
            window_name="shell",
            attach=False,
            window_shell="zsh",
            start_directory="/home",
        )

    def test_create_empty_session_raises(self, available_mgr):
        """空会话名称抛 ValueError"""
        with pytest.raises(ValueError, match="会话名称不能为空"):
            available_mgr.create_window("", "main")

    def test_create_whitespace_session_raises(self, available_mgr):
        """纯空格会话名称抛 ValueError"""
        with pytest.raises(ValueError, match="会话名称不能为空"):
            available_mgr.create_window("   ", "main")

    def test_create_empty_window_name_raises(self, available_mgr):
        """空窗口名称抛 ValueError"""
        with pytest.raises(ValueError, match="窗口名称不能为空"):
            available_mgr.create_window("agent_dev_001", "")

    def test_create_whitespace_window_name_raises(self, available_mgr):
        """纯空格窗口名称抛 ValueError"""
        with pytest.raises(ValueError, match="窗口名称不能为空"):
            available_mgr.create_window("agent_dev_001", "   ")

    def test_create_nonexistent_session_raises(self, available_mgr, mock_server):
        """会话不存在时抛 ValueError"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = []  # 空结果
        mock_server.sessions = mock_sessions
        with pytest.raises(ValueError, match="会话不存在"):
            available_mgr.create_window("nonexistent", "main")

    def test_create_returns_window(
        self, mgr_with_session, mock_tmux_session, mock_window
    ):
        """返回 libtmux.Window 实例"""
        mock_tmux_session.new_window.return_value = mock_window
        result = mgr_with_session.create_window("agent_dev_001", "main")
        assert result is mock_window

    def test_create_attach_false(
        self, mgr_with_session, mock_tmux_session, mock_window
    ):
        """创建窗口时 attach=False（不自动切换）"""
        mock_tmux_session.new_window.return_value = mock_window
        mgr_with_session.create_window("agent_dev_001", "main")
        call_kwargs = mock_tmux_session.new_window.call_args[1]
        assert call_kwargs["attach"] is False


# ─── kill_window 测试 ──────────────────────────────


class TestKillWindow:
    """kill_window() 方法测试"""

    def test_kill_existing_window(
        self, available_mgr, mock_server, mock_tmux_session
    ):
        """销毁存在的窗口返回 True"""
        # session_exists → True
        mock_server.has_session.return_value = True
        # window_exists → True: list_windows 返回包含窗口名
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = [mock_tmux_session]
        mock_server.sessions = mock_sessions

        w1 = MagicMock()
        w1.name = "main"
        mock_tmux_session.windows = [w1]

        result = available_mgr.kill_window("agent_dev_001", "main")
        assert result is True
        mock_tmux_session.kill_window.assert_called_once_with("main")

    def test_kill_session_not_exists(self, available_mgr, mock_server):
        """会话不存在返回 False"""
        mock_server.has_session.return_value = False
        result = available_mgr.kill_window("nonexistent", "main")
        assert result is False

    def test_kill_window_not_exists(self, available_mgr, mock_server, mock_tmux_session):
        """窗口不存在返回 False"""
        mock_server.has_session.return_value = True
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = [mock_tmux_session]
        mock_server.sessions = mock_sessions
        mock_tmux_session.windows = []  # 空窗口列表

        result = available_mgr.kill_window("agent_dev_001", "nonexistent")
        assert result is False
        mock_tmux_session.kill_window.assert_not_called()


# ─── list_windows 测试 ─────────────────────────────


class TestListWindows:
    """list_windows() 方法测试"""

    def test_list_with_windows(
        self, available_mgr, mock_server, mock_tmux_session
    ):
        """列出多个窗口"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = [mock_tmux_session]
        mock_server.sessions = mock_sessions

        w1 = MagicMock()
        w1.name = "main"
        w2 = MagicMock()
        w2.name = "shell"
        mock_tmux_session.windows = [w1, w2]

        result = available_mgr.list_windows("agent_dev_001")
        assert result == ["main", "shell"]

    def test_list_empty(self, available_mgr, mock_server, mock_tmux_session):
        """无窗口返回空列表"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = [mock_tmux_session]
        mock_server.sessions = mock_sessions
        mock_tmux_session.windows = []

        result = available_mgr.list_windows("agent_dev_001")
        assert result == []

    def test_list_filters_none_names(
        self, available_mgr, mock_server, mock_tmux_session
    ):
        """过滤 name 为 None 的窗口"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = [mock_tmux_session]
        mock_server.sessions = mock_sessions

        w1 = MagicMock()
        w1.name = "main"
        w2 = MagicMock()
        w2.name = None
        mock_tmux_session.windows = [w1, w2]

        result = available_mgr.list_windows("agent_dev_001")
        assert result == ["main"]

    def test_list_unavailable_returns_empty(self):
        """tmux 不可用返回空列表"""
        mgr = TmuxManager()
        mgr._available = False
        result = mgr.list_windows("any")
        assert result == []

    def test_list_session_not_exists(self, available_mgr, mock_server):
        """会话不存在返回空列表"""
        mock_server.has_session.return_value = False
        result = available_mgr.list_windows("nonexistent")
        assert result == []

    def test_list_exception_returns_empty(
        self, available_mgr, mock_server, mock_tmux_session
    ):
        """列出窗口异常返回空列表"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = [mock_tmux_session]
        mock_server.sessions = mock_sessions
        # 模拟访问 windows 时抛异常
        type(mock_tmux_session).windows = PropertyMock(
            side_effect=Exception("fail")
        )
        result = available_mgr.list_windows("agent_dev_001")
        assert result == []


# ─── window_exists 测试 ────────────────────────────


class TestWindowExists:
    """window_exists() 方法测试"""

    def test_exists_true(self, available_mgr, mock_server, mock_tmux_session):
        """窗口存在返回 True"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = [mock_tmux_session]
        mock_server.sessions = mock_sessions

        w1 = MagicMock()
        w1.name = "main"
        mock_tmux_session.windows = [w1]

        assert available_mgr.window_exists("agent_dev_001", "main") is True

    def test_exists_false(self, available_mgr, mock_server, mock_tmux_session):
        """窗口不存在返回 False"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = [mock_tmux_session]
        mock_server.sessions = mock_sessions
        mock_tmux_session.windows = []

        assert available_mgr.window_exists("agent_dev_001", "nonexistent") is False

    def test_exists_unavailable_returns_false(self):
        """tmux 不可用返回 False"""
        mgr = TmuxManager()
        mgr._available = False
        assert mgr.window_exists("any", "any") is False

    def test_exists_session_not_exists(self, available_mgr, mock_server):
        """会话不存在返回 False"""
        mock_server.has_session.return_value = False
        assert available_mgr.window_exists("nonexistent", "main") is False

    def test_exists_exception_returns_false(
        self, available_mgr, mock_server, mock_tmux_session
    ):
        """异常返回 False"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = [mock_tmux_session]
        mock_server.sessions = mock_sessions
        type(mock_tmux_session).windows = PropertyMock(
            side_effect=Exception("fail")
        )
        assert available_mgr.window_exists("agent_dev_001", "main") is False


# ─── _get_window 测试 ──────────────────────────────


class TestGetWindow:
    """_get_window() 内部方法测试"""

    def test_get_existing_window(
        self, mgr_with_session, mock_tmux_session, mock_window
    ):
        """获取存在的窗口"""
        mock_windows = MagicMock()
        mock_windows.filter.return_value = [mock_window]
        mock_tmux_session.windows = mock_windows

        result = mgr_with_session._get_window("agent_dev_001", "main")
        assert result is mock_window
        mock_windows.filter.assert_called_once_with(window_name="main")

    def test_get_nonexistent_window_raises(
        self, mgr_with_session, mock_tmux_session
    ):
        """获取不存在的窗口抛 ValueError"""
        mock_windows = MagicMock()
        mock_windows.filter.return_value = []
        mock_tmux_session.windows = mock_windows

        with pytest.raises(ValueError, match="窗口不存在"):
            mgr_with_session._get_window("agent_dev_001", "nonexistent")

    def test_get_window_session_not_exists(self, available_mgr, mock_server):
        """会话不存在时抛 ValueError"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = []
        mock_server.sessions = mock_sessions

        with pytest.raises(ValueError, match="会话不存在"):
            available_mgr._get_window("nonexistent", "main")

    def test_get_filter_exception_raises(
        self, mgr_with_session, mock_tmux_session
    ):
        """filter 异常抛 ValueError"""
        mock_windows = MagicMock()
        mock_windows.filter.side_effect = Exception("fail")
        mock_tmux_session.windows = mock_windows

        with pytest.raises(ValueError, match="窗口不存在"):
            mgr_with_session._get_window("agent_dev_001", "main")


# ─── _get_active_pane 测试 ─────────────────────────


class TestGetActivePane:
    """_get_active_pane() 内部方法测试"""

    def test_get_pane_from_window(
        self, mgr_with_session, mock_tmux_session, mock_window
    ):
        """从窗口获取活跃 pane"""
        mock_windows = MagicMock()
        mock_windows.filter.return_value = [mock_window]
        mock_tmux_session.windows = mock_windows

        result = mgr_with_session._get_active_pane("agent_dev_001", "main")
        assert result is mock_window.active_pane

    def test_get_pane_window_not_exists(
        self, mgr_with_session, mock_tmux_session
    ):
        """窗口不存在时抛 ValueError"""
        mock_windows = MagicMock()
        mock_windows.filter.return_value = []
        mock_tmux_session.windows = mock_windows

        with pytest.raises(ValueError, match="窗口不存在"):
            mgr_with_session._get_active_pane("agent_dev_001", "nonexistent")

    def test_get_pane_session_not_exists(self, available_mgr, mock_server):
        """会话不存在时抛 ValueError"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = []
        mock_server.sessions = mock_sessions

        with pytest.raises(ValueError, match="会话不存在"):
            available_mgr._get_active_pane("nonexistent", "main")


# ─── 命名规范测试 ──────────────────────────────────


class TestNamingConvention:
    """命名规范方法综合测试"""

    def test_format_basic(self):
        """基本格式化"""
        mgr = TmuxManager()
        assert mgr.format_agent_window_name("dev", 1) == "agent_dev_001"

    def test_format_with_hyphen_role(self):
        """带连字符的角色名"""
        mgr = TmuxManager()
        assert mgr.format_agent_window_name("senior-dev", 5) == "agent_senior-dev_005"

    def test_format_seq_boundaries(self):
        """序号边界值"""
        mgr = TmuxManager()
        assert mgr.format_agent_window_name("dev", 1) == "agent_dev_001"
        assert mgr.format_agent_window_name("dev", 999) == "agent_dev_999"

    def test_format_empty_role_raises(self):
        """空 role 抛 ValueError"""
        mgr = TmuxManager()
        with pytest.raises(ValueError, match="角色名称不能为空"):
            mgr.format_agent_window_name("", 1)

    def test_format_uppercase_role_raises(self):
        """大写 role 抛 ValueError"""
        mgr = TmuxManager()
        with pytest.raises(ValueError, match="角色名称仅允许"):
            mgr.format_agent_window_name("Dev", 1)

    def test_format_seq_zero_raises(self):
        """seq=0 抛 ValueError"""
        mgr = TmuxManager()
        with pytest.raises(ValueError, match="序号必须为 1~999"):
            mgr.format_agent_window_name("dev", 0)

    def test_format_seq_over_999_raises(self):
        """seq>999 抛 ValueError"""
        mgr = TmuxManager()
        with pytest.raises(ValueError, match="序号必须为 1~999"):
            mgr.format_agent_window_name("dev", 1000)

    def test_format_role_starts_with_digit_raises(self):
        """role 以数字开头抛 ValueError"""
        mgr = TmuxManager()
        with pytest.raises(ValueError, match="角色名称仅允许"):
            mgr.format_agent_window_name("1dev", 1)

    def test_parse_valid_name(self):
        """解析有效名称"""
        mgr = TmuxManager()
        role, seq = mgr.parse_agent_window_name("agent_dev_001")
        assert role == "dev"
        assert seq == 1

    def test_parse_hyphen_role(self):
        """解析带连字符的角色名"""
        mgr = TmuxManager()
        role, seq = mgr.parse_agent_window_name("agent_senior-dev_005")
        assert role == "senior-dev"
        assert seq == 5

    def test_parse_invalid_name_raises(self):
        """解析无效名称抛 ValueError"""
        mgr = TmuxManager()
        with pytest.raises(ValueError, match="名称不符合"):
            mgr.parse_agent_window_name("invalid")

    def test_parse_no_seq_raises(self):
        """解析无序号名称抛 ValueError"""
        mgr = TmuxManager()
        with pytest.raises(ValueError, match="名称不符合"):
            mgr.parse_agent_window_name("agent_dev")

    def test_validate_valid(self):
        """校验有效名称返回 True"""
        mgr = TmuxManager()
        assert mgr.validate_agent_window_name("agent_dev_001") is True

    def test_validate_invalid(self):
        """校验无效名称返回 False"""
        mgr = TmuxManager()
        assert mgr.validate_agent_window_name("random_name") is False

    def test_validate_role_starts_with_digit(self):
        """校验数字开头的 role 返回 False"""
        mgr = TmuxManager()
        assert mgr.validate_agent_window_name("agent_1dev_001") is False

    def test_roundtrip(self):
        """格式化后解析一致性"""
        mgr = TmuxManager()
        for role, seq in [("dev", 1), ("qa", 12), ("pm", 999), ("senior-dev", 5)]:
            name = mgr.format_agent_window_name(role, seq)
            parsed_role, parsed_seq = mgr.parse_agent_window_name(name)
            assert parsed_role == role
            assert parsed_seq == seq


# ─── 窗口管理综合场景 ──────────────────────────────


class TestWindowRoundTrip:
    """窗口管理综合场景测试"""

    def test_create_then_exists(
        self, mgr_with_session, mock_tmux_session, mock_window
    ):
        """创建窗口后检查存在"""
        mock_tmux_session.new_window.return_value = mock_window
        mgr_with_session.create_window("agent_dev_001", "main")

        # 模拟窗口存在
        w1 = MagicMock()
        w1.name = "main"
        mock_tmux_session.windows = [w1]
        assert mgr_with_session.window_exists("agent_dev_001", "main") is True

    def test_kill_then_not_exists(
        self, available_mgr, mock_server, mock_tmux_session
    ):
        """销毁窗口后检查不存在"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = [mock_tmux_session]
        mock_server.sessions = mock_sessions

        # 窗口存在 → kill 成功
        w1 = MagicMock()
        w1.name = "main"
        mock_tmux_session.windows = [w1]
        result = available_mgr.kill_window("agent_dev_001", "main")
        assert result is True

        # 窗口已销毁 → 不存在
        mock_tmux_session.windows = []
        assert available_mgr.window_exists("agent_dev_001", "main") is False

    def test_create_list_kill_flow(
        self, available_mgr, mock_server, mock_tmux_session, mock_window
    ):
        """创建 → 列出 → 销毁完整流程"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = [mock_tmux_session]
        mock_server.sessions = mock_sessions

        # 创建窗口
        mock_tmux_session.new_window.return_value = mock_window
        available_mgr.create_window("agent_dev_001", "main")

        # 列出窗口
        w1 = MagicMock()
        w1.name = "main"
        mock_tmux_session.windows = [w1]
        windows = available_mgr.list_windows("agent_dev_001")
        assert "main" in windows

        # 销毁窗口
        result = available_mgr.kill_window("agent_dev_001", "main")
        assert result is True

    def test_multiple_windows(
        self, mgr_with_session, mock_tmux_session, mock_window
    ):
        """多窗口管理"""
        mock_tmux_session.new_window.return_value = mock_window
        mgr_with_session.create_window("agent_dev_001", "main")
        mgr_with_session.create_window("agent_dev_001", "shell")

        w1 = MagicMock()
        w1.name = "main"
        w2 = MagicMock()
        w2.name = "shell"
        mock_tmux_session.windows = [w1, w2]

        windows = mgr_with_session.list_windows("agent_dev_001")
        assert len(windows) == 2
        assert "main" in windows
        assert "shell" in windows

    def test_naming_convention_with_window_ops(
        self, mgr_with_session, mock_tmux_session, mock_window
    ):
        """使用命名规范名称进行窗口操作"""
        mgr = mgr_with_session
        name = mgr.format_agent_window_name("dev", 1)
        assert name == "agent_dev_001"
        assert mgr.validate_agent_window_name(name) is True

        # 用格式化名称创建窗口
        mock_tmux_session.new_window.return_value = mock_window
        mgr.create_window("agent_dev_001", name)

        # 解析窗口名
        role, seq = mgr.parse_agent_window_name(name)
        assert role == "dev"
        assert seq == 1

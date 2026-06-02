"""
TmuxManager 会话管理单元测试

使用 mock 隔离 libtmux 依赖，覆盖会话管理的所有公共方法：
- create_session: 正常创建、参数传递、空名称校验
- kill_session: 正常销毁、会话不存在返回 False
- list_sessions: 正常列出、tmux 不可用返回空列表
- session_exists: 存在/不存在、tmux 不可用返回 False
- is_available: 可用/不可用/缓存行为
- server 属性: 延迟初始化、tmux 不可用抛 RuntimeError
- reset_availability: 重置缓存
- _parse_version: 各种版本格式
"""

from unittest.mock import MagicMock, patch

import pytest

from agent_automation_system.tmux_manager import TmuxManager


# ─── Fixtures ──────────────────────────────────────


@pytest.fixture
def mock_server():
    """创建 mock libtmux.Server 实例"""
    server = MagicMock()
    server.is_alive.return_value = True
    server.has_session.return_value = False
    server.sessions = []
    return server


@pytest.fixture
def mock_session():
    """创建 mock libtmux.Session 实例"""
    session = MagicMock()
    session.name = "test_session"
    return session


@pytest.fixture
def tmux_mgr():
    """创建 TmuxManager 实例（不连接真实 tmux）"""
    return TmuxManager()


@pytest.fixture
def available_mgr(mock_server):
    """创建已标记为可用的 TmuxManager 实例，注入 mock server"""
    mgr = TmuxManager()
    mgr._available = True
    mgr._server = mock_server
    return mgr


# ─── is_available 测试 ──────────────────────────────


class TestIsAvailable:
    """is_available() 方法测试"""

    @patch("agent_automation_system.tmux_manager.tmux_manager.shutil.which")
    def test_tmux_not_in_path(self, mock_which):
        """tmux 不在 PATH 中返回 False"""
        mock_which.return_value = None
        mgr = TmuxManager()
        assert mgr.is_available() is False

    @patch("agent_automation_system.tmux_manager.tmux_manager.shutil.which")
    def test_tmux_in_path_server_alive(self, mock_which):
        """tmux 在 PATH 且 server 存活返回 True"""
        mock_which.return_value = "/usr/bin/tmux"
        mgr = TmuxManager()
        mock_srv = MagicMock()
        mock_srv.is_alive.return_value = True
        mgr._create_server = MagicMock(return_value=mock_srv)
        assert mgr.is_available() is True

    @patch("agent_automation_system.tmux_manager.tmux_manager.shutil.which")
    def test_tmux_in_path_server_dead_can_start(self, mock_which):
        """tmux 在 PATH、server 不存活但可以启动返回 True"""
        mock_which.return_value = "/usr/bin/tmux"
        mgr = TmuxManager()
        mock_srv = MagicMock()
        mock_srv.is_alive.return_value = False
        mock_srv.new_session.return_value = MagicMock()
        mgr._create_server = MagicMock(return_value=mock_srv)
        assert mgr.is_available() is True
        mock_srv.new_session.assert_called_once()

    @patch("agent_automation_system.tmux_manager.tmux_manager.shutil.which")
    def test_tmux_in_path_server_dead_cannot_start(self, mock_which):
        """tmux 在 PATH、server 不存活且无法启动返回 False"""
        mock_which.return_value = "/usr/bin/tmux"
        mgr = TmuxManager()
        mock_srv = MagicMock()
        mock_srv.is_alive.return_value = False
        mock_srv.new_session.side_effect = Exception("cannot start")
        mgr._create_server = MagicMock(return_value=mock_srv)
        assert mgr.is_available() is False

    @patch("agent_automation_system.tmux_manager.tmux_manager.shutil.which")
    def test_create_server_exception(self, mock_which):
        """_create_server 抛异常返回 False"""
        mock_which.return_value = "/usr/bin/tmux"
        mgr = TmuxManager()
        mgr._create_server = MagicMock(side_effect=Exception("fail"))
        assert mgr.is_available() is False

    def test_cached_available(self):
        """可用性结果被缓存"""
        mgr = TmuxManager()
        mgr._available = True
        # 不应调用 shutil.which
        assert mgr.is_available() is True

    def test_cached_unavailable(self):
        """不可用结果被缓存"""
        mgr = TmuxManager()
        mgr._available = False
        assert mgr.is_available() is False


# ─── server 属性 测试 ──────────────────────────────


class TestServerProperty:
    """server 属性测试"""

    def test_lazy_init(self, mock_server):
        """server 延迟初始化"""
        mgr = TmuxManager()
        mgr._available = True
        mgr._create_server = MagicMock(return_value=mock_server)
        srv = mgr.server
        assert srv is mock_server
        mgr._create_server.assert_called_once()

    def test_server_cached(self, mock_server):
        """server 缓存后不重复创建"""
        mgr = TmuxManager()
        mgr._available = True
        mgr._server = mock_server
        srv1 = mgr.server
        srv2 = mgr.server
        assert srv1 is srv2

    def test_server_unavailable_raises(self):
        """tmux 不可用时访问 server 抛 RuntimeError"""
        mgr = TmuxManager()
        mgr._available = False
        with pytest.raises(RuntimeError, match="tmux 不可用"):
            _ = mgr.server


# ─── reset_availability 测试 ────────────────────────


class TestResetAvailability:
    """reset_availability() 方法测试"""

    def test_resets_all_cache(self, mock_server):
        """重置清空所有缓存"""
        mgr = TmuxManager()
        mgr._available = True
        mgr._version = "3.4"
        mgr._server = mock_server
        mgr.reset_availability()
        assert mgr._available is None
        assert mgr._version is None
        assert mgr._server is None

    def test_reset_forces_redetect(self):
        """重置后 is_available 重新检测"""
        mgr = TmuxManager()
        mgr._available = True
        mgr.reset_availability()
        # 重置后 _available 为 None，下次调用 is_available 会重新检测
        assert mgr._available is None


# ─── _parse_version 测试 ────────────────────────────


class TestParseVersion:
    """_parse_version() 静态方法测试"""

    def test_standard_version(self):
        """标准版本格式"""
        assert TmuxManager._parse_version("tmux 3.4") == "3.4"

    def test_next_version(self):
        """next- 前缀版本"""
        assert TmuxManager._parse_version("tmux next-3.5") == "next-3.5"

    def test_letter_suffix(self):
        """字母后缀版本"""
        assert TmuxManager._parse_version("tmux 3.3a") == "3.3a"

    def test_rc_version(self):
        """RC 版本"""
        assert TmuxManager._parse_version("tmux 1.9-rc4") == "1.9-rc4"

    def test_invalid_format(self):
        """无效格式返回 None"""
        assert TmuxManager._parse_version("not tmux") is None

    def test_empty_string(self):
        """空字符串返回 None"""
        assert TmuxManager._parse_version("") is None

    def test_extra_spaces(self):
        """多余空格也能解析（正则匹配多空格）"""
        assert TmuxManager._parse_version("tmux  3.4") == "3.4"


# ─── create_session 测试 ────────────────────────────


class TestCreateSession:
    """create_session() 方法测试"""

    def test_create_basic(self, available_mgr, mock_server, mock_session):
        """基本创建会话"""
        mock_server.new_session.return_value = mock_session
        result = available_mgr.create_session("agent_dev_001")
        assert result is mock_session
        mock_server.new_session.assert_called_once_with(
            session_name="agent_dev_001", detach=True
        )

    def test_create_with_start_directory(self, available_mgr, mock_server, mock_session):
        """指定起始目录创建会话"""
        mock_server.new_session.return_value = mock_session
        available_mgr.create_session("test", start_directory="/tmp/project")
        mock_server.new_session.assert_called_once_with(
            session_name="test", detach=True, start_directory="/tmp/project"
        )

    def test_create_with_window_name(self, available_mgr, mock_server, mock_session):
        """指定窗口名称创建会话"""
        mock_server.new_session.return_value = mock_session
        available_mgr.create_session("test", window_name="main")
        mock_server.new_session.assert_called_once_with(
            session_name="test", detach=True, window_name="main"
        )

    def test_create_with_window_command(self, available_mgr, mock_server, mock_session):
        """指定窗口命令创建会话"""
        mock_server.new_session.return_value = mock_session
        available_mgr.create_session("test", window_command="bash")
        mock_server.new_session.assert_called_once_with(
            session_name="test", detach=True, window_command="bash"
        )

    def test_create_with_all_options(self, available_mgr, mock_server, mock_session):
        """指定所有选项创建会话"""
        mock_server.new_session.return_value = mock_session
        available_mgr.create_session(
            "test",
            start_directory="/home",
            window_name="shell",
            window_command="zsh",
        )
        mock_server.new_session.assert_called_once_with(
            session_name="test",
            detach=True,
            start_directory="/home",
            window_name="shell",
            window_command="zsh",
        )

    def test_create_empty_name_raises(self, available_mgr):
        """空名称抛 ValueError"""
        with pytest.raises(ValueError, match="会话名称不能为空"):
            available_mgr.create_session("")

    def test_create_whitespace_name_raises(self, available_mgr):
        """纯空格名称抛 ValueError"""
        with pytest.raises(ValueError, match="会话名称不能为空"):
            available_mgr.create_session("   ")

    def test_create_triggers_server(self, mock_server, mock_session):
        """create_session 触发 server 初始化"""
        mgr = TmuxManager()
        mgr._available = True
        mgr._create_server = MagicMock(return_value=mock_server)
        mock_server.new_session.return_value = mock_session
        mgr.create_session("test")
        assert mgr._server is mock_server

    def test_create_returns_session(self, available_mgr, mock_server, mock_session):
        """返回 libtmux.Session 实例"""
        mock_server.new_session.return_value = mock_session
        result = available_mgr.create_session("test")
        assert result is mock_session


# ─── kill_session 测试 ──────────────────────────────


class TestKillSession:
    """kill_session() 方法测试"""

    def test_kill_existing_session(self, available_mgr, mock_server):
        """销毁存在的会话返回 True"""
        mock_server.has_session.return_value = True
        result = available_mgr.kill_session("agent_dev_001")
        assert result is True
        mock_server.kill_session.assert_called_once_with("agent_dev_001")

    def test_kill_nonexistent_session(self, available_mgr, mock_server):
        """销毁不存在的会话返回 False"""
        mock_server.has_session.return_value = False
        result = available_mgr.kill_session("nonexistent")
        assert result is False
        mock_server.kill_session.assert_not_called()

    def test_kill_uses_exact_match(self, available_mgr, mock_server):
        """使用 exact=True 精确匹配"""
        mock_server.has_session.return_value = True
        available_mgr.kill_session("test")
        mock_server.has_session.assert_called_with("test", exact=True)


# ─── list_sessions 测试 ─────────────────────────────


class TestListSessions:
    """list_sessions() 方法测试"""

    def test_list_with_sessions(self, available_mgr, mock_server):
        """列出多个会话"""
        s1 = MagicMock()
        s1.name = "agent_dev_001"
        s2 = MagicMock()
        s2.name = "agent_qa_002"
        mock_server.sessions = [s1, s2]
        result = available_mgr.list_sessions()
        assert result == ["agent_dev_001", "agent_qa_002"]

    def test_list_empty(self, available_mgr, mock_server):
        """无会话返回空列表"""
        mock_server.sessions = []
        result = available_mgr.list_sessions()
        assert result == []

    def test_list_filters_none_names(self, available_mgr, mock_server):
        """过滤 name 为 None 的会话"""
        s1 = MagicMock()
        s1.name = "valid"
        s2 = MagicMock()
        s2.name = None
        mock_server.sessions = [s1, s2]
        result = available_mgr.list_sessions()
        assert result == ["valid"]

    def test_list_unavailable_returns_empty(self, tmux_mgr):
        """tmux 不可用返回空列表"""
        tmux_mgr._available = False
        result = tmux_mgr.list_sessions()
        assert result == []

    def test_list_exception_returns_empty(self, available_mgr, mock_server):
        """列出会话异常返回空列表"""
        mock_server.sessions = property(lambda self: (_ for _ in ()).throw(Exception("fail")))
        # 使用更直接的方式模拟异常
        type(mock_server).sessions = property(lambda self: (_ for _ in ()).throw(Exception("fail")))
        result = available_mgr.list_sessions()
        assert result == []


# ─── session_exists 测试 ────────────────────────────


class TestSessionExists:
    """session_exists() 方法测试"""

    def test_exists_true(self, available_mgr, mock_server):
        """会话存在返回 True"""
        mock_server.has_session.return_value = True
        assert available_mgr.session_exists("agent_dev_001") is True

    def test_exists_false(self, available_mgr, mock_server):
        """会话不存在返回 False"""
        mock_server.has_session.return_value = False
        assert available_mgr.session_exists("nonexistent") is False

    def test_exists_uses_exact(self, available_mgr, mock_server):
        """使用 exact=True 精确匹配"""
        mock_server.has_session.return_value = False
        available_mgr.session_exists("test")
        mock_server.has_session.assert_called_with("test", exact=True)

    def test_exists_unavailable_returns_false(self, tmux_mgr):
        """tmux 不可用返回 False"""
        tmux_mgr._available = False
        assert tmux_mgr.session_exists("any") is False

    def test_exists_exception_returns_false(self, available_mgr, mock_server):
        """has_session 异常返回 False"""
        mock_server.has_session.side_effect = Exception("error")
        assert available_mgr.session_exists("any") is False


# ─── _get_session 测试 ──────────────────────────────


class TestGetSession:
    """_get_session() 内部方法测试"""

    def test_get_existing_session(self, available_mgr, mock_server, mock_session):
        """获取存在的会话"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = [mock_session]
        mock_server.sessions = mock_sessions
        result = available_mgr._get_session("test")
        assert result is mock_session
        mock_sessions.filter.assert_called_once_with(session_name="test")

    def test_get_nonexistent_session_raises(self, available_mgr, mock_server):
        """获取不存在的会话抛 ValueError"""
        mock_sessions = MagicMock()
        mock_sessions.filter.return_value = []
        mock_server.sessions = mock_sessions
        with pytest.raises(ValueError, match="会话不存在"):
            available_mgr._get_session("nonexistent")

    def test_get_filter_exception_raises(self, available_mgr, mock_server):
        """filter 异常抛 ValueError"""
        mock_sessions = MagicMock()
        mock_sessions.filter.side_effect = Exception("fail")
        mock_server.sessions = mock_sessions
        with pytest.raises(ValueError, match="会话不存在"):
            available_mgr._get_session("test")


# ─── 综合场景 ──────────────────────────────────────


class TestSessionRoundTrip:
    """会话管理综合场景测试"""

    def test_create_then_exists(self, available_mgr, mock_server, mock_session):
        """创建后检查存在"""
        mock_server.new_session.return_value = mock_session
        available_mgr.create_session("agent_dev_001")

        mock_server.has_session.return_value = True
        assert available_mgr.session_exists("agent_dev_001") is True

    def test_kill_then_not_exists(self, available_mgr, mock_server):
        """销毁后检查不存在"""
        mock_server.has_session.return_value = True
        available_mgr.kill_session("agent_dev_001")

        mock_server.has_session.return_value = False
        assert available_mgr.session_exists("agent_dev_001") is False

    def test_create_list_kill_flow(self, available_mgr, mock_server, mock_session):
        """创建 → 列出 → 销毁完整流程"""
        # 创建
        mock_server.new_session.return_value = mock_session
        available_mgr.create_session("agent_dev_001")

        # 列出
        s1 = MagicMock()
        s1.name = "agent_dev_001"
        mock_server.sessions = [s1]
        sessions = available_mgr.list_sessions()
        assert "agent_dev_001" in sessions

        # 销毁
        mock_server.has_session.return_value = True
        result = available_mgr.kill_session("agent_dev_001")
        assert result is True

    def test_multiple_sessions(self, available_mgr, mock_server, mock_session):
        """多个会话管理"""
        mock_server.new_session.return_value = mock_session
        available_mgr.create_session("agent_dev_001")
        available_mgr.create_session("agent_qa_002")

        s1 = MagicMock()
        s1.name = "agent_dev_001"
        s2 = MagicMock()
        s2.name = "agent_qa_002"
        mock_server.sessions = [s1, s2]

        sessions = available_mgr.list_sessions()
        assert len(sessions) == 2
        assert "agent_dev_001" in sessions
        assert "agent_qa_002" in sessions

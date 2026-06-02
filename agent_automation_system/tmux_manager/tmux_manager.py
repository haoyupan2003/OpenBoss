"""
TmuxManager - tmux 集成管理器

基于 libtmux 封装，提供 tmux 可用性检测、版本获取和会话管理能力。

设计原则：
    - 优雅处理 tmux 未安装的场景（is_available → False）
    - 所有 tmux 操作通过 libtmux.Server 执行
    - 版本检测兼容 tmux 不同输出格式（"tmux 3.4" / "tmux next-3.5"）
    - 会话操作失败时抛出明确异常，不静默吞错误

依赖：
    - libtmux>=0.23.0
    - 系统 tmux 二进制文件
"""

import logging
import re
import shutil
from pathlib import Path
from typing import Optional

import libtmux

logger = logging.getLogger(__name__)


class TmuxManager:
    """tmux 集成管理器

    提供 tmux 环境检测和会话管理能力，是所有 tmux 操作的入口。

    基于 PRD §7.4 tmux Session Management：
    - 每个 Agent 运行在独立的 tmux 会话中
    - 会话命名规范：agent_{role}_{seq}
    - tmux 提供进程级隔离和会话持久化

    会话管理方法：
    - create_session(name): 创建后台 tmux 会话
    - kill_session(name): 销毁指定会话
    - list_sessions(): 列出所有会话名称
    - session_exists(name): 检查会话是否存在

    窗口管理方法：
    - create_window(session, name, cmd): 在指定会话中创建窗口
    - kill_window(session, window): 销毁指定窗口
    - list_windows(session): 列出会话中的所有窗口名称

    命令发送方法：
    - send_keys(session, window, keys): 向窗口发送按键
    - send_command(session, window, cmd): 向窗口发送命令（自动回车）

    输出捕获方法：
    - capture_pane(session, window): 捕获窗口当前可见输出
    - capture_pane_history(session, window, lines): 捕获窗口历史输出

    命名规范方法：
    - format_agent_window_name(role, seq): 生成 agent_{role}_{seq} 格式名称
    - parse_agent_window_name(name): 解析名称为 (role, seq) 元组
    - validate_agent_window_name(name): 校验名称是否符合规范

    Args:
        socket_name: tmux socket 名称（可选，用于隔离不同项目）
        socket_path: tmux socket 路径（可选）
        config_file: tmux 配置文件路径（可选）
        tmux_bin: tmux 二进制文件路径（可选，默认自动检测）
    """

    def __init__(
        self,
        socket_name: Optional[str] = None,
        socket_path: Optional[str] = None,
        config_file: Optional[str] = None,
        tmux_bin: Optional[str] = None,
    ):
        self._socket_name = socket_name
        self._socket_path = socket_path
        self._config_file = config_file
        self._tmux_bin = tmux_bin

        # 延迟初始化 Server，避免 tmux 不可用时构造失败
        self._server: Optional[libtmux.Server] = None
        self._available: Optional[bool] = None
        self._version: Optional[str] = None

    # ─── 属性 ───────────────────────────────────────

    @property
    def server(self) -> libtmux.Server:
        """获取 libtmux.Server 实例（延迟初始化）

        Returns:
            libtmux.Server 实例

        Raises:
            RuntimeError: tmux 不可用时
        """
        if self._server is None:
            if not self.is_available():
                raise RuntimeError(
                    "tmux 不可用，请确认 tmux 已安装且在 PATH 中"
                )
            self._server = self._create_server()
        return self._server

    # ─── 可用性检测 ─────────────────────────────────

    def is_available(self) -> bool:
        """检测 tmux 是否可用

        检查步骤：
        1. tmux 二进制文件是否在 PATH 中
        2. tmux 是否可执行
        3. libtmux.Server 是否能连接到 tmux 服务器

        结果会被缓存，后续调用直接返回缓存值。
        可通过 reset_availability() 重置缓存。

        Returns:
            True 如果 tmux 可用，False 否则
        """
        if self._available is not None:
            return self._available

        # 步骤 1：检查 tmux 二进制
        tmux_path = shutil.which("tmux")
        if tmux_path is None:
            logger.debug("tmux 二进制文件未在 PATH 中找到")
            self._available = False
            return False

        # 步骤 2：尝试通过 libtmux 检测
        try:
            server = self._create_server()
            # is_alive 会尝试连接 tmux server
            # 如果 tmux server 未运行，尝试启动
            if not server.is_alive():
                # 尝试启动 server（创建一个临时会话来触发 server 启动）
                try:
                    server.new_session(
                        session_name="__tmux_check__",
                        detach=True,
                        window_name="check",
                    )
                    # 清理临时会话
                    server.kill_session("__tmux_check__")
                except Exception:
                    logger.debug("无法启动 tmux 服务器")
                    self._available = False
                    return False

            self._available = True
            return True
        except Exception as e:
            logger.debug(f"tmux 可用性检测失败: {e}")
            self._available = False
            return False

    def reset_availability(self) -> None:
        """重置可用性缓存，强制下次 is_available() 重新检测"""
        self._available = None
        self._version = None
        self._server = None

    # ─── 版本检测 ───────────────────────────────────

    def get_version(self) -> Optional[str]:
        """获取 tmux 版本号

        执行 `tmux -V` 并解析版本字符串。

        tmux 版本输出格式示例：
        - "tmux 3.4"
        - "tmux next-3.5"
        - "tmux 3.3a"

        Returns:
            版本号字符串（如 "3.4"），如果 tmux 不可用则返回 None
        """
        if self._version is not None:
            return self._version

        if not self.is_available():
            return None

        try:
            server = self._create_server()
            result = server.cmd("-V")
            if result.stdout:
                raw = result.stdout[0].strip()
                self._version = self._parse_version(raw)
                return self._version
        except Exception as e:
            logger.debug(f"获取 tmux 版本失败: {e}")

        # 备用方案：直接执行 tmux -V
        try:
            import subprocess

            result = subprocess.run(
                ["tmux", "-V"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                raw = result.stdout.strip()
                self._version = self._parse_version(raw)
                return self._version
        except Exception as e:
            logger.debug(f"备用版本检测失败: {e}")

        return None

    def get_tmux_bin_path(self) -> Optional[str]:
        """获取 tmux 二进制文件路径

        Returns:
            tmux 的绝对路径，如果不在 PATH 中则返回 None
        """
        return shutil.which("tmux")

    # ─── 会话管理 ───────────────────────────────────

    def create_session(
        self,
        name: str,
        start_directory: Optional[str] = None,
        window_name: Optional[str] = None,
        window_command: Optional[str] = None,
    ) -> libtmux.Session:
        """创建 tmux 会话

        创建一个后台分离的 tmux 会话，用于运行 Agent 进程。

        对应 tmux 命令：tmux new-session -d -s {name}

        Args:
            name: 会话名称（建议遵循 agent_{role}_{seq} 命名规范）
            start_directory: 会话起始工作目录（可选）
            window_name: 初始窗口名称（可选）
            window_command: 初始窗口执行的命令（可选，窗口在命令退出时关闭）

        Returns:
            libtmux.Session 实例

        Raises:
            RuntimeError: tmux 不可用
            ValueError: 会话名称为空
            libtmux.exc.BadSessionName: 会话名称不合法
            Exception: 会话已存在或创建失败
        """
        if not name or not name.strip():
            raise ValueError("会话名称不能为空")

        server = self.server  # 触发可用性检查

        kwargs = {
            "session_name": name,
            "detach": True,  # 后台创建
        }
        if start_directory:
            kwargs["start_directory"] = start_directory
        if window_name:
            kwargs["window_name"] = window_name
        if window_command:
            kwargs["window_command"] = window_command

        session = server.new_session(**kwargs)
        logger.info(f"创建 tmux 会话: {name}")
        return session

    def kill_session(self, name: str) -> bool:
        """销毁 tmux 会话

        对应 tmux 命令：tmux kill-session -t {name}

        Args:
            name: 会话名称

        Returns:
            True 如果成功销毁，False 如果会话不存在

        Raises:
            RuntimeError: tmux 不可用
        """
        if not self.session_exists(name):
            logger.debug(f"会话不存在，跳过销毁: {name}")
            return False

        server = self.server
        server.kill_session(name)
        logger.info(f"销毁 tmux 会话: {name}")
        return True

    def list_sessions(self) -> list[str]:
        """列出所有 tmux 会话名称

        对应 tmux 命令：tmux list-sessions

        Returns:
            会话名称列表，tmux 不可用时返回空列表
        """
        if not self.is_available():
            return []

        try:
            server = self.server
            return [s.name for s in server.sessions if s.name is not None]
        except Exception as e:
            logger.debug(f"列出会话失败: {e}")
            return []

    def session_exists(self, name: str) -> bool:
        """检查 tmux 会话是否存在

        对应 tmux 命令：tmux has-session -t ={name}

        使用精确匹配（exact=True）避免 fnmatch 模糊匹配。

        Args:
            name: 会话名称

        Returns:
            True 如果会话存在，False 否则
        """
        if not self.is_available():
            return False

        try:
            server = self.server
            return server.has_session(name, exact=True)
        except Exception:
            return False

    # ─── 窗口管理 ───────────────────────────────────

    def create_window(
        self,
        session: str,
        name: str,
        cmd: Optional[str] = None,
        start_directory: Optional[str] = None,
    ) -> libtmux.Window:
        """在指定会话中创建窗口

        对应 tmux 命令：tmux new-window -t {session} -n {name} [{cmd}]

        Args:
            session: 目标会话名称
            name: 窗口名称
            cmd: 窗口启动时执行的命令（可选，命令退出后窗口关闭）
            start_directory: 窗口起始工作目录（可选）

        Returns:
            libtmux.Window 实例

        Raises:
            RuntimeError: tmux 不可用
            ValueError: 会话名称或窗口名称为空
            Exception: 会话不存在或窗口创建失败
        """
        if not session or not session.strip():
            raise ValueError("会话名称不能为空")
        if not name or not name.strip():
            raise ValueError("窗口名称不能为空")

        tmux_session = self._get_session(session)

        kwargs = {
            "window_name": name,
            "attach": False,  # 不自动切换到新窗口
        }
        if cmd:
            kwargs["window_shell"] = cmd
        if start_directory:
            kwargs["start_directory"] = start_directory

        window = tmux_session.new_window(**kwargs)
        logger.info(f"创建 tmux 窗口: {session}:{name}")
        return window

    def kill_window(self, session: str, window: str) -> bool:
        """销毁指定窗口

        对应 tmux 命令：tmux kill-window -t {session}:{window}

        Args:
            session: 会话名称
            window: 窗口名称

        Returns:
            True 如果成功销毁，False 如果窗口不存在

        Raises:
            RuntimeError: tmux 不可用
            Exception: 会话不存在
        """
        if not self.session_exists(session):
            logger.debug(f"会话不存在，跳过窗口销毁: {session}")
            return False

        if not self.window_exists(session, window):
            logger.debug(f"窗口不存在，跳过销毁: {session}:{window}")
            return False

        tmux_session = self._get_session(session)
        tmux_session.kill_window(window)
        logger.info(f"销毁 tmux 窗口: {session}:{window}")
        return True

    def list_windows(self, session: str) -> list[str]:
        """列出会话中的所有窗口名称

        对应 tmux 命令：tmux list-windows -t {session}

        Args:
            session: 会话名称

        Returns:
            窗口名称列表，会话不存在或 tmux 不可用时返回空列表
        """
        if not self.is_available():
            return []

        if not self.session_exists(session):
            return []

        try:
            tmux_session = self._get_session(session)
            return [w.name for w in tmux_session.windows if w.name is not None]
        except Exception as e:
            logger.debug(f"列出窗口失败: {e}")
            return []

    def window_exists(self, session: str, window: str) -> bool:
        """检查窗口是否存在于指定会话中

        Args:
            session: 会话名称
            window: 窗口名称

        Returns:
            True 如果窗口存在，False 否则
        """
        if not self.is_available():
            return False

        if not self.session_exists(session):
            return False

        try:
            windows = self.list_windows(session)
            return window in windows
        except Exception:
            return False

    # ─── 命令发送 ───────────────────────────────────

    def send_keys(
        self,
        session: str,
        window: str,
        keys: str,
        enter: bool = False,
        literal: bool = False,
        reset: bool = False,
    ) -> None:
        """向指定窗口发送按键

        对应 tmux 命令：tmux send-keys -t {session}:{window} {keys}

        通过窗口的 active_pane 发送按键。可用于发送特殊按键
        （如 C-c、C-d、Enter 等）或原始文本。

        Args:
            session: 会话名称
            window: 窗口名称
            keys: 要发送的按键或文本
            enter: 发送后是否自动回车，默认 False
            literal: 是否按字面发送（不解释特殊按键），默认 False
            reset: 发送前是否重置终端状态，默认 False

        Raises:
            RuntimeError: tmux 不可用
            ValueError: 会话或窗口不存在
        """
        pane = self._get_active_pane(session, window)

        kwargs = {}
        if literal:
            kwargs["literal"] = True
        if reset:
            kwargs["reset"] = True

        pane.send_keys(keys, enter=enter, **kwargs)
        logger.debug(f"发送按键到 {session}:{window}: {keys[:50]}...")

    def send_command(
        self,
        session: str,
        window: str,
        cmd: str,
        enter: bool = True,
        suppress_history: bool = True,
    ) -> None:
        """向指定窗口发送命令

        对应 tmux 命令：tmux send-keys -t {session}:{window} '{cmd}' Enter

        这是 send_keys 的高层封装，专门用于发送 shell 命令。
        默认自动回车执行，且在命令前加空格以避免污染 shell history。

        Args:
            session: 会话名称
            window: 窗口名称
            cmd: 要执行的命令
            enter: 发送后是否自动回车执行，默认 True
            suppress_history: 是否在命令前加空格以抑制 shell 历史，默认 True

        Raises:
            RuntimeError: tmux 不可用
            ValueError: 会话或窗口不存在
        """
        pane = self._get_active_pane(session, window)

        pane.send_keys(
            cmd,
            enter=enter,
            suppress_history=suppress_history,
        )
        logger.info(f"发送命令到 {session}:{window}: {cmd[:80]}")

    # ─── 输出捕获 ───────────────────────────────────

    def capture_pane(self, session: str, window: str) -> list[str]:
        """捕获指定窗口的当前终端输出

        对应 tmux 命令：tmux capture-pane -t {session}:{window} -p

        捕获窗口活跃 pane 的当前可见区域内容。
        返回的每行文本包含终端中的完整行（含尾部空格已被 tmux 去除）。

        Args:
            session: 会话名称
            window: 窗口名称

        Returns:
            终端输出行列表，每行一个字符串

        Raises:
            RuntimeError: tmux 不可用
            ValueError: 会话或窗口不存在
        """
        pane = self._get_active_pane(session, window)
        result = pane.capture_pane()
        if result is None:
            result = []
        logger.debug(f"捕获终端输出 {session}:{window}: {len(result)} 行")
        return result

    def capture_pane_history(
        self, session: str, window: str, lines: int = 100
    ) -> list[str]:
        """捕获指定窗口的终端历史输出

        对应 tmux 命令：tmux capture-pane -t {session}:{window} -p -S -{lines}

        从历史缓冲区中捕获指定行数的输出。
        与 capture_pane 不同，此方法会包含滚动出可见区域的旧输出。

        参数 lines 的含义：
        - lines > 0: 从历史缓冲区回溯 lines 行到当前可见区域末尾
        - lines == 0: 等同于 capture_pane()，仅返回可见区域

        Args:
            session: 会话名称
            window: 窗口名称
            lines: 要捕获的历史行数，默认 100

        Returns:
            终端输出行列表（含历史），每行一个字符串

        Raises:
            RuntimeError: tmux 不可用
            ValueError: 会话或窗口不存在、lines 为负数
        """
        if lines < 0:
            raise ValueError(f"历史行数不能为负数: {lines}")

        if lines == 0:
            return self.capture_pane(session, window)

        pane = self._get_active_pane(session, window)
        result = pane.capture_pane(start=-lines)
        if result is None:
            result = []
        logger.debug(
            f"捕获终端历史 {session}:{window}: 回溯 {lines} 行, "
            f"获取 {len(result)} 行"
        )
        return result

    # ─── 命名规范 ───────────────────────────────────

    # Agent 窗口命名正则：agent_{role}_{seq}
    # role: 小写字母和连字符（如 dev、qa、pm、senior-dev）
    # seq: 3 位零填充序号（如 001、012、999）
    _AGENT_NAME_PATTERN = re.compile(r"^agent_([a-z][a-z0-9-]*)_(\d{3})$")

    def format_agent_window_name(self, role: str, seq: int) -> str:
        """按 PRD §7.4 规范生成 Agent 窗口名称

        命名格式：agent_{role}_{seq}
        - role: Agent 角色（小写字母、数字和连字符）
        - seq: 序号（3 位零填充，如 001）

        示例：
        - format_agent_window_name("dev", 1)   → "agent_dev_001"
        - format_agent_window_name("qa", 12)   → "agent_qa_012"
        - format_agent_window_name("pm", 999)  → "agent_pm_999"

        Args:
            role: Agent 角色名称（仅允许小写字母、数字和连字符，必须以字母开头）
            seq: 序号（1~999）

        Returns:
            格式化的窗口名称

        Raises:
            ValueError: role 为空或包含非法字符、seq 超出范围
        """
        if not role or not role.strip():
            raise ValueError("角色名称不能为空")

        if not re.match(r"^[a-z][a-z0-9-]*$", role):
            raise ValueError(
                f"角色名称仅允许小写字母、数字和连字符，且必须以字母开头: {role!r}"
            )

        if not isinstance(seq, int) or seq < 1 or seq > 999:
            raise ValueError(f"序号必须为 1~999 的整数: {seq}")

        return f"agent_{role}_{seq:03d}"

    def parse_agent_window_name(self, name: str) -> tuple[str, int]:
        """解析 Agent 窗口名称为 (role, seq) 元组

        反向操作 format_agent_window_name。

        示例：
        - parse_agent_window_name("agent_dev_001") → ("dev", 1)
        - parse_agent_window_name("agent_qa_012")  → ("qa", 12)

        Args:
            name: 窗口名称

        Returns:
            (role, seq) 元组

        Raises:
            ValueError: 名称不符合 agent_{role}_{seq} 规范
        """
        match = self._AGENT_NAME_PATTERN.match(name)
        if not match:
            raise ValueError(
                f"名称不符合 agent_{{role}}_{{seq}} 规范: {name!r}"
            )
        role = match.group(1)
        seq = int(match.group(2))
        return (role, seq)

    def validate_agent_window_name(self, name: str) -> bool:
        """校验名称是否符合 Agent 窗口命名规范

        Args:
            name: 窗口名称

        Returns:
            True 如果符合规范，False 否则
        """
        return bool(self._AGENT_NAME_PATTERN.match(name))

    # ─── 内部方法 ───────────────────────────────────

    def _get_session(self, name: str) -> libtmux.Session:
        """根据名称获取 libtmux.Session 实例

        Args:
            name: 会话名称

        Returns:
            libtmux.Session 实例

        Raises:
            ValueError: 会话不存在
        """
        server = self.server
        try:
            return server.sessions.filter(session_name=name)[0]
        except (IndexError, Exception):
            raise ValueError(f"会话不存在: {name}")

    def _get_window(self, session: str, window: str) -> libtmux.Window:
        """根据名称获取 libtmux.Window 实例

        Args:
            session: 会话名称
            window: 窗口名称

        Returns:
            libtmux.Window 实例

        Raises:
            ValueError: 会话或窗口不存在
        """
        tmux_session = self._get_session(session)
        try:
            return tmux_session.windows.filter(window_name=window)[0]
        except (IndexError, Exception):
            raise ValueError(f"窗口不存在: {session}:{window}")

    def _get_active_pane(self, session: str, window: str) -> libtmux.Pane:
        """获取指定窗口的活跃 Pane

        Args:
            session: 会话名称
            window: 窗口名称

        Returns:
            libtmux.Pane 实例

        Raises:
            ValueError: 会话或窗口不存在
        """
        tmux_window = self._get_window(session, window)
        return tmux_window.active_pane

    def _create_server(self) -> libtmux.Server:
        """创建 libtmux.Server 实例

        Returns:
            libtmux.Server 实例
        """
        kwargs = {}
        if self._socket_name:
            kwargs["socket_name"] = self._socket_name
        if self._socket_path:
            kwargs["socket_path"] = self._socket_path
        if self._config_file:
            kwargs["config_file"] = self._config_file
        if self._tmux_bin:
            kwargs["tmux_bin"] = self._tmux_bin

        return libtmux.Server(**kwargs)

    @staticmethod
    def _parse_version(raw: str) -> Optional[str]:
        """解析 tmux -V 输出的版本字符串

        支持的格式：
        - "tmux 3.4"       → "3.4"
        - "tmux next-3.5"  → "next-3.5"
        - "tmux 3.3a"      → "3.3a"
        - "tmux 1.9-rc4"   → "1.9-rc4"

        Args:
            raw: tmux -V 的原始输出

        Returns:
            解析后的版本号字符串，解析失败返回 None
        """
        # 匹配 "tmux <version>" 格式
        match = re.match(r"^tmux\s+(\S+)$", raw)
        if match:
            return match.group(1)
        return None

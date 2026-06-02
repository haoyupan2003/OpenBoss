"""
ClaudeCodeCLI — Claude Code CLI 启动与交互管理器

基于 PRD V2.0 §7.3 Claude Code Integration 和 §7.4 tmux Session Management 设计。
通过 TmuxManager 的 send_keys/send_command 能力，在 tmux 窗口中启动
Claude Code CLI 并注入初始 prompt。

启动流程：
1. 验证 tmux 会话和窗口存在
2. 在目标窗口中执行 `claude` 命令启动 CLI
3. 等待 CLI 就绪（检测输出中的提示符标志）
4. 通过 send_keys 注入 prompt 文本

交互流程：
- send_prompt: 向已运行的 CLI 发送新的 prompt
- is_cli_ready: 检测 CLI 是否就绪
- stop_cli: 优雅停止 CLI（发送 /exit 或 C-c）

设计原则：
    - 与 TmuxManager 解耦，通过依赖注入接收 TmuxManager 实例
    - CLI 启动参数可配置（命令路径、工作目录、模型参数等）
    - 支持自定义就绪检测逻辑
    - 优雅停止：先尝试 /exit，失败则 C-c
"""

import logging
import time
from enum import Enum
from typing import Optional, Union

from agent_automation_system.tmux_manager.tmux_manager import TmuxManager

logger = logging.getLogger(__name__)


class CLIStatus(str, Enum):
    """Claude Code CLI 运行状态

    对应 CLI 进程在 tmux 窗口中的生命周期。
    """

    NOT_STARTED = "not_started"  # CLI 尚未启动
    STARTING = "starting"        # CLI 正在启动中
    READY = "ready"              # CLI 已就绪，可以接收输入
    RUNNING = "running"          # CLI 正在执行任务（已发送 prompt）
    STOPPED = "stopped"          # CLI 已停止
    ERROR = "error"              # CLI 启动或运行出错


# Claude Code CLI 就绪标志 — 出现在输出中表示 CLI 已准备好接收输入
# Claude Code 启动后通常显示 "claude>" 或类似提示符
_CLI_READY_PATTERNS: list[str] = [
    "claude>",
    "claude >",
    ">",
]

# 默认 CLI 命令
_DEFAULT_CLI_COMMAND = "claude"

# 默认启动超时（秒）
_DEFAULT_STARTUP_TIMEOUT = 30

# 默认就绪检测间隔（秒）
_DEFAULT_READY_CHECK_INTERVAL = 0.5

# 默认停止等待超时（秒）
_DEFAULT_STOP_TIMEOUT = 10


class ClaudeCodeCLI:
    """Claude Code CLI 启动与交互管理器

    在 tmux 窗口中启动 Claude Code CLI，注入 prompt，
    并提供状态检测和优雅停止能力。

    Usage:
        tmux = TmuxManager()
        session = tmux.create_session("boss")
        window = tmux.create_window("boss", "agent_dev_001")

        cli = ClaudeCodeCLI(tmux_manager=tmux)
        result = cli.start_cli(
            session="boss",
            window="agent_dev_001",
            prompt="请实现用户登录页面",
        )

    Args:
        tmux_manager: TmuxManager 实例（必须）
        cli_command: CLI 命令路径，默认 "claude"
        startup_timeout: 启动超时时间（秒），默认 30
        ready_check_interval: 就绪检测间隔（秒），默认 0.5
        ready_patterns: 自定义就绪检测模式列表
        extra_args: CLI 启动时的额外参数（如 "--model opus"）
    """

    def __init__(
        self,
        tmux_manager: TmuxManager,
        cli_command: str = _DEFAULT_CLI_COMMAND,
        startup_timeout: float = _DEFAULT_STARTUP_TIMEOUT,
        ready_check_interval: float = _DEFAULT_READY_CHECK_INTERVAL,
        ready_patterns: Optional[list[str]] = None,
        extra_args: Optional[list[str]] = None,
    ) -> None:
        if tmux_manager is None:
            raise ValueError("tmux_manager cannot be None")

        self._tmux = tmux_manager
        self._cli_command = cli_command
        self._startup_timeout = startup_timeout
        self._ready_check_interval = ready_check_interval
        self._ready_patterns = ready_patterns or _CLI_READY_PATTERNS
        self._extra_args = extra_args or []

        # 跟踪各窗口的 CLI 状态
        self._status_map: dict[str, CLIStatus] = {}

    # ── 属性 ──────────────────────────────────────────────

    @property
    def tmux_manager(self) -> TmuxManager:
        """关联的 TmuxManager 实例"""
        return self._tmux

    @property
    def cli_command(self) -> str:
        """CLI 命令路径"""
        return self._cli_command

    @property
    def startup_timeout(self) -> float:
        """启动超时时间（秒）"""
        return self._startup_timeout

    @property
    def ready_check_interval(self) -> float:
        """就绪检测间隔（秒）"""
        return self._ready_check_interval

    @property
    def ready_patterns(self) -> list[str]:
        """就绪检测模式列表（只读副本）"""
        return list(self._ready_patterns)

    @property
    def extra_args(self) -> list[str]:
        """CLI 额外参数（只读副本）"""
        return list(self._extra_args)

    # ── 核心方法 ──────────────────────────────────────────

    def start_cli(
        self,
        session: str,
        window: str,
        prompt: Optional[str] = None,
        working_directory: Optional[str] = None,
    ) -> CLIStatus:
        """在 tmux 窗口中启动 Claude Code CLI

        执行流程：
        1. 验证 tmux 会话和窗口存在
        2. 构造 CLI 启动命令
        3. 通过 send_command 发送启动命令
        4. 等待 CLI 就绪（轮询输出检测提示符）
        5. 注入初始 prompt（如果提供）

        Args:
            session: tmux 会话名称
            window: tmux 窗口名称
            prompt: 初始 prompt 文本（可选，启动后注入）
            working_directory: 启动前切换的工作目录（可选）

        Returns:
            CLIStatus: CLI 启动后的状态

        Raises:
            ValueError: 会话或窗口不存在、参数无效
            RuntimeError: CLI 启动超时
        """
        # 参数校验
        if not session or not session.strip():
            raise ValueError("session cannot be empty")
        if not window or not window.strip():
            raise ValueError("window cannot be empty")

        # 验证会话和窗口存在
        if not self._tmux.session_exists(session):
            raise ValueError(f"Session does not exist: {session}")
        if not self._tmux.window_exists(session, window):
            raise ValueError(f"Window does not exist: {session}:{window}")

        key = self._make_key(session, window)

        # 如果已在运行，直接返回当前状态
        current_status = self._status_map.get(key)
        if current_status in (CLIStatus.READY, CLIStatus.RUNNING):
            logger.warning(
                "CLI already running in %s:%s (status=%s), skipping start",
                session,
                window,
                current_status.value,
            )
            return current_status

        # 可选：切换工作目录
        if working_directory:
            self._tmux.send_command(
                session, window, f"cd {working_directory}"
            )
            time.sleep(0.3)  # 等待 cd 完成

        # 构造 CLI 启动命令
        cmd = self._build_cli_command()
        logger.info(
            "Starting Claude Code CLI in %s:%s: %s",
            session,
            window,
            cmd,
        )

        # 发送启动命令
        self._status_map[key] = CLIStatus.STARTING
        self._tmux.send_command(session, window, cmd)

        # 等待 CLI 就绪
        ready = self._wait_for_ready(session, window)
        if not ready:
            self._status_map[key] = CLIStatus.ERROR
            raise RuntimeError(
                f"Claude Code CLI startup timed out after "
                f"{self._startup_timeout}s in {session}:{window}"
            )

        self._status_map[key] = CLIStatus.READY
        logger.info("Claude Code CLI ready in %s:%s", session, window)

        # 注入初始 prompt
        if prompt and prompt.strip():
            self._inject_prompt(session, window, prompt)
            self._status_map[key] = CLIStatus.RUNNING

        return self._status_map[key]

    def send_prompt(
        self,
        session: str,
        window: str,
        prompt: str,
    ) -> CLIStatus:
        """向已运行的 CLI 发送新 prompt

        前提：CLI 必须处于 READY 或 RUNNING 状态。
        如果 CLI 正在执行中，此方法会等待执行完成后再发送。

        Args:
            session: tmux 会话名称
            window: tmux 窗口名称
            prompt: 要发送的 prompt 文本

        Returns:
            CLIStatus: 发送后的 CLI 状态

        Raises:
            ValueError: CLI 未启动或参数无效
        """
        if not prompt or not prompt.strip():
            raise ValueError("prompt cannot be empty")

        key = self._make_key(session, window)
        current_status = self._status_map.get(key, CLIStatus.NOT_STARTED)

        if current_status not in (CLIStatus.READY, CLIStatus.RUNNING):
            raise ValueError(
                f"CLI is not ready in {session}:{window} "
                f"(status={current_status.value}). "
                f"Call start_cli() first."
            )

        self._inject_prompt(session, window, prompt)
        self._status_map[key] = CLIStatus.RUNNING
        logger.info(
            "Prompt sent to CLI in %s:%s (%d chars)",
            session,
            window,
            len(prompt),
        )
        return CLIStatus.RUNNING

    def is_cli_ready(
        self,
        session: str,
        window: str,
    ) -> bool:
        """检测 CLI 是否就绪

        通过捕获 tmux 窗口输出，检查是否包含就绪标志。

        Args:
            session: tmux 会话名称
            window: tmux 窗口名称

        Returns:
            True 如果 CLI 已就绪，False 否则
        """
        try:
            output = self._tmux.capture_pane_history(session, window, lines=50)
            output_text = "\n".join(output)
            return self._check_ready_output(output_text)
        except Exception as e:
            logger.debug(
                "Ready check failed for %s:%s: %s", session, window, e
            )
            return False

    def stop_cli(
        self,
        session: str,
        window: str,
        timeout: float = _DEFAULT_STOP_TIMEOUT,
    ) -> CLIStatus:
        """优雅停止 CLI

        停止策略：
        1. 先发送 /exit 命令（Claude Code 的退出命令）
        2. 等待一段时间检测是否退出
        3. 如果未退出，发送 C-c（SIGINT）
        4. 再等待，如果仍未退出，发送 C-c + C-d

        Args:
            session: tmux 会话名称
            window: tmux 窗口名称
            timeout: 停止等待超时（秒），默认 10

        Returns:
            CLIStatus: 停止后的状态
        """
        key = self._make_key(session, window)
        current_status = self._status_map.get(key, CLIStatus.NOT_STARTED)

        if current_status in (CLIStatus.NOT_STARTED, CLIStatus.STOPPED):
            logger.debug(
                "CLI already stopped in %s:%s", session, window
            )
            return current_status

        logger.info("Stopping CLI in %s:%s", session, window)

        # 策略 1: 发送 /exit
        try:
            self._tmux.send_command(session, window, "/exit")
            if self._wait_for_stop(session, window, timeout=timeout / 2):
                self._status_map[key] = CLIStatus.STOPPED
                logger.info("CLI stopped gracefully in %s:%s", session, window)
                return CLIStatus.STOPPED
        except Exception as e:
            logger.debug("/exit failed: %s", e)

        # 策略 2: 发送 C-c (SIGINT)
        try:
            self._tmux.send_keys(session, window, "C-c")
            if self._wait_for_stop(session, window, timeout=timeout / 2):
                self._status_map[key] = CLIStatus.STOPPED
                logger.info("CLI stopped with C-c in %s:%s", session, window)
                return CLIStatus.STOPPED
        except Exception as e:
            logger.debug("C-c failed: %s", e)

        # 策略 3: C-c + C-d
        try:
            self._tmux.send_keys(session, window, "C-c")
            time.sleep(0.5)
            self._tmux.send_keys(session, window, "C-d")
        except Exception as e:
            logger.debug("C-c + C-d failed: %s", e)

        # 即使不确定是否成功退出，也标记为 STOPPED
        self._status_map[key] = CLIStatus.STOPPED
        logger.warning(
            "CLI stop result uncertain in %s:%s, marked as STOPPED",
            session,
            window,
        )
        return CLIStatus.STOPPED

    def get_status(self, session: str, window: str) -> CLIStatus:
        """获取指定窗口的 CLI 状态

        Args:
            session: tmux 会话名称
            window: tmux 窗口名称

        Returns:
            CLIStatus: 当前状态
        """
        key = self._make_key(session, window)
        return self._status_map.get(key, CLIStatus.NOT_STARTED)

    # ── 内部方法 ──────────────────────────────────────────

    def _build_cli_command(self) -> str:
        """构造 CLI 启动命令

        Returns:
            完整的 CLI 启动命令字符串
        """
        parts = [self._cli_command]
        parts.extend(self._extra_args)
        return " ".join(parts)

    def _inject_prompt(
        self,
        session: str,
        window: str,
        prompt: str,
    ) -> None:
        """向 CLI 窗口注入 prompt 文本

        通过 send_keys 逐段发送 prompt（避免超长文本被截断），
        最后发送回车执行。

        Args:
            session: tmux 会话名称
            window: tmux 窗口名称
            prompt: prompt 文本
        """
        # 使用 literal=True 避免 tmux 解释特殊字符
        # 先发送 prompt 文本（不带回车），再单独发送回车
        prompt = prompt.strip()

        if len(prompt) <= 500:
            # 短 prompt 一次性发送
            self._tmux.send_keys(
                session, window, prompt, literal=True, enter=True
            )
        else:
            # 长 prompt 分段发送（每段 500 字符）
            chunks = self._split_prompt(prompt, chunk_size=500)
            for i, chunk in enumerate(chunks):
                is_last = i == len(chunks) - 1
                self._tmux.send_keys(
                    session,
                    window,
                    chunk,
                    literal=True,
                    enter=is_last,  # 只在最后一段发送回车
                )
                if not is_last:
                    time.sleep(0.1)  # 段间短暂延迟

        logger.debug(
            "Injected prompt into %s:%s (%d chars)",
            session,
            window,
            len(prompt),
        )

    @staticmethod
    def _split_prompt(prompt: str, chunk_size: int = 500) -> list[str]:
        """将长 prompt 分割为多个片段

        优先在换行符处分割，避免截断单词。

        Args:
            prompt: 原始 prompt 文本
            chunk_size: 每段最大字符数

        Returns:
            分割后的片段列表
        """
        if len(prompt) <= chunk_size:
            return [prompt]

        chunks: list[str] = []
        remaining = prompt

        while remaining:
            if len(remaining) <= chunk_size:
                chunks.append(remaining)
                break

            # 在 chunk_size 范围内找最后一个换行符
            cut_pos = remaining[:chunk_size].rfind("\n")
            if cut_pos == -1:
                # 没有换行符，强制在 chunk_size 处分割
                cut_pos = chunk_size
            else:
                cut_pos += 1  # 包含换行符

            chunks.append(remaining[:cut_pos])
            remaining = remaining[cut_pos:]

        return chunks

    def _wait_for_ready(
        self,
        session: str,
        window: str,
    ) -> bool:
        """等待 CLI 就绪

        轮询 tmux 输出，检测 CLI 提示符出现。

        Args:
            session: tmux 会话名称
            window: tmux 窗口名称

        Returns:
            True 如果 CLI 在超时前就绪，False 否则
        """
        elapsed = 0.0
        while elapsed < self._startup_timeout:
            if self.is_cli_ready(session, window):
                return True
            time.sleep(self._ready_check_interval)
            elapsed += self._ready_check_interval

        return False

    def _check_ready_output(self, output_text: str) -> bool:
        """检查输出文本是否包含就绪标志

        Args:
            output_text: tmux 窗口输出文本

        Returns:
            True 如果检测到就绪标志
        """
        for pattern in self._ready_patterns:
            if pattern in output_text:
                return True
        return False

    def _wait_for_stop(
        self,
        session: str,
        window: str,
        timeout: float = 5.0,
    ) -> bool:
        """等待 CLI 停止

        通过检测 tmux 输出中是否出现 shell 提示符
        （如 $ 或 >）来判断 CLI 是否已退出。

        Args:
            session: tmux 会话名称
            window: tmux 窗口名称
            timeout: 等待超时（秒）

        Returns:
            True 如果检测到 CLI 已退出
        """
        elapsed = 0.0
        interval = 0.5
        while elapsed < timeout:
            try:
                output = self._tmux.capture_pane(session, window)
                output_text = "\n".join(output)
                # 检测 shell 提示符（CLI 退出后会回到 shell）
                for line in output[-5:]:
                    stripped = line.strip()
                    if stripped.endswith("$") or stripped.endswith("#"):
                        return True
            except Exception:
                pass
            time.sleep(interval)
            elapsed += interval

        return False

    @staticmethod
    def _make_key(session: str, window: str) -> str:
        """生成状态跟踪的 key

        Args:
            session: 会话名称
            window: 窗口名称

        Returns:
            格式为 "session:window" 的 key
        """
        return f"{session}:{window}"

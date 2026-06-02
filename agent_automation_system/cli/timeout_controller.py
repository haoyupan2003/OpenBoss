"""
TimeoutController — 超时控制器

基于 PRD V2.0 §7.3 Claude Code Integration 设计。
为 Claude Code CLI 执行的任务提供超时控制能力，
当任务超时后自动终止 CLI 进程。

工作流程：
1. 调用 execute_with_timeout() 启动带超时的执行监控
2. 轮询 ResultDetector 检测任务是否完成/失败
3. 如果在超时前检测到终态 → 返回对应结果
4. 如果超时 → 调用 ClaudeCodeCLI.stop_cli() 终止 CLI → 返回 TIMEOUT 结果

设计原则：
    - 与 ClaudeCodeCLI 和 ResultDetector 解耦，通过依赖注入
    - 默认超时 600 秒（10 分钟），可按任务配置
    - 轮询间隔可配置，默认 5 秒
    - 超时后优雅终止 CLI（复用 stop_cli 的三级策略）
    - 支持取消正在监控的任务
    - 线程安全：仅记录跟踪信息，不做跨线程协调
"""

import logging
import time
from datetime import datetime
from enum import Enum
from typing import Optional

from agent_automation_system.cli.claude_code_cli import ClaudeCodeCLI, CLIStatus
from agent_automation_system.cli.result_detector import (
    DetectionResult,
    ExecutionStatus,
    ResultDetector,
)

logger = logging.getLogger(__name__)


class TimeoutStatus(str, Enum):
    """超时控制结果状态

    表示 execute_with_timeout() 的最终判定。
    """

    COMPLETED = "completed"    # 任务在超时前完成
    FAILED = "failed"          # 任务在超时前失败
    TIMEOUT = "timeout"        # 任务超时，CLI 已终止
    CANCELLED = "cancelled"    # 监控被取消
    UNKNOWN = "unknown"        # 无法判定（如无法获取输出）


class TimeoutResult:
    """超时控制结果

    封装 execute_with_timeout() 的所有返回信息。

    Attributes:
        status: 最终判定状态
        detection_result: 最后一次检测结果（可能为 None）
        timed_out: 是否超时
        elapsed_seconds: 实际执行耗时（秒）
        timeout_seconds: 设定的超时时间（秒）
        cancelled: 是否被取消
        stopped_cli: 超时后是否调用了 stop_cli
    """

    def __init__(
        self,
        status: TimeoutStatus,
        detection_result: Optional[DetectionResult] = None,
        timed_out: bool = False,
        elapsed_seconds: float = 0.0,
        timeout_seconds: float = 0.0,
        cancelled: bool = False,
        stopped_cli: bool = False,
    ) -> None:
        self.status = status
        self.detection_result = detection_result
        self.timed_out = timed_out
        self.elapsed_seconds = elapsed_seconds
        self.timeout_seconds = timeout_seconds
        self.cancelled = cancelled
        self.stopped_cli = stopped_cli

    @property
    def is_terminal(self) -> bool:
        """是否为终态"""
        return self.status in (
            TimeoutStatus.COMPLETED,
            TimeoutStatus.FAILED,
            TimeoutStatus.TIMEOUT,
        )

    @property
    def remaining_seconds(self) -> float:
        """超时剩余时间（可能为负数表示已超时）"""
        return self.timeout_seconds - self.elapsed_seconds

    def __repr__(self) -> str:
        return (
            f"TimeoutResult(status={self.status.value!r}, "
            f"elapsed={self.elapsed_seconds:.1f}s, "
            f"timeout={self.timeout_seconds:.1f}s, "
            f"timed_out={self.timed_out})"
        )


# ── 默认配置 ─────────────────────────────────────────────

# 默认任务超时时间（秒）— 10 分钟
_DEFAULT_TASK_TIMEOUT = 600

# 默认轮询间隔（秒）
_DEFAULT_POLL_INTERVAL = 5.0

# 超时后停止 CLI 的等待超时（秒）
_DEFAULT_STOP_TIMEOUT = 15.0


class TimeoutController:
    """超时控制器

    为 Claude Code CLI 执行的任务提供超时控制。
    当任务在指定时间内未完成时，自动终止 CLI 进程。

    执行流程：
    1. execute_with_timeout() 启动轮询监控
    2. 每隔 poll_interval 秒检测一次任务状态
    3. 检测到终态（完成/失败）→ 返回结果
    4. 超时 → 调用 stop_cli 终止 CLI → 返回 TIMEOUT 结果

    Usage:
        tmux = TmuxManager()
        cli = ClaudeCodeCLI(tmux_manager=tmux)
        detector = ResultDetector(tmux_manager=tmux)

        controller = TimeoutController(cli=cli, detector=detector)
        result = controller.execute_with_timeout(
            session="boss",
            window="agent_dev_001",
            timeout=300,
        )
        if result.timed_out:
            print(f"Task timed out after {result.elapsed_seconds:.1f}s")

    Args:
        cli: ClaudeCodeCLI 实例（必须）
        detector: ResultDetector 实例（必须）
        default_timeout: 默认超时时间（秒），默认 600
        poll_interval: 轮询检测间隔（秒），默认 5.0
        stop_timeout: 超时后停止 CLI 的等待时间（秒），默认 15.0
    """

    def __init__(
        self,
        cli: ClaudeCodeCLI,
        detector: ResultDetector,
        default_timeout: float = _DEFAULT_TASK_TIMEOUT,
        poll_interval: float = _DEFAULT_POLL_INTERVAL,
        stop_timeout: float = _DEFAULT_STOP_TIMEOUT,
    ) -> None:
        if cli is None:
            raise ValueError("cli cannot be None")
        if detector is None:
            raise ValueError("detector cannot be None")
        if default_timeout <= 0:
            raise ValueError("default_timeout must be positive")
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")

        self._cli = cli
        self._detector = detector
        self._default_timeout = default_timeout
        self._poll_interval = poll_interval
        self._stop_timeout = stop_timeout

        # 跟踪各窗口的超时状态
        self._start_times: dict[str, datetime] = {}
        self._timeouts: dict[str, float] = {}
        self._cancelled: dict[str, bool] = {}
        self._timed_out: dict[str, bool] = {}

    # ── 属性 ──────────────────────────────────────────────

    @property
    def cli(self) -> ClaudeCodeCLI:
        """关联的 ClaudeCodeCLI 实例"""
        return self._cli

    @property
    def detector(self) -> ResultDetector:
        """关联的 ResultDetector 实例"""
        return self._detector

    @property
    def default_timeout(self) -> float:
        """默认超时时间（秒）"""
        return self._default_timeout

    @property
    def poll_interval(self) -> float:
        """轮询间隔（秒）"""
        return self._poll_interval

    @property
    def stop_timeout(self) -> float:
        """停止 CLI 的等待超时（秒）"""
        return self._stop_timeout

    # ── 核心方法 ──────────────────────────────────────────

    def execute_with_timeout(
        self,
        session: str,
        window: str,
        timeout: Optional[float] = None,
    ) -> TimeoutResult:
        """带超时控制的执行监控

        轮询检测任务执行状态，直到任务完成/失败或超时。
        超时后自动调用 stop_cli() 终止 CLI 进程。

        Args:
            session: tmux 会话名称
            window: tmux 窗口名称
            timeout: 超时时间（秒），None 使用 default_timeout

        Returns:
            TimeoutResult: 超时控制结果

        Raises:
            ValueError: 参数无效
        """
        if not session or not session.strip():
            raise ValueError("session cannot be empty")
        if not window or not window.strip():
            raise ValueError("window cannot be empty")

        effective_timeout = timeout if timeout is not None else self._default_timeout
        if effective_timeout <= 0:
            raise ValueError("timeout must be positive")

        key = self._make_key(session, window)

        # 初始化跟踪状态
        self._start_times[key] = datetime.now()
        self._timeouts[key] = effective_timeout
        self._cancelled[key] = False
        self._timed_out[key] = False

        logger.info(
            "TimeoutController: monitoring %s:%s with timeout=%.1fs",
            session,
            window,
            effective_timeout,
        )

        start = time.monotonic()
        last_detection: Optional[DetectionResult] = None

        try:
            while True:
                elapsed = time.monotonic() - start

                # 检查是否被取消
                if self._cancelled.get(key, False):
                    logger.info(
                        "TimeoutController: %s:%s cancelled after %.1fs",
                        session,
                        window,
                        elapsed,
                    )
                    return TimeoutResult(
                        status=TimeoutStatus.CANCELLED,
                        detection_result=last_detection,
                        timed_out=False,
                        elapsed_seconds=elapsed,
                        timeout_seconds=effective_timeout,
                        cancelled=True,
                    )

                # 检查是否超时
                if elapsed >= effective_timeout:
                    logger.warning(
                        "TimeoutController: %s:%s timed out after %.1fs "
                        "(limit=%.1fs), stopping CLI",
                        session,
                        window,
                        elapsed,
                        effective_timeout,
                    )
                    self._timed_out[key] = True
                    stopped = self._stop_cli_on_timeout(session, window)

                    return TimeoutResult(
                        status=TimeoutStatus.TIMEOUT,
                        detection_result=last_detection,
                        timed_out=True,
                        elapsed_seconds=elapsed,
                        timeout_seconds=effective_timeout,
                        stopped_cli=stopped,
                    )

                # 检测任务状态
                detection = self._detector.detect(session, window)
                last_detection = detection

                if detection.is_terminal:
                    # 任务已到达终态
                    status = self._map_execution_to_timeout(detection.status)
                    logger.info(
                        "TimeoutController: %s:%s %s after %.1fs",
                        session,
                        window,
                        status.value,
                        elapsed,
                    )
                    return TimeoutResult(
                        status=status,
                        detection_result=detection,
                        timed_out=False,
                        elapsed_seconds=elapsed,
                        timeout_seconds=effective_timeout,
                    )

                # 未到终态，等待下次轮询
                time.sleep(self._poll_interval)

        finally:
            # 清理跟踪状态
            self._start_times.pop(key, None)
            self._timeouts.pop(key, None)
            self._cancelled.pop(key, None)
            # 注意：_timed_out 保留，供 is_timed_out 查询

    def cancel(self, session: str, window: str) -> bool:
        """取消正在进行的超时监控

        设置取消标志，execute_with_timeout() 在下次轮询时检测到后返回。

        Args:
            session: tmux 会话名称
            window: tmux 窗口名称

        Returns:
            True 如果成功设置取消标志，False 如果没有活跃监控
        """
        key = self._make_key(session, window)
        if key in self._cancelled:
            self._cancelled[key] = True
            logger.info(
                "TimeoutController: cancel requested for %s:%s",
                session,
                window,
            )
            return True
        return False

    def is_timed_out(self, session: str, window: str) -> bool:
        """检查任务是否已超时

        Args:
            session: tmux 会话名称
            window: tmux 窗口名称

        Returns:
            True 如果任务已超时
        """
        key = self._make_key(session, window)
        return self._timed_out.get(key, False)

    def get_remaining_time(self, session: str, window: str) -> Optional[float]:
        """获取任务超时剩余时间

        Args:
            session: tmux 会话名称
            window: tmux 窗口名称

        Returns:
            剩余秒数，None 如果没有活跃监控
        """
        key = self._make_key(session, window)
        start_time = self._start_times.get(key)
        timeout = self._timeouts.get(key)

        if start_time is None or timeout is None:
            return None

        elapsed = (datetime.now() - start_time).total_seconds()
        return max(0.0, timeout - elapsed)

    def get_elapsed_time(self, session: str, window: str) -> Optional[float]:
        """获取任务已执行时间

        Args:
            session: tmux 会话名称
            window: tmux 窗口名称

        Returns:
            已执行秒数，None 如果没有活跃监控
        """
        key = self._make_key(session, window)
        start_time = self._start_times.get(key)

        if start_time is None:
            return None

        return (datetime.now() - start_time).total_seconds()

    # ── 内部方法 ──────────────────────────────────────────

    def _stop_cli_on_timeout(self, session: str, window: str) -> bool:
        """超时后停止 CLI 进程

        Args:
            session: 会话名称
            window: 窗口名称

        Returns:
            True 如果成功停止 CLI
        """
        try:
            result = self._cli.stop_cli(
                session, window, timeout=self._stop_timeout
            )
            stopped = result == CLIStatus.STOPPED
            if stopped:
                logger.info(
                    "TimeoutController: CLI stopped after timeout in %s:%s",
                    session,
                    window,
                )
            else:
                logger.warning(
                    "TimeoutController: CLI stop returned %s after timeout "
                    "in %s:%s",
                    result.value,
                    session,
                    window,
                )
            return stopped
        except Exception as e:
            logger.error(
                "TimeoutController: failed to stop CLI after timeout "
                "in %s:%s: %s",
                session,
                window,
                e,
            )
            return False

    @staticmethod
    def _map_execution_to_timeout(
        execution_status: ExecutionStatus,
    ) -> TimeoutStatus:
        """将 ExecutionStatus 映射为 TimeoutStatus

        Args:
            execution_status: ResultDetector 检测到的执行状态

        Returns:
            对应的 TimeoutStatus
        """
        mapping = {
            ExecutionStatus.COMPLETED: TimeoutStatus.COMPLETED,
            ExecutionStatus.FAILED: TimeoutStatus.FAILED,
            ExecutionStatus.RUNNING: TimeoutStatus.UNKNOWN,
            ExecutionStatus.UNKNOWN: TimeoutStatus.UNKNOWN,
        }
        return mapping.get(execution_status, TimeoutStatus.UNKNOWN)

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

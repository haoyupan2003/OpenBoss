"""
ResultDetector — 执行结果检测器

基于 PRD V2.0 §7.3 Claude Code Integration 设计。
监控 tmux 窗口中 Claude Code CLI 的输出，判断任务完成/失败状态。

检测策略：
1. 完成（COMPLETED）：CLI 输出中出现任务完成标志（如返回就绪提示符、
   包含"完成"/"completed"等关键词）
2. 失败（FAILED）：CLI 输出中出现错误标志（如错误关键词、
   进程崩溃信号等）
3. 运行中（RUNNING）：未检测到完成或失败标志
4. 未知（UNKNOWN）：无法获取输出

设计原则：
    - 与 TmuxManager 解耦，通过依赖注入获取 TmuxManager 实例
    - 完成和失败模式可配置，支持自定义扩展
    - 支持增量检测（只分析新增输出）和全量检测两种模式
    - 检测结果包含匹配到的具体模式，便于诊断和日志
"""

import logging
import re
from enum import Enum
from typing import Optional

from agent_automation_system.tmux_manager.tmux_manager import TmuxManager

logger = logging.getLogger(__name__)


class ExecutionStatus(str, Enum):
    """执行状态枚举

    表示 CLI 输出分析后的任务执行判定结果。
    """

    COMPLETED = "completed"    # 任务已完成
    FAILED = "failed"          # 任务失败
    RUNNING = "running"        # 任务正在执行中
    UNKNOWN = "unknown"        # 无法判定（如无法获取输出）


class DetectionResult:
    """检测结果

    封装一次输出分析的所有信息，包括判定状态、匹配的模式、
    原始输出摘要等。

    Attributes:
        status: 判定的执行状态
        matched_pattern: 匹配到的模式（None 表示无匹配）
        matched_line: 匹配到的原始行内容
        output_lines: 分析的输出行数
        raw_output: 原始输出文本（可选，用于调试）
    """

    def __init__(
        self,
        status: ExecutionStatus,
        matched_pattern: Optional[str] = None,
        matched_line: Optional[str] = None,
        output_lines: int = 0,
        raw_output: Optional[str] = None,
    ) -> None:
        self.status = status
        self.matched_pattern = matched_pattern
        self.matched_line = matched_line
        self.output_lines = output_lines
        self.raw_output = raw_output

    @property
    def is_terminal(self) -> bool:
        """是否为终态（COMPLETED 或 FAILED）"""
        return self.status in (ExecutionStatus.COMPLETED, ExecutionStatus.FAILED)

    def __repr__(self) -> str:
        return (
            f"DetectionResult(status={self.status.value!r}, "
            f"matched_pattern={self.matched_pattern!r}, "
            f"output_lines={self.output_lines})"
        )


# ── 默认检测模式 ───────────────────────────────────────

# 完成模式：当 CLI 输出中出现这些内容时，判定任务已完成
# Claude Code 完成任务后通常回到就绪提示符
_DEFAULT_COMPLETION_PATTERNS: list[str] = [
    r"claude>\s*$",            # Claude Code 就绪提示符（行尾）
    r"claude\s*>\s*$",         # Claude Code 就绪提示符（带空格）
    r">\s*$",                  # 通用提示符
    r"[完成已结束].*[\.\。]?\s*$",  # 中文完成关键词
    r"(?i)task\s+completed",   # 英文完成关键词
    r"(?i)done\s*[\.\。]?\s*$", # 英文完成关键词
    r"(?i)finished\s*[\.\。]?\s*$",  # 英文完成关键词
]

# 失败模式：当 CLI 输出中出现这些内容时，判定任务失败
_DEFAULT_FAILURE_PATTERNS: list[str] = [
    r"(?i)error\s*[:：]",       # 错误关键词
    r"(?i)fatal\s*[:：]",       # 致命错误
    r"(?i)exception\s*[:：]",   # 异常关键词
    r"(?i)failed\s*[:：]",      # 失败关键词
    r"(?i)crash",              # 崩溃关键词
    r"(?i)segmentation\s+fault",  # 段错误
    r"(?i)permission\s+denied",   # 权限拒绝
    r"(?i)connection\s+refused",  # 连接拒绝
    r"(?i)timeout\s+expired",     # 超时过期
]

# 排除模式：即使匹配到失败模式，但如果同时匹配排除模式，则不判定为失败
# 例如 CLI 正在输出错误帮助信息但不是真正失败
_DEFAULT_EXCLUSION_PATTERNS: list[str] = [
    r"(?i)error\s*[:：]\s*message\s+format",  # 帮助文档中的 error 说明
    r"(?i)--help",                              # 帮助信息
]

# 默认回溯行数：检测时从输出末尾回溯多少行
_DEFAULT_HISTORY_LINES = 100


class ResultDetector:
    """执行结果检测器

    监控 tmux 窗口中 Claude Code CLI 的输出，判断任务完成/失败状态。

    检测流程：
    1. 通过 TmuxManager 捕获 tmux 窗口输出
    2. 对输出文本应用完成/失败模式匹配
    3. 返回 DetectionResult 包含判定结果和匹配细节

    Usage:
        tmux = TmuxManager()
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect("boss", "agent_dev_001")
        if result.is_terminal:
            print(f"Task {result.status.value}: {result.matched_pattern}")

    Args:
        tmux_manager: TmuxManager 实例（必须）
        completion_patterns: 自定义完成模式列表（正则表达式）
        failure_patterns: 自定义失败模式列表（正则表达式）
        exclusion_patterns: 自定义排除模式列表（正则表达式）
        history_lines: 回溯输出行数，默认 100
    """

    def __init__(
        self,
        tmux_manager: TmuxManager,
        completion_patterns: Optional[list[str]] = None,
        failure_patterns: Optional[list[str]] = None,
        exclusion_patterns: Optional[list[str]] = None,
        history_lines: int = _DEFAULT_HISTORY_LINES,
    ) -> None:
        if tmux_manager is None:
            raise ValueError("tmux_manager cannot be None")

        self._tmux = tmux_manager
        self._completion_patterns = (
            completion_patterns if completion_patterns is not None
            else _DEFAULT_COMPLETION_PATTERNS
        )
        self._failure_patterns = (
            failure_patterns if failure_patterns is not None
            else _DEFAULT_FAILURE_PATTERNS
        )
        self._exclusion_patterns = (
            exclusion_patterns if exclusion_patterns is not None
            else _DEFAULT_EXCLUSION_PATTERNS
        )
        self._history_lines = history_lines

        # 预编译正则表达式以提高检测性能
        self._compiled_completion = self._compile_patterns(self._completion_patterns)
        self._compiled_failure = self._compile_patterns(self._failure_patterns)
        self._compiled_exclusion = self._compile_patterns(self._exclusion_patterns)

    # ── 属性 ──────────────────────────────────────────────

    @property
    def tmux_manager(self) -> TmuxManager:
        """关联的 TmuxManager 实例"""
        return self._tmux

    @property
    def completion_patterns(self) -> list[str]:
        """完成模式列表（只读副本）"""
        return list(self._completion_patterns)

    @property
    def failure_patterns(self) -> list[str]:
        """失败模式列表（只读副本）"""
        return list(self._failure_patterns)

    @property
    def exclusion_patterns(self) -> list[str]:
        """排除模式列表（只读副本）"""
        return list(self._exclusion_patterns)

    @property
    def history_lines(self) -> int:
        """回溯输出行数"""
        return self._history_lines

    # ── 核心方法 ──────────────────────────────────────────

    def detect(
        self,
        session: str,
        window: str,
    ) -> DetectionResult:
        """检测指定窗口的 CLI 执行状态

        捕获 tmux 窗口输出并分析，判断任务是否完成或失败。

        检测优先级：失败 > 完成 > 运行中
        原因：失败通常是紧急信号，优先检测可以更早终止异常任务。

        Args:
            session: tmux 会话名称
            window: tmux 窗口名称

        Returns:
            DetectionResult: 检测结果
        """
        output = self._capture_output(session, window)

        if output is None:
            return DetectionResult(
                status=ExecutionStatus.UNKNOWN,
                output_lines=0,
            )

        output_text = "\n".join(output)
        output_lines = len(output)

        if not output_text.strip():
            return DetectionResult(
                status=ExecutionStatus.RUNNING,
                output_lines=output_lines,
                raw_output=output_text,
            )

        # 优先检测失败（紧急信号优先）
        failure_match = self._match_patterns(
            output, self._compiled_failure, self._compiled_exclusion
        )
        if failure_match:
            return DetectionResult(
                status=ExecutionStatus.FAILED,
                matched_pattern=failure_match.pattern,
                matched_line=failure_match.line,
                output_lines=output_lines,
                raw_output=output_text,
            )

        # 检测完成
        completion_match = self._match_patterns(
            output, self._compiled_completion
        )
        if completion_match:
            return DetectionResult(
                status=ExecutionStatus.COMPLETED,
                matched_pattern=completion_match.pattern,
                matched_line=completion_match.line,
                output_lines=output_lines,
                raw_output=output_text,
            )

        # 未匹配到任何终态模式，判定为运行中
        return DetectionResult(
            status=ExecutionStatus.RUNNING,
            output_lines=output_lines,
            raw_output=output_text,
        )

    def detect_from_output(self, output: list[str]) -> DetectionResult:
        """直接分析输出文本（不需要 tmux 会话）

        适用于已有输出文本需要分析的场景（如测试、回放日志）。

        Args:
            output: 输出行列表

        Returns:
            DetectionResult: 检测结果
        """
        if output is None:
            return DetectionResult(
                status=ExecutionStatus.UNKNOWN,
                output_lines=0,
            )

        output_text = "\n".join(output)
        output_lines = len(output)

        if not output_text.strip():
            return DetectionResult(
                status=ExecutionStatus.RUNNING,
                output_lines=output_lines,
            )

        # 优先检测失败
        failure_match = self._match_patterns(
            output, self._compiled_failure, self._compiled_exclusion
        )
        if failure_match:
            return DetectionResult(
                status=ExecutionStatus.FAILED,
                matched_pattern=failure_match.pattern,
                matched_line=failure_match.line,
                output_lines=output_lines,
                raw_output=output_text,
            )

        # 检测完成
        completion_match = self._match_patterns(
            output, self._compiled_completion
        )
        if completion_match:
            return DetectionResult(
                status=ExecutionStatus.COMPLETED,
                matched_pattern=completion_match.pattern,
                matched_line=completion_match.line,
                output_lines=output_lines,
                raw_output=output_text,
            )

        return DetectionResult(
            status=ExecutionStatus.RUNNING,
            output_lines=output_lines,
            raw_output=output_text,
        )

    def is_completed(self, session: str, window: str) -> bool:
        """快捷方法：检测任务是否已完成

        Args:
            session: tmux 会话名称
            window: tmux 窗口名称

        Returns:
            True 如果任务已完成
        """
        return self.detect(session, window).status == ExecutionStatus.COMPLETED

    def is_failed(self, session: str, window: str) -> bool:
        """快捷方法：检测任务是否失败

        Args:
            session: tmux 会话名称
            window: tmux 窗口名称

        Returns:
            True 如果任务失败
        """
        return self.detect(session, window).status == ExecutionStatus.FAILED

    def is_terminal(self, session: str, window: str) -> bool:
        """快捷方法：检测任务是否处于终态（完成或失败）

        Args:
            session: tmux 会话名称
            window: tmux 窗口名称

        Returns:
            True 如果任务处于终态
        """
        return self.detect(session, window).is_terminal

    def register_completion_pattern(self, pattern: str) -> None:
        """注册自定义完成模式

        Args:
            pattern: 正则表达式字符串

        Raises:
            ValueError: 模式为空或不是合法正则表达式
        """
        if not pattern or not pattern.strip():
            raise ValueError("pattern cannot be empty")
        try:
            re.compile(pattern)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {pattern!r}: {e}") from e

        self._completion_patterns.append(pattern)
        self._compiled_completion.append(re.compile(pattern, re.MULTILINE))
        logger.debug("Registered completion pattern: %s", pattern)

    def register_failure_pattern(self, pattern: str) -> None:
        """注册自定义失败模式

        Args:
            pattern: 正则表达式字符串

        Raises:
            ValueError: 模式为空或不是合法正则表达式
        """
        if not pattern or not pattern.strip():
            raise ValueError("pattern cannot be empty")
        try:
            re.compile(pattern)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern: {pattern!r}: {e}") from e

        self._failure_patterns.append(pattern)
        self._compiled_failure.append(re.compile(pattern, re.MULTILINE))
        logger.debug("Registered failure pattern: %s", pattern)

    # ── 内部方法 ──────────────────────────────────────────

    def _capture_output(
        self, session: str, window: str
    ) -> Optional[list[str]]:
        """捕获 tmux 窗口输出

        Args:
            session: 会话名称
            window: 窗口名称

        Returns:
            输出行列表，失败时返回 None
        """
        try:
            return self._tmux.capture_pane_history(
                session, window, lines=self._history_lines
            )
        except Exception as e:
            logger.debug(
                "Failed to capture output from %s:%s: %s",
                session,
                window,
                e,
            )
            return None

    @staticmethod
    def _compile_patterns(patterns: list[str]) -> list[re.Pattern]:
        """预编译正则表达式列表

        Args:
            patterns: 正则表达式字符串列表

        Returns:
            编译后的 Pattern 对象列表
        """
        compiled: list[re.Pattern] = []
        for pattern in patterns:
            try:
                compiled.append(re.compile(pattern, re.MULTILINE))
            except re.error as e:
                logger.warning(
                    "Skipping invalid regex pattern %r: %s", pattern, e
                )
        return compiled

    @staticmethod
    def _match_patterns(
        lines: list[str],
        patterns: list[re.Pattern],
        exclusions: Optional[list[re.Pattern]] = None,
    ) -> Optional["_PatternMatch"]:
        """对输出行逐行应用模式匹配

        从输出末尾向前搜索（最新的输出优先匹配），
        因为任务完成/失败的标志通常出现在输出的最后几行。

        Args:
            lines: 输出行列表
            patterns: 编译后的正则表达式列表
            exclusions: 排除模式列表（可选）

        Returns:
            PatternMatch 如果匹配到，None 否则
        """
        # 从末尾向前搜索，最新的输出优先
        for line in reversed(lines):
            stripped = line.strip()
            if not stripped:
                continue

            for pattern in patterns:
                match = pattern.search(stripped)
                if match:
                    # 检查排除模式
                    if exclusions:
                        excluded = any(
                            exc.search(stripped) for exc in exclusions
                        )
                        if excluded:
                            continue

                    return _PatternMatch(
                        pattern=pattern.pattern,
                        line=stripped,
                    )

        return None


class _PatternMatch:
    """模式匹配结果（内部使用）

    Attributes:
        pattern: 匹配到的模式字符串
        line: 匹配到的原始行内容
    """

    __slots__ = ("pattern", "line")

    def __init__(self, pattern: str, line: str) -> None:
        self.pattern = pattern
        self.line = line

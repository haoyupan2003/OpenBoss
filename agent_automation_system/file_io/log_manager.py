"""
LogManager - 日志管理器

基于 PRD V2.0 §6.6 日志文件规范。
提供结构化日志写入，自动按日期分割日志文件。

日志文件规范：
    logs/main_agent_YYYY-MM-DD.log      # Master Agent 运行日志
    logs/sub_agent_exec_YYYY-MM-DD.log  # Sub-Agent 执行日志
    logs/error_YYYY-MM-DD.log           # 错误日志（ERROR/CRITICAL）

日志格式：
    YYYY-MM-DD HH:MM:SS [LEVEL] [agent_id] Message
"""

import enum
from datetime import datetime
from pathlib import Path
from typing import Optional


class LogLevel(str, enum.Enum):
    """日志级别"""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    def __ge__(self, other: object) -> bool:
        if not isinstance(other, LogLevel):
            return NotImplemented
        order = [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARNING, LogLevel.ERROR, LogLevel.CRITICAL]
        return order.index(self) >= order.index(other)

    def __gt__(self, other: object) -> bool:
        if not isinstance(other, LogLevel):
            return NotImplemented
        order = [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARNING, LogLevel.ERROR, LogLevel.CRITICAL]
        return order.index(self) > order.index(other)

    def __le__(self, other: object) -> bool:
        if not isinstance(other, LogLevel):
            return NotImplemented
        order = [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARNING, LogLevel.ERROR, LogLevel.CRITICAL]
        return order.index(self) <= order.index(other)

    def __lt__(self, other: object) -> bool:
        if not isinstance(other, LogLevel):
            return NotImplemented
        order = [LogLevel.DEBUG, LogLevel.INFO, LogLevel.WARNING, LogLevel.ERROR, LogLevel.CRITICAL]
        return order.index(self) < order.index(other)


class LogCategory(str, enum.Enum):
    """日志类别，对应不同的日志文件"""

    MAIN_AGENT = "main_agent"
    SUB_AGENT = "sub_agent_exec"
    ERROR = "error"


class LogManager:
    """日志管理器

    提供结构化日志写入功能，自动按日期分割日志文件。

    根据 PRD §6.6，系统维护三类日志文件：
    - main_agent.log：Master Agent 调度决策、Sub-Agent 创建/销毁
    - sub_agent_exec.log：Sub-Agent 执行过程
    - error.log：ERROR 和 CRITICAL 级别的错误信息

    按日期分割：文件名格式为 {category}_YYYY-MM-DD.log

    Args:
        log_dir: 日志目录，默认 logs/
        min_level: 最低日志级别，低于此级别的日志不会写入
        auto_create_dir: 是否自动创建日志目录
    """

    # 日志行格式
    LOG_FORMAT = "{timestamp} [{level}] [{agent_id}] {message}\n"

    def __init__(
        self,
        log_dir: Optional[Path] = None,
        min_level: LogLevel = LogLevel.INFO,
        auto_create_dir: bool = True,
    ):
        self.log_dir = log_dir or Path("logs")
        self.min_level = min_level
        self.auto_create_dir = auto_create_dir

    def write_log(
        self,
        level: LogLevel,
        agent_id: str,
        message: str,
        category: Optional[LogCategory] = None,
    ) -> Optional[Path]:
        """写入一条日志

        根据日志级别自动路由到对应的日志文件：
        - ERROR/CRITICAL → 同时写入 error.log 和来源日志文件
        - Master Agent → main_agent.log
        - Sub-Agent → sub_agent_exec.log
        - 可通过 category 参数手动指定

        Args:
            level: 日志级别
            agent_id: Agent 标识（如 "master"、"dev-agent-001"）
            message: 日志消息
            category: 日志类别（可选，不指定则根据 agent_id 自动判断）

        Returns:
            写入的日志文件路径（主文件），如果级别低于阈值则返回 None
        """
        # 级别过滤
        if level < self.min_level:
            return None

        # 确定日志类别
        if category is None:
            category = self._infer_category(level, agent_id)

        # 确保目录存在
        if self.auto_create_dir:
            self.log_dir.mkdir(parents=True, exist_ok=True)

        # 格式化日志行
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_line = self.LOG_FORMAT.format(
            timestamp=timestamp,
            level=level.value,
            agent_id=agent_id,
            message=message,
        )

        # 写入主日志文件
        log_path = self._get_log_path(category)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(log_line)

        # ERROR/CRITICAL 同时写入 error.log
        if level >= LogLevel.ERROR and category != LogCategory.ERROR:
            error_path = self._get_log_path(LogCategory.ERROR)
            with open(error_path, "a", encoding="utf-8") as f:
                f.write(log_line)

        return log_path

    def debug(self, agent_id: str, message: str, **kwargs) -> Optional[Path]:
        """写入 DEBUG 级别日志"""
        return self.write_log(LogLevel.DEBUG, agent_id, message, **kwargs)

    def info(self, agent_id: str, message: str, **kwargs) -> Optional[Path]:
        """写入 INFO 级别日志"""
        return self.write_log(LogLevel.INFO, agent_id, message, **kwargs)

    def warning(self, agent_id: str, message: str, **kwargs) -> Optional[Path]:
        """写入 WARNING 级别日志"""
        return self.write_log(LogLevel.WARNING, agent_id, message, **kwargs)

    def error(self, agent_id: str, message: str, **kwargs) -> Optional[Path]:
        """写入 ERROR 级别日志"""
        return self.write_log(LogLevel.ERROR, agent_id, message, **kwargs)

    def critical(self, agent_id: str, message: str, **kwargs) -> Optional[Path]:
        """写入 CRITICAL 级别日志"""
        return self.write_log(LogLevel.CRITICAL, agent_id, message, **kwargs)

    def get_log_path(self, category: LogCategory) -> Path:
        """获取指定类别的当日日志文件路径

        Args:
            category: 日志类别

        Returns:
            日志文件路径
        """
        return self._get_log_path(category)

    def read_logs(
        self,
        category: LogCategory,
        date: Optional[str] = None,
    ) -> list[str]:
        """读取指定类别和日期的日志

        Args:
            category: 日志类别
            date: 日期字符串（YYYY-MM-DD），默认今天

        Returns:
            日志行列表
        """
        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        log_path = self.log_dir / f"{category.value}_{date}.log"
        if not log_path.exists():
            return []

        return log_path.read_text(encoding="utf-8").splitlines()

    # ─── 内部方法 ───────────────────────────────────

    def _get_log_path(self, category: LogCategory) -> Path:
        """获取日志文件路径（按日期分割）

        Args:
            category: 日志类别

        Returns:
            日志文件路径，格式 logs/{category}_YYYY-MM-DD.log
        """
        date_str = datetime.now().strftime("%Y-%m-%d")
        return self.log_dir / f"{category.value}_{date_str}.log"

    @staticmethod
    def _infer_category(level: LogLevel, agent_id: str) -> LogCategory:
        """根据日志级别和 agent_id 推断日志类别

        推断规则：
        - ERROR/CRITICAL 且 agent_id 不含 "agent" → error
        - agent_id 为 "master" 或以 "master-" 开头 → main_agent
        - 其他 → sub_agent_exec

        Args:
            level: 日志级别
            agent_id: Agent 标识

        Returns:
            推断的日志类别
        """
        if level >= LogLevel.ERROR and "agent" not in agent_id.lower():
            return LogCategory.ERROR

        if agent_id == "master" or agent_id.startswith("master-"):
            return LogCategory.MAIN_AGENT

        return LogCategory.SUB_AGENT

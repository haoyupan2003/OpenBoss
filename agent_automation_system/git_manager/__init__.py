"""git_manager - Git 版本管理模块

基于 gitpython 封装，提供 Git 仓库初始化、状态检测和版本管理能力。
还包含 TaskCommitter — 任务完成后的自动 commit + progress 编排。
"""

from .commit_message import CommitMessageFormatter
from .failure_handler import FailureHandleResult, FailureHandler
from .git_manager import GitManager
from .report_generator import ExecutionReport, ReportGenerator, TaskReportLine
from .task_committer import CommitResult, TaskCommitter

__all__ = [
    "CommitMessageFormatter",
    "CommitResult",
    "ExecutionReport",
    "FailureHandleResult",
    "FailureHandler",
    "GitManager",
    "ReportGenerator",
    "TaskCommitter",
    "TaskReportLine",
]

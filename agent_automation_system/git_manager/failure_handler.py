"""
FailureHandler — 任务失败处理流程（P2-030）

测试失败 → 记录错误 → 更新 task.json → 不 commit。
与 TaskCommitter（P2-028）互补，TaskCommitter 处理成功路径，FailureHandler 处理失败路径。

流程：
1. 记录错误到日志（通过 LogManager）
2. 更新 task.json 中对应 task 状态为 FAILED
3. 更新 progress.txt（通过 ProgressManager）
4. 确保不执行 git commit

使用方式：
    handler = FailureHandler(log_manager, task_file_manager, progress_manager)
    result = handler.handle_failure(task, error_message, role="dev")
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from agent_automation_system.file_io.log_manager import LogLevel, LogManager
from agent_automation_system.file_io.progress_manager import ProgressManager
from agent_automation_system.file_io.task_file_manager import TaskFileManager
from agent_automation_system.models.task import Task, TaskStatus
from agent_automation_system.models.progress import ProgressEntry, ProgressStatus

logger = logging.getLogger(__name__)


# ── 结果模型 ────────────────────────────────────────────


@dataclass
class FailureHandleResult:
    """失败处理结果

    Attributes:
        task_id: 任务 ID
        logged: 是否写入日志
        task_json_updated: 是否更新了 task.json
        progress_updated: 是否更新了 progress.txt
        error_message: 错误信息
        committed: 始终为 False（确保不 commit）
    """

    task_id: str
    logged: bool = False
    task_json_updated: bool = False
    progress_updated: bool = False
    error_message: str = ""
    committed: bool = False  # 永远 False — P2-030 核心约束

    @property
    def success(self) -> bool:
        """处理是否完整（三步全做完）"""
        return self.logged and self.task_json_updated and self.progress_updated


# ── FailureHandler ──────────────────────────────────────


class FailureHandler:
    """任务失败处理器

    职责：测试失败后，不 commit，但完整记录错误到日志和状态文件。

    Args:
        log_manager: LogManager 实例
        task_file_manager: TaskFileManager 实例
        progress_manager: ProgressManager 实例
    """

    def __init__(
        self,
        log_manager: LogManager,
        task_file_manager: TaskFileManager,
        progress_manager: ProgressManager,
    ) -> None:
        if log_manager is None:
            raise ValueError("log_manager cannot be None")
        if task_file_manager is None:
            raise ValueError("task_file_manager cannot be None")
        if progress_manager is None:
            raise ValueError("progress_manager cannot be None")

        self._log = log_manager
        self._tasks = task_file_manager
        self._progress = progress_manager

    @property
    def log_manager(self) -> LogManager:
        return self._log

    @property
    def task_file_manager(self) -> TaskFileManager:
        return self._tasks

    @property
    def progress_manager(self) -> ProgressManager:
        return self._progress

    # ── 核心方法 ──────────────────────────────────────

    def handle_failure(
        self,
        task: Task,
        error_message: str,
        role: str = "dev",
    ) -> FailureHandleResult:
        """处理任务失败：记录 → 更新 → 不 commit

        三步完整流程：
        1. 写日志（ERROR 级别）
        2. 更新 task.json 中任务状态为 FAILED
        3. 更新 progress.txt 为 FAILED

        确保任何一步失败不影响后续步骤（best-effort）。

        Args:
            task: 失败的任务
            error_message: 失败原因描述
            role: Agent 角色简称

        Returns:
            FailureHandleResult
        """
        if task is None:
            raise ValueError("task cannot be None")

        error_msg = error_message or "unknown error"
        result = FailureHandleResult(
            task_id=task.id,
            error_message=error_msg,
        )

        # 1. 写日志
        try:
            self._log.write_log(
                level=LogLevel.ERROR,
                agent_id=role,
                message=f"Task {task.id} failed: {error_msg}",
            )
            result.logged = True
        except Exception as e:
            logger.warning("Failed to write error log: %s", e)

        # 2. 更新 task.json
        try:
            self._tasks.update_task_status(
                task_id=task.id,
                status=TaskStatus.FAILED,
                error_message=error_msg,
            )
            result.task_json_updated = True
        except KeyError:
            logger.warning("Task %s not found in task.json", task.id)
            result.error_message = f"{error_msg} (task not found in task.json)"
        except Exception as e:
            logger.warning("Failed to update task.json: %s", e)

        # 3. 更新 progress.txt
        try:
            now = datetime.now()
            self._progress.write_entry(
                ProgressEntry(
                    task_id=task.id,
                    status=ProgressStatus.FAILED,
                    role=role,
                    started=task.started_at or now,
                    finished=now,
                    error=error_msg,
                )
            )
            result.progress_updated = True
        except Exception as e:
            logger.warning("Failed to update progress.txt: %s", e)

        logger.info(
            "FailureHandler: %s — logged=%s task_json=%s progress=%s",
            task.id, result.logged, result.task_json_updated, result.progress_updated,
        )
        return result

    def handle_failure_from_result(
        self,
        task: Task,
        agent_result,
        role: str = "dev",
    ) -> FailureHandleResult:
        """从 SubAgentResult 自动提取错误信息并处理

        便捷方法：直接从失败的 SubAgentResult 中提取 error 字段。

        Args:
            task: 失败的任务
            agent_result: SubAgentResult（status 应为 FAILED/TIMEOUT/BLOCKED）
            role: 角色简称

        Returns:
            FailureHandleResult
        """
        error_msg = ""
        try:
            error_msg = agent_result.error or ""
        except AttributeError:
            error_msg = str(agent_result)

        return self.handle_failure(task, error_msg, role)

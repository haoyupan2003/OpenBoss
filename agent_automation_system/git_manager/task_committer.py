"""
TaskCommitter — 任务完成自动提交流程（P2-028）

每个 Sub-Agent 完成任务后，自动执行：
1. git commit（通过 GitManager）
2. 更新 progress.txt（通过 ProgressManager）
3. 返回统一结果

与 PRD §4.7 一致：
- 提交格式：[task-{id}] {role}: {description}
- 成功 → commit + progress
- 失败 → 不 commit，但仍更新 progress 为 FAILED

使用方式：
    committer = TaskCommitter(git_manager, progress_manager)
    result = committer.commit_on_success(task, agent_result)
    # 或
    result = committer.commit_or_record_failure(task, agent_result)
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from agent_automation_system.git_manager.git_manager import GitManager
from agent_automation_system.file_io.progress_manager import ProgressManager
from agent_automation_system.models.task import Task, TaskStatus
from agent_automation_system.models.progress import ProgressEntry, ProgressStatus
from agent_automation_system.sub_agent.sub_agent import SubAgentResult, SubAgentResultStatus

logger = logging.getLogger(__name__)


# ── 结果模型 ────────────────────────────────────────────


@dataclass
class CommitResult:
    """自动提交结果

    Attributes:
        task_id: 任务 ID
        committed: 是否成功 commit
        commit_hash: Git commit hash（成功时）
        short_sha: 短 hash
        commit_message: 提交信息
        files_committed: 提交的文件列表
        progress_updated: 是否更新了 progress.txt
        error_message: 错误信息
        retries: 重试次数
    """

    task_id: str
    committed: bool = False
    commit_hash: Optional[str] = None
    short_sha: Optional[str] = None
    commit_message: str = ""
    files_committed: list[str] = field(default_factory=list)
    progress_updated: bool = False
    error_message: str = ""
    retries: int = 0

    @property
    def success(self) -> bool:
        return self.committed and self.progress_updated

    @property
    def summary(self) -> str:
        if self.committed:
            sha = self.short_sha or (self.commit_hash[:7] if self.commit_hash else "?")
            return (
                f"[{self.task_id}] committed {sha} "
                f"({len(self.files_committed)} files) — {self.commit_message}"
            )
        return f"[{self.task_id}] NOT committed — {self.error_message}"


# ── TaskCommitter ────────────────────────────────────────


class TaskCommitter:
    """任务提交编排器

    职责：在 Sub-Agent 完成（或失败）后，统一编排 Git 提交和 progress 更新。
    不负责执行任务本身，只负责"成功后落盘"。

    Args:
        git_manager: GitManager 实例（必需）
        progress_manager: ProgressManager 实例（必需）
        role_short: 默认角色简称（如 "dev"），可在方法调用时覆盖
    """

    def __init__(
        self,
        git_manager: GitManager,
        progress_manager: ProgressManager,
        role_short: str = "dev",
    ) -> None:
        if git_manager is None:
            raise ValueError("git_manager cannot be None")
        if progress_manager is None:
            raise ValueError("progress_manager cannot be None")
        self._git = git_manager
        self._progress = progress_manager
        self._role_short = role_short

    @property
    def git_manager(self) -> GitManager:
        return self._git

    @property
    def progress_manager(self) -> ProgressManager:
        return self._progress

    # ── 核心方法 ──────────────────────────────────────

    def commit_on_success(
        self,
        task: Task,
        agent_result: SubAgentResult,
        role: Optional[str] = None,
        description: Optional[str] = None,
    ) -> CommitResult:
        """成功后自动提交

        当 Sub-Agent 执行成功（SubAgentResultStatus.SUCCESS）时：
        1. 生成 commit message
        2. git commit 变更
        3. 更新 progress.txt 为 COMPLETED
        4. 返回 CommitResult

        Args:
            task: 完成的任务
            agent_result: SubAgent 的执行结果
            role: 角色简称（覆盖构造函数默认值）
            description: 自定义描述（默认使用 task.title）

        Returns:
            CommitResult

        Raises:
            ValueError: task / agent_result 为 None
        """
        if task is None:
            raise ValueError("task cannot be None")
        if agent_result is None:
            raise ValueError("agent_result cannot be None")

        role_name = role or self._role_short
        desc = description or task.title or task.description
        task_id_raw = task.id.replace("task-", "")

        # 1. Git commit
        commit_result = self._git.commit_changes(
            task_id=task_id_raw,
            role=role_name,
            description=desc,
        )

        result = CommitResult(task_id=task.id)

        if commit_result.get("success"):
            result.committed = True
            result.commit_hash = commit_result.get("hexsha")
            result.short_sha = commit_result.get("short_sha")
            result.commit_message = commit_result.get("message", "")
            result.files_committed = commit_result.get("files_committed", [])
            result.retries = commit_result.get("retries", 0)

            # 2. 更新 progress
            now = datetime.now()
            self._progress.write_entry(
                ProgressEntry(
                    task_id=task.id,
                    status=ProgressStatus.COMPLETED,
                    role=role_name,
                    started=agent_result.started_at or now,
                    finished=now,
                    git_sha=result.short_sha or result.commit_hash or "",
                    git_msg=result.commit_message,
                )
            )
            result.progress_updated = True
            logger.info(
                "TaskCommitter: %s committed %s — %s",
                task.id, result.short_sha, desc,
            )
        else:
            result.error_message = commit_result.get("error", "commit failed")
            result.retries = commit_result.get("retries", 0)
            logger.warning(
                "TaskCommitter: %s commit failed — %s",
                task.id, result.error_message,
            )

        return result

    def record_failure(
        self,
        task: Task,
        agent_result: SubAgentResult,
        role: Optional[str] = None,
    ) -> CommitResult:
        """失败时记录（不 commit）

        当 Sub-Agent 执行失败时，仅更新 progress.txt 为 FAILED。
        不执行 git commit。

        Args:
            task: 失败的任务
            agent_result: 执行结果（含错误信息）
            role: 角色简称

        Returns:
            CommitResult（committed=False, progress_updated=True）
        """
        if task is None:
            raise ValueError("task cannot be None")
        if agent_result is None:
            raise ValueError("agent_result cannot be None")

        role_name = role or self._role_short
        now = datetime.now()

        self._progress.write_entry(
            ProgressEntry(
                task_id=task.id,
                status=ProgressStatus.FAILED,
                role=role_name,
                started=agent_result.started_at or now,
                finished=now,
                error=agent_result.error or "task failed",
            )
        )

        result = CommitResult(
            task_id=task.id,
            progress_updated=True,
            error_message=agent_result.error or "task failed",
        )
        logger.info("TaskCommitter: %s recorded as FAILED", task.id)
        return result

    def commit_or_record(
        self,
        task: Task,
        agent_result: SubAgentResult,
        role: Optional[str] = None,
        description: Optional[str] = None,
    ) -> CommitResult:
        """智能提交：成功→commit+progress，失败→progress 不 commit

        这是推荐的入口方法。根据 agent_result.status 自动分流：
        - SUCCESS → commit_on_success()
        - 其他 → record_failure()

        Args:
            task: 任务
            agent_result: 执行结果
            role: 角色简称
            description: commit 描述

        Returns:
            CommitResult
        """
        if agent_result.status == SubAgentResultStatus.SUCCESS:
            return self.commit_on_success(
                task=task,
                agent_result=agent_result,
                role=role,
                description=description,
            )
        return self.record_failure(
            task=task,
            agent_result=agent_result,
            role=role,
        )

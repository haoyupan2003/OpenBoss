"""
ProgressEntry 数据模型

基于 PRD V2.0 §6.3 progress.txt 格式规范定义。
每条 ProgressEntry 记录一个任务的执行状态和结果。
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ProgressStatus(str, Enum):
    """进度状态枚举"""

    COMPLETED = "COMPLETED"
    IN_PROGRESS = "IN_PROGRESS"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    SKIPPED = "SKIPPED"
    RETRYING = "RETRYING"


class ProgressEntry(BaseModel):
    """任务进度条目数据模型

    对应 PRD §6.3 progress.txt 中的单个任务进度记录。
    由 Sub-Agent 在完成每个 task 后更新。

    Attributes:
        task_id: 任务唯一标识（对应 Task.id）
        status: 当前执行状态
        role: 执行该任务的 Agent 角色
        started: 开始执行时间
        finished: 执行完成时间
        git_sha: Git 提交的 commit hash
        git_msg: Git 提交信息（格式：[task-{id}] {role}: {description}）
        error: 失败时的错误信息
        retry: 已重试次数
    """

    task_id: str = Field(
        ...,
        description="任务唯一标识（对应 Task.id）",
    )
    status: ProgressStatus = Field(
        ...,
        description="当前执行状态",
    )
    role: str = Field(
        ...,
        description="执行该任务的 Agent 角色",
    )
    started: Optional[datetime] = Field(
        None,
        description="开始执行时间",
    )
    finished: Optional[datetime] = Field(
        None,
        description="执行完成时间",
    )
    git_sha: Optional[str] = Field(
        None,
        description="Git 提交的 commit hash",
    )
    git_msg: Optional[str] = Field(
        None,
        description="Git 提交信息（格式：[task-{id}] {role}: {description}）",
    )
    error: Optional[str] = Field(
        None,
        description="失败时的错误信息",
    )
    retry: int = Field(
        default=0,
        ge=0,
        description="已重试次数",
    )

    def is_terminal(self) -> bool:
        """判断是否为终态（不会再变化）"""
        return self.status in (
            ProgressStatus.COMPLETED,
            ProgressStatus.FAILED,
            ProgressStatus.SKIPPED,
        )

    def to_text_block(self) -> str:
        """转换为 progress.txt 格式的文本块

        Returns:
            符合 PRD §6.3 规范的结构化文本
        """
        lines = [f"[{self.task_id}]"]

        # 状态行（右对齐）
        lines.append(f"  Status:    {self.status.value}")
        lines.append(f"  Role:      {self.role}")

        if self.started:
            lines.append(f"  Started:   {self.started.strftime('%Y-%m-%d %H:%M:%S')}")
        if self.finished:
            lines.append(f"  Finished:  {self.finished.strftime('%Y-%m-%d %H:%M:%S')}")
        if self.git_sha:
            lines.append(f"  Git SHA:   {self.git_sha}")
        if self.git_msg:
            lines.append(f"  Git Msg:   {self.git_msg}")
        if self.error:
            lines.append(f"  Error:     {self.error}")
        if self.retry > 0:
            lines.append(f"  Retry:     {self.retry}")

        return "\n".join(lines)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "task_id": "task-001",
                    "status": "COMPLETED",
                    "role": "senior-developer",
                    "started": "2026-05-13T11:05:00Z",
                    "finished": "2026-05-13T11:32:15Z",
                    "git_sha": "a3f7b2c",
                    "git_msg": "[task-001] senior-developer: 实现用户登录页面 UI",
                    "error": None,
                    "retry": 0,
                }
            ]
        }
    }

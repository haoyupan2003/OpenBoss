"""
TaskFileManager - task.json 读写器

基于 PRD V2.0 §6.2 task.json 格式规范。
提供 task.json 文件的读取、写入、更新操作。
"""

import json
from pathlib import Path
from typing import Optional

from agent_automation_system.models.task import Task, TaskStatus
from agent_automation_system.models.task_json import TaskJSON


class TaskFileManager:
    """task.json 文件管理器

    负责 task.json 文件的读取、写入和状态更新。
    所有写操作自动创建备份。

    Args:
        file_path: task.json 文件路径，默认 data/task.json
        backup_dir: 备份目录，默认 data/backup
    """

    def __init__(
        self,
        file_path: Optional[Path] = None,
        backup_dir: Optional[Path] = None,
    ):
        self.file_path = file_path or Path("data/task.json")
        self.backup_dir = backup_dir or Path("data/backup")

    def read_tasks(self) -> TaskJSON:
        """读取 task.json 文件并解析为 TaskJSON 模型

        Returns:
            TaskJSON 对象

        Raises:
            FileNotFoundError: 文件不存在
            json.JSONDecodeError: JSON 格式错误
            pydantic.ValidationError: 数据校验失败
        """
        with open(self.file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return TaskJSON.model_validate(data)

    def write_tasks(self, task_json: TaskJSON) -> None:
        """将 TaskJSON 写入 task.json 文件

        写入前自动备份现有文件。

        Args:
            task_json: 要写入的 TaskJSON 对象
        """
        if self.file_path.exists():
            self._backup()

        # 确保父目录存在
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(self.file_path, "w", encoding="utf-8") as f:
            f.write(task_json.model_dump_json(indent=2, exclude_none=True))

    def update_task_status(
        self,
        task_id: str,
        status: TaskStatus,
        error_message: Optional[str] = None,
    ) -> Task:
        """更新指定任务的状态

        Args:
            task_id: 任务 ID
            status: 新状态
            error_message: 失败时的错误信息（可选）

        Returns:
            更新后的 Task 对象

        Raises:
            KeyError: 任务 ID 不存在
        """
        task_json = self.read_tasks()

        for task in task_json.tasks:
            if task.id == task_id:
                task.status = status
                if error_message is not None:
                    task.error_message = error_message
                self.write_tasks(task_json)
                return task

        raise KeyError(f"Task '{task_id}' not found in task.json")

    def get_task(self, task_id: str) -> Task:
        """获取指定任务

        Args:
            task_id: 任务 ID

        Returns:
            Task 对象

        Raises:
            KeyError: 任务 ID 不存在
        """
        task_json = self.read_tasks()
        for task in task_json.tasks:
            if task.id == task_id:
                return task
        raise KeyError(f"Task '{task_id}' not found in task.json")

    def get_pending_tasks(self) -> list[Task]:
        """获取所有待执行任务

        Returns:
            状态为 pending 的 Task 列表
        """
        task_json = self.read_tasks()
        return [t for t in task_json.tasks if t.status == TaskStatus.PENDING]

    def _backup(self) -> Path:
        """备份当前 task.json 文件

        Returns:
            备份文件路径
        """
        from datetime import datetime

        self.backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backup_dir / f"task.json.{timestamp}.bak"

        # 复制文件内容
        with open(self.file_path, "r", encoding="utf-8") as src:
            content = src.read()
        with open(backup_path, "w", encoding="utf-8") as dst:
            dst.write(content)

        return backup_path

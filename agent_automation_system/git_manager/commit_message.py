"""
CommitMessageFormatter — 统一 commit message 格式化工具（P2-029）

格式：[task-{id}] {role}: {description}
与 PRD §4.7 完全一致。

能力：
- format(task_id, role, description) → 格式化消息
- format_from_task(task) → 从 Task 对象自动提取
- parse(message) → 解析消息为结构化 dict
- 标题截断（>50 字符 → 47 + "..."）
- 空值校验

使用方式：
    fmt = CommitMessageFormatter()
    msg = fmt.format("001", "dev", "实现用户登录")
    # → "[task-001] dev: 实现用户登录"

    parsed = fmt.parse(msg)
    # → {"task_id": "001", "role": "dev", "description": "实现用户登录"}
"""

import re
from typing import Optional


class CommitMessageFormatter:
    """统一 commit message 格式化器

    确保全项目 commit message 格式一致：[task-{id}] {role}: {description}
    """

    # 格式常量
    FORMAT = "[task-{id}] {role}: {description}"
    # 解析正则（与 GitManager._COMMIT_MSG_PATTERN 一致）
    PARSE_PATTERN = re.compile(r"^\[task-([^\]]+)\]\s+([^:]+):\s+(.+)$")
    # 标题最大长度（按字符）
    MAX_DESC_LENGTH = 50
    # 截断后缀
    TRUNCATION_SUFFIX = "..."

    def format(
        self,
        task_id: str,
        role: str,
        description: str,
        truncate: bool = True,
    ) -> str:
        """格式化 commit message

        Args:
            task_id: 任务 ID（如 "001"，不含 "task-" 前缀）
            role: Agent 角色名（如 "dev"、"senior-developer"）
            description: 变更描述（如任务标题）
            truncate: 是否截断过长描述（默认 True）

        Returns:
            格式化的 commit message

        Raises:
            ValueError: task_id/role/description 为空
        """
        if not task_id or not task_id.strip():
            raise ValueError("task_id cannot be empty")
        if not role or not role.strip():
            raise ValueError("role cannot be empty")
        if not description or not description.strip():
            raise ValueError("description cannot be empty")

        desc = description.strip()
        if truncate and len(desc) > self.MAX_DESC_LENGTH:
            desc = desc[: self.MAX_DESC_LENGTH - len(self.TRUNCATION_SUFFIX)] + self.TRUNCATION_SUFFIX

        return self.FORMAT.format(
            id=task_id.strip(),
            role=role.strip(),
            description=desc,
        )

    def format_from_task(
        self,
        task,
        role: str = "dev",
    ) -> str:
        """从 Task 对象自动生成 commit message

        自动提取 task.id → task_id（去除 "task-" 前缀）
        使用 task.title 作为 description。

        Args:
            task: Task 模型实例（需有 id 和 title 属性）
            role: 角色名（默认 "dev"）

        Returns:
            格式化的 commit message

        Raises:
            ValueError: task 为 None
        """
        if task is None:
            raise ValueError("task cannot be None")

        task_id = task.id.replace("task-", "")
        description = task.title or task.description or ""
        return self.format(task_id, role, description)

    def parse(self, message: str) -> Optional[dict]:
        """解析 commit message 为结构化数据

        反向操作 format：将 "[task-001] dev: 实现登录" 解析为
        {"task_id": "001", "role": "dev", "description": "实现登录"}

        Args:
            message: commit message 字符串

        Returns:
            解析结果 dict，格式不匹配返回 None
        """
        if not message:
            return None
        m = self.PARSE_PATTERN.match(message.strip())
        if not m:
            return None
        return {
            "task_id": m.group(1),
            "role": m.group(2),
            "description": m.group(3),
        }

    def is_valid_format(self, message: str) -> bool:
        """检查消息是否符合 [task-{id}] {role}: {description} 格式"""
        return self.parse(message) is not None

    def extract_task_id(self, message: str) -> Optional[str]:
        """从 commit message 中提取 task_id"""
        parsed = self.parse(message)
        return parsed["task_id"] if parsed else None

    def extract_role(self, message: str) -> Optional[str]:
        """从 commit message 中提取角色名"""
        parsed = self.parse(message)
        return parsed["role"] if parsed else None

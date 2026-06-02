"""
ProgressManager - progress.txt 读写器

基于 PRD V2.0 §6.3 progress.txt 格式规范。
提供 progress.txt 文件的读取、写入、更新操作。

文件格式示例：
    # ============================================
    # Project: 电商平台重构项目
    # Updated: 2026-05-13 15:42:18
    # Progress: 12 / 48 tasks completed
    # ============================================

    [task-001] 用户登录页面 UI 实现
      Status:    COMPLETED
      Role:      senior-developer
      Started:   2026-05-13 11:05:00
      Finished:  2026-05-13 11:32:15
      Git SHA:   a3f7b2c
      Git Msg:   [task-001] senior-developer: 实现用户登录页面布局和样式
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from agent_automation_system.models.progress import ProgressEntry, ProgressStatus


class ProgressManager:
    """progress.txt 文件管理器

    负责 progress.txt 文件的读取、写入和进度条目更新。

    Args:
        file_path: progress.txt 文件路径，默认 data/progress.txt
    """

    # 文件头模板
    HEADER_TEMPLATE = (
        "# ============================================\n"
        "# Project: {project_name}\n"
        "# Updated: {updated_at}\n"
        "# Progress: {completed} / {total} tasks completed\n"
        "# ============================================\n"
    )

    def __init__(self, file_path: Optional[Path] = None):
        self.file_path = file_path or Path("data/progress.txt")

    def read_progress(self) -> list[ProgressEntry]:
        """读取 progress.txt 并解析为 ProgressEntry 列表

        Returns:
            ProgressEntry 列表，按文件中的顺序排列

        Raises:
            FileNotFoundError: 文件不存在
        """
        if not self.file_path.exists():
            return []

        content = self.file_path.read_text(encoding="utf-8")
        return self._parse_entries(content)

    def write_entry(self, entry: ProgressEntry) -> None:
        """写入一条进度条目

        如果同 task_id 的条目已存在，则替换；否则追加。
        同时更新文件头部的进度统计。

        Args:
            entry: 要写入的 ProgressEntry 对象
            total_tasks: 任务总数（用于更新头部统计）
        """
        entries = self.read_progress()

        # 替换已有条目或追加新条目
        replaced = False
        for i, existing in enumerate(entries):
            if existing.task_id == entry.task_id:
                entries[i] = entry
                replaced = True
                break
        if not replaced:
            entries.append(entry)

        self._write_file(entries)

    def update_status(
        self,
        task_id: str,
        status: ProgressStatus,
        title: Optional[str] = None,
        role: Optional[str] = None,
        started: Optional[datetime] = None,
        finished: Optional[datetime] = None,
        git_sha: Optional[str] = None,
        git_msg: Optional[str] = None,
        error: Optional[str] = None,
        retry: Optional[int] = None,
        total_tasks: Optional[int] = None,
    ) -> ProgressEntry:
        """更新指定任务的进度状态

        如果条目已存在，则更新指定字段；否则创建新条目。

        Args:
            task_id: 任务 ID
            status: 新状态
            title: 任务标题（仅新条目时使用）
            role: 执行角色
            started: 开始时间
            finished: 完成时间
            git_sha: Git commit hash
            git_msg: Git commit message
            error: 错误信息
            retry: 重试次数
            total_tasks: 任务总数（用于更新头部统计）

        Returns:
            更新后的 ProgressEntry
        """
        entries = self.read_progress()

        # 查找已有条目
        target: Optional[ProgressEntry] = None
        for existing in entries:
            if existing.task_id == task_id:
                target = existing
                break

        if target is not None:
            # 更新已有条目
            update_data: dict = {"status": status}
            if role is not None:
                update_data["role"] = role
            if started is not None:
                update_data["started"] = started
            if finished is not None:
                update_data["finished"] = finished
            if git_sha is not None:
                update_data["git_sha"] = git_sha
            if git_msg is not None:
                update_data["git_msg"] = git_msg
            if error is not None:
                update_data["error"] = error
            if retry is not None:
                update_data["retry"] = retry

            updated = target.model_copy(update=update_data)

            # 替换列表中的旧条目
            for i, e in enumerate(entries):
                if e.task_id == task_id:
                    entries[i] = updated
                    break
        else:
            # 创建新条目
            updated = ProgressEntry(
                task_id=task_id,
                status=status,
                role=role or "unknown",
                started=started,
                finished=finished,
                git_sha=git_sha,
                git_msg=git_msg,
                error=error,
                retry=retry or 0,
            )
            entries.append(updated)

        self._write_file(entries)
        return updated

    def get_entry(self, task_id: str) -> Optional[ProgressEntry]:
        """获取指定任务的进度条目

        Args:
            task_id: 任务 ID

        Returns:
            ProgressEntry 或 None
        """
        entries = self.read_progress()
        for entry in entries:
            if entry.task_id == task_id:
                return entry
        return None

    def get_completed_count(self) -> int:
        """获取已完成任务数量

        Returns:
            状态为 COMPLETED 的条目数
        """
        entries = self.read_progress()
        return sum(1 for e in entries if e.status == ProgressStatus.COMPLETED)

    # ─── 内部方法 ───────────────────────────────────

    def _write_file(
        self,
        entries: list[ProgressEntry],
        project_name: str = "OpenBoss Project",
        total_tasks: Optional[int] = None,
    ) -> None:
        """将条目列表写入 progress.txt 文件

        Args:
            entries: 进度条目列表
            project_name: 项目名称（用于文件头）
            total_tasks: 任务总数（用于文件头统计）
        """
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        completed = sum(1 for e in entries if e.status == ProgressStatus.COMPLETED)
        total = total_tasks if total_tasks is not None else len(entries)
        updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines = []

        # 文件头
        lines.append(
            self.HEADER_TEMPLATE.format(
                project_name=project_name,
                updated_at=updated_at,
                completed=completed,
                total=total,
            )
        )

        # 条目
        for entry in entries:
            lines.append(entry.to_text_block())
            lines.append("")  # 空行分隔

        self.file_path.write_text("\n".join(lines), encoding="utf-8")

    @staticmethod
    def _parse_entries(content: str) -> list[ProgressEntry]:
        """解析 progress.txt 内容为 ProgressEntry 列表

        逐行扫描，以行首 [task-xxx] 作为新条目起始。

        Args:
            content: 文件文本内容

        Returns:
            ProgressEntry 列表
        """
        entries: list[dict] = []
        current: Optional[dict] = None

        for line in content.splitlines():
            # 检测新条目起始：行首 [task-xxx]
            header_match = re.match(r"^\[(task-\d+)\]", line)
            if header_match:
                # 保存上一个条目
                if current is not None:
                    entries.append(current)
                current = {"task_id": header_match.group(1)}
                continue

            # 跳过空行和注释
            if current is None or not line.strip() or line.strip().startswith("#"):
                continue

            # 解析字段：  Key:   Value
            field_match = re.match(r"^\s+(\w[\w\s]*?):\s+(.+)$", line)
            if field_match:
                key = field_match.group(1).strip()
                value = field_match.group(2).strip()

                if key == "Status":
                    try:
                        current["status"] = ProgressStatus(value)
                    except ValueError:
                        current["status"] = ProgressStatus.IN_PROGRESS
                elif key == "Role":
                    current["role"] = value
                elif key == "Started":
                    current["started"] = _parse_datetime(value)
                elif key == "Finished":
                    current["finished"] = _parse_datetime(value)
                elif key == "Git SHA":
                    current["git_sha"] = value
                elif key == "Git Msg":
                    current["git_msg"] = value
                elif key == "Error":
                    current["error"] = value
                elif key == "Retry":
                    try:
                        current["retry"] = int(value)
                    except ValueError:
                        pass

        # 保存最后一个条目
        if current is not None:
            entries.append(current)

        # 构建 ProgressEntry 对象
        result: list[ProgressEntry] = []
        for fields in entries:
            # 必填字段回退
            if "status" not in fields:
                fields["status"] = ProgressStatus.IN_PROGRESS
            if "role" not in fields:
                fields["role"] = "unknown"
            try:
                result.append(ProgressEntry(**fields))
            except Exception:
                pass

        return result


def _parse_datetime(s: str) -> Optional[datetime]:
    """尝试解析日期时间字符串

    支持格式：
    - 2026-05-13 11:05:00
    - 2026-05-13T11:05:00Z
    - 2026-05-13T11:05:00+08:00
    """
    formats = [
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None

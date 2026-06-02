"""
ExecutionReport — 执行报告生成器（P2-031）

从 task.json + progress.txt 生成完整的执行报告。
包含每个 task 的状态、commit hash、执行时间、成功/失败统计。

与 PRD §4.7 一致：
- 每个 task 的状态和 git commit 信息
- 全局统计摘要（完成率、耗时等）
- 人类可读和结构化输出双格式

使用方式：
    gen = ReportGenerator(task_file_manager, progress_manager)
    report = gen.generate()
    print(report.to_text())
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from agent_automation_system.file_io.progress_manager import ProgressManager
from agent_automation_system.file_io.task_file_manager import TaskFileManager
from agent_automation_system.models.task import TaskStatus
from agent_automation_system.models.progress import ProgressStatus


# ── 数据模型 ────────────────────────────────────────────


@dataclass
class TaskReportLine:
    """单个任务的报告行"""

    task_id: str
    title: str
    status: str  # COMPLETED / FAILED / PENDING / IN_PROGRESS / BLOCKED
    role: str = ""
    started: Optional[datetime] = None
    finished: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    commit_hash: Optional[str] = None
    commit_message: str = ""
    error: str = ""

    @property
    def completed(self) -> bool:
        return self.status == "COMPLETED"

    @property
    def failed(self) -> bool:
        return self.status == "FAILED"


@dataclass
class ExecutionReport:
    """完整执行报告"""

    project_name: str = ""
    generated_at: datetime = field(default_factory=datetime.now)
    total_tasks: int = 0
    completed_count: int = 0
    failed_count: int = 0
    pending_count: int = 0
    in_progress_count: int = 0
    blocked_count: int = 0
    total_duration_seconds: float = 0.0
    tasks: list[TaskReportLine] = field(default_factory=list)

    @property
    def completion_rate(self) -> float:
        if self.total_tasks == 0:
            return 0.0
        return round(self.completed_count / self.total_tasks, 4)

    @property
    def is_all_done(self) -> bool:
        return self.pending_count == 0 and self.in_progress_count == 0

    @property
    def summary(self) -> str:
        pct = f"{self.completion_rate:.0%}"
        return (
            f"{self.completed_count}/{self.total_tasks} completed ({pct}) — "
            f"{self.failed_count} failed, {self.pending_count} pending, "
            f"{self.blocked_count} blocked"
        )

    def to_text(self) -> str:
        """生成人类可读的多行文本报告"""
        lines = [
            "=" * 60,
            f"  执行报告 — {self.project_name}",
            f"  生成时间：{self.generated_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"  进度：{self.summary}",
            "=" * 60,
            "",
        ]

        # 成功任务
        completed = [t for t in self.tasks if t.completed]
        if completed:
            lines.append("── 已完成任务 ──")
            for t in completed:
                sha = t.commit_hash[:7] if t.commit_hash else "?"
                dur = f"{t.duration_seconds:.1f}s" if t.duration_seconds else "?"
                lines.append(
                    f"  ✅ [{t.task_id}] {t.title[:40]} "
                    f"({t.role}, {sha}, {dur})"
                )
            lines.append("")

        # 失败任务
        failed = [t for t in self.tasks if t.failed]
        if failed:
            lines.append("── 失败任务 ──")
            for t in failed:
                err = t.error[:60] if t.error else "?"
                lines.append(f"  ❌ [{t.task_id}] {t.title[:40]} — {err}")
            lines.append("")

        # 待处理
        pending = [t for t in self.tasks if t.status == "PENDING"]
        if pending:
            lines.append(
                f"── 待处理（{len(pending)} 个）──"
            )
            for t in pending[:10]:  # 最多显示 10 个
                lines.append(f"  ⏳ [{t.task_id}] {t.title[:40]}")
            if len(pending) > 10:
                lines.append(f"  ... 还有 {len(pending) - 10} 个")
            lines.append("")

        # 统计
        lines.extend([
            "── 统计 ──",
            f"  总任务数：{self.total_tasks}",
            f"  已完成：{self.completed_count} ({self.completion_rate:.0%})",
            f"  失败：{self.failed_count}",
            f"  待处理：{self.pending_count}",
            f"  阻塞：{self.blocked_count}",
            f"  总耗时：{self.total_duration_seconds:.1f}s",
        ])

        return "\n".join(lines)


# ── ReportGenerator ──────────────────────────────────────


class ReportGenerator:
    """执行报告生成器

    从 TaskFileManager 和 ProgressManager 读取数据，
    合并生成完整的 ExecutionReport。

    Args:
        task_file_manager: TaskFileManager 实例
        progress_manager: ProgressManager 实例
    """

    def __init__(
        self,
        task_file_manager: TaskFileManager,
        progress_manager: ProgressManager,
    ) -> None:
        if task_file_manager is None:
            raise ValueError("task_file_manager cannot be None")
        if progress_manager is None:
            raise ValueError("progress_manager cannot be None")

        self._tasks = task_file_manager
        self._progress = progress_manager

    @property
    def task_file_manager(self) -> TaskFileManager:
        return self._tasks

    @property
    def progress_manager(self) -> ProgressManager:
        return self._progress

    def generate(self) -> ExecutionReport:
        """生成完整的执行报告

        1. 从 task.json 读取所有任务
        2. 从 progress.txt 读取所有进度条目
        3. 合并生成每个 TaskReportLine
        4. 汇总统计

        Returns:
            ExecutionReport

        Raises:
            RuntimeError: task.json 不可读
        """
        task_json = self._tasks.read_tasks()
        progress_entries = self._progress.read_progress()

        # 建立 progress 索引：task_id → ProgressEntry
        progress_map: dict[str, any] = {}
        for entry in progress_entries:
            progress_map[entry.task_id] = entry

        # 生成每行报告
        report_lines: list[TaskReportLine] = []
        for task in task_json.tasks:
            progress_entry = progress_map.get(task.id)

            if progress_entry:
                status_str = progress_entry.status.value
                role = progress_entry.role
                started = progress_entry.started
                finished = progress_entry.finished
                duration = None
                if started and finished:
                    duration = (finished - started).total_seconds()
                commit_hash = progress_entry.git_sha or None
                commit_msg = progress_entry.git_msg or ""
                error = progress_entry.error or ""
            else:
                # 无 progress 条目 → 映射 task.json 状态
                ts = task.status
                if ts == TaskStatus.COMPLETED:
                    status_str = "COMPLETED"
                elif ts == TaskStatus.FAILED:
                    status_str = "FAILED"
                elif ts == TaskStatus.IN_PROGRESS:
                    status_str = "IN_PROGRESS"
                elif ts == TaskStatus.BLOCKED:
                    status_str = "BLOCKED"
                else:
                    status_str = "PENDING"
                role = ""
                started = task.started_at
                finished = task.finished_at
                duration = None
                if started and finished:
                    duration = (finished - started).total_seconds()
                commit_hash = None
                commit_msg = ""
                error = task.error_message or ""

            report_lines.append(TaskReportLine(
                task_id=task.id,
                title=task.title,
                status=status_str,
                role=role,
                started=started,
                finished=finished,
                duration_seconds=duration,
                commit_hash=commit_hash,
                commit_message=commit_msg,
                error=error,
            ))

        # 统计汇总
        completed = sum(1 for t in report_lines if t.completed)
        failed = sum(1 for t in report_lines if t.failed)
        pending = sum(1 for t in report_lines if t.status == "PENDING")
        in_progress = sum(1 for t in report_lines if t.status == "IN_PROGRESS")
        blocked = sum(1 for t in report_lines if t.status == "BLOCKED")
        total_duration = sum(
            t.duration_seconds for t in report_lines if t.duration_seconds
        )

        return ExecutionReport(
            project_name=task_json.project_name,
            total_tasks=len(report_lines),
            completed_count=completed,
            failed_count=failed,
            pending_count=pending,
            in_progress_count=in_progress,
            blocked_count=blocked,
            total_duration_seconds=total_duration,
            tasks=report_lines,
        )

"""
P2-031 测试：ReportGenerator 执行报告生成

验证从 task.json + progress.txt 生成完整执行报告。
覆盖：
1. ExecutionReport / TaskReportLine 模型
2. generate 完整报告生成（含统计）
3. to_text 人类可读输出
4. completion_rate / is_all_done / summary
5. 空项目 / 全完成 / 混合状态场景
6. progress 与 task 数据合并
7. 参数校验
"""

from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest

from agent_automation_system.git_manager.report_generator import (
    ExecutionReport,
    ReportGenerator,
    TaskReportLine,
)
from agent_automation_system.models.task import (
    Task,
    TaskComplexity,
    TaskPriority,
    TaskStatus,
)
from agent_automation_system.models.task_json import TaskJSON
from agent_automation_system.models.progress import ProgressEntry, ProgressStatus


def _make_task(task_id: str, title: str, status=TaskStatus.PENDING):
    return Task(
        id=task_id, title=title, description=title,
        dependencies=[], suggested_role="dev",
        priority=TaskPriority.MEDIUM,
        estimated_complexity=TaskComplexity.MEDIUM,
        status=status,
    )


def _make_progress(task_id: str, status: ProgressStatus, role="dev",
                   git_sha="", error="", started=None, finished=None):
    now = datetime(2026, 5, 26, 10, 0, 0)
    return ProgressEntry(
        task_id=task_id, status=status, role=role,
        git_sha=git_sha, git_msg=f"[{task_id}] {role}: {task_id}",
        error=error,
        started=started or now,
        finished=finished or (now + timedelta(seconds=30)),
    )


# ── fixtures ──────────────────────────────────────────────


@pytest.fixture
def empty_task_json():
    return TaskJSON(
        project_name="空项目", created_by="test", total_tasks=0, tasks=[]
    )


@pytest.fixture
def simple_task_json():
    return TaskJSON(
        project_name="测试项目", created_by="test", total_tasks=3,
        tasks=[
            _make_task("task-001", "任务A", TaskStatus.COMPLETED),
            _make_task("task-002", "任务B", TaskStatus.FAILED),
            _make_task("task-003", "任务C", TaskStatus.PENDING),
        ],
    )


@pytest.fixture
def full_task_json():
    """各种状态混合"""
    return TaskJSON(
        project_name="完整项目", created_by="test", total_tasks=5,
        tasks=[
            _make_task("task-001", "已完成1", TaskStatus.COMPLETED),
            _make_task("task-002", "已完成2", TaskStatus.COMPLETED),
            _make_task("task-003", "失败1", TaskStatus.FAILED),
            _make_task("task-004", "进行中", TaskStatus.IN_PROGRESS),
            _make_task("task-005", "待处理", TaskStatus.PENDING),
        ],
    )


@pytest.fixture
def mock_tfm(empty_task_json):
    tfm = MagicMock()
    tfm.read_tasks.return_value = empty_task_json
    return tfm


@pytest.fixture
def mock_pm():
    pm = MagicMock()
    pm.read_progress.return_value = []
    return pm


# ── TaskReportLine 模型 ───────────────────────────────────


class TestTaskReportLine:
    def test_completed(self):
        line = TaskReportLine(task_id="t1", title="T", status="COMPLETED")
        assert line.completed is True
        assert line.failed is False

    def test_failed(self):
        line = TaskReportLine(task_id="t1", title="T", status="FAILED")
        assert line.completed is False
        assert line.failed is True

    def test_duration(self):
        line = TaskReportLine(
            task_id="t1", title="T", status="COMPLETED",
            started=datetime(2026, 5, 26, 10, 0, 0),
            finished=datetime(2026, 5, 26, 10, 5, 0),
            duration_seconds=300.0,
        )
        assert line.duration_seconds == 300.0

    def test_commit_info(self):
        line = TaskReportLine(
            task_id="t1", title="T", status="COMPLETED",
            commit_hash="abc1234567890def",
            commit_message="[task-001] dev: T",
        )
        assert line.commit_hash == "abc1234567890def"
        assert "[task-001]" in line.commit_message


# ── ExecutionReport 模型 ──────────────────────────────────


class TestExecutionReport:
    def test_empty(self):
        r = ExecutionReport(project_name="P")
        assert r.total_tasks == 0
        assert r.completion_rate == 0.0
        assert r.is_all_done is True

    def test_completion_rate(self):
        r = ExecutionReport(
            total_tasks=10, completed_count=7, failed_count=2, pending_count=1,
        )
        assert r.completion_rate == 0.7

    def test_is_all_done_false(self):
        r = ExecutionReport(total_tasks=5, pending_count=1)
        assert r.is_all_done is False

    def test_summary_format(self):
        r = ExecutionReport(
            project_name="P",
            total_tasks=10, completed_count=8, failed_count=1,
            pending_count=1, blocked_count=0,
        )
        s = r.summary
        assert "8/10" in s
        assert "80%" in s
        assert "1 failed" in s

    def test_to_text_includes_sections(self):
        r = ExecutionReport(
            project_name="P", total_tasks=3, completed_count=1,
            failed_count=1, pending_count=1,
            tasks=[
                TaskReportLine(task_id="task-001", title="完成", status="COMPLETED",
                               role="dev", commit_hash="abc1234", duration_seconds=30.0),
                TaskReportLine(task_id="task-002", title="失败", status="FAILED",
                               error="assert False"),
                TaskReportLine(task_id="task-003", title="待办", status="PENDING"),
            ],
        )
        text = r.to_text()
        assert "执行报告" in text
        assert "已完成" in text
        assert "失败" in text
        assert "待处理" in text
        assert "统计" in text
        assert "task-001" in text
        assert "abc1234" in text
        assert "assert False" in text

    def test_to_text_pending_limit(self):
        """待处理超过 10 个时截断显示"""
        tasks = [
            TaskReportLine(task_id=f"task-{i:03d}", title=f"T{i}", status="PENDING")
            for i in range(15)
        ]
        r = ExecutionReport(
            project_name="P", total_tasks=15, pending_count=15, tasks=tasks,
        )
        text = r.to_text()
        assert "还有 5 个" in text


# ── ReportGenerator.generate ──────────────────────────────


class TestReportGenerator:
    """完整报告生成"""

    def test_empty_project(self, mock_tfm, mock_pm):
        gen = ReportGenerator(mock_tfm, mock_pm)
        report = gen.generate()
        assert report.total_tasks == 0
        assert report.completion_rate == 0.0
        assert report.project_name == "空项目"

    def test_generates_from_task_json_only(self, simple_task_json):
        """仅有 task.json，无 progress 条目"""
        tfm = MagicMock()
        tfm.read_tasks.return_value = simple_task_json
        pm = MagicMock()
        pm.read_progress.return_value = []

        gen = ReportGenerator(tfm, pm)
        report = gen.generate()

        assert report.total_tasks == 3
        assert report.completed_count == 1
        assert report.failed_count == 1
        assert report.pending_count == 1

    def test_merges_progress_with_tasks(self, simple_task_json):
        """progress 覆盖 task.json 状态"""
        tfm = MagicMock()
        tfm.read_tasks.return_value = simple_task_json
        pm = MagicMock()
        pm.read_progress.return_value = [
            _make_progress("task-001", ProgressStatus.COMPLETED,
                           git_sha="abc1234", role="dev"),
            _make_progress("task-002", ProgressStatus.FAILED,
                           error="test fail", role="qa"),
        ]

        gen = ReportGenerator(tfm, pm)
        report = gen.generate()

        # task-001: progress 信息
        t1 = next(t for t in report.tasks if t.task_id == "task-001")
        assert t1.status == "COMPLETED"
        assert t1.commit_hash == "abc1234"
        assert t1.duration_seconds is not None

        # task-002: progress 失败信息
        t2 = next(t for t in report.tasks if t.task_id == "task-002")
        assert t2.status == "FAILED"
        assert t2.error == "test fail"
        assert t2.role == "qa"

        # task-003: 无 progress → 从 task.json
        t3 = next(t for t in report.tasks if t.task_id == "task-003")
        assert t3.status == "PENDING"

    def test_all_states_counted(self, full_task_json):
        """5 种状态正确统计"""
        tfm = MagicMock()
        tfm.read_tasks.return_value = full_task_json
        pm = MagicMock()
        pm.read_progress.return_value = []

        gen = ReportGenerator(tfm, pm)
        report = gen.generate()

        assert report.completed_count == 2
        assert report.failed_count == 1
        assert report.in_progress_count == 1
        assert report.pending_count == 1

    def test_duration_from_progress(self):
        """时长从 progress started/finished 计算"""
        tfm = MagicMock()
        tfm.read_tasks.return_value = TaskJSON(
            project_name="P", created_by="t", total_tasks=1,
            tasks=[_make_task("task-001", "T")],
        )
        start = datetime(2026, 5, 26, 10, 0, 0)
        end = datetime(2026, 5, 26, 10, 5, 30)
        pm = MagicMock()
        pm.read_progress.return_value = [
            _make_progress("task-001", ProgressStatus.COMPLETED,
                           started=start, finished=end),
        ]

        gen = ReportGenerator(tfm, pm)
        report = gen.generate()
        t = report.tasks[0]
        assert t.duration_seconds == pytest.approx(330.0, abs=1)

    def test_total_duration(self, simple_task_json):
        """总时长累加"""
        tfm = MagicMock()
        tfm.read_tasks.return_value = simple_task_json
        pm = MagicMock()
        pm.read_progress.return_value = [
            _make_progress("task-001", ProgressStatus.COMPLETED),
            _make_progress("task-002", ProgressStatus.FAILED),
        ]

        gen = ReportGenerator(tfm, pm)
        report = gen.generate()
        assert report.total_duration_seconds > 0

    def test_generated_at_is_now(self, mock_tfm, mock_pm):
        gen = ReportGenerator(mock_tfm, mock_pm)
        report = gen.generate()
        assert isinstance(report.generated_at, datetime)

    def test_to_text_no_crash_on_empty(self, mock_tfm, mock_pm):
        gen = ReportGenerator(mock_tfm, mock_pm)
        report = gen.generate()
        text = report.to_text()
        assert "执行报告" in text


# ── 参数校验 ──────────────────────────────────────────────


class TestValidation:
    def test_none_tfm_raises(self, mock_pm):
        with pytest.raises(ValueError, match="task_file_manager"):
            ReportGenerator(None, mock_pm)

    def test_none_pm_raises(self, mock_tfm):
        with pytest.raises(ValueError, match="progress_manager"):
            ReportGenerator(mock_tfm, None)

    def test_properties(self, mock_tfm, mock_pm):
        gen = ReportGenerator(mock_tfm, mock_pm)
        assert gen.task_file_manager is mock_tfm
        assert gen.progress_manager is mock_pm


# ── 边界场景 ──────────────────────────────────────────────


class TestEdgeCases:
    def test_blocked_status(self):
        tfm = MagicMock()
        tfm.read_tasks.return_value = TaskJSON(
            project_name="P", created_by="t", total_tasks=1,
            tasks=[_make_task("task-001", "阻塞任务", TaskStatus.BLOCKED)],
        )
        pm = MagicMock()
        pm.read_progress.return_value = []

        gen = ReportGenerator(tfm, pm)
        report = gen.generate()
        assert report.blocked_count == 1

    def test_in_progress_status(self):
        tfm = MagicMock()
        tfm.read_tasks.return_value = TaskJSON(
            project_name="P", created_by="t", total_tasks=1,
            tasks=[_make_task("task-001", "进行中", TaskStatus.IN_PROGRESS)],
        )
        pm = MagicMock()
        pm.read_progress.return_value = []

        gen = ReportGenerator(tfm, pm)
        report = gen.generate()
        assert report.in_progress_count == 1
        assert report.is_all_done is False

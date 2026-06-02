"""
ProgressManager 单元测试

覆盖 ProgressManager 的所有公共方法和边界场景：
- read_progress: 正常读取、文件不存在、解析各种格式
- write_entry: 新增条目、替换已有条目
- update_status: 更新已有条目、创建新条目、多字段更新
- get_entry: 存在/不存在
- get_completed_count: 各状态计数
- _parse_entries: 各种格式兼容性（Git Msg 含中括号、多日期格式等）
"""

from datetime import datetime
from pathlib import Path

import pytest

from agent_automation_system.file_io.progress_manager import ProgressManager
from agent_automation_system.models.progress import ProgressEntry, ProgressStatus


# ─── Fixtures ──────────────────────────────────────


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """创建临时 data 目录"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def progress_manager(tmp_data_dir: Path) -> ProgressManager:
    """创建使用临时目录的 ProgressManager 实例"""
    return ProgressManager(file_path=tmp_data_dir / "progress.txt")


@pytest.fixture
def completed_entry() -> ProgressEntry:
    """返回一个已完成的 ProgressEntry"""
    return ProgressEntry(
        task_id="task-001",
        status=ProgressStatus.COMPLETED,
        role="senior-developer",
        started=datetime(2026, 5, 16, 10, 0, 0),
        finished=datetime(2026, 5, 16, 10, 30, 0),
        git_sha="a3f7b2c",
        git_msg="[task-001] senior-developer: 实现用户登录页面",
        retry=0,
    )


@pytest.fixture
def in_progress_entry() -> ProgressEntry:
    """返回一个进行中的 ProgressEntry"""
    return ProgressEntry(
        task_id="task-002",
        status=ProgressStatus.IN_PROGRESS,
        role="dev",
        started=datetime(2026, 5, 16, 10, 35, 0),
    )


@pytest.fixture
def failed_entry() -> ProgressEntry:
    """返回一个失败的 ProgressEntry"""
    return ProgressEntry(
        task_id="task-003",
        status=ProgressStatus.FAILED,
        role="qa",
        started=datetime(2026, 5, 16, 11, 0, 0),
        finished=datetime(2026, 5, 16, 11, 15, 0),
        error="测试超时",
        retry=1,
    )


# ─── read_progress 测试 ────────────────────────────


class TestReadProgress:
    """read_progress() 方法测试"""

    def test_read_empty_file(self, progress_manager):
        """空文件返回空列表"""
        progress_manager.file_path.write_text("", encoding="utf-8")
        result = progress_manager.read_progress()
        assert result == []

    def test_read_nonexistent_file(self, progress_manager):
        """文件不存在返回空列表"""
        result = progress_manager.read_progress()
        assert result == []

    def test_read_only_header(self, progress_manager):
        """只含文件头（无条目）返回空列表"""
        content = (
            "# ============================================\n"
            "# Project: Test\n"
            "# Updated: 2026-05-16 10:00:00\n"
            "# Progress: 0 / 0 tasks completed\n"
            "# ============================================\n"
        )
        progress_manager.file_path.write_text(content, encoding="utf-8")
        result = progress_manager.read_progress()
        assert result == []

    def test_read_single_entry(self, progress_manager, completed_entry):
        """正确解析单条记录"""
        progress_manager.write_entry(completed_entry)
        result = progress_manager.read_progress()

        assert len(result) == 1
        entry = result[0]
        assert entry.task_id == "task-001"
        assert entry.status == ProgressStatus.COMPLETED
        assert entry.role == "senior-developer"
        assert entry.git_sha == "a3f7b2c"

    def test_read_multiple_entries(
        self, progress_manager, completed_entry, in_progress_entry
    ):
        """正确解析多条记录"""
        progress_manager.write_entry(completed_entry)
        progress_manager.write_entry(in_progress_entry)
        result = progress_manager.read_progress()

        assert len(result) == 2
        assert result[0].task_id == "task-001"
        assert result[1].task_id == "task-002"


# ─── write_entry 测试 ──────────────────────────────


class TestWriteEntry:
    """write_entry() 方法测试"""

    def test_write_new_entry(self, progress_manager, completed_entry):
        """写入新条目"""
        progress_manager.write_entry(completed_entry)

        assert progress_manager.file_path.exists()
        result = progress_manager.read_progress()
        assert len(result) == 1
        assert result[0].task_id == "task-001"

    def test_write_replaces_existing(self, progress_manager, completed_entry):
        """同 task_id 的写入应替换旧条目"""
        progress_manager.write_entry(completed_entry)

        # 更新条目
        updated = ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.COMPLETED,
            role="senior-developer",
            git_sha="newhash9",
        )
        progress_manager.write_entry(updated)

        result = progress_manager.read_progress()
        assert len(result) == 1
        assert result[0].git_sha == "newhash9"

    def test_write_appends_different_task_id(
        self, progress_manager, completed_entry, in_progress_entry
    ):
        """不同 task_id 应追加"""
        progress_manager.write_entry(completed_entry)
        progress_manager.write_entry(in_progress_entry)

        result = progress_manager.read_progress()
        assert len(result) == 2

    def test_write_creates_parent_directory(self, tmp_path: Path):
        """自动创建父目录"""
        deep_path = tmp_path / "deep" / "nested" / "progress.txt"
        mgr = ProgressManager(file_path=deep_path)

        entry = ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.IN_PROGRESS,
            role="dev",
        )
        mgr.write_entry(entry)
        assert deep_path.exists()

    def test_written_file_has_header(self, progress_manager, completed_entry):
        """写入的文件包含文件头"""
        progress_manager.write_entry(completed_entry)
        content = progress_manager.file_path.read_text(encoding="utf-8")

        assert "# Project:" in content
        assert "# Progress:" in content
        assert "tasks completed" in content


# ─── update_status 测试 ────────────────────────────


class TestUpdateStatus:
    """update_status() 方法测试"""

    def test_update_existing_entry_status(self, progress_manager, in_progress_entry):
        """更新已有条目的状态"""
        progress_manager.write_entry(in_progress_entry)

        result = progress_manager.update_status(
            "task-002", ProgressStatus.COMPLETED
        )
        assert result.status == ProgressStatus.COMPLETED

        # 验证持久化
        entry = progress_manager.get_entry("task-002")
        assert entry is not None
        assert entry.status == ProgressStatus.COMPLETED

    def test_update_with_multiple_fields(self, progress_manager, in_progress_entry):
        """更新多个字段"""
        progress_manager.write_entry(in_progress_entry)

        now = datetime(2026, 5, 16, 11, 0, 0)
        result = progress_manager.update_status(
            "task-002",
            ProgressStatus.COMPLETED,
            finished=now,
            git_sha="c4d5e6f",
            git_msg="[task-002] dev: 完成 CI 配置",
        )
        assert result.status == ProgressStatus.COMPLETED
        assert result.finished == now
        assert result.git_sha == "c4d5e6f"
        assert result.git_msg == "[task-002] dev: 完成 CI 配置"

    def test_update_creates_new_entry_if_not_exists(self, progress_manager):
        """条目不存在时自动创建"""
        result = progress_manager.update_status(
            "task-005",
            ProgressStatus.IN_PROGRESS,
            role="dev",
        )
        assert result.task_id == "task-005"
        assert result.status == ProgressStatus.IN_PROGRESS
        assert result.role == "dev"

        # 验证持久化
        entry = progress_manager.get_entry("task-005")
        assert entry is not None

    def test_update_with_error_and_retry(self, progress_manager, in_progress_entry):
        """更新状态为失败并设置错误信息和重试次数"""
        progress_manager.write_entry(in_progress_entry)

        result = progress_manager.update_status(
            "task-002",
            ProgressStatus.FAILED,
            error="构建失败",
            retry=2,
        )
        assert result.status == ProgressStatus.FAILED
        assert result.error == "构建失败"
        assert result.retry == 2

    def test_update_preserves_other_fields(self, progress_manager, completed_entry):
        """更新状态时保留未更新的字段"""
        progress_manager.write_entry(completed_entry)

        # 只更新 retry
        result = progress_manager.update_status("task-001", ProgressStatus.COMPLETED, retry=1)
        assert result.retry == 1
        # 其他字段应保留
        assert result.role == "senior-developer"
        assert result.git_sha == "a3f7b2c"

    def test_update_new_entry_defaults(self, progress_manager):
        """创建新条目时 role 默认为 unknown，retry 默认为 0"""
        result = progress_manager.update_status("task-010", ProgressStatus.IN_PROGRESS)
        assert result.role == "unknown"
        assert result.retry == 0


# ─── get_entry 测试 ────────────────────────────────


class TestGetEntry:
    """get_entry() 方法测试"""

    def test_get_existing_entry(self, progress_manager, completed_entry):
        """获取已存在的条目"""
        progress_manager.write_entry(completed_entry)
        result = progress_manager.get_entry("task-001")
        assert result is not None
        assert result.task_id == "task-001"

    def test_get_nonexistent_entry(self, progress_manager, completed_entry):
        """获取不存在的条目返回 None"""
        progress_manager.write_entry(completed_entry)
        result = progress_manager.get_entry("task-999")
        assert result is None

    def test_get_entry_empty_file(self, progress_manager):
        """空文件中获取条目返回 None"""
        result = progress_manager.get_entry("task-001")
        assert result is None


# ─── get_completed_count 测试 ───────────────────────


class TestGetCompletedCount:
    """get_completed_count() 方法测试"""

    def test_count_zero(self, progress_manager, in_progress_entry):
        """没有已完成的条目"""
        progress_manager.write_entry(in_progress_entry)
        assert progress_manager.get_completed_count() == 0

    def test_count_some(
        self, progress_manager, completed_entry, in_progress_entry, failed_entry
    ):
        """部分条目已完成"""
        progress_manager.write_entry(completed_entry)
        progress_manager.write_entry(in_progress_entry)
        progress_manager.write_entry(failed_entry)
        assert progress_manager.get_completed_count() == 1

    def test_count_all_completed(self, progress_manager):
        """所有条目都已完成"""
        for i in range(3):
            entry = ProgressEntry(
                task_id=f"task-00{i+1}",
                status=ProgressStatus.COMPLETED,
                role="dev",
            )
            progress_manager.write_entry(entry)
        assert progress_manager.get_completed_count() == 3

    def test_count_empty_file(self, progress_manager):
        """空文件返回 0"""
        assert progress_manager.get_completed_count() == 0


# ─── 解析器边界场景 ──────────────────────────────────


class TestParserEdgeCases:
    """_parse_entries 解析器边界场景测试"""

    def test_parse_git_msg_with_brackets(self, progress_manager):
        """Git Msg 值中包含 [task-xxx] 不应被误认为新条目

        这是之前修复过的 bug：Git Msg: [task-001] dev: 描述
        """
        content = (
            "# ============================================\n"
            "# Project: Test\n"
            "# Updated: 2026-05-16 10:00:00\n"
            "# Progress: 1 / 1 tasks completed\n"
            "# ============================================\n"
            "\n"
            "[task-001]\n"
            "  Status:    COMPLETED\n"
            "  Role:      dev\n"
            "  Git Msg:   [task-001] dev: 实现功能\n"
            "\n"
        )
        progress_manager.file_path.write_text(content, encoding="utf-8")
        result = progress_manager.read_progress()

        assert len(result) == 1, "Git Msg 中的 [task-xxx] 不应被解析为新条目"
        assert result[0].git_msg == "[task-001] dev: 实现功能"

    def test_parse_multiple_datetime_formats(self, progress_manager):
        """解析多种日期时间格式"""
        content = (
            "# ============================================\n"
            "# Project: Test\n"
            "# Updated: 2026-05-16 10:00:00\n"
            "# Progress: 1 / 1 tasks completed\n"
            "# ============================================\n"
            "\n"
            "[task-001]\n"
            "  Status:    COMPLETED\n"
            "  Role:      dev\n"
            "  Started:   2026-05-13 11:05:00\n"
            "  Finished:  2026-05-13T11:32:15Z\n"
            "\n"
        )
        progress_manager.file_path.write_text(content, encoding="utf-8")
        result = progress_manager.read_progress()

        assert len(result) == 1
        assert result[0].started == datetime(2026, 5, 13, 11, 5, 0)
        assert result[0].finished == datetime(2026, 5, 13, 11, 32, 15)

    def test_parse_minimal_entry(self, progress_manager):
        """解析只有必填字段的条目"""
        content = (
            "# ============================================\n"
            "# Project: Test\n"
            "# Updated: 2026-05-16 10:00:00\n"
            "# Progress: 1 / 1 tasks completed\n"
            "# ============================================\n"
            "\n"
            "[task-001]\n"
            "  Status:    IN_PROGRESS\n"
            "  Role:      dev\n"
            "\n"
        )
        progress_manager.file_path.write_text(content, encoding="utf-8")
        result = progress_manager.read_progress()

        assert len(result) == 1
        assert result[0].task_id == "task-001"
        assert result[0].status == ProgressStatus.IN_PROGRESS
        assert result[0].started is None
        assert result[0].git_sha is None

    def test_parse_entry_with_all_fields(self, progress_manager):
        """解析包含所有字段的条目"""
        content = (
            "# ============================================\n"
            "# Project: Test\n"
            "# Updated: 2026-05-16 10:00:00\n"
            "# Progress: 1 / 1 tasks completed\n"
            "# ============================================\n"
            "\n"
            "[task-001]\n"
            "  Status:    COMPLETED\n"
            "  Role:      senior-developer\n"
            "  Started:   2026-05-13 11:05:00\n"
            "  Finished:  2026-05-13 11:32:15\n"
            "  Git SHA:   a3f7b2c\n"
            "  Git Msg:   [task-001] senior-developer: 实现功能\n"
            "  Retry:     0\n"
            "\n"
        )
        progress_manager.file_path.write_text(content, encoding="utf-8")
        result = progress_manager.read_progress()

        assert len(result) == 1
        entry = result[0]
        assert entry.task_id == "task-001"
        assert entry.status == ProgressStatus.COMPLETED
        assert entry.role == "senior-developer"
        assert entry.started == datetime(2026, 5, 13, 11, 5, 0)
        assert entry.finished == datetime(2026, 5, 13, 11, 32, 15)
        assert entry.git_sha == "a3f7b2c"
        assert entry.retry == 0

    def test_parse_failed_entry_with_error(self, progress_manager):
        """解析失败的条目（含 Error 和 Retry 字段）"""
        content = (
            "# ============================================\n"
            "# Project: Test\n"
            "# Updated: 2026-05-16 10:00:00\n"
            "# Progress: 0 / 1 tasks completed\n"
            "# ============================================\n"
            "\n"
            "[task-003]\n"
            "  Status:    FAILED\n"
            "  Role:      qa\n"
            "  Error:     测试执行超时\n"
            "  Retry:     2\n"
            "\n"
        )
        progress_manager.file_path.write_text(content, encoding="utf-8")
        result = progress_manager.read_progress()

        assert len(result) == 1
        assert result[0].status == ProgressStatus.FAILED
        assert result[0].error == "测试执行超时"
        assert result[0].retry == 2


# ─── 写入-读取一致性 ─────────────────────────────────


class TestRoundTrip:
    """写入后读取一致性测试"""

    def test_roundtrip_completed_entry(self, progress_manager, completed_entry):
        """完成条目的写入-读取一致性"""
        progress_manager.write_entry(completed_entry)
        result = progress_manager.read_progress()

        assert len(result) == 1
        entry = result[0]
        assert entry.task_id == completed_entry.task_id
        assert entry.status == completed_entry.status
        assert entry.role == completed_entry.role
        assert entry.started == completed_entry.started
        assert entry.finished == completed_entry.finished
        assert entry.git_sha == completed_entry.git_sha

    def test_roundtrip_multiple_entries(
        self, progress_manager, completed_entry, in_progress_entry, failed_entry
    ):
        """多个条目的写入-读取一致性"""
        progress_manager.write_entry(completed_entry)
        progress_manager.write_entry(in_progress_entry)
        progress_manager.write_entry(failed_entry)

        result = progress_manager.read_progress()
        assert len(result) == 3

        ids = {e.task_id for e in result}
        assert ids == {"task-001", "task-002", "task-003"}

        statuses = {e.task_id: e.status for e in result}
        assert statuses["task-001"] == ProgressStatus.COMPLETED
        assert statuses["task-002"] == ProgressStatus.IN_PROGRESS
        assert statuses["task-003"] == ProgressStatus.FAILED

    def test_roundtrip_minimal_entry(self, progress_manager):
        """最简条目的写入-读取一致性"""
        minimal = ProgressEntry(
            task_id="task-099",
            status=ProgressStatus.IN_PROGRESS,
            role="dev",
        )
        progress_manager.write_entry(minimal)
        result = progress_manager.read_progress()

        assert len(result) == 1
        assert result[0].task_id == "task-099"
        assert result[0].status == ProgressStatus.IN_PROGRESS
        assert result[0].started is None

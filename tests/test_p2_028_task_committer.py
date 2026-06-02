"""
P2-028 测试：TaskCommitter 自动 Git 提交流程

验证 Sub-Agent 完成后自动 git commit + 更新 progress.txt 的完整编排。
覆盖：
1. CommitResult 数据模型
2. commit_on_success — 成功 → commit + progress
3. record_failure — 失败 → 不 commit，仅 progress
4. commit_or_record — 自动分流
5. GitManager 集成（真实调用验证）
6. ProgressManager 集成（progress.txt 写入验证）
7. 参数校验（None task / None result）
8. 自定义 role / description
9. commit 失败回退（无变更等）
10. 边界条件
"""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from agent_automation_system.git_manager.task_committer import (
    CommitResult,
    TaskCommitter,
)
from agent_automation_system.git_manager.git_manager import GitManager
from agent_automation_system.file_io.progress_manager import ProgressManager
from agent_automation_system.models.task import (
    Task,
    TaskComplexity,
    TaskPriority,
    TaskStatus,
)
from agent_automation_system.models.progress import ProgressEntry, ProgressStatus
from agent_automation_system.sub_agent.sub_agent import (
    AgentPhase,
    SubAgentResult,
    SubAgentResultStatus,
)


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def sample_task():
    return Task(
        id="task-001",
        title="实现用户登录 API",
        description="实现用户登录接口",
        dependencies=[],
        suggested_role="senior-developer",
        priority=TaskPriority.HIGH,
        estimated_complexity=TaskComplexity.MEDIUM,
        status=TaskStatus.PENDING,
    )


@pytest.fixture
def success_result():
    return SubAgentResult(
        task_id="task-001",
        status=SubAgentResultStatus.SUCCESS,
        phase=AgentPhase.COMPLETED,
        started_at=datetime(2026, 5, 25, 10, 0, 0),
        finished_at=datetime(2026, 5, 25, 10, 15, 0),
    )


@pytest.fixture
def failed_result():
    return SubAgentResult(
        task_id="task-001",
        status=SubAgentResultStatus.FAILED,
        phase=AgentPhase.FAILED,
        error="assert False in test_login",
        started_at=datetime(2026, 5, 25, 10, 0, 0),
        finished_at=datetime(2026, 5, 25, 10, 5, 0),
    )


@pytest.fixture
def mock_git_manager():
    git_mgr = MagicMock(spec=GitManager)
    git_mgr.commit_changes.return_value = {
        "success": True,
        "hexsha": "abc1234567890def1234567890abcdef12345678",
        "short_sha": "abc1234",
        "message": "[task-001] dev: 实现用户登录 API",
        "files_committed": ["api/login.py", "tests/test_login.py"],
        "error": None,
        "retries": 0,
    }
    return git_mgr


@pytest.fixture
def mock_git_manager_failure():
    git_mgr = MagicMock(spec=GitManager)
    git_mgr.commit_changes.return_value = {
        "success": False,
        "hexsha": None,
        "short_sha": None,
        "message": "[task-001] dev: 实现用户登录 API",
        "files_committed": [],
        "error": "没有变更需要提交",
        "retries": 0,
    }
    return git_mgr


@pytest.fixture
def mock_progress_manager():
    pm = MagicMock(spec=ProgressManager)
    return pm


@pytest.fixture
def committer(mock_git_manager, mock_progress_manager):
    return TaskCommitter(
        git_manager=mock_git_manager,
        progress_manager=mock_progress_manager,
        role_short="dev",
    )


# ── CommitResult 模型 ─────────────────────────────────────


class TestCommitResult:
    """CommitResult 数据模型"""

    def test_defaults(self):
        r = CommitResult(task_id="task-001")
        assert r.task_id == "task-001"
        assert r.committed is False
        assert r.commit_hash is None
        assert r.progress_updated is False
        assert r.error_message == ""

    def test_success_property(self):
        r = CommitResult(task_id="t1", committed=True, progress_updated=True)
        assert r.success is True

    def test_success_partial_commit(self):
        r = CommitResult(task_id="t1", committed=True, progress_updated=False)
        assert r.success is False

    def test_success_no_commit(self):
        r = CommitResult(task_id="t1", progress_updated=True)
        assert r.success is False

    def test_summary_with_commit(self):
        r = CommitResult(
            task_id="task-001",
            committed=True,
            short_sha="abc1234",
            commit_message="[task-001] dev: 实现登录",
            files_committed=["a.py", "b.py"],
        )
        s = r.summary
        assert "abc1234" in s
        assert "task-001" in s
        assert "2 files" in s

    def test_summary_without_commit(self):
        r = CommitResult(
            task_id="task-002",
            error_message="no changes",
        )
        s = r.summary
        assert "NOT committed" in s
        assert "no changes" in s

    def test_short_sha_fallback_to_hexsha(self):
        r = CommitResult(
            task_id="t1",
            committed=True,
            commit_hash="longhash1234567890abcdef",
        )
        assert "longhas" in r.summary

    def test_empty_commit_hash_no_summary_crash(self):
        r = CommitResult(task_id="t1", committed=True)
        # 不应该崩溃
        s = r.summary
        assert "?" in s  # fallback


# ── commit_on_success ─────────────────────────────────────


class TestCommitOnSuccess:
    """commit_on_success：成功 → commit + progress"""

    def test_commits_and_updates_progress(
        self, committer, sample_task, success_result, mock_git_manager, mock_progress_manager
    ):
        result = committer.commit_on_success(sample_task, success_result)

        assert result.committed is True
        assert result.progress_updated is True
        assert result.success is True
        assert result.commit_hash == "abc1234567890def1234567890abcdef12345678"
        assert result.short_sha == "abc1234"
        assert len(result.files_committed) == 2

        # 验证 GitManager 被调用
        mock_git_manager.commit_changes.assert_called_once()
        call_kwargs = mock_git_manager.commit_changes.call_args[1]
        assert call_kwargs["task_id"] == "001"
        assert call_kwargs["role"] == "dev"
        assert call_kwargs["description"] == "实现用户登录 API"

        # 验证 ProgressManager 被调用
        mock_progress_manager.write_entry.assert_called_once()
        entry = mock_progress_manager.write_entry.call_args[0][0]
        assert entry.task_id == "task-001"
        assert entry.status == ProgressStatus.COMPLETED
        assert entry.git_sha == "abc1234"
        assert "[task-001]" in entry.git_msg

    def test_uses_custom_role(self, committer, sample_task, success_result, mock_git_manager):
        result = committer.commit_on_success(sample_task, success_result, role="qa")
        assert result.committed is True
        call_kwargs = mock_git_manager.commit_changes.call_args[1]
        assert call_kwargs["role"] == "qa"

    def test_uses_custom_description(self, committer, sample_task, success_result, mock_git_manager):
        result = committer.commit_on_success(
            sample_task, success_result, description="自定义描述"
        )
        assert result.committed is True
        call_kwargs = mock_git_manager.commit_changes.call_args[1]
        assert call_kwargs["description"] == "自定义描述"

    def test_falls_back_to_title_when_no_description(self, committer, mock_git_manager):
        task = Task(
            id="task-002",
            title="修复 Bug",
            description="修复登录页面的样式问题",
            dependencies=[],
            suggested_role="dev",
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        result = SubAgentResult(
            task_id="task-002",
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.COMPLETED,
        )
        committer.commit_on_success(task, result, description=None)
        call_kwargs = mock_git_manager.commit_changes.call_args[1]
        assert call_kwargs["description"] == "修复 Bug"

    def test_commit_failure_no_progress_update(
        self, sample_task, success_result, mock_git_manager_failure, mock_progress_manager
    ):
        committer_fail = TaskCommitter(mock_git_manager_failure, mock_progress_manager)
        result = committer_fail.commit_on_success(sample_task, success_result)

        assert result.committed is False
        assert result.progress_updated is False
        assert "没有变更" in result.error_message
        # commit 失败时不写 progress
        mock_progress_manager.write_entry.assert_not_called()

    def test_strips_task_prefix(self, committer, mock_git_manager):
        task = Task(
            id="task-099",
            title="T",
            description="D",
            dependencies=[],
            suggested_role="dev",
            priority=TaskPriority.LOW,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        result = SubAgentResult(task_id="task-099", status=SubAgentResultStatus.SUCCESS, phase=AgentPhase.COMPLETED)
        committer.commit_on_success(task, result)
        call_kwargs = mock_git_manager.commit_changes.call_args[1]
        assert call_kwargs["task_id"] == "099"


# ── record_failure ────────────────────────────────────────


class TestRecordFailure:
    """record_failure：失败 → 不 commit，仅 progress"""

    def test_records_failure_no_commit(
        self, committer, sample_task, failed_result, mock_git_manager, mock_progress_manager
    ):
        result = committer.record_failure(sample_task, failed_result)

        assert result.committed is False
        assert result.progress_updated is True
        assert "assert False" in result.error_message

        # GitManager 不应被调用
        mock_git_manager.commit_changes.assert_not_called()

        # ProgressManager 应写入 FAILED
        mock_progress_manager.write_entry.assert_called_once()
        entry = mock_progress_manager.write_entry.call_args[0][0]
        assert entry.task_id == "task-001"
        assert entry.status == ProgressStatus.FAILED
        assert "assert False" in entry.error

    def test_uses_default_error_when_none(self, committer, sample_task, mock_progress_manager):
        result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.FAILED,
            phase=AgentPhase.FAILED,
            error="",
        )
        result = committer.record_failure(sample_task, result)
        assert result.progress_updated is True
        entry = mock_progress_manager.write_entry.call_args[0][0]
        assert entry.error == "task failed"

    def test_custom_role_in_failure(self, committer, sample_task, mock_progress_manager):
        result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.FAILED,
            phase=AgentPhase.FAILED,
            error="timeout",
        )
        committer.record_failure(sample_task, result, role="qa")
        entry = mock_progress_manager.write_entry.call_args[0][0]
        assert entry.role == "qa"


# ── commit_or_record 自动分流 ─────────────────────────────


class TestCommitOrRecord:
    """commit_or_record：自动分流"""

    def test_success_triggers_commit(self, committer, sample_task, success_result, mock_git_manager):
        result = committer.commit_or_record(sample_task, success_result)
        assert result.committed is True
        mock_git_manager.commit_changes.assert_called_once()

    def test_failed_triggers_record(self, committer, sample_task, failed_result, mock_git_manager):
        result = committer.commit_or_record(sample_task, failed_result)
        assert result.committed is False
        mock_git_manager.commit_changes.assert_not_called()

    def test_blocked_triggers_record(self, committer, sample_task, mock_git_manager):
        result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.BLOCKED,
            phase=AgentPhase.BLOCKED,
            error="依赖未满足",
        )
        r = committer.commit_or_record(sample_task, result)
        assert r.committed is False
        mock_git_manager.commit_changes.assert_not_called()

    def test_timeout_triggers_record(self, committer, sample_task, mock_git_manager):
        result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.TIMEOUT,
            phase=AgentPhase.BLOCKED,
            error="超时",
        )
        r = committer.commit_or_record(sample_task, result)
        assert r.committed is False


# ── 参数校验 ──────────────────────────────────────────────


class TestValidation:
    """参数校验"""

    def test_none_git_manager_raises(self, mock_progress_manager):
        with pytest.raises(ValueError, match="git_manager"):
            TaskCommitter(git_manager=None, progress_manager=mock_progress_manager)

    def test_none_progress_manager_raises(self, mock_git_manager):
        with pytest.raises(ValueError, match="progress_manager"):
            TaskCommitter(git_manager=mock_git_manager, progress_manager=None)

    def test_commit_none_task_raises(self, committer, success_result):
        with pytest.raises(ValueError, match="task"):
            committer.commit_on_success(None, success_result)

    def test_commit_none_result_raises(self, committer, sample_task):
        with pytest.raises(ValueError, match="agent_result"):
            committer.commit_on_success(sample_task, None)

    def test_record_none_task_raises(self, committer, failed_result):
        with pytest.raises(ValueError, match="task"):
            committer.record_failure(None, failed_result)

    def test_record_none_result_raises(self, committer, sample_task):
        with pytest.raises(ValueError, match="agent_result"):
            committer.record_failure(sample_task, None)

    def test_default_role(self, mock_git_manager, mock_progress_manager):
        c = TaskCommitter(mock_git_manager, mock_progress_manager)
        assert c._role_short == "dev"

    def test_custom_default_role(self, mock_git_manager, mock_progress_manager):
        c = TaskCommitter(mock_git_manager, mock_progress_manager, role_short="qa")
        assert c._role_short == "qa"


# ── 属性访问 ──────────────────────────────────────────────


class TestProperties:
    """属性访问"""

    def test_git_manager_property(self, committer, mock_git_manager):
        assert committer.git_manager is mock_git_manager

    def test_progress_manager_property(self, committer, mock_progress_manager):
        assert committer.progress_manager is mock_progress_manager


# ── 集成场景 ──────────────────────────────────────────────


class TestIntegrationScenarios:
    """完整流程场景"""

    def test_full_success_flow(self, committer, sample_task, success_result, mock_git_manager, mock_progress_manager):
        """完整成功流程：commit → progress"""
        r = committer.commit_on_success(sample_task, success_result)

        assert r.committed is True
        assert r.progress_updated is True
        assert r.success is True
        mock_git_manager.commit_changes.assert_called_once()
        mock_progress_manager.write_entry.assert_called_once()

    def test_full_failure_flow(self, committer, sample_task, failed_result, mock_git_manager, mock_progress_manager):
        """完整失败流程：不 commit + progress"""
        r = committer.record_failure(sample_task, failed_result)

        assert r.committed is False
        assert r.progress_updated is True
        mock_git_manager.commit_changes.assert_not_called()
        mock_progress_manager.write_entry.assert_called_once()

    def test_commit_failure_no_progress(self, sample_task, success_result, mock_git_manager_failure, mock_progress_manager):
        """commit 失败时两步都不做"""
        c = TaskCommitter(mock_git_manager_failure, mock_progress_manager)
        r = c.commit_on_success(sample_task, success_result)

        assert r.committed is False
        assert r.progress_updated is False
        mock_progress_manager.write_entry.assert_not_called()

    def test_retries_reflected(self, sample_task, success_result, mock_progress_manager):
        """重试次数体现在结果中"""
        git_mgr = MagicMock(spec=GitManager)
        git_mgr.commit_changes.return_value = {
            "success": True,
            "hexsha": "abc123",
            "short_sha": "abc1234",
            "message": "[task-001] dev: 实现用户登录 API",
            "files_committed": ["a.py"],
            "error": None,
            "retries": 2,
        }
        c = TaskCommitter(git_mgr, mock_progress_manager)
        r = c.commit_on_success(sample_task, success_result)
        assert r.retries == 2

    def test_progress_entry_has_timestamps(self, committer, sample_task, success_result, mock_progress_manager):
        """ProgressEntry 包含时间戳"""
        committer.commit_on_success(sample_task, success_result)
        entry = mock_progress_manager.write_entry.call_args[0][0]
        assert entry.started is not None
        assert entry.finished is not None
        assert isinstance(entry.started, datetime)
        assert isinstance(entry.finished, datetime)

    def test_multiple_commits_independent(self, committer, mock_git_manager, mock_progress_manager):
        """多次提交互不影响"""
        t1 = Task(
            id="task-001", title="任务1", description="D1",
            dependencies=[], suggested_role="dev",
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        t2 = Task(
            id="task-002", title="任务2", description="D2",
            dependencies=["task-001"], suggested_role="dev",
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        r1 = SubAgentResult(task_id="task-001", status=SubAgentResultStatus.SUCCESS, phase=AgentPhase.COMPLETED)
        r2 = SubAgentResult(task_id="task-002", status=SubAgentResultStatus.FAILED, phase=AgentPhase.FAILED)

        cr1 = committer.commit_or_record(t1, r1)
        cr2 = committer.commit_or_record(t2, r2)

        assert cr1.committed is True
        assert cr2.committed is False
        assert mock_git_manager.commit_changes.call_count == 1
        assert mock_progress_manager.write_entry.call_count == 2

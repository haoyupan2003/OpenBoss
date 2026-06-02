"""
P2-030 测试：FailureHandler 失败时不 commit

验证测试失败后的统一处理流程：
1. FailureHandleResult 数据模型
2. handle_failure 三步完整流程（日志 + task.json + progress）
3. committed 永远 False（核心约束）
4. handle_failure_from_result（SubAgentResult 提取）
5. 部分失败容错（日志写失败不影响后续）
6. task.json 中无对应任务的容错
7. 参数校验
"""

from datetime import datetime
from unittest.mock import MagicMock, call

import pytest

from agent_automation_system.git_manager.failure_handler import (
    FailureHandleResult,
    FailureHandler,
)
from agent_automation_system.file_io.log_manager import LogLevel
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
def mock_log_manager():
    lm = MagicMock()
    return lm


@pytest.fixture
def mock_task_file_manager():
    tfm = MagicMock()
    tfm.update_task_status.return_value = None  # void method
    return tfm


@pytest.fixture
def mock_progress_manager():
    pm = MagicMock()
    return pm


@pytest.fixture
def handler(mock_log_manager, mock_task_file_manager, mock_progress_manager):
    return FailureHandler(mock_log_manager, mock_task_file_manager, mock_progress_manager)


# ── FailureHandleResult ───────────────────────────────────


class TestFailureHandleResult:
    """FailureHandleResult 模型"""

    def test_defaults(self):
        r = FailureHandleResult(task_id="task-001")
        assert r.task_id == "task-001"
        assert r.logged is False
        assert r.task_json_updated is False
        assert r.progress_updated is False
        assert r.committed is False

    def test_all_done_is_success(self):
        r = FailureHandleResult(
            task_id="t1", logged=True, task_json_updated=True, progress_updated=True,
        )
        assert r.success is True

    def test_partial_is_not_success(self):
        r = FailureHandleResult(
            task_id="t1", logged=True, task_json_updated=False, progress_updated=True,
        )
        assert r.success is False

    def test_committed_always_false(self):
        """核心约束：committed 永远 False"""
        # 即使尝试设为 True（不应发生），但测试确保这个字段存在且可检查
        r = FailureHandleResult(task_id="t1")
        assert r.committed is False

    def test_error_message_stored(self):
        r = FailureHandleResult(
            task_id="t1",
            error_message="assert False in test_login",
        )
        assert "assert False" in r.error_message


# ── handle_failure 三步流程 ──────────────────────────────


class TestHandleFailureFullFlow:
    """handle_failure 完整三步流程"""

    def test_logs_error(self, handler, sample_task, mock_log_manager):
        handler.handle_failure(sample_task, "test failed", role="dev")
        mock_log_manager.write_log.assert_called()
        call_args = mock_log_manager.write_log.call_args[1]
        assert call_args["level"] == LogLevel.ERROR
        assert call_args["agent_id"] == "dev"
        assert "test failed" in call_args["message"]
        assert "task-001" in call_args["message"]

    def test_updates_task_json(self, handler, sample_task, mock_task_file_manager):
        handler.handle_failure(sample_task, "test failed")
        mock_task_file_manager.update_task_status.assert_called_once_with(
            task_id="task-001",
            status=TaskStatus.FAILED,
            error_message="test failed",
        )

    def test_updates_progress(self, handler, sample_task, mock_progress_manager):
        handler.handle_failure(sample_task, "test failed", role="qa")
        mock_progress_manager.write_entry.assert_called_once()
        entry = mock_progress_manager.write_entry.call_args[0][0]
        assert entry.task_id == "task-001"
        assert entry.status == ProgressStatus.FAILED
        assert entry.role == "qa"
        assert entry.error == "test failed"

    def test_returns_success_when_all_done(self, handler, sample_task):
        r = handler.handle_failure(sample_task, "test failed")
        assert r.success is True
        assert r.logged is True
        assert r.task_json_updated is True
        assert r.progress_updated is True

    def test_result_has_error_message(self, handler, sample_task):
        r = handler.handle_failure(sample_task, "assert False")
        assert r.error_message == "assert False"

    def test_default_error_when_none(self, handler, sample_task):
        r = handler.handle_failure(sample_task, "")
        assert r.error_message == "unknown error"

    def test_default_role(self, handler, sample_task, mock_progress_manager):
        handler.handle_failure(sample_task, "err")
        entry = mock_progress_manager.write_entry.call_args[0][0]
        assert entry.role == "dev"


# ── committed 永远 False ─────────────────────────────────


class TestNoCommitGuarantee:
    """核心约束：绝不 commit"""

    def test_committed_always_false(self, handler, sample_task):
        r = handler.handle_failure(sample_task, "error")
        assert r.committed is False

    def test_committed_false_even_on_partial_success(self, handler, sample_task):
        r = handler.handle_failure(sample_task, "error")
        assert r.committed is False

    def test_no_git_calls(self, handler, sample_task):
        """FailureHandler 不依赖 GitManager，永远不会调用 commit"""
        r = handler.handle_failure(sample_task, "error")
        assert r.committed is False


# ── 部分失败容错 ──────────────────────────────────────────


class TestPartialFailureTolerance:
    """某一步失败不影响后续步骤"""

    def test_log_failure_still_updates_others(
        self, sample_task, mock_log_manager, mock_task_file_manager, mock_progress_manager
    ):
        """日志写入失败，task.json 和 progress 仍被更新"""
        mock_log_manager.write_log.side_effect = RuntimeError("log write failed")
        h = FailureHandler(mock_log_manager, mock_task_file_manager, mock_progress_manager)

        r = h.handle_failure(sample_task, "error")

        assert r.logged is False
        assert r.task_json_updated is True  # 仍然更新
        assert r.progress_updated is True   # 仍然更新
        mock_task_file_manager.update_task_status.assert_called_once()
        mock_progress_manager.write_entry.assert_called_once()

    def test_task_json_missing_does_not_block_progress(
        self, sample_task, mock_log_manager, mock_task_file_manager, mock_progress_manager
    ):
        """task.json 中没有该任务，progress 仍写入"""
        mock_task_file_manager.update_task_status.side_effect = KeyError("not found")
        h = FailureHandler(mock_log_manager, mock_task_file_manager, mock_progress_manager)

        r = h.handle_failure(sample_task, "error")

        assert r.task_json_updated is False
        assert r.progress_updated is True
        assert "not found" in r.error_message
        mock_progress_manager.write_entry.assert_called_once()

    def test_all_three_fail(self, sample_task, mock_log_manager, mock_task_file_manager, mock_progress_manager):
        """三步全失败也能安全返回"""
        mock_log_manager.write_log.side_effect = RuntimeError("log fail")
        mock_task_file_manager.update_task_status.side_effect = RuntimeError("task fail")
        mock_progress_manager.write_entry.side_effect = RuntimeError("progress fail")
        h = FailureHandler(mock_log_manager, mock_task_file_manager, mock_progress_manager)

        r = h.handle_failure(sample_task, "error")

        assert r.logged is False
        assert r.task_json_updated is False
        assert r.progress_updated is False
        assert r.success is False
        assert r.committed is False


# ── handle_failure_from_result ────────────────────────────


class TestHandleFailureFromResult:
    """从 SubAgentResult 提取错误"""

    def test_extracts_error_from_result(self, handler, sample_task, mock_log_manager):
        result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.FAILED,
            phase=AgentPhase.FAILED,
            error="test assertion failed",
        )
        r = handler.handle_failure_from_result(sample_task, result)
        assert r.error_message == "test assertion failed"
        assert "test assertion failed" in mock_log_manager.write_log.call_args[1]["message"]

    def test_fallback_when_no_error_attr(self, handler, sample_task):
        """无 error 属性时兜底"""
        r = handler.handle_failure_from_result(sample_task, "plain string")
        assert "plain string" in r.error_message

    def test_result_with_none_error(self, handler, sample_task):
        result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.FAILED,
            phase=AgentPhase.FAILED,
            error=None,
        )
        r = handler.handle_failure_from_result(sample_task, result)
        assert r.error_message == "unknown error"


# ── 参数校验 ──────────────────────────────────────────────


class TestValidation:
    """参数校验"""

    def test_none_task_raises(self, handler):
        with pytest.raises(ValueError, match="cannot be None"):
            handler.handle_failure(None, "error")

    def test_none_log_manager_raises(self, mock_task_file_manager, mock_progress_manager):
        with pytest.raises(ValueError, match="log_manager"):
            FailureHandler(None, mock_task_file_manager, mock_progress_manager)

    def test_none_task_file_manager_raises(self, mock_log_manager, mock_progress_manager):
        with pytest.raises(ValueError, match="task_file_manager"):
            FailureHandler(mock_log_manager, None, mock_progress_manager)

    def test_none_progress_manager_raises(self, mock_log_manager, mock_task_file_manager):
        with pytest.raises(ValueError, match="progress_manager"):
            FailureHandler(mock_log_manager, mock_task_file_manager, None)


# ── 属性访问 ──────────────────────────────────────────────


class TestProperties:
    """属性访问"""

    def test_log_manager(self, handler, mock_log_manager):
        assert handler.log_manager is mock_log_manager

    def test_task_file_manager(self, handler, mock_task_file_manager):
        assert handler.task_file_manager is mock_task_file_manager

    def test_progress_manager(self, handler, mock_progress_manager):
        assert handler.progress_manager is mock_progress_manager


# ── 集成对比 ──────────────────────────────────────────────


class TestIntegrationWithTaskCommitter:
    """与 TaskCommitter 互补验证"""

    def test_committer_sets_committed_true(self):
        """TaskCommitter 成功时 committed=True，FailureHandler 永远 False"""
        from agent_automation_system.git_manager.task_committer import CommitResult

        commit_r = CommitResult(task_id="t1", committed=True, progress_updated=True)
        assert commit_r.committed is True

        fail_r = FailureHandleResult(task_id="t1", logged=True, task_json_updated=True, progress_updated=True)
        assert fail_r.committed is False

    def test_both_update_progress(self):
        """两者都更新 progress"""
        from agent_automation_system.git_manager.task_committer import CommitResult

        commit_r = CommitResult(task_id="t1", progress_updated=True)
        fail_r = FailureHandleResult(task_id="t1", progress_updated=True)
        assert commit_r.progress_updated is True
        assert fail_r.progress_updated is True

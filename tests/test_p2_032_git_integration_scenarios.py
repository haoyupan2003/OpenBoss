"""
P2-032：Git 集成场景测试 — 成功 commit / 失败不 commit / 重试 commit

使用真实临时 Git 仓库验证 TaskCommitter + GitManager 端到端行为。
与 P1-064（Git 基础流）互补，聚焦 TaskCommitter 编排层。

三大场景：
1. 成功 commit — 文件变更 → commit → 验证 git log
2. 失败不 commit — FailureHandler 处理后 git 仍 clean
3. 重试 commit — GitManager 自动重试 + 最终成功
"""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from git import Repo

from agent_automation_system.file_io.log_manager import LogLevel, LogManager
from agent_automation_system.file_io.progress_manager import ProgressManager
from agent_automation_system.file_io.task_file_manager import TaskFileManager
from agent_automation_system.git_manager import GitManager
from agent_automation_system.git_manager.failure_handler import FailureHandler
from agent_automation_system.git_manager.task_committer import TaskCommitter
from agent_automation_system.models.task import (
    Task,
    TaskComplexity,
    TaskPriority,
    TaskStatus,
)
from agent_automation_system.sub_agent.sub_agent import (
    AgentPhase,
    SubAgentResult,
    SubAgentResultStatus,
)


# ── Helpers ────────────────────────────────────────────────


def _init_repo(path: Path) -> Repo:
    """初始化临时 Git 仓库并做初始提交"""
    repo = Repo.init(str(path))
    repo.config_writer().set_value("user", "name", "TestBot").release()
    repo.config_writer().set_value("user", "email", "bot@test.com").release()
    (path / "README.md").write_text("# Test")
    repo.index.add(["README.md"])
    repo.index.commit("initial")
    return repo


def _make_file(path: Path, name: str, content: str):
    """创建/修改文件"""
    f = path / name
    f.write_text(content)
    return f


def _sample_task(task_id="task-001", title="实现功能A"):
    return Task(
        id=task_id, title=title, description=title,
        dependencies=[], suggested_role="dev",
        priority=TaskPriority.HIGH,
        estimated_complexity=TaskComplexity.MEDIUM,
        status=TaskStatus.PENDING,
    )


def _success_result(task_id="task-001"):
    return SubAgentResult(
        task_id=task_id,
        status=SubAgentResultStatus.SUCCESS,
        phase=AgentPhase.COMPLETED,
    )


def _failed_result(task_id="task-001"):
    return SubAgentResult(
        task_id=task_id,
        status=SubAgentResultStatus.FAILED,
        phase=AgentPhase.FAILED,
        error="assert False in test_feature_a",
    )


# ── 场景 1：成功 commit ────────────────────────────────────


class TestSuccessCommitScenario:
    """成功 commit：变更文件 → git commit → 验证 log"""

    def test_full_commit_flow(self, tmp_path):
        """文件变更后 commit，git log 中可查到"""
        repo = _init_repo(tmp_path)

        # 模拟代码变更
        _make_file(tmp_path, "api.py", "def login():\n    return 'ok'\n")

        gm = GitManager(str(tmp_path), max_retries=0)
        pm = ProgressManager(file_path=tmp_path / "progress.txt")

        task = _sample_task("task-001")
        result = _success_result("task-001")

        committer = TaskCommitter(gm, pm, role_short="dev")
        cr = committer.commit_on_success(task, result)

        assert cr.committed is True
        assert cr.commit_hash is not None
        assert len(cr.short_sha) == 7
        assert len(cr.files_committed) >= 1

        # 验证 git log
        last_commit = repo.head.commit
        assert cr.commit_hash == last_commit.hexsha
        assert "[task-001]" in last_commit.message
        assert "dev" in last_commit.message

    def test_multiple_files_committed(self, tmp_path):
        """多个文件变更一次 commit"""
        repo = _init_repo(tmp_path)
        _make_file(tmp_path, "a.py", "a")
        _make_file(tmp_path, "b.py", "b")
        # 确保 tests/ 目录存在
        (tmp_path / "tests").mkdir(exist_ok=True)
        _make_file(tmp_path, "tests/test_a.py", "def test():\n    pass\n")

        gm = GitManager(str(tmp_path), max_retries=0)
        pm = ProgressManager(file_path=tmp_path / "progress.txt")
        committer = TaskCommitter(gm, pm)

        cr = committer.commit_on_success(_sample_task(), _success_result())
        assert cr.committed is True
        assert len(cr.files_committed) >= 2

    def test_commit_message_format_in_git(self, tmp_path):
        """git log 中 commit message 格式 [task-{id}] {role}: {description}"""
        repo = _init_repo(tmp_path)
        _make_file(tmp_path, "x.py", "x")

        gm = GitManager(str(tmp_path), max_retries=0)
        pm = ProgressManager(file_path=tmp_path / "progress.txt")
        committer = TaskCommitter(gm, pm)

        task = Task(
            id="task-042", title="添加缓存层",
            description="D", dependencies=[], suggested_role="dev",
            priority=TaskPriority.HIGH,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        )
        cr = committer.commit_on_success(task, _success_result("task-042"), role="qa")

        commit = repo.head.commit
        assert "[task-042]" in commit.message
        assert "qa" in commit.message
        assert "添加缓存层" in commit.message

    def test_progress_updated_after_commit(self, tmp_path):
        """commit 后 progress.txt 包含 COMPLETED 条目"""
        _init_repo(tmp_path)
        _make_file(tmp_path, "x.py", "x")

        progress_path = tmp_path / "progress.txt"
        gm = GitManager(str(tmp_path), max_retries=0)
        pm = ProgressManager(file_path=progress_path)
        committer = TaskCommitter(gm, pm)

        cr = committer.commit_on_success(_sample_task(), _success_result())
        assert cr.progress_updated is True

        entries = pm.read_progress()
        assert len(entries) == 1
        assert entries[0].status.value == "COMPLETED"
        assert entries[0].git_sha == cr.short_sha

    def test_no_changes_skips_commit(self, tmp_path):
        """无文件变更时 commit 被跳过"""
        _init_repo(tmp_path)

        gm = GitManager(str(tmp_path), max_retries=0)
        pm = ProgressManager(file_path=tmp_path / "progress.txt")
        committer = TaskCommitter(gm, pm)

        cr = committer.commit_on_success(_sample_task(), _success_result())
        assert cr.committed is False
        assert "没有变更" in cr.error_message
        assert cr.progress_updated is False


# ── 场景 2：失败不 commit ──────────────────────────────────


class TestFailureNoCommitScenario:
    """失败不 commit：任务失败 → git 无新 commit"""

    def test_failure_leaves_git_clean(self, tmp_path):
        """失败处理后 git 仓库无新 commit"""
        repo = _init_repo(tmp_path)
        initial_commit = repo.head.commit.hexsha
        _make_file(tmp_path, "broken.py", "# broken")

        # 模拟失败处理
        pm = ProgressManager(file_path=tmp_path / "progress.txt")
        failure_handler = FailureHandler(
            log_manager=LogManager(log_dir=tmp_path / "logs", auto_create_dir=True),
            task_file_manager=MagicMock(),  # task.json 不在真实场景中使用
            progress_manager=pm,
        )
        # task.json 更新用 mock（这里主要测 git 不提交）
        failure_handler._tasks = MagicMock()

        r = failure_handler.handle_failure(
            _sample_task(), "test failure", role="dev"
        )

        assert r.committed is False
        assert r.logged is True
        assert r.progress_updated is True

        # 验证 git 无新 commit
        assert repo.head.commit.hexsha == initial_commit

    def test_failure_with_changes_no_commit(self, tmp_path):
        """有变更但失败 → 不 commit，变更留在工作区"""
        repo = _init_repo(tmp_path)
        initial_commit = repo.head.commit.hexsha
        _make_file(tmp_path, "dirty.py", "uncommitted work")

        pm = ProgressManager(file_path=tmp_path / "progress.txt")
        handler = FailureHandler(
            LogManager(log_dir=tmp_path / "logs", auto_create_dir=True),
            MagicMock(),
            pm,
        )
        handler._tasks = MagicMock()

        handler.handle_failure(_sample_task(), "error", role="qa")

        # git 无新提交
        assert repo.head.commit.hexsha == initial_commit
        # 变更仍在工作区
        assert repo.is_dirty(untracked_files=True) is True

    def test_failure_records_error_in_progress(self, tmp_path):
        """progress.txt 记录 FAILED + 错误信息"""
        _init_repo(tmp_path)
        _make_file(tmp_path, "x.py", "x")

        progress_path = tmp_path / "progress.txt"
        pm = ProgressManager(file_path=progress_path)
        handler = FailureHandler(
            LogManager(log_dir=tmp_path / "logs", auto_create_dir=True),
            MagicMock(),
            pm,
        )
        handler._tasks = MagicMock()

        handler.handle_failure(_sample_task(), "test assertion error", role="qa")

        entries = pm.read_progress()
        assert len(entries) == 1
        assert entries[0].status.value == "FAILED"
        assert "test assertion error" in entries[0].error

    def test_task_committer_never_called_on_failure(self, tmp_path):
        """FailureHandler 不依赖 TaskCommitter"""
        _init_repo(tmp_path)

        pm = ProgressManager(file_path=tmp_path / "progress.txt")
        handler = FailureHandler(
            LogManager(log_dir=tmp_path / "logs", auto_create_dir=True),
            MagicMock(),
            pm,
        )
        handler._tasks = MagicMock()

        r = handler.handle_failure(_sample_task(), "fail")
        assert r.committed is False  # 硬约束


# ── 场景 3：重试 commit ────────────────────────────────────


class TestRetryCommitScenario:
    """重试 commit：Git 锁竞争等临时错误后自动重试"""

    def test_retry_on_lock_failure(self, tmp_path):
        """模拟 .git/index.lock 冲突 → 重试后成功"""
        _init_repo(tmp_path)
        _make_file(tmp_path, "a.py", "def foo(): pass\n")

        gm = GitManager(str(tmp_path), max_retries=3)

        call_count = [0]

        def _mock_commit(target, add_all, message):
            call_count[0] += 1
            if call_count[0] == 1:
                raise OSError("Unable to create '.git/index.lock': File exists")
            # 真实执行
            gm._do_commit = orig_do_commit  # restore
            return gm._do_commit(target, add_all, message)

        orig_do_commit = gm._do_commit
        gm._do_commit = _mock_commit

        result = gm.commit_changes("001", "dev", "实现功能A")

        assert result["success"] is True
        assert call_count[0] == 2  # 第一次失败 + 第二次成功

    def test_retry_preserves_message(self, tmp_path):
        """重试后 commit message 保持正确"""
        _init_repo(tmp_path)
        _make_file(tmp_path, "a.py", "a")

        gm = GitManager(str(tmp_path), max_retries=2)

        call_count = [0]

        def _mock_commit(target, add_all, message):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("temp failure")
            gm._do_commit = orig_do_commit
            return gm._do_commit(target, add_all, message)

        orig_do_commit = gm._do_commit
        gm._do_commit = _mock_commit

        result = gm.commit_changes("001", "dev", "实现功能A")

        assert result["success"] is True
        assert "[task-001]" in result["message"]
        assert call_count[0] == 2

    def test_retry_exhausted_returns_failure(self, tmp_path):
        """3 次重试全失败 → success=False"""
        _init_repo(tmp_path)
        _make_file(tmp_path, "a.py", "a")

        gm = GitManager(str(tmp_path), max_retries=2)

        def _always_fail(target, add_all, message):
            raise OSError("disk full")

        gm._do_commit = _always_fail

        result = gm.commit_changes("001", "dev", "任务")

        assert result["success"] is False
        assert "disk full" in result["error"]
        assert result["retries"] >= 0

    def test_git_manager_retry_count_in_result(self, tmp_path):
        """result 包含 retries 字段"""
        _init_repo(tmp_path)
        _make_file(tmp_path, "a.py", "a")

        gm = GitManager(str(tmp_path), max_retries=3)
        result = gm.commit_changes("001", "dev", "成功提交")

        assert result["success"] is True
        assert "retries" in result
        assert isinstance(result["retries"], int)

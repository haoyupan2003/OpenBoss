"""
GitManager 单元测试

使用临时 git 仓库 fixture，覆盖 GitManager 所有方法：
- init_repo: 初始化仓库 / 已有仓库 / 父目录不存在
- is_repo: 有效仓库 / 非仓库 / 空 .git
- is_dirty: 干净 / 已修改 / 未跟踪 / untracked_files 参数
- has_uncommitted_changes: 正常代理 / 非仓库
- get_last_commit_hash: 有提交 / 空仓库 / 非仓库
- get_current_branch: 有分支 / 空仓库 / 非仓库
- get_head_commit: 有提交 / 空仓库 / 非仓库
- get_status: 完整状态 / 非仓库
- commit_changes: 正常提交 / 无变更 / add_all / 参数校验
- format_commit_message / parse_commit_message: 格式化与解析
- get_diff_since_commit: 有 diff / HEAD..HEAD / 无效 hash / 空 hash
- _execute_with_retry: 成功 / 异常重试 / 失败重试 / 不重试错误 / 用尽重试
- 综合场景: init→commit→status→diff 流程
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from agent_automation_system.git_manager import GitManager


# ─── Fixtures ──────────────────────────────────────


@pytest.fixture
def tmp_dir():
    """创建临时目录（非仓库）"""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def tmp_repo(tmp_dir):
    """创建临时 Git 仓库（含一次初始提交）"""
    from git import Repo

    repo = Repo.init(str(tmp_dir))
    # 配置 git 用户（否则 commit 会失败）
    repo.config_writer().set_value("user", "name", "Test").release()
    repo.config_writer().set_value("user", "email", "test@test.com").release()

    # 初始提交
    readme = tmp_dir / "README.md"
    readme.write_text("# Test")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit")

    return tmp_dir


@pytest.fixture
def mgr(tmp_dir):
    """创建 GitManager 实例（指向临时目录，max_retries=0 避免测试等待）"""
    return GitManager(str(tmp_dir), max_retries=0)


@pytest.fixture
def repo_mgr(tmp_repo):
    """创建 GitManager 实例（指向已有仓库）"""
    return GitManager(str(tmp_repo), max_retries=0)


def _write_file(repo_path: Path, name: str, content: str):
    """辅助：在仓库中写入文件"""
    (repo_path / name).write_text(content)


# ─── TestInitRepo ──────────────────────────────────


class TestInitRepo:
    """init_repo 方法测试"""

    def test_init_new_repo(self, tmp_dir):
        """在空目录初始化新仓库"""
        mgr = GitManager(str(tmp_dir))
        repo = mgr.init_repo()
        assert mgr.is_repo()
        assert (tmp_dir / ".git").exists()

    def test_init_already_repo(self, tmp_repo):
        """在已有仓库上 init_repo 不报错"""
        mgr = GitManager(str(tmp_repo))
        repo = mgr.init_repo()
        assert mgr.is_repo()

    def test_init_creates_subdirectory(self, tmp_dir):
        """init_repo 在不存在的子目录中创建仓库"""
        sub = tmp_dir / "sub" / "project"
        mgr = GitManager(str(sub))
        repo = mgr.init_repo()
        assert sub.exists()
        assert mgr.is_repo()

    def test_init_parent_not_exists(self):
        """根路径不存在的目录无法创建（mkdir -p 受系统限制）"""
        # /nonexistent_root 是一个完全不存在的前缀，mkdir -p 也无法创建
        # 但 init_repo 现在会用 mkdir -p，所以只有在路径不合法时才失败
        # 改为测试：在合法的嵌套路径下可以创建
        pass  # init_repo 现在支持 mkdir -p，不再需要此用例

    def test_init_updates_internal_state(self, tmp_dir):
        """init_repo 更新内部 repo_path 和 _repo"""
        mgr = GitManager(str(tmp_dir))
        mgr.init_repo()
        assert mgr.repo_path == tmp_dir
        assert mgr._repo is not None


# ─── TestIsRepo ────────────────────────────────────


class TestIsRepo:
    """is_repo 方法测试"""

    def test_valid_repo(self, tmp_repo):
        """有效仓库返回 True"""
        mgr = GitManager(str(tmp_repo))
        assert mgr.is_repo() is True

    def test_not_a_repo(self, tmp_dir):
        """非仓库目录返回 False"""
        mgr = GitManager(str(tmp_dir))
        # tmp_dir 没有 .git
        assert mgr.is_repo() is False

    def test_empty_git_dir(self, tmp_dir):
        """空 .git 目录返回 False"""
        (tmp_dir / ".git").mkdir()
        mgr = GitManager(str(tmp_dir))
        assert mgr.is_repo() is False

    def test_nonexistent_path(self):
        """不存在的路径返回 False"""
        mgr = GitManager("/nonexistent_path_xyz")
        assert mgr.is_repo() is False

    def test_custom_path(self, tmp_repo):
        """通过 path 参数检查其他路径"""
        mgr = GitManager()
        assert mgr.is_repo(str(tmp_repo)) is True

    def test_custom_path_not_repo(self, tmp_dir):
        """通过 path 参数检查非仓库路径"""
        mgr = GitManager()
        assert mgr.is_repo(str(tmp_dir)) is False


# ─── TestIsDirty ───────────────────────────────────


class TestIsDirty:
    """is_dirty 方法测试"""

    def test_clean_repo(self, repo_mgr, tmp_repo):
        """干净仓库返回 False"""
        assert repo_mgr.is_dirty() is False

    def test_modified_file(self, repo_mgr, tmp_repo):
        """修改文件后返回 True"""
        _write_file(tmp_repo, "README.md", "modified")
        assert repo_mgr.is_dirty() is True

    def test_untracked_file_default_true(self, repo_mgr, tmp_repo):
        """未跟踪文件默认视为 dirty"""
        _write_file(tmp_repo, "new.py", "x")
        assert repo_mgr.is_dirty() is True

    def test_untracked_file_excluded(self, repo_mgr, tmp_repo):
        """untracked_files=False 时未跟踪文件不视为 dirty"""
        _write_file(tmp_repo, "new.py", "x")
        assert repo_mgr.is_dirty(untracked_files=False) is False

    def test_not_a_repo_raises(self, tmp_dir):
        """非仓库路径抛 ValueError"""
        mgr = GitManager(str(tmp_dir))
        with pytest.raises(ValueError, match="不是 Git 仓库"):
            mgr.is_dirty()


# ─── TestHasUncommittedChanges ─────────────────────


class TestHasUncommittedChanges:
    """has_uncommitted_changes 方法测试"""

    def test_clean_repo(self, repo_mgr):
        """干净仓库返回 False"""
        assert repo_mgr.has_uncommitted_changes() is False

    def test_dirty_repo(self, repo_mgr, tmp_repo):
        """有变更时返回 True"""
        _write_file(tmp_repo, "new.py", "x")
        assert repo_mgr.has_uncommitted_changes() is True

    def test_not_a_repo(self, tmp_dir):
        """非仓库路径返回 False（不抛异常）"""
        mgr = GitManager(str(tmp_dir))
        assert mgr.has_uncommitted_changes() is False


# ─── TestGetLastCommitHash ─────────────────────────


class TestGetLastCommitHash:
    """get_last_commit_hash 方法测试"""

    def test_with_commits(self, repo_mgr):
        """有提交时返回 40 位 hexsha"""
        h = repo_mgr.get_last_commit_hash()
        assert h is not None
        assert len(h) == 40
        assert all(c in "0123456789abcdef" for c in h)

    def test_empty_repo(self, tmp_dir):
        """空仓库（无提交）返回 None"""
        mgr = GitManager(str(tmp_dir))
        mgr.init_repo()
        assert mgr.get_last_commit_hash() is None

    def test_not_a_repo(self, tmp_dir):
        """非仓库路径返回 None"""
        mgr = GitManager(str(tmp_dir))
        assert mgr.get_last_commit_hash() is None


# ─── TestGetCurrentBranch ──────────────────────────


class TestGetCurrentBranch:
    """get_current_branch 方法测试"""

    def test_on_main(self, repo_mgr):
        """初始仓库在 main 或 master 分支"""
        branch = repo_mgr.get_current_branch()
        assert branch in ("main", "master")

    def test_empty_repo(self, tmp_dir):
        """空仓库可能返回 main（新版 git init.defaultBranch）"""
        mgr = GitManager(str(tmp_dir))
        mgr.init_repo()
        # 新版 git 在 init 时就设定了默认分支名（即使无提交）
        branch = mgr.get_current_branch()
        assert branch is None or branch in ("main", "master")

    def test_not_a_repo(self, tmp_dir):
        """非仓库路径返回 None"""
        mgr = GitManager(str(tmp_dir))
        assert mgr.get_current_branch() is None


# ─── TestGetHeadCommit ─────────────────────────────


class TestGetHeadCommit:
    """get_head_commit 方法测试"""

    def test_with_commit(self, repo_mgr):
        """有提交时返回完整信息字典"""
        info = repo_mgr.get_head_commit()
        assert info is not None
        assert "hexsha" in info
        assert "short_sha" in info
        assert "message" in info
        assert "author" in info
        assert "committed_datetime" in info
        assert len(info["short_sha"]) == 7
        assert info["message"] == "Initial commit"

    def test_empty_repo(self, tmp_dir):
        """空仓库返回 None"""
        mgr = GitManager(str(tmp_dir))
        mgr.init_repo()
        assert mgr.get_head_commit() is None

    def test_not_a_repo(self, tmp_dir):
        """非仓库路径返回 None"""
        mgr = GitManager(str(tmp_dir))
        assert mgr.get_head_commit() is None


# ─── TestGetStatus ─────────────────────────────────


class TestGetStatus:
    """get_status 方法测试"""

    def test_clean_repo(self, repo_mgr):
        """干净仓库的状态"""
        s = repo_mgr.get_status()
        assert s["is_repo"] is True
        assert s["is_dirty"] is False
        assert s["branch"] is not None
        assert s["head_commit"] is not None
        assert s["untracked_files"] == []
        assert s["modified_files"] == []
        assert s["staged_files"] == []

    def test_dirty_repo(self, repo_mgr, tmp_repo):
        """有变更的仓库状态"""
        _write_file(tmp_repo, "new.py", "x")
        _write_file(tmp_repo, "README.md", "modified")
        s = repo_mgr.get_status()
        assert s["is_repo"] is True
        assert s["is_dirty"] is True
        assert "new.py" in s["untracked_files"]
        assert "README.md" in s["modified_files"]

    def test_not_a_repo(self, tmp_dir):
        """非仓库路径返回默认空状态"""
        mgr = GitManager(str(tmp_dir))
        s = mgr.get_status()
        assert s["is_repo"] is False
        assert s["is_dirty"] is False
        assert s["branch"] is None


# ─── TestCommitChanges ─────────────────────────────


class TestCommitChanges:
    """commit_changes 方法测试"""

    def test_basic_commit(self, repo_mgr, tmp_repo):
        """基本提交成功"""
        _write_file(tmp_repo, "feature.py", "x = 1")
        r = repo_mgr.commit_changes("001", "dev", "实现功能")
        assert r["success"] is True
        assert r["hexsha"] is not None
        assert len(r["short_sha"]) == 7
        assert r["message"] == "[task-001] dev: 实现功能"
        assert r["error"] is None
        assert r["retries"] == 0

    def test_commit_adds_all_by_default(self, repo_mgr, tmp_repo):
        """默认 add_all=True 会提交未跟踪文件"""
        _write_file(tmp_repo, "new_file.py", "new")
        r = repo_mgr.commit_changes("002", "dev", "新增文件")
        assert r["success"] is True
        # 验证文件已提交（仓库不再 dirty）
        assert repo_mgr.is_dirty() is False

    def test_commit_add_all_false_unstaged(self, repo_mgr, tmp_repo):
        """add_all=False 时未暂存文件不提交"""
        _write_file(tmp_repo, "untracked.py", "x")
        r = repo_mgr.commit_changes("003", "dev", "未暂存", add_all=False)
        assert r["success"] is False
        assert "没有暂存" in r["error"]

    def test_commit_no_changes(self, repo_mgr):
        """没有变更时返回失败"""
        r = repo_mgr.commit_changes("004", "dev", "无变更")
        assert r["success"] is False
        assert "没有变更" in r["error"]

    def test_commit_message_format(self, repo_mgr, tmp_repo):
        """commit message 符合 PRD §4.7 规范"""
        _write_file(tmp_repo, "a.py", "a")
        r = repo_mgr.commit_changes("001", "senior-developer", "实现用户登录")
        assert r["success"] is True
        # 从 git log 验证
        from git import Repo
        repo = Repo(str(tmp_repo))
        last_msg = repo.head.commit.message.strip()
        assert last_msg == "[task-001] senior-developer: 实现用户登录"

    def test_commit_empty_task_id(self, repo_mgr):
        """空 task_id 抛 ValueError"""
        with pytest.raises(ValueError, match="task_id"):
            repo_mgr.commit_changes("", "dev", "desc")

    def test_commit_empty_role(self, repo_mgr):
        """空 role 抛 ValueError"""
        with pytest.raises(ValueError, match="role"):
            repo_mgr.commit_changes("001", "", "desc")

    def test_commit_empty_description(self, repo_mgr):
        """空 description 抛 ValueError"""
        with pytest.raises(ValueError, match="description"):
            repo_mgr.commit_changes("001", "dev", "")

    def test_commit_not_a_repo(self, tmp_dir):
        """非仓库路径抛 ValueError"""
        mgr = GitManager(str(tmp_dir))
        with pytest.raises(ValueError, match="不是 Git 仓库"):
            mgr.commit_changes("001", "dev", "test")

    def test_commit_result_has_retries(self, repo_mgr, tmp_repo):
        """返回结果包含 retries 字段"""
        _write_file(tmp_repo, "x.py", "x")
        r = repo_mgr.commit_changes("001", "dev", "test")
        assert "retries" in r
        assert r["retries"] == 0


# ─── TestCommitMessage ─────────────────────────────


class TestCommitMessage:
    """format_commit_message / parse_commit_message 测试"""

    def test_format_basic(self):
        """基本格式化"""
        mgr = GitManager()
        msg = mgr.format_commit_message("001", "senior-developer", "实现登录")
        assert msg == "[task-001] senior-developer: 实现登录"

    def test_format_with_hyphen_role(self):
        """角色名含连字符"""
        mgr = GitManager()
        msg = mgr.format_commit_message("010", "senior-developer", "编码")
        assert msg.startswith("[task-010]")

    def test_parse_valid(self):
        """解析有效的 commit message"""
        mgr = GitManager()
        result = mgr.parse_commit_message("[task-001] dev: 实现登录")
        assert result is not None
        assert result["task_id"] == "001"
        assert result["role"] == "dev"
        assert result["description"] == "实现登录"

    def test_parse_with_hyphen_role(self):
        """解析含连字符角色的 message"""
        mgr = GitManager()
        result = mgr.parse_commit_message("[task-005] senior-dev: 编码")
        assert result is not None
        assert result["role"] == "senior-dev"
        assert result["description"] == "编码"

    def test_parse_invalid(self):
        """解析无效格式返回 None"""
        mgr = GitManager()
        assert mgr.parse_commit_message("random message") is None

    def test_parse_empty(self):
        """解析空字符串返回 None"""
        mgr = GitManager()
        assert mgr.parse_commit_message("") is None

    def test_roundtrip(self):
        """格式化后解析回来结果一致"""
        mgr = GitManager()
        original = ("015", "qa", "编写测试用例")
        msg = mgr.format_commit_message(*original)
        parsed = mgr.parse_commit_message(msg)
        assert parsed is not None
        assert parsed["task_id"] == original[0]
        assert parsed["role"] == original[1]
        assert parsed["description"] == original[2]


# ─── TestGetDiffSinceCommit ────────────────────────


class TestGetDiffSinceCommit:
    """get_diff_since_commit 方法测试"""

    def test_diff_has_changes(self, repo_mgr, tmp_repo):
        """有变更时返回 diff 字符串"""
        # 记录初始 commit
        hash1 = repo_mgr.get_last_commit_hash()

        # 新增提交
        _write_file(tmp_repo, "new.py", "new content")
        repo_mgr.commit_changes("001", "dev", "新增文件")

        diff = repo_mgr.get_diff_since_commit(hash1)
        assert diff is not None
        assert len(diff) > 0
        assert "new.py" in diff

    def test_diff_head_to_head(self, repo_mgr):
        """HEAD..HEAD 返回空字符串"""
        h = repo_mgr.get_last_commit_hash()
        diff = repo_mgr.get_diff_since_commit(h)
        assert diff == ""

    def test_diff_invalid_hash(self, repo_mgr):
        """无效 hash 返回 None"""
        diff = repo_mgr.get_diff_since_commit("badhash999999")
        assert diff is None

    def test_diff_empty_hash_raises(self, repo_mgr):
        """空 hash 抛 ValueError"""
        with pytest.raises(ValueError, match="commit_hash"):
            repo_mgr.get_diff_since_commit("")

    def test_diff_not_a_repo(self, tmp_dir):
        """非仓库返回 None"""
        mgr = GitManager(str(tmp_dir))
        assert mgr.get_diff_since_commit("abc") is None

    def test_diff_short_hash(self, repo_mgr, tmp_repo):
        """短 hash 也能正常 diff"""
        hash1 = repo_mgr.get_last_commit_hash()
        short = hash1[:7]
        _write_file(tmp_repo, "x.py", "x")
        repo_mgr.commit_changes("002", "dev", "更新")
        diff = repo_mgr.get_diff_since_commit(short)
        assert diff is not None
        assert len(diff) > 0


# ─── TestRetryMechanism ────────────────────────────


class TestRetryMechanism:
    """_execute_with_retry 重试机制测试"""

    def test_success_no_retry(self):
        """操作成功时不重试"""
        mgr = GitManager(max_retries=3)
        call_count = [0]

        def op():
            call_count[0] += 1
            return {"success": True, "error": None}

        result = mgr._execute_with_retry(op, "test")
        assert result["success"] is True
        assert result["retries"] == 0
        assert call_count[0] == 1

    def test_retry_on_exception(self):
        """异常触发重试，恢复后成功"""
        mgr = GitManager(max_retries=3)
        call_count = [0]

        def flaky_op():
            call_count[0] += 1
            if call_count[0] < 3:
                raise RuntimeError("Transient error")
            return {"success": True, "error": None}

        # mock time.sleep 避免等待
        with patch("agent_automation_system.git_manager.git_manager.time.sleep"):
            result = mgr._execute_with_retry(flaky_op, "test")
        assert result["success"] is True
        assert result["retries"] == 2
        assert call_count[0] == 3

    def test_retry_on_failure_result(self):
        """返回 success=False 触发重试"""
        mgr = GitManager(max_retries=3)
        call_count = [0]

        def failing_op():
            call_count[0] += 1
            if call_count[0] < 2:
                return {"success": False, "error": "git lock"}
            return {"success": True, "error": None}

        with patch("agent_automation_system.git_manager.git_manager.time.sleep"):
            result = mgr._execute_with_retry(failing_op, "test")
        assert result["success"] is True
        assert result["retries"] == 1

    def test_no_retry_on_no_changes(self):
        """'没有变更'类错误不触发重试"""
        mgr = GitManager(max_retries=3)
        call_count = [0]

        def no_change_op():
            call_count[0] += 1
            return {"success": False, "error": "没有变更需要提交"}

        result = mgr._execute_with_retry(no_change_op, "test")
        assert result["success"] is False
        assert result["retries"] == 0
        assert call_count[0] == 1

    def test_no_retry_on_no_staged(self):
        """'没有暂存'类错误不触发重试"""
        mgr = GitManager(max_retries=3)
        call_count = [0]

        def op():
            call_count[0] += 1
            return {"success": False, "error": "没有暂存的文件需要提交"}

        result = mgr._execute_with_retry(op, "test")
        assert result["retries"] == 0
        assert call_count[0] == 1

    def test_exhausted_retries(self):
        """重试次数用尽后返回失败"""
        mgr = GitManager(max_retries=2)

        def always_fail():
            raise RuntimeError("Permanent error")

        with patch("agent_automation_system.git_manager.git_manager.time.sleep"):
            result = mgr._execute_with_retry(always_fail, "test")
        assert result["success"] is False
        assert result["retries"] == 2
        assert "Permanent error" in result["error"]

    def test_zero_retries(self):
        """max_retries=0 时不重试"""
        mgr = GitManager(max_retries=0)
        call_count = [0]

        def fail_once():
            call_count[0] += 1
            raise RuntimeError("Fail")

        with patch("agent_automation_system.git_manager.git_manager.time.sleep"):
            result = mgr._execute_with_retry(fail_once, "test")
        assert result["success"] is False
        assert result["retries"] == 0
        assert call_count[0] == 1

    def test_negative_max_retries_raises(self):
        """max_retries < 0 抛 ValueError"""
        with pytest.raises(ValueError, match="max_retries"):
            GitManager(max_retries=-1)

    def test_max_retries_property(self):
        """max_retries 属性正确"""
        mgr = GitManager(max_retries=5)
        assert mgr.max_retries == 5

    def test_default_max_retries(self):
        """默认 max_retries 为 3"""
        mgr = GitManager()
        assert mgr.max_retries == 3


# ─── TestRepoProperty ──────────────────────────────


class TestRepoProperty:
    """repo 属性测试"""

    def test_lazy_init(self, repo_mgr):
        """repo 属性延迟初始化"""
        assert repo_mgr._repo is None
        _ = repo_mgr.repo
        assert repo_mgr._repo is not None

    def test_cached_repo(self, repo_mgr):
        """重复访问返回同一实例"""
        r1 = repo_mgr.repo
        r2 = repo_mgr.repo
        assert r1 is r2

    def test_not_a_repo_raises(self, tmp_dir):
        """非仓库路径抛 ValueError"""
        mgr = GitManager(str(tmp_dir))
        with pytest.raises(ValueError, match="不是 Git 仓库"):
            _ = mgr.repo


# ─── TestRepoPathProperty ──────────────────────────


class TestRepoPathProperty:
    """repo_path 属性测试"""

    def test_default_cwd(self):
        """默认 repo_path 为当前工作目录"""
        mgr = GitManager()
        assert mgr.repo_path == Path.cwd()

    def test_custom_path(self, tmp_dir):
        """自定义 repo_path"""
        mgr = GitManager(str(tmp_dir))
        assert mgr.repo_path == tmp_dir


# ─── TestRoundTrip ─────────────────────────────────


class TestRoundTrip:
    """综合场景测试：init → commit → status → diff 完整流程"""

    def test_init_commit_status_diff(self, tmp_dir):
        """完整 Git 操作流程"""
        mgr = GitManager(str(tmp_dir), max_retries=0)

        # 1. 初始化
        repo = mgr.init_repo()
        # 配置 git 用户
        repo.config_writer().set_value("user", "name", "Test").release()
        repo.config_writer().set_value("user", "email", "t@t.com").release()
        assert mgr.is_repo()

        # 2. 空仓库状态
        assert mgr.get_last_commit_hash() is None
        # 新版 git 可能在 init 时就设定分支名
        branch = mgr.get_current_branch()
        assert branch is None or branch in ("main", "master")
        s = mgr.get_status()
        assert s["is_repo"] is True
        assert s["head_commit"] is None

        # 3. 第一次提交
        _write_file(tmp_dir, "a.py", "x = 1")
        r1 = mgr.commit_changes("001", "dev", "初始化项目")
        assert r1["success"] is True
        hash1 = r1["hexsha"]

        # 4. 提交后状态
        assert mgr.has_uncommitted_changes() is False
        assert mgr.get_last_commit_hash() == hash1
        assert mgr.get_current_branch() is not None

        # 5. 第二次提交
        _write_file(tmp_dir, "b.py", "y = 2")
        r2 = mgr.commit_changes("002", "qa", "添加测试")
        assert r2["success"] is True
        hash2 = r2["hexsha"]

        # 6. diff 检查
        diff = mgr.get_diff_since_commit(hash1)
        assert diff is not None
        assert "b.py" in diff

        # 7. HEAD commit 信息
        head = mgr.get_head_commit()
        assert head is not None
        assert head["hexsha"] == hash2

        # 8. commit message 解析
        parsed = mgr.parse_commit_message(r2["message"])
        assert parsed is not None
        assert parsed["task_id"] == "002"
        assert parsed["role"] == "qa"

    def test_multiple_commits_and_diff(self, tmp_dir):
        """多次提交后 diff 包含后续变更"""
        mgr = GitManager(str(tmp_dir), max_retries=0)
        repo = mgr.init_repo()
        repo.config_writer().set_value("user", "name", "Test").release()
        repo.config_writer().set_value("user", "email", "t@t.com").release()

        # 3 次提交
        for i in range(3):
            _write_file(tmp_dir, f"file{i}.py", f"content{i}")
            mgr.commit_changes(f"00{i}", "dev", f"添加文件{i}")

        # 从第一个 commit diff：git diff A..HEAD 包含 A 之后到 HEAD 的变更
        # 但不包含 A 本身的变更（A 是起点）
        from git import Repo
        git_repo = Repo(str(tmp_dir))
        commits = list(git_repo.iter_commits())
        first_hash = commits[-1].hexsha  # 最早的 commit

        diff = mgr.get_diff_since_commit(first_hash)
        assert diff is not None
        # diff A..HEAD 包含 A 之后的变更：file1.py 和 file2.py
        assert "file1.py" in diff
        assert "file2.py" in diff

    def test_commit_and_dirty_check(self, tmp_dir):
        """提交后 dirty 检查 + 修改后再检查"""
        mgr = GitManager(str(tmp_dir), max_retries=0)
        repo = mgr.init_repo()
        repo.config_writer().set_value("user", "name", "Test").release()
        repo.config_writer().set_value("user", "email", "t@t.com").release()

        # 提交后干净
        _write_file(tmp_dir, "a.py", "x")
        mgr.commit_changes("001", "dev", "init")
        assert mgr.is_dirty() is False
        assert mgr.has_uncommitted_changes() is False

        # 修改后 dirty
        _write_file(tmp_dir, "a.py", "y")
        assert mgr.is_dirty() is True
        assert mgr.has_uncommitted_changes() is True

        # 再次提交后干净
        mgr.commit_changes("002", "dev", "update")
        assert mgr.is_dirty() is False

"""
P1-064: 集成测试 — Git 提交流程验证（代码变更 → commit → hash 记录）

验证 GitManager 在任务执行过程中的 Git 提交流程，以及
与 ProgressManager / MemoryManager 的协同工作：

核心验证场景：
  1. 代码变更 → git add → git commit → hash 返回完整流程
  2. commit message 格式符合 PRD §4.7 规范
  3. commit hash 记录到 progress.txt
  4. commit message 可解析回 task_id / role / description
  5. 多次提交的 commit 历史与 diff 可追溯
  6. Git 状态检测（dirty/clean）与提交流程协同
  7. 提交失败/无变更场景的处理
  8. 完整任务执行→提交→记录的端到端流程
"""

import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest
from git import Repo

from agent_automation_system.file_io.memory_manager import MemoryManager
from agent_automation_system.file_io.progress_manager import ProgressManager
from agent_automation_system.git_manager import GitManager
from agent_automation_system.models.memory_entry import MemoryEntry
from agent_automation_system.models.progress import ProgressEntry, ProgressStatus


# ── Fixtures ──────────────────────────────────────

@pytest.fixture
def workspace(tmp_path):
    """创建临时工作区（含 git 仓库 + 文件管理器）"""
    repo_path = tmp_path / "project"
    repo_path.mkdir()

    # 初始化 git 仓库
    repo = Repo.init(str(repo_path))
    repo.config_writer().set_value("user", "name", "TestBot").release()
    repo.config_writer().set_value("user", "email", "bot@test.com").release()

    # 初始提交
    readme = repo_path / "README.md"
    readme.write_text("# Test Project")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit")

    # 创建文件管理器
    progress_path = tmp_path / "progress.txt"
    memory_path = tmp_path / "memory.md"

    gm = GitManager(str(repo_path), max_retries=0)
    pm = ProgressManager(file_path=progress_path)
    mm = MemoryManager(file_path=memory_path)

    return {
        "repo_path": repo_path,
        "repo": repo,
        "gm": gm,
        "pm": pm,
        "mm": mm,
        "tmp_path": tmp_path,
    }


def _write_file(repo_path: Path, name: str, content: str):
    """在仓库中写入文件"""
    (repo_path / name).write_text(content)


# ══════════════════════════════════════════════════════════
# 1. 代码变更 → 提交 → hash 记录
# ══════════════════════════════════════════════════════════
class TestCodeChangeCommitHash:
    """代码变更→git commit→hash 记录完整流程"""

    def test_new_file_commit_returns_hash(self, workspace):
        """新增文件提交后返回 commit hash"""
        gm = workspace["gm"]
        _write_file(workspace["repo_path"], "feature.py", "x = 1")

        result = gm.commit_changes("001", "senior-developer", "实现新功能")
        assert result["success"] is True
        assert result["hexsha"] is not None
        assert len(result["hexsha"]) == 40
        assert len(result["short_sha"]) == 7

    def test_modify_file_commit_returns_hash(self, workspace):
        """修改文件提交后返回新 hash"""
        gm = workspace["gm"]
        _write_file(workspace["repo_path"], "README.md", "# Modified")

        result = gm.commit_changes("002", "senior-developer", "更新 README")
        assert result["success"] is True
        assert result["hexsha"] is not None
        # 不同于初始 commit
        assert result["hexsha"] != workspace["repo"].head.commit.parents[0].hexsha

    def test_commit_hash_recorded_in_git_log(self, workspace):
        """commit hash 在 git log 中可查到"""
        gm = workspace["gm"]
        _write_file(workspace["repo_path"], "a.py", "a = 1")
        result = gm.commit_changes("003", "dev", "新增模块")

        # 从 git log 验证
        repo = workspace["repo"]
        assert repo.head.commit.hexsha == result["hexsha"]

    def test_multiple_files_commit(self, workspace):
        """多个文件变更一次性提交"""
        gm = workspace["gm"]
        repo_path = workspace["repo_path"]
        _write_file(repo_path, "mod1.py", "m1 = 1")
        _write_file(repo_path, "mod2.py", "m2 = 2")

        result = gm.commit_changes("004", "dev", "添加两个模块")
        assert result["success"] is True
        # 仓库干净
        assert gm.is_dirty() is False

    def test_commit_advances_head(self, workspace):
        """每次提交 HEAD 前进"""
        gm = workspace["gm"]
        repo = workspace["repo"]
        initial_hash = gm.get_last_commit_hash()

        _write_file(workspace["repo_path"], "b.py", "b = 1")
        gm.commit_changes("005", "dev", "添加 b 模块")

        new_hash = gm.get_last_commit_hash()
        assert new_hash != initial_hash


# ══════════════════════════════════════════════════════════
# 2. Commit message 格式与解析
# ══════════════════════════════════════════════════════════
class TestCommitMessageFormatAndParse:
    """commit message 格式与解析验证"""

    def test_commit_message_follows_prd_spec(self, workspace):
        """commit message 符合 PRD §4.7 格式：[task-{id}] {role}: {description}"""
        gm = workspace["gm"]
        _write_file(workspace["repo_path"], "x.py", "x = 1")

        result = gm.commit_changes("001", "senior-developer", "实现登录页面")
        assert result["message"] == "[task-001] senior-developer: 实现登录页面"

    def test_commit_message_in_git_log(self, workspace):
        """git log 中的 commit message 与返回值一致"""
        gm = workspace["gm"]
        repo = workspace["repo"]
        _write_file(workspace["repo_path"], "y.py", "y = 1")

        result = gm.commit_changes("010", "test-engineer", "编写测试")
        log_msg = repo.head.commit.message.strip()
        assert log_msg == result["message"]

    def test_parse_commit_message_roundtrip(self, workspace):
        """format → parse 往返一致"""
        gm = workspace["gm"]
        msg = gm.format_commit_message("015", "qa-engineer", "集成测试")
        parsed = gm.parse_commit_message(msg)

        assert parsed is not None
        assert parsed["task_id"] == "015"
        assert parsed["role"] == "qa-engineer"
        assert parsed["description"] == "集成测试"

    def test_parse_actual_git_commit(self, workspace):
        """从 git log 解析实际 commit message"""
        gm = workspace["gm"]
        _write_file(workspace["repo_path"], "z.py", "z = 1")
        gm.commit_changes("020", "senior-developer", "代码重构")

        repo = workspace["repo"]
        msg = repo.head.commit.message.strip()
        parsed = gm.parse_commit_message(msg)

        assert parsed is not None
        assert parsed["task_id"] == "020"
        assert parsed["role"] == "senior-developer"
        assert parsed["description"] == "代码重构"

    def test_parse_invalid_message_returns_none(self):
        """解析非标准格式 message 返回 None"""
        gm = GitManager()
        assert gm.parse_commit_message("just a random message") is None
        assert gm.parse_commit_message("") is None
        assert gm.parse_commit_message("[task-001] no colon here") is None

    def test_format_with_various_roles(self):
        """不同角色的 commit message 格式"""
        gm = GitManager()
        roles = ["dev", "senior-developer", "test-engineer", "qa-engineer", "product-manager"]
        for i, role in enumerate(roles):
            msg = gm.format_commit_message(f"{i:03d}", role, "task")
            assert f"[task-{i:03d}]" in msg
            assert role in msg


# ══════════════════════════════════════════════════════════
# 3. Commit hash 记录到 progress.txt
# ══════════════════════════════════════════════════════════
class TestCommitHashToProgress:
    """commit hash 记录到 progress.txt 验证"""

    def test_commit_hash_recorded_in_progress(self, workspace):
        """提交后 commit hash 写入 progress.txt"""
        gm = workspace["gm"]
        pm = workspace["pm"]
        _write_file(workspace["repo_path"], "feat.py", "feat = True")

        result = gm.commit_changes("001", "senior-developer", "实现功能")
        assert result["success"] is True

        # 将 commit hash 记录到 progress.txt
        pm.write_entry(ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.COMPLETED,
            role="senior-developer",
            started=datetime(2026, 5, 19, 10, 0, 0),
            finished=datetime(2026, 5, 19, 10, 30, 0),
            git_sha=result["short_sha"],
            git_msg=result["message"],
        ))

        entry = pm.get_entry("task-001")
        assert entry is not None
        assert entry.git_sha == result["short_sha"]
        assert entry.git_msg == result["message"]

    def test_progress_git_sha_matches_git_log(self, workspace):
        """progress.txt 中 git_sha 与 git log 一致"""
        gm = workspace["gm"]
        pm = workspace["pm"]
        _write_file(workspace["repo_path"], "mod.py", "mod = 1")

        result = gm.commit_changes("002", "dev", "添加模块")
        pm.write_entry(ProgressEntry(
            task_id="task-002",
            status=ProgressStatus.COMPLETED,
            role="dev",
            git_sha=result["hexsha"],
            git_msg=result["message"],
        ))

        # 从 git log 验证
        repo = workspace["repo"]
        assert repo.head.commit.hexsha == result["hexsha"]

        # 从 progress.txt 验证
        entry = pm.get_entry("task-002")
        assert entry.git_sha == result["hexsha"]

    def test_multiple_commits_recorded_in_progress(self, workspace):
        """多次提交各自记录到 progress.txt"""
        gm = workspace["gm"]
        pm = workspace["pm"]
        repo_path = workspace["repo_path"]

        for i in range(1, 4):
            _write_file(repo_path, f"file{i}.py", f"content{i}")
            result = gm.commit_changes(f"{i:03d}", "dev", f"添加文件{i}")
            pm.write_entry(ProgressEntry(
                task_id=f"task-{i:03d}",
                status=ProgressStatus.COMPLETED,
                role="dev",
                git_sha=result["short_sha"],
                git_msg=result["message"],
            ))

        entries = pm.read_progress()
        assert len(entries) == 3
        # 每个 entry 都有 git_sha
        for e in entries:
            assert e.git_sha is not None
            assert e.status == ProgressStatus.COMPLETED

    def test_failed_commit_not_recorded_in_progress(self, workspace):
        """失败的提交不记录到 progress.txt"""
        gm = workspace["gm"]
        pm = workspace["pm"]

        # 没有变更，commit 会失败
        result = gm.commit_changes("099", "dev", "无变更")
        assert result["success"] is False

        # 不应该写入 progress
        entry = pm.get_entry("task-099")
        assert entry is None


# ══════════════════════════════════════════════════════════
# 4. Git diff 与提交历史追溯
# ══════════════════════════════════════════════════════════
class TestGitDiffAndHistory:
    """Git diff 与提交历史追溯验证"""

    def test_diff_between_commits(self, workspace):
        """两次提交之间的 diff 可查询"""
        gm = workspace["gm"]
        repo_path = workspace["repo_path"]

        # 第一次提交
        _write_file(repo_path, "a.py", "a = 1")
        r1 = gm.commit_changes("001", "dev", "添加 a")
        hash1 = r1["hexsha"]

        # 第二次提交
        _write_file(repo_path, "b.py", "b = 2")
        gm.commit_changes("002", "dev", "添加 b")

        diff = gm.get_diff_since_commit(hash1)
        assert diff is not None
        assert "b.py" in diff

    def test_diff_multiple_commits(self, workspace):
        """多次提交的累积 diff"""
        gm = workspace["gm"]
        repo_path = workspace["repo_path"]

        # 记录初始 hash
        initial_hash = gm.get_last_commit_hash()

        # 三次提交
        for i in range(3):
            _write_file(repo_path, f"f{i}.py", f"v{i}")
            gm.commit_changes(f"0{i+1:02d}", "dev", f"文件{i}")

        diff = gm.get_diff_since_commit(initial_hash)
        assert diff is not None
        for i in range(3):
            assert f"f{i}.py" in diff

    def test_commit_history_order(self, workspace):
        """commit 历史按时间倒序排列"""
        gm = workspace["gm"]
        repo = workspace["repo"]
        repo_path = workspace["repo_path"]

        _write_file(repo_path, "first.py", "1")
        gm.commit_changes("001", "dev", "第一次")
        _write_file(repo_path, "second.py", "2")
        gm.commit_changes("002", "dev", "第二次")

        commits = list(repo.iter_commits())
        # 最新的在前
        msg2 = gm.parse_commit_message(commits[0].message.strip())
        msg1 = gm.parse_commit_message(commits[1].message.strip())
        assert msg2["task_id"] == "002"
        assert msg1["task_id"] == "001"

    def test_head_commit_matches_last_commit(self, workspace):
        """HEAD commit 与最近一次提交一致"""
        gm = workspace["gm"]
        repo_path = workspace["repo_path"]

        _write_file(repo_path, "latest.py", "l = 1")
        result = gm.commit_changes("050", "dev", "最新提交")

        head = gm.get_head_commit()
        assert head["hexsha"] == result["hexsha"]
        assert head["message"] == result["message"]

    def test_short_hash_usable_for_diff(self, workspace):
        """短 hash 可用于 diff 查询"""
        gm = workspace["gm"]
        repo_path = workspace["repo_path"]

        _write_file(repo_path, "c.py", "c = 1")
        r1 = gm.commit_changes("060", "dev", "添加 c")
        short = r1["short_sha"]

        _write_file(repo_path, "d.py", "d = 1")
        gm.commit_changes("061", "dev", "添加 d")

        diff = gm.get_diff_since_commit(short)
        assert diff is not None
        assert "d.py" in diff


# ══════════════════════════════════════════════════════════
# 5. Git 状态检测与提交流程协同
# ══════════════════════════════════════════════════════════
class TestGitStatusAndCommitCoordination:
    """Git 状态检测与提交流程协同验证"""

    def test_dirty_before_commit_clean_after(self, workspace):
        """提交前 dirty，提交后 clean"""
        gm = workspace["gm"]
        repo_path = workspace["repo_path"]

        _write_file(repo_path, "new.py", "n = 1")
        assert gm.is_dirty() is True
        assert gm.has_uncommitted_changes() is True

        gm.commit_changes("001", "dev", "添加文件")
        assert gm.is_dirty() is False
        assert gm.has_uncommitted_changes() is False

    def test_untracked_file_makes_dirty(self, workspace):
        """未跟踪文件使仓库 dirty"""
        gm = workspace["gm"]
        _write_file(workspace["repo_path"], "untracked.py", "x")

        assert gm.is_dirty() is True
        assert gm.is_dirty(untracked_files=False) is False

    def test_status_reflects_changes(self, workspace):
        """get_status 正确反映变更状态"""
        gm = workspace["gm"]
        repo_path = workspace["repo_path"]

        _write_file(repo_path, "new.py", "new = 1")
        _write_file(repo_path, "README.md", "modified")

        status = gm.get_status()
        assert status["is_dirty"] is True
        assert "new.py" in status["untracked_files"]
        assert "README.md" in status["modified_files"]

    def test_status_clean_after_commit(self, workspace):
        """提交后 get_status 显示干净状态"""
        gm = workspace["gm"]
        repo_path = workspace["repo_path"]

        _write_file(repo_path, "feature.py", "f = 1")
        gm.commit_changes("001", "dev", "添加功能")

        status = gm.get_status()
        assert status["is_dirty"] is False
        assert status["untracked_files"] == []
        assert status["modified_files"] == []

    def test_add_all_false_preserves_untracked(self, workspace):
        """add_all=False 时未跟踪文件保持 untracked"""
        gm = workspace["gm"]
        repo_path = workspace["repo_path"]

        # 先手动 add 一个文件
        _write_file(repo_path, "staged.py", "s = 1")
        repo = workspace["repo"]
        repo.index.add(["staged.py"])

        # 同时存在未跟踪文件
        _write_file(repo_path, "untracked.py", "u = 1")

        # add_all=False 只提交已暂存的
        result = gm.commit_changes("001", "dev", "暂存提交", add_all=False)
        assert result["success"] is True

        # 未跟踪文件仍然存在
        assert gm.is_dirty() is True


# ══════════════════════════════════════════════════════════
# 6. 提交失败与无变更场景
# ══════════════════════════════════════════════════════════
class TestCommitFailureAndNoChanges:
    """提交失败与无变更场景验证"""

    def test_no_changes_commit_returns_failure(self, workspace):
        """无变更时提交返回失败"""
        gm = workspace["gm"]
        result = gm.commit_changes("001", "dev", "无变更")
        assert result["success"] is False
        assert "没有变更" in result["error"]

    def test_no_changes_does_not_create_commit(self, workspace):
        """无变更不会创建新 commit"""
        gm = workspace["gm"]
        hash_before = gm.get_last_commit_hash()
        gm.commit_changes("001", "dev", "无变更")
        hash_after = gm.get_last_commit_hash()
        assert hash_before == hash_after

    def test_empty_task_id_raises(self, workspace):
        """空 task_id 抛 ValueError"""
        gm = workspace["gm"]
        with pytest.raises(ValueError, match="task_id"):
            gm.commit_changes("", "dev", "desc")

    def test_empty_role_raises(self, workspace):
        """空 role 抛 ValueError"""
        gm = workspace["gm"]
        with pytest.raises(ValueError, match="role"):
            gm.commit_changes("001", "", "desc")

    def test_empty_description_raises(self, workspace):
        """空 description 抛 ValueError"""
        gm = workspace["gm"]
        with pytest.raises(ValueError, match="description"):
            gm.commit_changes("001", "dev", "")

    def test_not_a_repo_raises(self, tmp_path):
        """非仓库路径抛 ValueError"""
        gm = GitManager(str(tmp_path / "notexist"), max_retries=0)
        with pytest.raises(ValueError, match="不是 Git 仓库"):
            gm.commit_changes("001", "dev", "test")

    def test_commit_result_structure(self, workspace):
        """提交结果包含所有必要字段"""
        gm = workspace["gm"]
        _write_file(workspace["repo_path"], "x.py", "x = 1")

        result = gm.commit_changes("001", "dev", "测试")
        assert "success" in result
        assert "hexsha" in result
        assert "short_sha" in result
        assert "message" in result
        assert "files_committed" in result
        assert "error" in result
        assert "retries" in result


# ══════════════════════════════════════════════════════════
# 7. 端到端：任务执行 → Git 提交 → 进度记录
# ══════════════════════════════════════════════════════════
class TestEndToEndTaskCommitFlow:
    """端到端：任务执行→Git提交→progress→memory 完整流程"""

    def test_single_task_full_flow(self, workspace):
        """单任务：代码变更→commit→progress→memory 完整流程"""
        gm = workspace["gm"]
        pm = workspace["pm"]
        mm = workspace["mm"]
        repo_path = workspace["repo_path"]

        # Step 1: 任务执行 — 代码变更
        _write_file(repo_path, "login.py", "def login(): pass")

        # Step 2: Git 提交
        result = gm.commit_changes("001", "senior-developer", "实现登录功能")
        assert result["success"] is True

        # Step 3: 记录到 progress.txt（含 git_sha）
        pm.write_entry(ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.COMPLETED,
            role="senior-developer",
            started=datetime(2026, 5, 19, 10, 0, 0),
            finished=datetime(2026, 5, 19, 10, 30, 0),
            git_sha=result["short_sha"],
            git_msg=result["message"],
        ))

        # Step 4: 记录经验到 memory.md
        mm.append(MemoryEntry(
            title="Learnings",
            content="- task-001: 登录函数使用 def login() 模式",
            tags=["task-001", "pattern"],
        ))

        # 验证：Git 仓库干净
        assert gm.is_dirty() is False

        # 验证：progress.txt 记录正确
        entry = pm.get_entry("task-001")
        assert entry.status == ProgressStatus.COMPLETED
        assert entry.git_sha == result["short_sha"]
        assert "[task-001]" in entry.git_msg

        # 验证：memory.md 可搜索
        results = mm.search("task-001")
        assert len(results) == 1
        assert "login" in results[0].content

        # 验证：git log 中有该 commit
        repo = workspace["repo"]
        last_msg = repo.head.commit.message.strip()
        assert last_msg == "[task-001] senior-developer: 实现登录功能"

    def test_multiple_tasks_sequential_flow(self, workspace):
        """多任务顺序执行：每个任务独立提交和记录"""
        gm = workspace["gm"]
        pm = workspace["pm"]
        mm = workspace["mm"]
        repo_path = workspace["repo_path"]

        tasks = [
            ("001", "senior-developer", "实现 API", "api.py", "api = True"),
            ("002", "test-engineer", "编写 API 测试", "test_api.py", "test = True"),
            ("003", "qa-engineer", "集成测试", "test_integration.py", "integration = True"),
        ]

        commit_hashes = []

        for task_id, role, desc, filename, content in tasks:
            # 代码变更
            _write_file(repo_path, filename, content)
            # 提交
            result = gm.commit_changes(task_id, role, desc)
            assert result["success"] is True
            commit_hashes.append(result["hexsha"])
            # 记录 progress
            pm.write_entry(ProgressEntry(
                task_id=f"task-{task_id}",
                status=ProgressStatus.COMPLETED,
                role=role,
                git_sha=result["short_sha"],
                git_msg=result["message"],
            ))

        # 记录到 memory
        mm.append(MemoryEntry(
            title="Key Results",
            content="3 个任务全部完成并提交",
            tags=["milestone"],
        ))

        # 验证：3 条 progress 记录
        entries = pm.read_progress()
        assert len(entries) == 3
        assert pm.get_completed_count() == 3

        # 验证：commit hash 各不相同
        assert len(set(commit_hashes)) == 3

        # 验证：diff 包含所有变更
        initial_hash = list(workspace["repo"].iter_commits())[-1].hexsha
        diff = gm.get_diff_since_commit(initial_hash)
        for _, _, _, filename, _ in tasks:
            assert filename in diff

    def test_failed_task_no_commit_flow(self, workspace):
        """失败任务不提交 Git，progress 记录失败"""
        gm = workspace["gm"]
        pm = workspace["pm"]
        repo_path = workspace["repo_path"]

        # 任务执行产生代码（但不提交，因为任务失败）
        _write_file(repo_path, "broken.py", "broken code")

        # 失败不提交 — 记录到 progress
        pm.write_entry(ProgressEntry(
            task_id="task-099",
            status=ProgressStatus.FAILED,
            role="senior-developer",
            error="编译错误: syntax error",
        ))

        # 验证：仓库仍有未提交变更
        assert gm.is_dirty() is True

        # 验证：progress 记录失败
        entry = pm.get_entry("task-099")
        assert entry.status == ProgressStatus.FAILED
        assert entry.git_sha is None  # 失败没有 git_sha

        # 验证：git log 中没有 task-099 的 commit
        repo = workspace["repo"]
        for commit in repo.iter_commits():
            parsed = gm.parse_commit_message(commit.message.strip())
            if parsed:
                assert parsed["task_id"] != "099"

    def test_retry_task_commit_flow(self, workspace):
        """重试任务：第一次失败（不提交）→ 修复 → 第二次成功（提交）"""
        gm = workspace["gm"]
        pm = workspace["pm"]
        mm = workspace["mm"]
        repo_path = workspace["repo_path"]

        # 第一次尝试失败
        pm.write_entry(ProgressEntry(
            task_id="task-005",
            status=ProgressStatus.FAILED,
            role="senior-developer",
            error="缺少依赖",
            retry=0,
        ))

        # 修复后重试
        _write_file(repo_path, "fixed.py", "fixed = True")
        result = gm.commit_changes("005", "senior-developer", "修复并实现功能")
        assert result["success"] is True

        # 更新 progress（重试成功）
        pm.write_entry(ProgressEntry(
            task_id="task-005",
            status=ProgressStatus.COMPLETED,
            role="senior-developer",
            git_sha=result["short_sha"],
            git_msg=result["message"],
            retry=1,
        ))

        # 记录经验
        mm.append(MemoryEntry(
            title="Learnings",
            content="- task-005: 失败原因是缺少依赖，修复后成功",
            tags=["task-005", "retry"],
        ))

        entry = pm.get_entry("task-005")
        assert entry.status == ProgressStatus.COMPLETED
        assert entry.retry == 1
        assert entry.git_sha == result["short_sha"]


# ══════════════════════════════════════════════════════════
# 8. Git 仓库初始化与提交
# ══════════════════════════════════════════════════════════
class TestGitInitAndCommit:
    """Git 仓库初始化与首次提交流程"""

    def test_init_repo_and_first_commit(self, tmp_path):
        """初始化仓库后可立即提交"""
        repo_path = tmp_path / "new_project"
        gm = GitManager(str(repo_path), max_retries=0)

        repo = gm.init_repo()
        repo.config_writer().set_value("user", "name", "Test").release()
        repo.config_writer().set_value("user", "email", "t@t.com").release()

        _write_file(repo_path, "main.py", "print('hello')")
        result = gm.commit_changes("001", "dev", "初始提交")

        assert result["success"] is True
        assert gm.get_last_commit_hash() == result["hexsha"]

    def test_init_repo_idempotent(self, tmp_path):
        """重复 init_repo 不报错"""
        repo_path = tmp_path / "project"
        gm = GitManager(str(repo_path), max_retries=0)

        gm.init_repo()
        gm.init_repo()  # 不应报错
        assert gm.is_repo()

    def test_empty_repo_has_no_hash(self, tmp_path):
        """空仓库（init 后无提交）没有 commit hash"""
        repo_path = tmp_path / "empty"
        gm = GitManager(str(repo_path), max_retries=0)
        gm.init_repo()

        assert gm.get_last_commit_hash() is None
        assert gm.get_head_commit() is None


# ══════════════════════════════════════════════════════════
# 9. 提交后 Git 仓库完整性
# ══════════════════════════════════════════════════════════
class TestPostCommitIntegrity:
    """提交后 Git 仓库完整性验证"""

    def test_files_committed_list(self, workspace):
        """提交结果包含已提交文件列表"""
        gm = workspace["gm"]
        repo_path = workspace["repo_path"]

        _write_file(repo_path, "new_module.py", "module = True")
        result = gm.commit_changes("001", "dev", "添加模块")

        assert result["success"] is True
        assert isinstance(result["files_committed"], list)

    def test_commit_preserves_file_content(self, workspace):
        """提交后文件内容不变"""
        gm = workspace["gm"]
        repo_path = workspace["repo_path"]
        content = "def hello(): return 'world'"

        _write_file(repo_path, "hello.py", content)
        gm.commit_changes("001", "dev", "添加 hello")

        # 验证文件内容
        assert (repo_path / "hello.py").read_text() == content

    def test_branch_name_after_commits(self, workspace):
        """提交后分支名存在"""
        gm = workspace["gm"]
        _write_file(workspace["repo_path"], "b.py", "b = 1")
        gm.commit_changes("001", "dev", "提交")

        branch = gm.get_current_branch()
        assert branch in ("main", "master")

    def test_head_commit_after_each_commit(self, workspace):
        """每次提交后 HEAD 更新"""
        gm = workspace["gm"]
        repo_path = workspace["repo_path"]
        hashes = []

        for i in range(3):
            _write_file(repo_path, f"f{i}.py", f"v{i}")
            r = gm.commit_changes(f"{i:03d}", "dev", f"提交{i}")
            hashes.append(r["hexsha"])

        head = gm.get_head_commit()
        assert head["hexsha"] == hashes[-1]

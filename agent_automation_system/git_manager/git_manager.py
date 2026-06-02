"""
GitManager - Git 版本管理器

基于 gitpython 封装，提供 Git 仓库初始化、状态检测和版本管理能力。

设计原则：
    - 优雅处理非 Git 仓库场景（is_repo → False）
    - 所有 Git 操作通过 gitpython.Repo 执行
    - 工作目录状态检测（是否为仓库、是否 dirty、当前分支等）
    - 仓库操作失败时抛出明确异常，不静默吞错误

依赖：
    - gitpython>=3.1.0
    - 系统 git 二进制文件
"""

import logging
import os
import re
import time
from pathlib import Path
from typing import Callable, Optional

import git
from git import Repo, InvalidGitRepositoryError, NoSuchPathError

logger = logging.getLogger(__name__)


class GitManager:
    """Git 版本管理器

    提供 Git 仓库初始化和状态检测能力，是所有 Git 操作的入口。

    基于 PRD §4.7 Git 提交规范：
    - 每个 task 完成后自动 git commit
    - commit message 格式：[task-{id}] {role}: {description}
    - 失败时不 commit

    基础能力（P1-030）：
    - init_repo(path): 初始化 Git 仓库
    - is_repo(path): 检查路径是否为 Git 仓库
    - get_repo(path): 获取 Repo 实例（延迟初始化）
    - get_status(path): 获取仓库状态摘要
    - is_dirty(path): 检查是否有未提交的变更
    - get_current_branch(path): 获取当前分支名
    - get_head_commit(path): 获取 HEAD commit 信息

    状态检查（P1-032）：
    - has_uncommitted_changes(path): 检查是否有未提交变更
    - get_last_commit_hash(path): 获取最近一次 commit hash

    Diff 查看（P1-033）：
    - get_diff_since_commit(commit_hash, path): 查看自指定 commit 以来的变更

    提交操作（P1-031）：
    - commit_changes(task_id, role, description): git add + commit
    - format_commit_message(task_id, role, description): 格式化 commit message
    - parse_commit_message(message): 解析 commit message

    重试机制（P1-034）：
    - 所有写操作（commit_changes 等）自动重试，失败最多重试 max_retries 次
    - 可通过构造参数 max_retries 配置，默认 3
    - 重试间隔采用指数退避：1s, 2s, 4s

    Args:
        repo_path: Git 仓库路径（可选，默认当前工作目录）
        max_retries: 写操作失败最大重试次数，默认 3
    """

    def __init__(
        self,
        repo_path: Optional[str] = None,
        max_retries: int = 3,
    ):
        if max_retries < 0:
            raise ValueError(f"max_retries 不能为负数: {max_retries}")
        self._repo_path = Path(repo_path) if repo_path else Path.cwd()
        self._repo: Optional[Repo] = None
        self._max_retries = max_retries

    # ─── 属性 ───────────────────────────────────────

    @property
    def repo_path(self) -> Path:
        """获取仓库路径"""
        return self._repo_path

    @property
    def max_retries(self) -> int:
        """获取最大重试次数"""
        return self._max_retries

    @property
    def repo(self) -> Repo:
        """获取 gitpython.Repo 实例（延迟初始化）

        Returns:
            git.Repo 实例

        Raises:
            ValueError: 路径不是 Git 仓库
        """
        if self._repo is not None:
            return self._repo

        if not self.is_repo():
            raise ValueError(
                f"路径不是 Git 仓库: {self._repo_path}"
            )

        self._repo = Repo(str(self._repo_path))
        return self._repo

    # ─── 仓库初始化 ─────────────────────────────────

    def init_repo(self, path: Optional[str] = None) -> Repo:
        """初始化 Git 仓库

        在指定路径创建新的 Git 仓库（git init）。
        如果路径已经是 Git 仓库，则直接返回 Repo 实例。

        Args:
            path: 仓库路径（可选，默认使用构造时的 repo_path）

        Returns:
            git.Repo 实例

        Raises:
            FileNotFoundError: 父目录不存在
            Exception: 初始化失败
        """
        target = Path(path) if path else self._repo_path

        # 如果已经是 Git 仓库，直接返回
        if self._is_git_dir(target):
            logger.debug(f"路径已经是 Git 仓库: {target}")
            repo = Repo(str(target))
        else:
            # 创建目录（如果不存在）
            target.mkdir(parents=True, exist_ok=True)
            repo = Repo.init(str(target))
            logger.info(f"初始化 Git 仓库: {target}")

        # 更新内部状态
        self._repo_path = target
        self._repo = repo
        return repo

    # ─── 仓库检测 ───────────────────────────────────

    def is_repo(self, path: Optional[str] = None) -> bool:
        """检查路径是否为 Git 仓库

        通过尝试打开 Repo 来验证路径是否为有效的 Git 仓库。

        Args:
            path: 要检查的路径（可选，默认使用 repo_path）

        Returns:
            True 如果是有效的 Git 仓库，False 否则
        """
        target = Path(path) if path else self._repo_path
        return self._is_git_dir(target)

    def is_dirty(
        self,
        path: Optional[str] = None,
        untracked_files: bool = True,
    ) -> bool:
        """检查是否有未提交的变更

        检查工作目录是否有修改、暂存或未跟踪的文件。

        Args:
            path: 仓库路径（可选，默认使用 repo_path）
            untracked_files: 是否将未跟踪文件视为 dirty，默认 True

        Returns:
            True 如果有未提交的变更，False 否则

        Raises:
            ValueError: 路径不是 Git 仓库
        """
        target = Path(path) if path else self._repo_path

        if not self.is_repo(target):
            raise ValueError(f"路径不是 Git 仓库: {target}")

        try:
            repo = Repo(str(target))
            return repo.is_dirty(untracked_files=untracked_files)
        except Exception as e:
            logger.debug(f"检查 dirty 状态失败: {e}")
            return False

    def has_uncommitted_changes(self, path: Optional[str] = None) -> bool:
        """检查是否有未提交的变更

        is_dirty 的语义化别名，专门用于 Master Agent 调度决策。
        检查工作目录是否有修改、暂存或未跟踪的文件。

        Args:
            path: 仓库路径（可选，默认使用 repo_path）

        Returns:
            True 如果有未提交的变更，False 否则
        """
        target = Path(path) if path else self._repo_path

        if not self.is_repo(target):
            return False

        try:
            return self.is_dirty(target, untracked_files=True)
        except Exception as e:
            logger.debug(f"检查未提交变更失败: {e}")
            return False

    def get_last_commit_hash(self, path: Optional[str] = None) -> Optional[str]:
        """获取最近一次 commit 的完整 hash

        对应 git 命令：git rev-parse HEAD

        Args:
            path: 仓库路径（可选，默认使用 repo_path）

        Returns:
            完整的 commit hash 字符串（40 位十六进制），
            如果仓库为空（无提交）或不是 Git 仓库则返回 None
        """
        target = Path(path) if path else self._repo_path

        if not self.is_repo(target):
            return None

        try:
            repo = Repo(str(target))
            return repo.head.commit.hexsha
        except ValueError:
            # 空仓库（无提交）
            logger.debug("仓库为空，无 commit hash")
            return None
        except Exception as e:
            logger.debug(f"获取 commit hash 失败: {e}")
            return None

    def get_diff_since_commit(
        self, commit_hash: str, path: Optional[str] = None
    ) -> Optional[str]:
        """查看自指定 commit 以来的所有变更

        对应 git 命令：git diff {commit_hash}..HEAD

        返回从指定 commit 到当前 HEAD 之间的完整 diff 输出。
        用于 Master Agent 在调度前查看某个 task 执行后的代码变更。

        Args:
            commit_hash: 起始 commit 的 hash（完整或短 hash 均可）
            path: 仓库路径（可选，默认使用 repo_path）

        Returns:
            diff 输出字符串，如果没有变更则返回空字符串；
            如果不是 Git 仓库、仓库为空或 commit_hash 无效，返回 None

        Raises:
            ValueError: commit_hash 为空
        """
        if not commit_hash or not commit_hash.strip():
            raise ValueError("commit_hash 不能为空")

        target = Path(path) if path else self._repo_path

        if not self.is_repo(target):
            return None

        try:
            repo = Repo(str(target))

            # 验证 commit_hash 是否有效
            try:
                commit_obj = repo.commit(commit_hash)
            except Exception:
                logger.debug(f"无效的 commit hash: {commit_hash}")
                return None

            # 如果 commit_hash 就是 HEAD，返回空字符串
            if commit_obj.hexsha == repo.head.commit.hexsha:
                return ""

            # 执行 diff
            diff_output = repo.git.diff(f"{commit_hash}..HEAD")
            logger.debug(
                f"获取 diff: {commit_hash[:7]}..HEAD, "
                f"{len(diff_output)} 字符"
            )
            return diff_output
        except Exception as e:
            logger.debug(f"获取 diff 失败: {e}")
            return None

    # ─── 状态查询 ───────────────────────────────────

    def get_current_branch(self, path: Optional[str] = None) -> Optional[str]:
        """获取当前分支名

        Args:
            path: 仓库路径（可选，默认使用 repo_path）

        Returns:
            当前分支名，如果仓库为空（无提交）则返回 None，
            如果不是 Git 仓库则返回 None
        """
        target = Path(path) if path else self._repo_path

        if not self.is_repo(target):
            return None

        try:
            repo = Repo(str(target))
            if repo.head.is_detached:
                return None
            return repo.active_branch.name
        except Exception as e:
            # 空仓库（无提交）会抛出 TypeError
            logger.debug(f"获取当前分支失败: {e}")
            return None

    def get_head_commit(self, path: Optional[str] = None) -> Optional[dict]:
        """获取 HEAD commit 信息

        Args:
            path: 仓库路径（可选，默认使用 repo_path）

        Returns:
            包含 commit 信息的字典：
            {
                "hexsha": 完整 commit hash,
                "short_sha": 短 commit hash（7 位）,
                "message": commit message（首行）,
                "author": 作者名,
                "committed_datetime": 提交时间,
            }
            如果仓库为空（无提交）或不是 Git 仓库，返回 None
        """
        target = Path(path) if path else self._repo_path

        if not self.is_repo(target):
            return None

        try:
            repo = Repo(str(target))
            if repo.head.is_detached:
                commit = repo.head.commit
            else:
                commit = repo.head.commit

            return {
                "hexsha": commit.hexsha,
                "short_sha": commit.hexsha[:7],
                "message": commit.message.split("\n", 1)[0].strip(),
                "author": str(commit.author),
                "committed_datetime": commit.committed_datetime.isoformat(),
            }
        except ValueError:
            # 空仓库（无提交）
            logger.debug("仓库为空，无 HEAD commit")
            return None
        except Exception as e:
            logger.debug(f"获取 HEAD commit 失败: {e}")
            return None

    def get_status(self, path: Optional[str] = None) -> dict:
        """获取仓库状态摘要

        综合返回仓库的关键状态信息。

        Args:
            path: 仓库路径（可选，默认使用 repo_path）

        Returns:
            状态字典：
            {
                "is_repo": 是否为 Git 仓库,
                "is_dirty": 是否有未提交变更,
                "branch": 当前分支名,
                "head_commit": HEAD commit 信息（同 get_head_commit 返回值）,
                "untracked_files": 未跟踪文件列表,
                "modified_files": 已修改文件列表,
                "staged_files": 已暂存文件列表,
            }
        """
        target = Path(path) if path else self._repo_path

        result = {
            "is_repo": False,
            "is_dirty": False,
            "branch": None,
            "head_commit": None,
            "untracked_files": [],
            "modified_files": [],
            "staged_files": [],
        }

        if not self.is_repo(target):
            return result

        result["is_repo"] = True

        try:
            repo = Repo(str(target))

            # 当前分支
            result["branch"] = self.get_current_branch(str(target))

            # HEAD commit
            result["head_commit"] = self.get_head_commit(str(target))

            # Dirty 状态
            result["is_dirty"] = repo.is_dirty(untracked_files=True)

            # 未跟踪文件
            result["untracked_files"] = repo.untracked_files

            # 已修改文件（工作目录中已修改但未暂存）
            result["modified_files"] = [
                item.a_path
                for item in repo.index.diff(None)
            ]

            # 已暂存文件（已 git add 但未 commit）
            try:
                result["staged_files"] = [
                    item.a_path
                    for item in repo.index.diff("HEAD")
                ]
            except Exception:
                # 空仓库无法 diff HEAD
                result["staged_files"] = [
                    item.a_path
                    for item in repo.index.diff(None)
                    if item.new_file
                ] if repo.index.diff(None) else []

            return result
        except Exception as e:
            logger.debug(f"获取仓库状态失败: {e}")
            result["is_repo"] = True
            return result

    # ─── 提交操作 ───────────────────────────────────

    # commit message 正则：[task-{id}] {role}: {description}
    _COMMIT_MSG_PATTERN = re.compile(
        r"^\[task-([^\]]+)\]\s+([^:]+):\s+(.+)$"
    )

    def commit_changes(
        self,
        task_id: str,
        role: str,
        description: str,
        add_all: bool = True,
        path: Optional[str] = None,
    ) -> dict:
        """提交工作目录变更（含自动重试）

        执行 git add + git commit，按 PRD §4.7 规范生成 commit message。
        格式：[task-{id}] {role}: {description}

        失败时自动重试，最多重试 max_retries 次（默认 3 次）。
        重试间隔采用指数退避：1s, 2s, 4s。

        Args:
            task_id: 任务标识（如 "001"）
            role: 执行该任务的 Agent 角色（如 "senior-developer"）
            description: 变更描述（如 "实现用户登录页面 UI"）
            add_all: 是否添加所有变更文件（git add -A），默认 True；
                     设为 False 时仅提交已暂存的文件
            path: 仓库路径（可选，默认使用 repo_path）

        Returns:
            提交结果字典：
            {
                "success": 是否成功,
                "hexsha": 完整 commit hash（成功时）,
                "short_sha": 短 commit hash（成功时）,
                "message": commit message,
                "files_committed": 提交的文件列表（成功时）,
                "error": 错误信息（失败时）,
                "retries": 实际重试次数,
            }

        Raises:
            ValueError: 路径不是 Git 仓库、参数为空
        """
        # 参数校验（不重试参数错误）
        if not task_id or not task_id.strip():
            raise ValueError("task_id 不能为空")
        if not role or not role.strip():
            raise ValueError("role 不能为空")
        if not description or not description.strip():
            raise ValueError("description 不能为空")

        target = Path(path) if path else self._repo_path

        if not self.is_repo(target):
            raise ValueError(f"路径不是 Git 仓库: {target}")

        message = self.format_commit_message(task_id, role, description)

        result = self._execute_with_retry(
            operation=lambda: self._do_commit(target, add_all, message),
            operation_name=f"commit_changes({task_id})",
        )

        # 确保 message 和 retries 字段始终存在
        result["message"] = message
        if "retries" not in result:
            result["retries"] = 0
        return result

    def _do_commit(
        self, target: Path, add_all: bool, message: str
    ) -> dict:
        """执行实际的 commit 操作（不含重试逻辑）

        Args:
            target: 仓库路径
            add_all: 是否 git add -A
            message: commit message

        Returns:
            提交结果字典

        Raises:
            Exception: 提交失败时抛出异常（触发重试）
        """
        repo = Repo(str(target))

        # git add
        if add_all:
            repo.git.add("-A")
            logger.debug(f"git add -A: {target}")

        # 检查是否有变更需要提交
        has_staged = False
        try:
            diff = repo.index.diff("HEAD")
            has_staged = len(diff) > 0
        except Exception:
            has_staged = len(repo.index.entries) > 0

        if not has_staged and not repo.is_dirty(untracked_files=True):
            logger.debug("没有变更需要提交")
            # 没有变更不抛异常，直接返回失败（不需要重试）
            return {
                "success": False,
                "hexsha": None,
                "short_sha": None,
                "files_committed": [],
                "error": "没有变更需要提交",
                "retries": 0,
            }

        # add_all=False 且没有暂存文件
        if not add_all and not has_staged:
            logger.debug("没有暂存的文件需要提交")
            return {
                "success": False,
                "hexsha": None,
                "short_sha": None,
                "files_committed": [],
                "error": "没有暂存的文件需要提交",
                "retries": 0,
            }

        # 记录将要提交的文件列表
        files_committed = []
        if has_staged:
            try:
                files_committed = [
                    item.a_path for item in repo.index.diff("HEAD")
                ]
            except Exception:
                files_committed = [
                    k[0] for k in repo.index.entries.keys()
                ]

        # git commit
        commit = repo.index.commit(message)
        logger.info(
            f"提交变更: {commit.hexsha[:7]} "
            f"({len(files_committed)} 文件) - {message}"
        )

        return {
            "success": True,
            "hexsha": commit.hexsha,
            "short_sha": commit.hexsha[:7],
            "files_committed": files_committed,
            "error": None,
            "retries": 0,
        }

    def format_commit_message(
        self, task_id: str, role: str, description: str
    ) -> str:
        """按 PRD §4.7 规范格式化 commit message

        格式：[task-{id}] {role}: {description}

        示例：
        - format_commit_message("001", "senior-developer", "实现用户登录")
          → "[task-001] senior-developer: 实现用户登录"

        Args:
            task_id: 任务标识
            role: Agent 角色
            description: 变更描述

        Returns:
            格式化的 commit message
        """
        return f"[task-{task_id}] {role}: {description}"

    def parse_commit_message(self, message: str) -> Optional[dict]:
        """解析 commit message 为结构化数据

        反向操作 format_commit_message。

        Args:
            message: commit message 字符串

        Returns:
            解析结果字典：{"task_id": ..., "role": ..., "description": ...}
            如果格式不匹配则返回 None
        """
        match = self._COMMIT_MSG_PATTERN.match(message.strip())
        if not match:
            return None
        return {
            "task_id": match.group(1),
            "role": match.group(2),
            "description": match.group(3),
        }

    # ─── 内部方法 ───────────────────────────────────

    def _execute_with_retry(
        self,
        operation: Callable,
        operation_name: str = "git_operation",
    ) -> dict:
        """带重试逻辑执行 Git 操作

        执行指定的操作，失败时自动重试。
        重试间隔采用指数退避：1s, 2s, 4s, ...

        如果操作返回的 dict 包含 success=True，视为成功，不重试。
        如果操作返回的 dict 包含 success=False 且 error 不为空，
        且 error 不是 "没有变更" 类错误，则触发重试。
        如果操作抛出异常，触发重试。

        Args:
            operation: 要执行的操作（无参数 callable，返回 dict）
            operation_name: 操作名称（用于日志）

        Returns:
            操作结果字典，额外包含 "retries" 字段记录实际重试次数
        """
        last_error = None
        retry_count = 0

        for attempt in range(self._max_retries + 1):
            try:
                result = operation()

                # 成功
                if result.get("success", False):
                    result["retries"] = retry_count
                    return result

                # 失败但不需要重试的错误（如"没有变更"）
                error_msg = result.get("error", "")
                no_retry_errors = (
                    "没有变更需要提交",
                    "没有暂存的文件需要提交",
                )
                if any(e in error_msg for e in no_retry_errors):
                    result["retries"] = 0
                    return result

                # 其他失败，尝试重试
                last_error = error_msg
                if attempt < self._max_retries:
                    retry_count += 1
                    wait = 2 ** (attempt)  # 指数退避: 1, 2, 4
                    logger.warning(
                        f"{operation_name} 失败 (尝试 {attempt + 1}/"
                        f"{self._max_retries + 1}): {error_msg}, "
                        f"{wait}s 后重试..."
                    )
                    time.sleep(wait)
                    continue

                # 重试次数用尽
                result["retries"] = retry_count
                return result

            except Exception as e:
                last_error = str(e)
                if attempt < self._max_retries:
                    retry_count += 1
                    wait = 2 ** (attempt)
                    logger.warning(
                        f"{operation_name} 异常 (尝试 {attempt + 1}/"
                        f"{self._max_retries + 1}): {e}, "
                        f"{wait}s 后重试..."
                    )
                    time.sleep(wait)
                    continue

                # 重试次数用尽
                logger.error(
                    f"{operation_name} 重试 {retry_count} 次后仍失败: {e}"
                )
                return {
                    "success": False,
                    "hexsha": None,
                    "short_sha": None,
                    "files_committed": [],
                    "error": last_error,
                    "retries": retry_count,
                }

        # 不应到达这里，但保险起见
        return {
            "success": False,
            "hexsha": None,
            "short_sha": None,
            "files_committed": [],
            "error": last_error,
            "retries": retry_count,
        }

    @staticmethod
    def _is_git_dir(path: Path) -> bool:
        """检查路径是否为 Git 仓库

        通过检查 .git 目录或文件是否存在来判断。
        同时也通过 gitpython 验证仓库有效性。

        Args:
            path: 要检查的路径

        Returns:
            True 如果是有效的 Git 仓库
        """
        git_path = path / ".git"
        if not git_path.exists():
            return False

        try:
            Repo(str(path))
            return True
        except (InvalidGitRepositoryError, NoSuchPathError, Exception):
            return False

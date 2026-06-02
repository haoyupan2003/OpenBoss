"""
SubAgent 基类 — 接口定义 + 生命周期管理

基于 PRD V2.0 §4.3 Workflow Engine 和 §6.10 Lifecycle Manager 设计。
SubAgent 是 Master-Agent 调度的最小执行单元，每个 SubAgent 负责执行一个原子任务。

生命周期：initialize() → execute(task) → verify() → commit() → cleanup()
- P1-036 定义接口签名和 SubAgentResult 数据模型
- P1-037 实现生命周期编排逻辑（状态流转、错误处理、run 便捷方法）
"""

import logging
from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

from agent_automation_system.models.task import Task

logger = logging.getLogger(__name__)


class AgentPhase(str, Enum):
    """SubAgent 生命周期阶段

    对应 PRD §6.3.2 PDCA 循环 + §6.10.1 Agent 生命周期。
    每个 SubAgent 实例按固定顺序经历这些阶段。
    """

    CREATED = "created"          # 已创建，尚未初始化
    INITIALIZED = "initialized"  # 环境初始化完成
    EXECUTING = "executing"      # 正在执行任务
    VERIFYING = "verifying"      # 正在验证执行结果
    COMMITTING = "committing"    # 正在提交变更
    COMPLETED = "completed"      # 任务完成
    FAILED = "failed"            # 任务失败
    BLOCKED = "blocked"          # 任务被阻塞
    CLEANED_UP = "cleaned_up"    # 资源已清理


class SubAgentResultStatus(str, Enum):
    """SubAgent 执行结果状态

    对应 PRD §4.3.3 主循环中的 WorkflowResult.status 枚举。
    """

    SUCCESS = "success"     # 任务成功完成
    FAILED = "failed"       # 任务失败
    BLOCKED = "blocked"     # 任务被阻塞（需人工介入）
    TIMEOUT = "timeout"     # 任务超时
    RETRY = "retry"         # 任务需要重试


class SubAgentResult(BaseModel):
    """SubAgent 执行结果数据模型

    execute(task) 方法的返回值，封装任务执行的所有关键信息。
    Master-Agent 根据此结果决定后续调度策略。

    Attributes:
        task_id: 对应的 Task ID
        status: 执行结果状态
        phase: 执行到哪个阶段结束（用于诊断中断位置）
        role: 执行该任务的 Agent 角色
        commit_hash: Git 提交的 commit hash（成功时有值）
        commit_message: Git 提交信息
        output: 执行过程的输出摘要
        error: 失败/阻塞时的错误信息
        started_at: 开始执行时间
        finished_at: 执行完成时间
        retries: 实际重试次数
        metadata: 扩展元数据（子类可填充额外信息）
    """

    task_id: str = Field(
        ...,
        description="对应的 Task ID",
    )
    status: SubAgentResultStatus = Field(
        ...,
        description="执行结果状态",
    )
    phase: AgentPhase = Field(
        ...,
        description="执行到哪个阶段结束",
    )
    role: str = Field(
        default="dev",
        description="执行该任务的 Agent 角色",
    )
    commit_hash: Optional[str] = Field(
        None,
        description="Git 提交的 commit hash",
    )
    commit_message: Optional[str] = Field(
        None,
        description="Git 提交信息",
    )
    output: Optional[str] = Field(
        None,
        description="执行过程的输出摘要",
    )
    error: Optional[str] = Field(
        None,
        description="失败/阻塞时的错误信息",
    )
    started_at: Optional[datetime] = Field(
        None,
        description="开始执行时间",
    )
    finished_at: Optional[datetime] = Field(
        None,
        description="执行完成时间",
    )
    retries: int = Field(
        default=0,
        ge=0,
        description="实际重试次数",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="扩展元数据",
    )

    @property
    def is_success(self) -> bool:
        """是否成功完成"""
        return self.status == SubAgentResultStatus.SUCCESS

    @property
    def is_terminal(self) -> bool:
        """是否为终态（不再重试）"""
        return self.status in (
            SubAgentResultStatus.SUCCESS,
            SubAgentResultStatus.BLOCKED,
        )

    @property
    def duration_seconds(self) -> Optional[float]:
        """执行耗时（秒），需同时有 started_at 和 finished_at"""
        if self.started_at and self.finished_at:
            return (self.finished_at - self.started_at).total_seconds()
        return None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "task_id": "task-001",
                    "status": "success",
                    "phase": "completed",
                    "role": "senior-developer",
                    "commit_hash": "a3f7b2c1d4e5f6",
                    "commit_message": "[task-001] senior-developer: 实现用户登录页面 UI",
                    "output": "创建 3 个文件：login.tsx, LoginForm.tsx, auth.css",
                    "error": None,
                    "started_at": "2026-05-13T11:05:00Z",
                    "finished_at": "2026-05-13T11:32:15Z",
                    "retries": 0,
                    "metadata": {},
                }
            ]
        }
    }


# 生命周期阶段合法转换表
# key: 当前阶段, value: 可转换到的阶段集合
_VALID_TRANSITIONS: dict[AgentPhase, set[AgentPhase]] = {
    AgentPhase.CREATED: {
        AgentPhase.INITIALIZED,
        AgentPhase.FAILED,
    },
    AgentPhase.INITIALIZED: {
        AgentPhase.EXECUTING,
        AgentPhase.FAILED,
        AgentPhase.BLOCKED,
    },
    AgentPhase.EXECUTING: {
        AgentPhase.VERIFYING,
        AgentPhase.FAILED,
        AgentPhase.BLOCKED,
        AgentPhase.TIMEOUT if hasattr(AgentPhase, "TIMEOUT") else AgentPhase.FAILED,
    },
    AgentPhase.VERIFYING: {
        AgentPhase.COMMITTING,
        AgentPhase.FAILED,
        AgentPhase.BLOCKED,
    },
    AgentPhase.COMMITTING: {
        AgentPhase.COMPLETED,
        AgentPhase.FAILED,
    },
    AgentPhase.COMPLETED: {
        AgentPhase.CLEANED_UP,
    },
    AgentPhase.FAILED: {
        AgentPhase.CLEANED_UP,
    },
    AgentPhase.BLOCKED: {
        AgentPhase.CLEANED_UP,
    },
    AgentPhase.CLEANED_UP: set(),  # 终态，不可再转换
}


class SubAgent(ABC):
    """SubAgent 抽象基类

    所有具体 Agent（SeniorDeveloperAgent、TestEngineerAgent 等）的基类。
    定义 Sub-Agent 的标准接口和生命周期编排逻辑。

    生命周期：
        initialize() → execute(task) → verify() → commit() → cleanup()

    由 run(task) 方法自动编排完整生命周期，也可手动分步调用。

    设计原则：
        - Ephemeral Agent 模式（PRD §6.10.2）：无状态、一次性、幂等
        - 每个 SubAgent 实例执行一个 Task 后退出
        - 通过文件系统恢复状态（读 task.json + progress.txt）
        - 阶段转换受合法性约束，非法转换抛 RuntimeError

    Attributes:
        role_name: Agent 角色名称（如 "senior-developer"、"test-engineer"）
        task: 当前分配的任务
        phase: 当前生命周期阶段
        result: 最新执行结果
    """

    def __init__(self, role_name: str) -> None:
        """初始化 SubAgent

        Args:
            role_name: Agent 角色名称
        """
        self._role_name: str = role_name
        self._task: Optional[Task] = None
        self._phase: AgentPhase = AgentPhase.CREATED
        self._result: Optional[SubAgentResult] = None

    # ── 属性 ──────────────────────────────────────────────

    @property
    def role_name(self) -> str:
        """Agent 角色名称"""
        return self._role_name

    @property
    def task(self) -> Optional[Task]:
        """当前分配的任务"""
        return self._task

    @property
    def phase(self) -> AgentPhase:
        """当前生命周期阶段"""
        return self._phase

    @property
    def result(self) -> Optional[SubAgentResult]:
        """最新执行结果"""
        return self._result

    # ── 阶段转换 ─────────────────────────────────────────

    def _transition_to(self, new_phase: AgentPhase) -> None:
        """安全转换生命周期阶段

        根据 _VALID_TRANSITIONS 校验转换合法性。
        非法转换抛出 RuntimeError，防止生命周期混乱。

        Args:
            new_phase: 目标阶段

        Raises:
            RuntimeError: 非法阶段转换
        """
        allowed = _VALID_TRANSITIONS.get(self._phase, set())
        if new_phase not in allowed:
            raise RuntimeError(
                f"Invalid phase transition: {self._phase.value} → {new_phase.value}. "
                f"Allowed transitions from {self._phase.value}: "
                f"{[p.value for p in allowed] if allowed else 'none (terminal)'}"
            )
        logger.debug(
            "SubAgent [%s] phase transition: %s → %s",
            self._role_name,
            self._phase.value,
            new_phase.value,
        )
        self._phase = new_phase

    # ── 构建结果辅助 ──────────────────────────────────────

    def _build_result(
        self,
        status: SubAgentResultStatus,
        phase: Optional[AgentPhase] = None,
        **overrides: Any,
    ) -> SubAgentResult:
        """构建 SubAgentResult 的辅助方法

        自动填充 task_id / role / started_at / finished_at 等公共字段，
        子类可传入 overrides 覆盖或添加额外字段。

        Args:
            status: 结果状态
            phase: 阶段（默认使用当前 phase）
            **overrides: 覆盖字段

        Returns:
            SubAgentResult 实例
        """
        data: dict[str, Any] = {
            "task_id": self._task.id if self._task else "unknown",
            "status": status,
            "phase": phase or self._phase,
            "role": self._role_name,
            "started_at": self._result.started_at if self._result else None,
            "finished_at": datetime.now(),
        }
        # 继承上次结果的 retries
        if self._result and self._result.retries:
            data.setdefault("retries", self._result.retries)
        # 继承上次结果的 commit 信息（除非被覆盖）
        if self._result:
            if self._result.commit_hash and "commit_hash" not in overrides:
                data["commit_hash"] = self._result.commit_hash
            if self._result.commit_message and "commit_message" not in overrides:
                data["commit_message"] = self._result.commit_message
            if self._result.output and "output" not in overrides:
                data["output"] = self._result.output
        data.update(overrides)
        return SubAgentResult(**data)

    # ── 抽象方法（子类实现具体逻辑）────────────────────────

    @abstractmethod
    def initialize(self) -> None:
        """初始化 SubAgent 执行环境

        在执行任务前调用，准备运行时环境：
        - 检查工具链可用性（如 tmux、git）
        - 加载角色约束（harness）
        - 验证前置依赖已满足

        子类实现此方法时应：
        1. 检查所需资源是否就绪
        2. 加载角色特定的约束规则
        3. 成功后无需手动设置 phase（run() 会自动转换）

        Raises:
            RuntimeError: 环境初始化失败
        """
        ...

    @abstractmethod
    def execute(self, task: Task) -> SubAgentResult:
        """执行任务

        SubAgent 的核心方法，接收一个 Task 并返回执行结果。
        由 run() 自动调用，每个 Task 对应一次 execute 调用。

        子类实现此方法时应：
        1. 执行具体的任务逻辑（编码、测试、分析等）
        2. 返回 SubAgentResult（status=SUCCESS 表示执行成功）
        3. 无需手动管理 phase（run() 会自动转换）

        Args:
            task: 要执行的任务

        Returns:
            SubAgentResult: 封装执行结果

        Raises:
            ValueError: task 参数无效
            RuntimeError: 执行过程中发生不可恢复的错误
        """
        ...

    @abstractmethod
    def verify(self) -> SubAgentResult:
        """验证执行结果

        在 execute 之后调用，验证任务产出的正确性：
        - 运行测试
        - 检查 lint/build
        - 验证 BDD Then 条件

        子类实现此方法时应：
        1. 执行验证逻辑
        2. 返回更新后的 SubAgentResult
        3. 无需手动管理 phase（run() 会自动转换）

        Returns:
            SubAgentResult: 更新后的执行结果
        """
        ...

    @abstractmethod
    def commit(self) -> SubAgentResult:
        """提交变更

        在 verify 通过后调用，原子性提交代码变更：
        - git add 相关文件
        - git commit（格式：[task-{id}] {role}: {description}）
        - 更新 progress.txt

        子类实现此方法时应：
        1. 执行 git 操作
        2. 返回包含 commit_hash 的 SubAgentResult
        3. 无需手动管理 phase（run() 会自动转换）

        Returns:
            SubAgentResult: 更新后的执行结果
        """
        ...

    @abstractmethod
    def cleanup(self) -> None:
        """清理资源

        在任务结束后调用（无论成功或失败），释放运行时资源：
        - 关闭 tmux 窗口/会话
        - 清理临时文件
        - 记录最终状态

        此方法不应抛出异常（异常应被捕获并记录日志）。
        子类实现此方法时应确保资源释放的健壮性。
        """
        ...

    # ── 生命周期编排（P1-037 实现）────────────────────────

    def run(self, task: Task) -> SubAgentResult:
        """运行完整的 SubAgent 生命周期

        自动编排 initialize → execute → verify → commit → cleanup，
        并在每个阶段之间进行状态流转控制。

        生命周期流程：
        1. INITIALIZE: 初始化环境
        2. EXECUTE: 执行任务
        3. VERIFY: 验证结果
        4. COMMIT: 提交变更
        5. CLEANUP: 清理资源

        任何阶段失败都会跳转到 CLEANUP，确保资源被释放。
        cleanup 本身的异常会被捕获，不影响最终结果。

        Args:
            task: 要执行的任务

        Returns:
            SubAgentResult: 最终执行结果

        Raises:
            ValueError: task 为 None 或已执行过任务
        """
        if task is None:
            raise ValueError("task cannot be None")

        # 每个 SubAgent 实例只能执行一次（Ephemeral Agent 模式）
        if self._task is not None:
            raise ValueError(
                f"SubAgent already executed task '{self._task.id}'. "
                f"Create a new SubAgent instance for task '{task.id}'."
            )

        self._task = task
        self._result = SubAgentResult(
            task_id=task.id,
            status=SubAgentResultStatus.RETRY,
            phase=AgentPhase.CREATED,
            role=self._role_name,
            started_at=datetime.now(),
        )

        try:
            # Phase 1: INITIALIZE
            self._run_initialize()

            # Phase 2: EXECUTE
            self._run_execute()

            # Phase 3: VERIFY
            self._run_verify()

            # Phase 4: COMMIT
            self._run_commit()

        except _LifecycleAbort as abort:
            # 生命周期被中止（初始化失败等），result 已设置
            logger.warning(
                "SubAgent [%s] lifecycle aborted at phase %s: %s",
                self._role_name,
                self._phase.value,
                abort.reason,
            )
        except Exception as exc:
            # 未预期的异常
            logger.exception(
                "SubAgent [%s] unexpected error at phase %s",
                self._role_name,
                self._phase.value,
            )
            self._result = self._build_result(
                status=SubAgentResultStatus.FAILED,
                error=str(exc),
            )
            try:
                self._transition_to(AgentPhase.FAILED)
            except RuntimeError:
                pass  # 如果已经处于终态，忽略转换错误

        finally:
            # Phase 5: CLEANUP（始终执行）
            self._run_cleanup()

        return self._result

    def _run_initialize(self) -> None:
        """执行 initialize 阶段"""
        logger.info(
            "SubAgent [%s] initializing for task '%s'...",
            self._role_name,
            self._task.id if self._task else "unknown",
        )
        try:
            self.initialize()
            self._transition_to(AgentPhase.INITIALIZED)
            logger.info("SubAgent [%s] initialized successfully", self._role_name)
        except Exception as exc:
            self._result = self._build_result(
                status=SubAgentResultStatus.FAILED,
                phase=AgentPhase.CREATED,
                error=f"Initialization failed: {exc}",
            )
            try:
                self._transition_to(AgentPhase.FAILED)
            except RuntimeError:
                pass
            raise _LifecycleAbort("Initialization failed") from exc

    def _run_execute(self) -> None:
        """执行 execute 阶段"""
        self._transition_to(AgentPhase.EXECUTING)
        logger.info(
            "SubAgent [%s] executing task '%s'...",
            self._role_name,
            self._task.id if self._task else "unknown",
        )
        result = self.execute(self._task)
        self._result = result

        # 如果 execute 返回非成功状态，中止生命周期
        if result.status == SubAgentResultStatus.BLOCKED:
            self._transition_to(AgentPhase.BLOCKED)
            raise _LifecycleAbort(f"Task blocked: {result.error}")

        if result.status != SubAgentResultStatus.SUCCESS:
            self._transition_to(AgentPhase.FAILED)
            raise _LifecycleAbort(f"Execute failed: {result.error}")

        logger.info("SubAgent [%s] execute completed", self._role_name)

    def _run_verify(self) -> None:
        """执行 verify 阶段"""
        self._transition_to(AgentPhase.VERIFYING)
        logger.info("SubAgent [%s] verifying results...", self._role_name)
        result = self.verify()
        self._result = result

        if result.status == SubAgentResultStatus.BLOCKED:
            self._transition_to(AgentPhase.BLOCKED)
            raise _LifecycleAbort(f"Verification blocked: {result.error}")

        if result.status != SubAgentResultStatus.SUCCESS:
            self._transition_to(AgentPhase.FAILED)
            raise _LifecycleAbort(f"Verification failed: {result.error}")

        logger.info("SubAgent [%s] verify passed", self._role_name)

    def _run_commit(self) -> None:
        """执行 commit 阶段"""
        self._transition_to(AgentPhase.COMMITTING)
        logger.info("SubAgent [%s] committing changes...", self._role_name)
        result = self.commit()
        self._result = result

        if result.status != SubAgentResultStatus.SUCCESS:
            self._transition_to(AgentPhase.FAILED)
            raise _LifecycleAbort(f"Commit failed: {result.error}")

        self._transition_to(AgentPhase.COMPLETED)
        logger.info(
            "SubAgent [%s] task completed (commit: %s)",
            self._role_name,
            result.commit_hash or "N/A",
        )

    def _run_cleanup(self) -> None:
        """执行 cleanup 阶段（始终调用，异常不外泄）"""
        try:
            logger.debug("SubAgent [%s] cleaning up...", self._role_name)
            self.cleanup()
            # 只在非终态时转换
            if self._phase not in (
                AgentPhase.COMPLETED,
                AgentPhase.FAILED,
                AgentPhase.BLOCKED,
                AgentPhase.CLEANED_UP,
            ):
                logger.warning(
                    "SubAgent [%s] cleanup called in non-terminal phase %s, "
                    "transitioning to CLEANED_UP",
                    self._role_name,
                    self._phase.value,
                )
            self._transition_to(AgentPhase.CLEANED_UP)
            logger.debug("SubAgent [%s] cleanup completed", self._role_name)
        except Exception as exc:
            # cleanup 不应抛出异常，但以防万一
            logger.exception(
                "SubAgent [%s] cleanup failed (suppressed): %s",
                self._role_name,
                exc,
            )
            # 强制设为 CLEANED_UP
            self._phase = AgentPhase.CLEANED_UP


class _LifecycleAbort(Exception):
    """生命周期中止信号

    用于在某个阶段失败时中止 run() 的正常流程，跳转到 cleanup。
    这不是对外暴露的异常，run() 会捕获它并返回 FAILED/BLOCKED 结果。
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)

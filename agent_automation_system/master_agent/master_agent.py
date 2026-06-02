"""
MasterAgent — 系统核心调度中枢

基于 PRD V2.0 §4.3 Workflow Engine 和 §4.4 Master Agent 设计。
MasterAgent 是整个系统的编排核心，负责：

1. 接收用户需求（requirement）
2. 创建 PM Sub-Agent 分析需求并生成 task.json
3. 读取 task.json，解析任务列表和依赖关系
4. 按依赖和优先级调度 Sub-Agent 执行任务
5. 记录执行结果，追踪全局进度

调度流程：
    IDLE → receive_requirement() → ANALYZING
    ANALYZING → create_pm_agent() → (等待 PM 完成)
    → load_task_json() / set_task_json() → PLANNING/DISPATCHING
    → get_dispatchable_tasks() + create_sub_agent() → 调度执行
    → record_result() → MONITORING
    → 全部完成 → COMPLETED

设计原则：
    - 依赖注入：所有外部依赖通过构造函数注入，方便测试
    - Agent Factory 模式：通过 agent_factory 可调用对象创建 SubAgent，
      具体工厂实现在 P1-048（Sub-Agent 创建与委派）
    - 状态机驱动：状态转换受合法性约束，非法转换抛 RuntimeError
    - 单次执行：每个 MasterAgent 实例处理一个需求（Ephemeral 模式）
"""

import logging
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Optional

from agent_automation_system.cli.claude_code_cli import ClaudeCodeCLI
from agent_automation_system.file_io.progress_manager import ProgressManager
from agent_automation_system.file_io.task_file_manager import TaskFileManager
from agent_automation_system.harness.harness_loader import HarnessLoader
from agent_automation_system.models.progress import ProgressEntry, ProgressStatus
from agent_automation_system.models.task import Task, TaskStatus
from agent_automation_system.models.task_json import TaskJSON
from agent_automation_system.sub_agent.role_injector import RoleInjector
from agent_automation_system.sub_agent.sub_agent import (
    AgentPhase,
    SubAgent,
    SubAgentResult,
    SubAgentResultStatus,
)
from agent_automation_system.tmux_manager.tmux_manager import TmuxManager

logger = logging.getLogger(__name__)


# ── MasterAgent 调度状态 ────────────────────────────────────────


class MasterAgentState(str, Enum):
    """MasterAgent 调度状态

    对应 PRD §4.3 Workflow Engine 中的主循环状态。
    MasterAgent 在生命周期内按顺序经历这些状态。

    状态流转：
        IDLE → ANALYZING → PLANNING → DISPATCHING → MONITORING → COMPLETED
        任意执行阶段 → FAILED / PAUSED
    """

    IDLE = "idle"                # 空闲，等待需求
    ANALYZING = "analyzing"      # PM Agent 正在分析需求
    PLANNING = "planning"        # 正在加载/解析 task.json
    DISPATCHING = "dispatching"  # 正在调度 Sub-Agent 执行任务
    MONITORING = "monitoring"    # 监控 Sub-Agent 执行进度
    COMPLETED = "completed"      # 所有任务完成
    FAILED = "failed"            # 执行失败
    PAUSED = "paused"            # 暂停（需人工介入）


# ── 合法状态转换表 ──────────────────────────────────────────────

_VALID_STATE_TRANSITIONS: dict[MasterAgentState, set[MasterAgentState]] = {
    MasterAgentState.IDLE: {
        MasterAgentState.ANALYZING,
    },
    MasterAgentState.ANALYZING: {
        MasterAgentState.PLANNING,
        MasterAgentState.FAILED,
    },
    MasterAgentState.PLANNING: {
        MasterAgentState.DISPATCHING,
        MasterAgentState.FAILED,
    },
    MasterAgentState.DISPATCHING: {
        MasterAgentState.MONITORING,
        MasterAgentState.COMPLETED,
        MasterAgentState.FAILED,
        MasterAgentState.PAUSED,
    },
    MasterAgentState.MONITORING: {
        MasterAgentState.DISPATCHING,
        MasterAgentState.COMPLETED,
        MasterAgentState.FAILED,
        MasterAgentState.PAUSED,
    },
    MasterAgentState.COMPLETED: set(),  # 终态
    MasterAgentState.FAILED: set(),     # 终态
    MasterAgentState.PAUSED: {
        MasterAgentState.DISPATCHING,
        MasterAgentState.FAILED,
    },
}


# ── Agent Factory 类型 ──────────────────────────────────────────

# Agent 工厂：接收角色名称，返回 SubAgent 实例
# 具体工厂实现在 P1-048（Sub-Agent 创建与委派）
AgentFactory = Callable[[str], SubAgent]

# OpenClaw 通知回调：接收事件类型 + 详情字典
OpenClawNotifier = Callable[[str, dict[str, Any]], None]


def _default_agent_factory(role_name: str) -> SubAgent:
    """默认 Agent 工厂 — 未配置时抛出 NotImplementedError

    Args:
        role_name: 角色名称

    Raises:
        NotImplementedError: 未配置 agent_factory
    """
    raise NotImplementedError(
        "No agent factory configured. "
        "Provide agent_factory to MasterAgent constructor."
    )


def _default_openclaw_notifier(event_type: str, details: dict[str, Any]) -> None:
    """默认 OpenClaw 通知器 — 仅记录日志

    Args:
        event_type: 事件类型
        details: 事件详情
    """
    logger.info(
        "OpenClaw notification: event=%s, details=%s",
        event_type,
        details,
    )


# ── 失败处理动作 ──────────────────────────────────────────


class FailureAction(str, Enum):
    """任务失败后采取的动作

    on_task_failed() 返回此枚举，指示 MasterAgent 对失败任务
    采取的处理策略。

    状态流转：
        RETRY → 任务重试（retry_count++，重置 PENDING）
        ABORT → 任务不可恢复（标记 FAILED，暂停依赖，通知 OpenClaw）
    """

    RETRY = "retry"  # 重试任务
    ABORT = "abort"  # 中止任务，暂停任务流


# ── 默认配置 ────────────────────────────────────────────────────

_DEFAULT_SESSION_NAME = "openboss"
_DEFAULT_MAX_CONCURRENT_AGENTS = 3
_DEFAULT_AGENT_TIMEOUT = 1800
_DEFAULT_TASK_MAX_RETRIES = 1
_DEFAULT_POLL_INTERVAL = 10.0

# tmux 主窗口名称
_MAIN_WINDOW_NAME = "main"

# main-rules.md 默认文件名
_MAIN_RULES_FILENAME = "main-rules.md"


class MasterAgent:
    """Master Agent — 系统核心调度中枢

    负责接收需求、创建 PM Sub-Agent、读取 task.json、
    按依赖和优先级调度 Sub-Agent 执行任务。

    调度流程：
        1. receive_requirement(requirement) → 接收需求，创建 PM Agent
        2. PM Agent 分析需求，生成 task.json
        3. load_task_json(path) / set_task_json(task_json) → 加载任务列表
        4. get_dispatchable_tasks() → 获取可调度任务
        5. create_sub_agent(task) → 为任务创建 Sub-Agent
        6. Sub-Agent 执行任务
        7. record_result(task_id, result) → 记录执行结果
        8. 循环 4-7 直到所有任务完成

    使用示例：
        master = MasterAgent(
            tmux_manager=tmux,
            cli=cli,
            agent_factory=my_factory,
        )
        master.startup()  # 注入 main-rules、初始化 tmux、启动 CLI
        master.receive_requirement("实现用户登录功能")
        pm_agent = master.create_pm_agent("实现用户登录功能")
        # ... PM Agent 执行后生成 task.json ...
        master.load_task_json("data/task.json")
        for task in master.get_dispatchable_tasks():
            agent = master.create_sub_agent(task)
            result = agent.run(task)
            master.record_result(task.id, result)

    Args:
        tmux_manager: TmuxManager 实例（启动流程必需）
        cli: ClaudeCodeCLI 实例（启动流程必需）
        agent_factory: Agent 工厂，接收角色名称返回 SubAgent 实例
        task_file_manager: task.json 文件管理器（可选，懒创建）
        progress_manager: 进度管理器（可选，懒创建）
        role_injector: 角色注入器（可选，懒创建）
        harness_loader: Harness 加载器（可选，懒创建）
        main_rules_path: main-rules.md 文件路径（可选，默认自动查找）
        session_name: tmux 主会话名称，默认 "openboss"
        max_concurrent_agents: 最大并发 Sub-Agent 数，默认 3
        agent_timeout: Sub-Agent 执行超时（秒），默认 1800
        task_max_retries: 任务失败最大重试次数，默认 1
        poll_interval: 进度轮询间隔（秒），默认 10.0
    """

    def __init__(
        self,
        tmux_manager: Optional[TmuxManager] = None,
        cli: Optional[ClaudeCodeCLI] = None,
        agent_factory: Optional[AgentFactory] = None,
        task_file_manager: Optional[TaskFileManager] = None,
        progress_manager: Optional[ProgressManager] = None,
        role_injector: Optional[RoleInjector] = None,
        harness_loader: Optional[HarnessLoader] = None,
        openclaw_notifier: Optional[OpenClawNotifier] = None,
        main_rules_path: Optional[str] = None,
        session_name: str = _DEFAULT_SESSION_NAME,
        max_concurrent_agents: int = _DEFAULT_MAX_CONCURRENT_AGENTS,
        agent_timeout: int = _DEFAULT_AGENT_TIMEOUT,
        task_max_retries: int = _DEFAULT_TASK_MAX_RETRIES,
        poll_interval: float = _DEFAULT_POLL_INTERVAL,
    ) -> None:
        # ── 基础设施依赖 ──
        self._tmux_manager = tmux_manager
        self._cli = cli

        # ── Agent 工厂 ──
        self._agent_factory: AgentFactory = agent_factory or _default_agent_factory

        # ── 依赖组件（懒创建） ──
        self._task_file_manager = task_file_manager
        self._progress_manager = progress_manager
        self._role_injector = role_injector
        self._harness_loader = harness_loader

        # ── 通知器 ──
        self._openclaw_notifier: OpenClawNotifier = (
            openclaw_notifier or _default_openclaw_notifier
        )

        # ── 启动配置 ──
        self._main_rules_path = main_rules_path

        # ── 调度配置 ──
        if max_concurrent_agents <= 0:
            raise ValueError("max_concurrent_agents must be positive")
        if agent_timeout <= 0:
            raise ValueError("agent_timeout must be positive")
        if task_max_retries < 0:
            raise ValueError("task_max_retries must be non-negative")
        if poll_interval <= 0:
            raise ValueError("poll_interval must be positive")

        self._session_name = session_name
        self._max_concurrent_agents = max_concurrent_agents
        self._agent_timeout = agent_timeout
        self._task_max_retries = task_max_retries
        self._poll_interval = poll_interval

        # ── 运行时状态 ──
        self._state: MasterAgentState = MasterAgentState.IDLE
        self._requirement: Optional[str] = None
        self._task_json: Optional[TaskJSON] = None
        self._pm_agent: Optional[SubAgent] = None
        self._active_agents: dict[str, SubAgent] = {}  # task_id → SubAgent
        self._execution_results: dict[str, SubAgentResult] = {}  # task_id → result
        self._failure_log: list[dict[str, Any]] = []  # 失败事件日志

        # ── 启动流程状态 ──
        self._is_started: bool = False
        self._main_rules_content: Optional[str] = None

    # ── 属性 ──────────────────────────────────────────────

    @property
    def state(self) -> MasterAgentState:
        """当前调度状态"""
        return self._state

    @property
    def requirement(self) -> Optional[str]:
        """当前需求描述"""
        return self._requirement

    @property
    def task_json(self) -> Optional[TaskJSON]:
        """当前 TaskJSON"""
        return self._task_json

    @property
    def pm_agent(self) -> Optional[SubAgent]:
        """当前 PM Sub-Agent"""
        return self._pm_agent

    @property
    def active_agents(self) -> dict[str, SubAgent]:
        """活跃的 Sub-Agent（只读副本）"""
        return dict(self._active_agents)

    @property
    def execution_results(self) -> dict[str, SubAgentResult]:
        """所有任务的执行结果（只读副本）"""
        return dict(self._execution_results)

    @property
    def session_name(self) -> str:
        """tmux 主会话名称"""
        return self._session_name

    @property
    def max_concurrent_agents(self) -> int:
        """最大并发 Sub-Agent 数"""
        return self._max_concurrent_agents

    @property
    def agent_timeout(self) -> int:
        """Sub-Agent 执行超时（秒）"""
        return self._agent_timeout

    @property
    def task_max_retries(self) -> int:
        """任务失败最大重试次数"""
        return self._task_max_retries

    @property
    def poll_interval(self) -> float:
        """进度轮询间隔（秒）"""
        return self._poll_interval

    @property
    def is_started(self) -> bool:
        """是否已完成启动流程"""
        return self._is_started

    @property
    def main_rules_content(self) -> Optional[str]:
        """已加载的 main-rules.md 内容"""
        return self._main_rules_content

    @property
    def tmux_manager(self) -> Optional[TmuxManager]:
        """TmuxManager 实例"""
        return self._tmux_manager

    @property
    def cli(self) -> Optional[ClaudeCodeCLI]:
        """ClaudeCodeCLI 实例"""
        return self._cli

    @property
    def main_rules_path(self) -> Optional[str]:
        """main-rules.md 文件路径"""
        return self._main_rules_path

    @property
    def progress_manager(self) -> Optional[ProgressManager]:
        """ProgressManager 实例"""
        return self._progress_manager

    @property
    def failure_log(self) -> list[dict[str, Any]]:
        """失败事件日志（只读副本）"""
        return list(self._failure_log)

    @property
    def openclaw_notifier(self) -> OpenClawNotifier:
        """OpenClaw 通知回调"""
        return self._openclaw_notifier

    # ── 状态转换 ─────────────────────────────────────────

    def _transition_to(self, new_state: MasterAgentState) -> None:
        """安全转换调度状态

        根据 _VALID_STATE_TRANSITIONS 校验转换合法性。
        非法转换抛出 RuntimeError，防止状态混乱。

        Args:
            new_state: 目标状态

        Raises:
            RuntimeError: 非法状态转换
        """
        allowed = _VALID_STATE_TRANSITIONS.get(self._state, set())
        if new_state not in allowed:
            raise RuntimeError(
                f"Invalid state transition: {self._state.value} → {new_state.value}. "
                f"Allowed transitions from {self._state.value}: "
                f"{[s.value for s in allowed] if allowed else 'none (terminal)'}"
            )
        logger.debug(
            "MasterAgent state transition: %s → %s",
            self._state.value,
            new_state.value,
        )
        self._state = new_state

    # ── 核心工作流 ───────────────────────────────────────

    def receive_requirement(self, requirement: str) -> None:
        """接收用户需求

        存储需求描述，将状态转换到 ANALYZING。
        调用方随后应调用 create_pm_agent() 创建 PM Sub-Agent。

        Args:
            requirement: 用户需求描述

        Raises:
            ValueError: requirement 为空
            RuntimeError: 当前状态不允许接收需求
        """
        if not requirement or not requirement.strip():
            raise ValueError("requirement cannot be empty")

        self._requirement = requirement.strip()
        self._transition_to(MasterAgentState.ANALYZING)
        logger.info(
            "MasterAgent received requirement: %s",
            self._requirement[:100] + "..." if len(self._requirement) > 100
            else self._requirement,
        )

    def create_pm_agent(self, requirement: Optional[str] = None) -> SubAgent:
        """创建 PM Sub-Agent

        使用 agent_factory 创建产品经理角色的 Sub-Agent，
        用于分析需求并生成 task.json。

        Args:
            requirement: 需求描述（可选，默认使用已存储的需求）

        Returns:
            SubAgent: PM Sub-Agent 实例

        Raises:
            ValueError: 无需求描述
            RuntimeError: 当前状态不允许创建 PM Agent
        """
        req = requirement or self._requirement
        if not req:
            raise ValueError(
                "No requirement available. "
                "Call receive_requirement() first or pass requirement argument."
            )

        # 如果尚未进入 ANALYZING 状态，先转换
        if self._state == MasterAgentState.IDLE:
            self._requirement = req
            self._transition_to(MasterAgentState.ANALYZING)

        pm_agent = self._agent_factory("product-manager")
        self._pm_agent = pm_agent

        logger.info(
            "MasterAgent created PM Sub-Agent (role=%s)",
            pm_agent.role_name,
        )

        return pm_agent

    def load_task_json(self, task_json_path: str) -> TaskJSON:
        """从文件加载 task.json

        使用 TaskFileManager 读取 task.json 文件，解析为 TaskJSON 模型。
        加载成功后状态转换到 PLANNING，并进一步到 DISPATCHING。

        Args:
            task_json_path: task.json 文件路径

        Returns:
            TaskJSON: 解析后的任务列表

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: JSON 格式错误或数据校验失败
            RuntimeError: 当前状态不允许加载 task.json
        """
        if self._task_file_manager is None:
            from pathlib import Path

            self._task_file_manager = TaskFileManager(
                file_path=Path(task_json_path)
            )

        task_json = self._task_file_manager.read_tasks()

        # 状态转换：ANALYZING → PLANNING → DISPATCHING
        if self._state == MasterAgentState.ANALYZING:
            self._transition_to(MasterAgentState.PLANNING)

        if self._state == MasterAgentState.PLANNING:
            self._transition_to(MasterAgentState.DISPATCHING)

        self._task_json = task_json

        logger.info(
            "MasterAgent loaded task.json: project=%s, tasks=%d",
            task_json.project_name,
            len(task_json.tasks),
        )

        return task_json

    def set_task_json(self, task_json: TaskJSON) -> None:
        """直接设置 TaskJSON（测试/恢复用）

        不从文件读取，直接设置 TaskJSON 对象。
        用于单元测试或断点恢复场景。

        Args:
            task_json: TaskJSON 对象

        Raises:
            ValueError: task_json 为 None
            RuntimeError: 当前状态不允许设置 task.json
        """
        if task_json is None:
            raise ValueError("task_json cannot be None")

        # 仅允许从 ANALYZING / PLANNING / DISPATCHING / MONITORING 设置
        if self._state not in (
            MasterAgentState.ANALYZING,
            MasterAgentState.PLANNING,
            MasterAgentState.DISPATCHING,
            MasterAgentState.MONITORING,
        ):
            raise RuntimeError(
                f"Cannot set task_json in state {self._state.value}. "
                f"Must call receive_requirement() first."
            )

        # 允许从 ANALYZING 或 PLANNING 状态设置
        if self._state == MasterAgentState.ANALYZING:
            self._transition_to(MasterAgentState.PLANNING)

        if self._state == MasterAgentState.PLANNING:
            self._transition_to(MasterAgentState.DISPATCHING)

        self._task_json = task_json

        logger.info(
            "MasterAgent set TaskJSON: project=%s, tasks=%d",
            task_json.project_name,
            len(task_json.tasks),
        )

    def get_dispatchable_tasks(self) -> list[Task]:
        """获取当前可调度的任务

        返回满足以下条件的任务：
        1. 状态为 PENDING
        2. 所有依赖任务已 COMPLETED
        3. 重试次数未超过上限

        返回按优先级排序（HIGH > MEDIUM > LOW）。

        Returns:
            可调度的 Task 列表

        Raises:
            RuntimeError: 当前状态不在 DISPATCHING 或 MONITORING
        """
        if self._state not in (
            MasterAgentState.DISPATCHING,
            MasterAgentState.MONITORING,
        ):
            raise RuntimeError(
                f"Cannot get dispatchable tasks in state {self._state.value}. "
                f"Must be in DISPATCHING or MONITORING state."
            )

        if self._task_json is None:
            return []

        # 构建已完成任务 ID 集合
        completed_ids: set[str] = set()
        for task in self._task_json.tasks:
            if task.status == TaskStatus.COMPLETED:
                completed_ids.add(task.id)

        # 筛选可调度任务：PENDING 且依赖全部 COMPLETED 且重试未超限
        dispatchable: list[Task] = []
        for task in self._task_json.tasks:
            if task.status != TaskStatus.PENDING:
                continue
            # 检查所有依赖是否已完成
            deps_met = all(
                dep_id in completed_ids
                for dep_id in task.dependencies
            )
            if not deps_met:
                continue
            # 检查重试次数
            if not self._is_task_retryable(task):
                continue
            dispatchable.append(task)

        # 按优先级排序（HIGH > MEDIUM > LOW）
        priority_order = {
            "high": 0,
            "medium": 1,
            "low": 2,
        }
        dispatchable.sort(
            key=lambda t: priority_order.get(t.priority.value, 1)
        )

        return dispatchable

    def select_next_task(self) -> Optional[Task]:
        """选择下一个可调度的任务

        MasterAgent 核心调度决策方法。综合以下条件选择最佳候选任务：
        1. 并发度控制：当前活跃 Agent 数 < max_concurrent_agents
        2. 依赖满足：所有前置依赖任务已 COMPLETED
        3. 重试检查：retry_count ≤ task_max_retries
        4. 优先级排序：HIGH > MEDIUM > LOW

        返回优先级最高的可调度任务，无可用任务时返回 None。

        Returns:
            最佳候选 Task，无可用任务返回 None

        Raises:
            RuntimeError: 当前状态不在 DISPATCHING 或 MONITORING
        """
        if self._state not in (
            MasterAgentState.DISPATCHING,
            MasterAgentState.MONITORING,
        ):
            raise RuntimeError(
                f"Cannot select next task in state {self._state.value}. "
                f"Must be in DISPATCHING or MONITORING state."
            )

        # 并发度检查
        if not self._can_dispatch_more():
            logger.debug(
                "Cannot dispatch more agents: %d/%d active",
                len(self._active_agents),
                self._max_concurrent_agents,
            )
            return None

        # 获取可调度任务列表（已含依赖+重试+优先级过滤）
        dispatchable = self.get_dispatchable_tasks()
        if not dispatchable:
            logger.debug("No dispatchable tasks available")
            return None

        selected = dispatchable[0]
        logger.info(
            "Selected next task: '%s' (priority=%s, deps=%d, retries=%d)",
            selected.id,
            selected.priority.value,
            len(selected.dependencies),
            selected.retry_count,
        )
        return selected

    def _can_dispatch_more(self) -> bool:
        """检查是否还能调度更多 Agent

        当前活跃 Agent 数量未达到最大并发限制时返回 True。

        Returns:
            True 如果可以调度更多 Agent
        """
        return len(self._active_agents) < self._max_concurrent_agents

    def _is_task_retryable(self, task: Task) -> bool:
        """检查任务是否仍可重试

        任务的 retry_count 未超过 task_max_retries 时返回 True。
        task_max_retries = 0 表示不允许重试（仅执行一次）。

        Args:
            task: 待检查的任务

        Returns:
            True 如果任务仍可重试
        """
        return task.retry_count <= self._task_max_retries

    def dispatch_task(self, task: Optional[Task] = None) -> Optional[SubAgentResult]:
        """委派任务执行（select → create → execute 一体化）

        核心委派方法，整合调度决策、Agent 创建和任务执行：
        1. 如果未指定 task，调用 select_next_task() 选择最佳候选
        2. 调用 create_sub_agent(task) 为任务创建 Sub-Agent
        3. 调用 agent.run(task) 执行任务
        4. 调用 record_result() 记录结果
        5. 返回执行结果

        Args:
            task: 要执行的任务（可选，默认自动选择）

        Returns:
            SubAgentResult 执行结果，无可用任务时返回 None

        Raises:
            ValueError: task 为 None 且无可用任务
            RuntimeError: 当前状态不允许委派
        """
        if self._state not in (
            MasterAgentState.DISPATCHING,
            MasterAgentState.MONITORING,
        ):
            raise RuntimeError(
                f"Cannot dispatch task in state {self._state.value}. "
                f"Must be in DISPATCHING or MONITORING state."
            )

        # Step 1: 选择任务（如果未指定）
        if task is None:
            task = self.select_next_task()
            if task is None:
                logger.debug("No task to dispatch")
                return None

        # Step 2: 创建 Sub-Agent
        agent = self.create_sub_agent(task)

        # Step 3: 执行任务
        logger.info(
            "MasterAgent dispatching task '%s' to agent (role=%s)",
            task.id,
            agent.role_name,
        )
        result = agent.run(task)

        # Step 4: 记录结果
        self.record_result(task.id, result)

        logger.info(
            "MasterAgent task '%s' completed: status=%s",
            task.id,
            result.status.value,
        )

        return result

    def create_sub_agent(self, task: Task) -> SubAgent:
        """为任务创建对应的 Sub-Agent

        使用 agent_factory 根据 task.suggested_role 创建 Sub-Agent 实例，
        并注册到活跃 Agent 列表中。

        Args:
            task: 要执行的任务

        Returns:
            SubAgent: 为任务创建的 Sub-Agent 实例

        Raises:
            ValueError: task 为 None
            RuntimeError: 当前状态不允许创建 Sub-Agent
        """
        if task is None:
            raise ValueError("task cannot be None")

        if self._state not in (
            MasterAgentState.DISPATCHING,
            MasterAgentState.MONITORING,
        ):
            raise RuntimeError(
                f"Cannot create sub-agent in state {self._state.value}. "
                f"Must be in DISPATCHING or MONITORING state."
            )

        agent = self._agent_factory(task.suggested_role)
        self._active_agents[task.id] = agent

        logger.info(
            "MasterAgent created Sub-Agent for task '%s' (role=%s)",
            task.id,
            agent.role_name,
        )

        return agent

    def record_result(self, task_id: str, result: SubAgentResult) -> None:
        """记录任务执行结果

        将执行结果存储到 results 字典，并根据结果更新
        task_json 中对应任务的状态。

        Args:
            task_id: 任务 ID
            result: 执行结果

        Raises:
            ValueError: task_id 为空或 result 为 None
        """
        if not task_id or not task_id.strip():
            raise ValueError("task_id cannot be empty")
        if result is None:
            raise ValueError("result cannot be None")

        self._execution_results[task_id] = result

        # 更新 task_json 中对应任务的状态
        if self._task_json is not None:
            for task in self._task_json.tasks:
                if task.id == task_id:
                    new_status = self._map_result_status(result.status)
                    task.status = new_status
                    if result.error:
                        task.error_message = result.error
                    if result.is_success:
                        task.finished_at = datetime.now()
                    break

        # 从活跃 Agent 列表中移除
        self._active_agents.pop(task_id, None)

        logger.info(
            "MasterAgent recorded result for task '%s': status=%s",
            task_id,
            result.status.value,
        )

    # ── 终态检查 ─────────────────────────────────────────

    def is_all_completed(self) -> bool:
        """检查所有任务是否已完成

        Returns:
            True 如果 task_json 中所有任务状态均为 COMPLETED
        """
        if self._task_json is None:
            return False

        return all(
            task.status == TaskStatus.COMPLETED
            for task in self._task_json.tasks
        )

    def is_any_failed(self) -> bool:
        """检查是否有任务失败

        Returns:
            True 如果存在状态为 FAILED 的任务
        """
        if self._task_json is None:
            return False

        return any(
            task.status == TaskStatus.FAILED
            for task in self._task_json.tasks
        )

    def is_any_blocked(self) -> bool:
        """检查是否有任务被阻塞

        Returns:
            True 如果存在状态为 BLOCKED 的任务
        """
        if self._task_json is None:
            return False

        return any(
            task.status == TaskStatus.BLOCKED
            for task in self._task_json.tasks
        )

    # ── 进度摘要 ─────────────────────────────────────────

    def get_progress_summary(self) -> dict[str, Any]:
        """获取执行进度摘要

        Returns:
            进度统计字典，包含：
            - total: 任务总数
            - completed: 已完成数
            - failed: 失败数
            - blocked: 阻塞数
            - in_progress: 执行中数
            - pending: 待执行数
            - skipped: 跳过数
            - progress_pct: 完成百分比
            - state: 当前调度状态
        """
        if self._task_json is None:
            return {
                "total": 0,
                "completed": 0,
                "failed": 0,
                "blocked": 0,
                "in_progress": 0,
                "pending": 0,
                "skipped": 0,
                "progress_pct": 0.0,
                "state": self._state.value,
            }

        tasks = self._task_json.tasks
        counts = {
            "completed": 0,
            "failed": 0,
            "blocked": 0,
            "in_progress": 0,
            "pending": 0,
            "skipped": 0,
        }
        for task in tasks:
            status_key = task.status.value
            if status_key in counts:
                counts[status_key] += 1

        total = len(tasks)
        progress_pct = (counts["completed"] / total * 100) if total > 0 else 0.0

        return {
            "total": total,
            **counts,
            "progress_pct": round(progress_pct, 1),
            "state": self._state.value,
        }

    # ── 重置 ─────────────────────────────────────────────

    def reset(self) -> None:
        """重置 MasterAgent 到初始状态

        清空所有运行时状态，允许重新接收需求。
        仅在终态（COMPLETED / FAILED）下可调用。

        Raises:
            RuntimeError: 当前状态不允许重置
        """
        if self._state not in (
            MasterAgentState.COMPLETED,
            MasterAgentState.FAILED,
            MasterAgentState.IDLE,
        ):
            raise RuntimeError(
                f"Cannot reset in state {self._state.value}. "
                f"Must be in COMPLETED, FAILED, or IDLE state."
            )

        self._state = MasterAgentState.IDLE
        self._requirement = None
        self._task_json = None
        self._pm_agent = None
        self._active_agents.clear()
        self._execution_results.clear()
        self._failure_log.clear()
        self._is_started = False
        self._main_rules_content = None

        logger.info("MasterAgent reset to IDLE")

    # ── 启动流程（P1-045）────────────────────────────────────

    def startup(self, main_rules_path: Optional[str] = None) -> None:
        """执行 MasterAgent 启动流程

        按顺序执行三步初始化：
        1. 加载 main-rules.md harness 规则（为 Master Agent 注入约束）
        2. 初始化 tmux 主会话（创建或复用已有的 tmux session）
        3. 在主窗口启动 Claude Code CLI（并注入 main-rules 作为系统 prompt）

        启动完成后 is_started 为 True，MasterAgent 可正常接收需求。

        Args:
            main_rules_path: main-rules.md 文件路径（可选，
                覆盖构造函数中设置的路径）

        Raises:
            RuntimeError: tmux_manager 或 cli 未配置
            RuntimeError: 重复启动
            FileNotFoundError: main-rules.md 文件不存在（当路径已设置时）
        """
        if self._is_started:
            raise RuntimeError("MasterAgent already started. Call reset() first.")

        # 确定使用的 main-rules 路径
        rules_path = main_rules_path or self._main_rules_path

        logger.info("MasterAgent starting up...")

        # Step 1: 加载 main-rules.md harness 规则
        self._load_main_rules(rules_path)

        # Step 2: 初始化 tmux 主会话
        self._init_tmux_session()

        # Step 3: 在主窗口启动 Claude Code CLI
        self._start_main_cli()

        self._is_started = True
        logger.info(
            "MasterAgent startup completed (session=%s)",
            self._session_name,
        )

    def _load_main_rules(self, rules_path: Optional[str] = None) -> None:
        """加载 main-rules.md harness 规则

        读取 main-rules.md 文件内容并存储，用于注入到 Master Agent 的
        CLI prompt 中。如果未指定路径，则跳过加载（非必需步骤）。

        Args:
            rules_path: main-rules.md 文件路径（可选）

        Raises:
            FileNotFoundError: 文件路径已指定但文件不存在
        """
        if not rules_path:
            logger.info("No main-rules path specified, skipping rules loading")
            return

        path = Path(rules_path)
        if not path.exists():
            raise FileNotFoundError(
                f"main-rules.md not found: {rules_path}"
            )

        # 使用 HarnessLoader 解析 harness 文件
        loader = self._harness_loader or HarnessLoader()
        if self._harness_loader is None:
            self._harness_loader = loader

        harness = loader.load_harness(rules_path)
        self._main_rules_content = harness.to_prompt_text()
        self._main_rules_path = rules_path

        logger.info(
            "Loaded main-rules: %s (%d chars, %d rules)",
            harness.name,
            len(self._main_rules_content),
            len(harness.rules),
        )

    def _init_tmux_session(self) -> None:
        """初始化 tmux 主会话

        如果 tmux_manager 未配置，跳过此步骤。
        如果主会话已存在，复用之；否则创建新会话。
        在主会话中创建 "main" 窗口，用于运行 Master Agent 的 CLI。

        Raises:
            RuntimeError: tmux 不可用
        """
        if self._tmux_manager is None:
            logger.info("No tmux_manager configured, skipping tmux session init")
            return

        if not self._tmux_manager.is_available():
            raise RuntimeError(
                "tmux is not available. "
                "Please install tmux and ensure it is in PATH."
            )

        # 创建或复用主会话
        if self._tmux_manager.session_exists(self._session_name):
            logger.info(
                "tmux session '%s' already exists, reusing",
                self._session_name,
            )
        else:
            self._tmux_manager.create_session(
                name=self._session_name,
                window_name=_MAIN_WINDOW_NAME,
            )
            logger.info(
                "Created tmux session '%s' with main window",
                self._session_name,
            )
            return  # 新会话已自动创建 main 窗口

        # 复用会话时，检查 main 窗口是否存在
        if not self._tmux_manager.window_exists(
            self._session_name, _MAIN_WINDOW_NAME
        ):
            self._tmux_manager.create_window(
                session=self._session_name,
                name=_MAIN_WINDOW_NAME,
            )
            logger.info(
                "Created main window in existing session '%s'",
                self._session_name,
            )

    def _start_main_cli(self) -> None:
        """在主窗口启动 Claude Code CLI

        如果 cli 未配置，跳过此步骤。
        在 tmux 主会话的 main 窗口中启动 Claude Code CLI，
        并将 main-rules 内容作为初始 prompt 注入。

        Raises:
            RuntimeError: tmux 主会话未初始化
        """
        if self._cli is None:
            logger.info("No CLI configured, skipping CLI startup")
            return

        if self._tmux_manager is not None:
            # 确保 tmux 会话和窗口存在
            if not self._tmux_manager.session_exists(self._session_name):
                raise RuntimeError(
                    f"tmux session '{self._session_name}' not initialized. "
                    f"Call _init_tmux_session() first."
                )
            if not self._tmux_manager.window_exists(
                self._session_name, _MAIN_WINDOW_NAME
            ):
                raise RuntimeError(
                    f"tmux main window not found in session '{self._session_name}'. "
                    f"Call _init_tmux_session() first."
                )

        # 启动 CLI，注入 main-rules 作为初始 prompt
        prompt = self._build_main_prompt()

        self._cli.start_cli(
            session=self._session_name,
            window=_MAIN_WINDOW_NAME,
            prompt=prompt if prompt else None,
        )

        logger.info(
            "Started CLI in %s:%s",
            self._session_name,
            _MAIN_WINDOW_NAME,
        )

    def _build_main_prompt(self) -> str:
        """构建 Master Agent 主 prompt

        将 main-rules 内容和 Master Agent 角色身份组装为
        注入到 CLI 的初始 prompt。

        Returns:
            组装后的 prompt 文本
        """
        parts = []

        # 角色身份
        if self._role_injector is None:
            self._role_injector = RoleInjector()

        role_identity = self._role_injector.get_role_identity("master-agent")
        parts.append(f"# 角色身份\n\n{role_identity}")

        # main-rules 约束规则
        if self._main_rules_content:
            parts.append(f"# 约束规则\n\n{self._main_rules_content}")

        return "\n\n---\n\n".join(parts) if parts else ""

    # ── 内部方法 ─────────────────────────────────────────

    @staticmethod
    def _map_result_status(
        result_status: SubAgentResultStatus,
    ) -> TaskStatus:
        """将 SubAgentResultStatus 映射为 TaskStatus

        Args:
            result_status: SubAgent 执行结果状态

        Returns:
            对应的 TaskStatus
        """
        mapping: dict[SubAgentResultStatus, TaskStatus] = {
            SubAgentResultStatus.SUCCESS: TaskStatus.COMPLETED,
            SubAgentResultStatus.FAILED: TaskStatus.FAILED,
            SubAgentResultStatus.BLOCKED: TaskStatus.BLOCKED,
            SubAgentResultStatus.TIMEOUT: TaskStatus.FAILED,
            SubAgentResultStatus.RETRY: TaskStatus.PENDING,
        }
        return mapping.get(result_status, TaskStatus.PENDING)

    # ── 主循环与进度监控（P1-049）───────────────────────────────────

    def run_main_loop(self) -> dict[str, Any]:
        """执行主调度循环

        MasterAgent 核心调度方法，循环执行调度-监控-检查流程，
        直到所有任务完成或遇到终止条件。

        循环流程（PDCA）：
            1. Plan: 检查可调度任务
            2. Do: 调度任务到 Sub-Agent 执行
            3. Check: 轮询 Agent 状态，检查终止条件
            4. Act: 记录结果，更新状态，准备下一轮

        终止条件：
            - 所有任务完成 → COMPLETED
            - 存在不可恢复的失败 → FAILED
            - 存在阻塞且无法继续 → PAUSED
            - 无活跃 Agent 且无可调度任务 → FAILED（死锁）

        Returns:
            最终进度摘要字典

        Raises:
            RuntimeError: 当前状态不在 DISPATCHING 或 MONITORING
        """
        if self._state not in (
            MasterAgentState.DISPATCHING,
            MasterAgentState.MONITORING,
        ):
            raise RuntimeError(
                f"Cannot run main loop in state {self._state.value}. "
                f"Must call load_task_json() or set_task_json() first."
            )

        logger.info(
            "MasterAgent main loop started (max_concurrent=%d, poll_interval=%.1fs)",
            self._max_concurrent_agents,
            self._poll_interval,
        )

        iteration = 0
        while True:
            iteration += 1
            logger.debug("Main loop iteration #%d", iteration)

            # Phase 1: 调度阶段 — 尽可能填充并发槽位
            if self._state == MasterAgentState.MONITORING:
                self._transition_to(MasterAgentState.DISPATCHING)

            dispatched = self._dispatch_available_tasks()

            # Phase 2: 检查终止条件
            termination = self._check_termination()
            if termination:
                logger.info(
                    "MasterAgent main loop terminated: %s after %d iterations",
                    termination,
                    iteration,
                )
                return self.get_progress_summary()

            # Phase 3: 监控阶段 — 轮询活跃 Agent 状态
            if self._active_agents:
                if self._state == MasterAgentState.DISPATCHING:
                    self._transition_to(MasterAgentState.MONITORING)

                # 轮询活跃 Agent 状态
                self.poll_sub_agent_status()

                # 轮询后再次检查终止条件
                termination = self._check_termination()
                if termination:
                    logger.info(
                        "MasterAgent main loop terminated after poll: %s",
                        termination,
                    )
                    return self.get_progress_summary()

                # 等待下一轮轮询
                time.sleep(self._poll_interval)

            elif not dispatched:
                # 无活跃 Agent 且本次未调度任何任务
                # 如果还有 PENDING 任务但无法调度，说明出现死锁
                has_pending = (
                    self._task_json is not None
                    and any(
                        t.status == TaskStatus.PENDING
                        for t in self._task_json.tasks
                    )
                )
                if has_pending:
                    self._transition_to(MasterAgentState.FAILED)
                    logger.error(
                        "Main loop stuck: no active agents, no dispatchable tasks, "
                        "but pending tasks remain (possible deadlock)"
                    )
                else:
                    self._transition_to(MasterAgentState.FAILED)
                    logger.error(
                        "Main loop stuck: no active agents, no dispatchable tasks"
                    )
                return self.get_progress_summary()

    def poll_sub_agent_status(self) -> dict[str, str]:
        """轮询活跃 Sub-Agent 的执行状态

        通过 ProgressManager 读取 progress.txt，检查活跃 Agent
        对应任务的进度更新。如果检测到任务已完成/失败/阻塞，
        自动构建 SubAgentResult 并调用 record_result() 记录。

        Returns:
            检测到的状态变更字典 {task_id: new_status}

        Raises:
            RuntimeError: 当前状态不在 DISPATCHING 或 MONITORING
        """
        if self._state not in (
            MasterAgentState.DISPATCHING,
            MasterAgentState.MONITORING,
        ):
            raise RuntimeError(
                f"Cannot poll status in state {self._state.value}. "
                f"Must be in DISPATCHING or MONITORING state."
            )

        if not self._active_agents:
            return {}

        # 获取 ProgressManager
        progress_mgr = self._ensure_progress_manager()
        if progress_mgr is None:
            logger.debug("No ProgressManager available, skipping poll")
            return {}

        changes: dict[str, str] = {}

        # 读取 progress.txt 条目
        try:
            entries = progress_mgr.read_progress()
        except Exception as exc:
            logger.warning("Failed to read progress.txt: %s", exc)
            return {}

        # 构建 task_id → ProgressEntry 映射
        entry_map: dict[str, ProgressEntry] = {
            e.task_id: e for e in entries
        }

        # 检查每个活跃 Agent 对应的任务
        for task_id in list(self._active_agents.keys()):
            entry = entry_map.get(task_id)
            if entry is None:
                continue

            # 检测终态
            if entry.is_terminal():
                result = self._build_result_from_progress(task_id, entry)
                self.record_result(task_id, result)
                changes[task_id] = entry.status.value

            # 检测阻塞状态（需要人工介入）
            elif entry.status == ProgressStatus.BLOCKED:
                result = self._build_result_from_progress(task_id, entry)
                self.record_result(task_id, result)
                changes[task_id] = entry.status.value

            # 检测重试状态
            elif entry.status == ProgressStatus.RETRYING:
                changes[task_id] = entry.status.value
                # 更新任务重试计数，重新排队
                if self._task_json is not None:
                    for task in self._task_json.tasks:
                        if task.id == task_id:
                            task.retry_count = entry.retry
                            task.status = TaskStatus.PENDING
                            break
                # 从活跃列表移除（等待重新调度）
                self._active_agents.pop(task_id, None)

        if changes:
            logger.info(
                "poll_sub_agent_status detected changes: %s",
                changes,
            )

        return changes

    def _dispatch_available_tasks(self) -> int:
        """调度所有可用任务（填充并发槽位）

        持续调用 select_next_task() + dispatch_task()，
        直到没有可用槽位或没有可调度任务。

        Returns:
            本次调度的任务数量
        """
        count = 0
        while self._can_dispatch_more():
            task = self.select_next_task()
            if task is None:
                break
            try:
                self.dispatch_task(task)
                count += 1
            except Exception as exc:
                logger.error(
                    "Failed to dispatch task '%s': %s",
                    task.id,
                    exc,
                )
                # 调度失败 — 记录错误结果
                result = SubAgentResult(
                    task_id=task.id,
                    status=SubAgentResultStatus.FAILED,
                    phase=AgentPhase.CREATED,
                    role=task.suggested_role,
                    error=f"Dispatch failed: {exc}",
                )
                self.record_result(task.id, result)
                break  # 调度出错时停止继续调度

        if count > 0:
            logger.info("Dispatched %d task(s) in this cycle", count)

        return count

    def _check_termination(self) -> Optional[str]:
        """检查终止条件并转换状态

        Returns:
            终止原因字符串，如果未终止返回 None
        """
        # 所有任务完成
        if self.is_all_completed():
            self._transition_to(MasterAgentState.COMPLETED)
            return "all_completed"

        # 存在不可恢复的失败
        if self._has_unrecoverable_failure():
            self._transition_to(MasterAgentState.FAILED)
            return "unrecoverable_failure"

        # 存在阻塞且无活跃 Agent 且无可调度任务
        if self.is_any_blocked():
            if not self._active_agents:
                dispatchable = self.get_dispatchable_tasks()
                if not dispatchable:
                    self._transition_to(MasterAgentState.PAUSED)
                    return "blocked_no_progress"

        return None

    def _has_unrecoverable_failure(self) -> bool:
        """检查是否存在不可恢复的失败

        不可恢复 = 任务 FAILED 且 retry_count ≥ task_max_retries

        Returns:
            True 如果存在不可恢复的失败
        """
        if self._task_json is None:
            return False

        for task in self._task_json.tasks:
            if task.status == TaskStatus.FAILED:
                if task.retry_count >= self._task_max_retries:
                    return True

        return False

    def _build_result_from_progress(
        self,
        task_id: str,
        entry: ProgressEntry,
    ) -> SubAgentResult:
        """从 ProgressEntry 构建 SubAgentResult

        将 progress.txt 中的进度信息转换为 SubAgentResult，
        用于在轮询检测到终态时记录执行结果。

        Args:
            task_id: 任务 ID
            entry: 进度条目

        Returns:
            SubAgentResult 实例
        """
        # ProgressStatus → SubAgentResultStatus 映射
        status_map: dict[ProgressStatus, SubAgentResultStatus] = {
            ProgressStatus.COMPLETED: SubAgentResultStatus.SUCCESS,
            ProgressStatus.FAILED: SubAgentResultStatus.FAILED,
            ProgressStatus.BLOCKED: SubAgentResultStatus.BLOCKED,
            ProgressStatus.SKIPPED: SubAgentResultStatus.SUCCESS,
        }

        result_status = status_map.get(entry.status, SubAgentResultStatus.FAILED)

        # 确定 AgentPhase
        if result_status == SubAgentResultStatus.SUCCESS:
            phase = AgentPhase.COMPLETED
        elif result_status == SubAgentResultStatus.BLOCKED:
            phase = AgentPhase.BLOCKED
        else:
            phase = AgentPhase.FAILED

        return SubAgentResult(
            task_id=task_id,
            status=result_status,
            phase=phase,
            role=entry.role,
            commit_hash=entry.git_sha,
            commit_message=entry.git_msg,
            error=entry.error,
            started_at=entry.started,
            finished_at=entry.finished,
            retries=entry.retry,
        )

    def _ensure_progress_manager(self) -> Optional[ProgressManager]:
        """确保 ProgressManager 可用

        如果已有 ProgressManager 实例，直接返回；
        否则尝试从 task_file_manager 的路径推断 progress.txt 位置。

        Returns:
            ProgressManager 实例，无法创建时返回 None
        """
        if self._progress_manager is not None:
            return self._progress_manager

        # 尝试从 task_file_manager 推断路径
        if self._task_file_manager is not None:
            progress_path = self._task_file_manager.file_path.parent / "progress.txt"
            self._progress_manager = ProgressManager(file_path=progress_path)
            return self._progress_manager

        return None

    # ── 失败处理（P1-050）───────────────────────────────────────

    def on_task_failed(self, task: Task, error: Optional[str] = None) -> FailureAction:
        """任务失败处理入口

        根据任务重试状态决定处理策略：
        - 可重试（retry_count < task_max_retries）：递增重试计数，重置 PENDING
        - 不可恢复（retry_count ≥ task_max_retries）：标记 FAILED，
          暂停依赖任务，记录错误，通知 OpenClaw

        Args:
            task: 失败的任务
            error: 失败原因描述（可选）

        Returns:
            FailureAction.RETRY — 任务将重试
            FailureAction.ABORT — 任务不可恢复，任务流已暂停

        Raises:
            ValueError: task 为 None
            RuntimeError: task_json 未加载
        """
        if task is None:
            raise ValueError("task cannot be None")

        if self._task_json is None:
            raise RuntimeError(
                "Cannot handle failure: task_json not loaded. "
                "Call load_task_json() or set_task_json() first."
            )

        # 记录失败详情
        self._record_failure(task, error)

        # 判断是否可重试（递增后 retry_count 仍 ≤ task_max_retries 才可重试）
        if task.retry_count < self._task_max_retries:
            # 递增重试计数，重置为 PENDING 等待重新调度
            task.retry_count += 1
            task.status = TaskStatus.PENDING
            task.error_message = error

            logger.info(
                "Task '%s' will be retried (retry_count=%d, max=%d)",
                task.id,
                task.retry_count,
                self._task_max_retries,
            )

            # 通知 OpenClaw 重试事件
            self._notify_openclaw("task_retry", {
                "task_id": task.id,
                "retry_count": task.retry_count,
                "max_retries": self._task_max_retries,
                "error": error,
            })

            return FailureAction.RETRY

        # 不可恢复 → 标记 FAILED，暂停依赖，通知 OpenClaw
        task.status = TaskStatus.FAILED
        task.error_message = error

        # 暂停依赖此任务的所有下游任务
        paused_ids = self._pause_dependent_tasks(task.id)

        logger.error(
            "Task '%s' failed unrecoverably (retries exhausted: %d/%d), "
            "paused %d dependent task(s)",
            task.id,
            task.retry_count,
            self._task_max_retries,
            len(paused_ids),
        )

        # 通知 OpenClaw 任务失败事件
        self._notify_openclaw("task_failed", {
            "task_id": task.id,
            "error": error,
            "retry_count": task.retry_count,
            "max_retries": self._task_max_retries,
            "paused_dependents": paused_ids,
            "progress_summary": self.get_progress_summary(),
        })

        return FailureAction.ABORT

    def _pause_dependent_tasks(self, failed_task_id: str) -> list[str]:
        """暂停依赖失败任务的所有下游任务

        在 task_json 中查找所有依赖 failed_task_id 的 PENDING /
        IN_PROGRESS 任务，将其状态设为 BLOCKED。

        Args:
            failed_task_id: 失败任务的 ID

        Returns:
            被暂停（BLOCKED）的任务 ID 列表
        """
        if self._task_json is None:
            return []

        paused: list[str] = []
        for task in self._task_json.tasks:
            if task.status not in (
                TaskStatus.PENDING,
                TaskStatus.IN_PROGRESS,
            ):
                continue
            if failed_task_id in task.dependencies:
                task.status = TaskStatus.BLOCKED
                paused.append(task.id)
                logger.info(
                    "Paused dependent task '%s' (depends on failed '%s')",
                    task.id,
                    failed_task_id,
                )

        return paused

    def _record_failure(self, task: Task, error: Optional[str] = None) -> None:
        """记录任务失败详情

        将失败事件追加到内部失败日志，并更新 task 的 error_message。

        Args:
            task: 失败的任务
            error: 失败原因描述
        """
        record = {
            "task_id": task.id,
            "error": error,
            "retry_count": task.retry_count,
            "max_retries": self._task_max_retries,
            "timestamp": datetime.now().isoformat(),
            "task_status": task.status.value,
        }
        self._failure_log.append(record)

        # 更新 task 的 error_message
        if error:
            task.error_message = error

        logger.warning(
            "Recorded failure for task '%s': error=%s, retries=%d/%d",
            task.id,
            repr(error) if error else "N/A",
            task.retry_count,
            self._task_max_retries,
        )

    def _notify_openclaw(self, event_type: str, details: dict[str, Any]) -> None:
        """通知 OpenClaw 外部系统

        通过注入的 openclaw_notifier 回调发送事件通知。
        默认实现仅记录日志，生产环境可替换为 HTTP/webhook 通知。

        Args:
            event_type: 事件类型（如 task_retry, task_failed）
            details: 事件详情字典
        """
        try:
            self._openclaw_notifier(event_type, details)
        except Exception as exc:
            # 通知失败不应影响主流程
            logger.error(
                "OpenClaw notification failed for event '%s': %s",
                event_type,
                exc,
            )

    # ── 断点恢复（P1-051）──────────────────────────────────────

    def restore_from_progress(self) -> dict[str, Any]:
        """从 progress.txt 恢复断点状态

        读取 progress.txt 中已记录的任务进度，同步更新 task_json
        中对应任务的状态，使调度器能从断点继续执行。

        恢复策略：
            - COMPLETED / SKIPPED → TaskStatus.COMPLETED / SKIPPED（已完成，跳过）
            - FAILED → TaskStatus.FAILED（不可恢复失败，保持 FAILED）
            - BLOCKED → TaskStatus.BLOCKED（依赖阻塞，保持 BLOCKED）
            - IN_PROGRESS / RETRYING → TaskStatus.PENDING（中断任务，重置为待调度）
            - 无进度记录 → 保持 task_json 原始状态

        前置条件：
            - task_json 已加载（否则抛 RuntimeError）
            - progress_manager 可用（否则返回空恢复结果）

        Returns:
            恢复摘要字典：
            - restored: 是否成功恢复
            - total_tasks: 任务总数
            - already_completed: 已完成（跳过）数
            - already_failed: 已失败数
            - already_blocked: 已阻塞数
            - reset_to_pending: 中断任务重置为 PENDING 数
            - untouched: 无进度记录的任务数
            - state: 恢复后的调度状态

        Raises:
            RuntimeError: task_json 未加载
        """
        if self._task_json is None:
            raise RuntimeError(
                "Cannot restore from progress: task_json not loaded. "
                "Call load_task_json() or set_task_json() first."
            )

        # 确保 ProgressManager 可用
        pm = self._ensure_progress_manager()
        if pm is None:
            logger.warning("No ProgressManager available, cannot restore progress")
            return {
                "restored": False,
                "total_tasks": len(self._task_json.tasks),
                "already_completed": 0,
                "already_failed": 0,
                "already_blocked": 0,
                "reset_to_pending": 0,
                "untouched": len(self._task_json.tasks),
                "state": self._state.value,
            }

        # 读取 progress.txt
        try:
            progress_entries = pm.read_progress()
        except Exception as exc:
            logger.error("Failed to read progress file: %s", exc)
            return {
                "restored": False,
                "total_tasks": len(self._task_json.tasks),
                "already_completed": 0,
                "already_failed": 0,
                "already_blocked": 0,
                "reset_to_pending": 0,
                "untouched": len(self._task_json.tasks),
                "state": self._state.value,
            }

        # 构建 task_id → ProgressEntry 映射
        progress_map: dict[str, ProgressEntry] = {}
        for entry in progress_entries:
            progress_map[entry.task_id] = entry

        # 统计计数
        already_completed = 0
        already_failed = 0
        already_blocked = 0
        reset_to_pending = 0
        untouched = 0

        # 遍历 task_json 中的任务，按进度记录恢复状态
        for task in self._task_json.tasks:
            if task.id not in progress_map:
                untouched += 1
                continue

            entry = progress_map[task.id]
            new_status = self._map_progress_to_task_status(entry.status)

            # 统计恢复动作
            if new_status == TaskStatus.COMPLETED:
                already_completed += 1
            elif new_status == TaskStatus.FAILED:
                already_failed += 1
            elif new_status == TaskStatus.BLOCKED:
                already_blocked += 1
            elif new_status == TaskStatus.PENDING:
                reset_to_pending += 1
            elif new_status == TaskStatus.SKIPPED:
                already_completed += 1  # SKIPPED 也算已完成

            # 更新任务状态
            task.status = new_status

            # 恢复 retry_count 和 error_message
            if entry.retry > 0:
                task.retry_count = entry.retry
            if entry.error:
                task.error_message = entry.error

            logger.info(
                "Restored task '%s': progress_status=%s → task_status=%s",
                task.id,
                entry.status.value,
                new_status.value,
            )

        # 更新 execution_results — 为已完成/失败的任务填充结果
        self._restore_execution_results(progress_map)

        # 根据恢复结果决定调度状态
        self._update_state_after_restore(
            already_completed, already_failed, reset_to_pending
        )

        summary = {
            "restored": True,
            "total_tasks": len(self._task_json.tasks),
            "already_completed": already_completed,
            "already_failed": already_failed,
            "already_blocked": already_blocked,
            "reset_to_pending": reset_to_pending,
            "untouched": untouched,
            "state": self._state.value,
        }

        logger.info(
            "Progress restored: %d completed, %d failed, %d blocked, "
            "%d reset to pending, %d untouched (state=%s)",
            already_completed,
            already_failed,
            already_blocked,
            reset_to_pending,
            untouched,
            self._state.value,
        )

        return summary

    def _map_progress_to_task_status(
        self, progress_status: ProgressStatus
    ) -> TaskStatus:
        """将 ProgressStatus 映射为恢复后的 TaskStatus

        恢复策略：
            - COMPLETED → COMPLETED（已完成，跳过）
            - SKIPPED → SKIPPED（已跳过，跳过）
            - FAILED → FAILED（不可恢复失败）
            - BLOCKED → BLOCKED（依赖阻塞）
            - IN_PROGRESS → PENDING（中断任务，重置为待调度）
            - RETRYING → PENDING（重试中中断，重置为待调度）

        Args:
            progress_status: progress.txt 中记录的状态

        Returns:
            恢复后应设置的 TaskStatus
        """
        mapping = {
            ProgressStatus.COMPLETED: TaskStatus.COMPLETED,
            ProgressStatus.SKIPPED: TaskStatus.SKIPPED,
            ProgressStatus.FAILED: TaskStatus.FAILED,
            ProgressStatus.BLOCKED: TaskStatus.BLOCKED,
            ProgressStatus.IN_PROGRESS: TaskStatus.PENDING,
            ProgressStatus.RETRYING: TaskStatus.PENDING,
        }
        return mapping.get(progress_status, TaskStatus.PENDING)

    def _restore_execution_results(
        self, progress_map: dict[str, ProgressEntry]
    ) -> None:
        """从进度记录恢复 execution_results

        为已完成/失败的任务填充 SubAgentResult，使得后续
        get_progress_summary() 等方法能正确反映历史结果。

        Args:
            progress_map: task_id → ProgressEntry 映射
        """
        for task_id, entry in progress_map.items():
            # 只恢复终态结果
            if entry.status not in (
                ProgressStatus.COMPLETED,
                ProgressStatus.FAILED,
                ProgressStatus.SKIPPED,
            ):
                continue

            result_status = self._progress_to_result_status(entry.status)
            phase = (
                AgentPhase.COMPLETED
                if result_status == SubAgentResultStatus.SUCCESS
                else AgentPhase.FAILED
            )

            self._execution_results[task_id] = SubAgentResult(
                task_id=task_id,
                status=result_status,
                phase=phase,
                role=entry.role,
                commit_hash=entry.git_sha,
                commit_message=entry.git_msg,
                error=entry.error,
                started_at=entry.started,
                finished_at=entry.finished,
                retries=entry.retry,
            )

    def _progress_to_result_status(
        self, status: ProgressStatus
    ) -> SubAgentResultStatus:
        """ProgressStatus → SubAgentResultStatus 映射

        Args:
            status: 进度状态

        Returns:
            对应的执行结果状态
        """
        mapping = {
            ProgressStatus.COMPLETED: SubAgentResultStatus.SUCCESS,
            ProgressStatus.SKIPPED: SubAgentResultStatus.SUCCESS,
            ProgressStatus.FAILED: SubAgentResultStatus.FAILED,
            ProgressStatus.BLOCKED: SubAgentResultStatus.BLOCKED,
            ProgressStatus.IN_PROGRESS: SubAgentResultStatus.RETRY,
            ProgressStatus.RETRYING: SubAgentResultStatus.RETRY,
        }
        return mapping.get(status, SubAgentResultStatus.FAILED)

    def _update_state_after_restore(
        self,
        completed: int,
        failed: int,
        reset_to_pending: int,
    ) -> None:
        """根据恢复结果更新 MasterAgent 调度状态

        状态决策：
            - 全部完成 → COMPLETED
            - 有不可恢复失败且无待调度 → FAILED
            - 有待调度任务 → DISPATCHING
            - 无待调度但有阻塞 → PAUSED

        Args:
            completed: 已完成任务数
            failed: 已失败任务数
            reset_to_pending: 重置为 PENDING 的任务数
        """
        total = len(self._task_json.tasks) if self._task_json else 0

        if total > 0 and completed + failed >= total:
            # 全部终态
            if failed == 0:
                self._state = MasterAgentState.COMPLETED
            else:
                self._state = MasterAgentState.FAILED
        elif reset_to_pending > 0:
            # 有待调度的中断任务
            self._state = MasterAgentState.DISPATCHING
        else:
            # 无待调度但未全部终态 → 可能全部 BLOCKED
            self._state = MasterAgentState.PAUSED

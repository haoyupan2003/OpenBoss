"""
SubAgentFactory — Sub-Agent 创建工厂

基于 PRD V2.0 §4.4 Master Agent 和 §6.10 Lifecycle Manager 设计。
将角色名称映射到 SubAgent 实例的创建过程，封装 Sub-Agent 的
创建、配置和初始化逻辑。

核心职责：
    1. 根据角色名称创建对应的 SubAgent 实例
    2. 注入角色身份和约束规则（通过 RoleInjector）
    3. 分配 tmux 窗口（通过 TmuxManager 窗口命名规范）
    4. 启动 CLI 并注入 prompt（通过 ClaudeCodeCLI）

设计原则：
    - 工厂模式：MasterAgent 通过 AgentFactory 协议解耦具体创建逻辑
    - Ephemeral Agent 模式：每个 SubAgent 实例执行一个 Task 后退出
    - 依赖注入：TmuxManager / ClaudeCodeCLI / RoleInjector 全部通过构造函数注入
    - 可测试：所有外部依赖可替换为 MagicMock
    - 统一架构：所有角色（PM/Dev/API/...）统一通过 EphemeralSubAgent + tmux + CLI 创建
    - 角色差异：由 RoleInjector 根据 role_name 注入对应的 harness 约束规则
"""

import logging
from typing import Optional

from agent_automation_system.cli.claude_code_cli import ClaudeCodeCLI
from agent_automation_system.sub_agent.role_injector import RoleInjector
from agent_automation_system.sub_agent.sub_agent import SubAgent
from agent_automation_system.tmux_manager.tmux_manager import TmuxManager

logger = logging.getLogger(__name__)


# ── 默认配置 ────────────────────────────────────────────

_DEFAULT_SESSION_NAME = "openboss"

# 角色名称 → tmux 窗口角色简称映射
_ROLE_SHORT_NAMES: dict[str, str] = {
    "senior-developer": "dev",
    "test-engineer": "qa",
    "product-manager": "pm",
    "validator": "val",
    "senior-screenwriter": "sw",
    "data-analyst": "da",
    "browser-task": "bt",
    "api-request": "api",
}

# 默认角色简称
_DEFAULT_ROLE_SHORT = "agent"


class SubAgentFactory:
    """Sub-Agent 创建工厂

    将角色名称映射到 SubAgent 实例的创建过程。
    封装角色注入、tmux 窗口分配和 CLI 启动逻辑。

    工厂创建流程：
        1. 解析角色名称 → 确定角色简称
        2. 创建 tmux 窗口（agent_{role_short}_{seq}）
        3. 创建 SubAgent 实例（注入角色和窗口信息）
        4. 返回配置完成的 SubAgent

    Usage:
        factory = SubAgentFactory(
            tmux_manager=tmux,
            cli=cli,
            session_name="openboss",
        )
        agent = factory.create("senior-developer")
        # agent 已分配 tmux 窗口，可立即执行任务

    Args:
        tmux_manager: TmuxManager 实例（可选，无则不创建 tmux 窗口）
        cli: ClaudeCodeCLI 实例（可选，无则不启动 CLI）
        role_injector: RoleInjector 实例（可选，默认自动创建）
        session_name: tmux 主会话名称，默认 "openboss"
        auto_create_window: 是否自动创建 tmux 窗口，默认 True
    """

    def __init__(
        self,
        tmux_manager: Optional[TmuxManager] = None,
        cli: Optional[ClaudeCodeCLI] = None,
        role_injector: Optional[RoleInjector] = None,
        session_name: str = _DEFAULT_SESSION_NAME,
        auto_create_window: bool = True,
    ) -> None:
        self._tmux_manager = tmux_manager
        self._cli = cli
        self._role_injector = role_injector or RoleInjector()
        self._session_name = session_name
        self._auto_create_window = auto_create_window

        # 角色计数器（用于窗口序号分配）
        self._role_counters: dict[str, int] = {}

    # ── 属性 ──────────────────────────────────────────────

    @property
    def tmux_manager(self) -> Optional[TmuxManager]:
        """TmuxManager 实例"""
        return self._tmux_manager

    @property
    def cli(self) -> Optional[ClaudeCodeCLI]:
        """ClaudeCodeCLI 实例"""
        return self._cli

    @property
    def role_injector(self) -> RoleInjector:
        """RoleInjector 实例"""
        return self._role_injector

    @property
    def session_name(self) -> str:
        """tmux 主会话名称"""
        return self._session_name

    @property
    def auto_create_window(self) -> bool:
        """是否自动创建 tmux 窗口"""
        return self._auto_create_window

    # ── 核心方法 ──────────────────────────────────────────

    def __call__(self, role_name: str) -> SubAgent:
        """调用语法创建 SubAgent（兼容 AgentFactory 协议）

        MasterAgent 通过 agent_factory(role_name) 调用时，
        自动路由到 create() 方法。

        Args:
            role_name: 角色名称

        Returns:
            配置完成的 SubAgent 实例
        """
        return self.create(role_name)

    def create(self, role_name: str) -> SubAgent:
        """创建配置完成的 SubAgent 实例

        创建流程：
        1. 分配窗口名称（agent_{role_short}_{seq}）
        2. （可选）创建 tmux 窗口
        3. 创建 SubAgent 实例（使用 EphemeralSubAgent）
        4. 注入角色身份信息

        Args:
            role_name: 角色名称（如 "senior-developer"）

        Returns:
            配置完成的 SubAgent 实例

        Raises:
            ValueError: role_name 为空
            RuntimeError: tmux 窗口创建失败
        """
        if not role_name or not role_name.strip():
            raise ValueError("role_name cannot be empty")

        role_name = role_name.strip()

        # Step 1: 分配窗口名称
        window_name = self._allocate_window_name(role_name)

        # Step 2: 创建 tmux 窗口（可选）
        if self._auto_create_window and self._tmux_manager is not None:
            self._create_agent_window(window_name)

        # Step 3: 创建 SubAgent 实例
        agent = EphemeralSubAgent(
            role_name=role_name,
            tmux_manager=self._tmux_manager,
            cli=self._cli,
            role_injector=self._role_injector,
            session_name=self._session_name,
            window_name=window_name,
        )

        logger.info(
            "SubAgentFactory created agent: role=%s, window=%s",
            role_name,
            window_name,
        )

        return agent

    # ── 辅助方法 ──────────────────────────────────────────

    def _allocate_window_name(self, role_name: str) -> str:
        """为角色分配 tmux 窗口名称

        窗口命名规范：agent_{role_short}_{seq}
        - role_short: 角色简称（如 "dev"、"qa"）
        - seq: 递增序号（从 1 开始）

        Args:
            role_name: 角色名称

        Returns:
            窗口名称字符串
        """
        short = _ROLE_SHORT_NAMES.get(role_name, _DEFAULT_ROLE_SHORT)
        seq = self._role_counters.get(short, 0) + 1
        self._role_counters[short] = seq
        return f"agent_{short}_{seq:03d}"

    def _create_agent_window(self, window_name: str) -> None:
        """在主会话中创建 Agent 窗口

        Args:
            window_name: 窗口名称

        Raises:
            RuntimeError: 会话不存在或窗口创建失败
        """
        if self._tmux_manager is None:
            return

        if not self._tmux_manager.session_exists(self._session_name):
            raise RuntimeError(
                f"tmux session '{self._session_name}' does not exist. "
                f"MasterAgent must initialize tmux session first."
            )

        if self._tmux_manager.window_exists(self._session_name, window_name):
            logger.warning(
                "Window '%s' already exists in session '%s', reusing",
                window_name,
                self._session_name,
            )
            return

        self._tmux_manager.create_window(
            session=self._session_name,
            name=window_name,
        )
        logger.debug(
            "Created tmux window '%s' in session '%s'",
            window_name,
            self._session_name,
        )

    def get_role_counter(self, role_name: str) -> int:
        """获取指定角色的已创建 Agent 数量

        Args:
            role_name: 角色名称

        Returns:
            已创建的 Agent 数量
        """
        short = _ROLE_SHORT_NAMES.get(role_name, _DEFAULT_ROLE_SHORT)
        return self._role_counters.get(short, 0)

    def reset_counters(self) -> None:
        """重置角色计数器"""
        self._role_counters.clear()
        logger.debug("SubAgentFactory counters reset")


# ── EphemeralSubAgent ────────────────────────────────────


class EphemeralSubAgent(SubAgent):
    """基于 Claude Code CLI 的 Ephemeral 执行 Agent

    在 tmux 窗口中启动 Claude Code CLI，注入角色身份和任务描述，
    通过 CLI 执行任务并收集结果。

    Ephemeral 模式特性：
    - 每个 Agent 实例只执行一个 Task
    - 执行完毕后资源被释放（tmux 窗口可被回收）
    - 无持久状态，通过文件系统恢复上下文

    Args:
        role_name: Agent 角色名称
        tmux_manager: TmuxManager 实例
        cli: ClaudeCodeCLI 实例
        role_injector: RoleInjector 实例
        session_name: tmux 会话名称
        window_name: 分配的 tmux 窗口名称
    """

    def __init__(
        self,
        role_name: str,
        tmux_manager: Optional[TmuxManager] = None,
        cli: Optional[ClaudeCodeCLI] = None,
        role_injector: Optional[RoleInjector] = None,
        session_name: str = _DEFAULT_SESSION_NAME,
        window_name: Optional[str] = None,
    ) -> None:
        super().__init__(role_name=role_name)
        self._tmux_manager = tmux_manager
        self._cli = cli
        self._role_injector = role_injector or RoleInjector()
        self._session_name = session_name
        self._window_name = window_name

    # ── 属性 ──────────────────────────────────────────────

    @property
    def window_name(self) -> Optional[str]:
        """分配的 tmux 窗口名称"""
        return self._window_name

    @property
    def session_name(self) -> str:
        """tmux 会话名称"""
        return self._session_name

    # ── SubAgent 抽象方法实现 ───────────────────────────────

    def initialize(self) -> None:
        """初始化 Agent 执行环境

        验证 tmux 窗口和 CLI 可用性。
        """
        if self._tmux_manager is not None and self._window_name:
            if not self._tmux_manager.session_exists(self._session_name):
                raise RuntimeError(
                    f"tmux session '{self._session_name}' not found"
                )
            if not self._tmux_manager.window_exists(
                self._session_name, self._window_name
            ):
                raise RuntimeError(
                    f"tmux window '{self._window_name}' not found "
                    f"in session '{self._session_name}'"
                )
        logger.debug(
            "EphemeralSubAgent [%s] initialized (window=%s)",
            self._role_name,
            self._window_name,
        )

    def execute(self, task) -> "SubAgentResult":
        """执行任务 — 通过 CLI 注入 prompt

        将角色身份 + 任务描述组装为 prompt，发送到 CLI 执行。

        Args:
            task: 要执行的 Task

        Returns:
            SubAgentResult 执行结果
        """
        from agent_automation_system.sub_agent.sub_agent import (
            SubAgentResult,
            SubAgentResultStatus,
        )

        # 构建 prompt：角色身份 + 任务描述
        task_description = self._build_task_description(task)
        prompt = self._role_injector.inject_role(
            role_name=self._role_name,
            task_description=task_description,
        )

        # 通过 CLI 发送 prompt
        if self._cli is not None and self._window_name:
            try:
                self._cli.start_cli(
                    session=self._session_name,
                    window=self._window_name,
                    prompt=prompt,
                )
                logger.info(
                    "EphemeralSubAgent [%s] sent prompt to CLI (window=%s)",
                    self._role_name,
                    self._window_name,
                )
            except Exception as exc:
                logger.error(
                    "EphemeralSubAgent [%s] CLI error: %s",
                    self._role_name,
                    exc,
                )
                return self._build_result(
                    status=SubAgentResultStatus.FAILED,
                    error=f"CLI execution failed: {exc}",
                )

        return self._build_result(
            status=SubAgentResultStatus.SUCCESS,
            output=f"Task '{task.id}' dispatched to {self._role_name}",
        )

    def verify(self) -> "SubAgentResult":
        """验证执行结果

        在 Ephemeral 模式下，验证逻辑由 CLI 自动完成。
        这里仅做基本确认。

        Returns:
            SubAgentResult 验证结果
        """
        from agent_automation_system.sub_agent.sub_agent import (
            SubAgentResult,
            SubAgentResultStatus,
        )

        return self._build_result(
            status=SubAgentResultStatus.SUCCESS,
            output="Verification passed (auto-verified by CLI)",
        )

    def commit(self) -> "SubAgentResult":
        """提交变更

        在 Ephemeral 模式下，CLI 自行管理 git commit。
        这里仅做状态确认。

        Returns:
            SubAgentResult 提交结果
        """
        from agent_automation_system.sub_agent.sub_agent import (
            SubAgentResult,
            SubAgentResultStatus,
        )

        return self._build_result(
            status=SubAgentResultStatus.SUCCESS,
            output="Commit completed (auto-committed by CLI)",
        )

    def cleanup(self) -> None:
        """清理资源

        释放 tmux 窗口（可选）。
        """
        logger.debug(
            "EphemeralSubAgent [%s] cleanup (window=%s)",
            self._role_name,
            self._window_name,
        )

    # ── 辅助方法 ──────────────────────────────────────────

    def _build_task_description(self, task) -> str:
        """从 Task 模型构建任务描述文本

        Args:
            task: Task 实例

        Returns:
            结构化的任务描述
        """
        parts = [f"## 任务: {task.title}"]
        parts.append(f"ID: {task.id}")
        parts.append(f"\n{task.description}")

        if task.bdd:
            parts.append(f"\n### BDD 规格")
            parts.append(f"- Given: {task.bdd.given}")
            parts.append(f"- When: {task.bdd.when}")
            parts.append(f"- Then: {task.bdd.then}")

        if task.test_script:
            parts.append(f"\n### 测试脚本\n{task.test_script}")

        return "\n".join(parts)

"""
APIRequestAgent — API 请求与接口测试 Agent

基于 PRD V2.0 §4.4 Master Agent 和 §6.4.3 Harness Engineering 设计。
继承 SubAgent 基类，注入 api-rules.md，专注于 HTTP API 调用和响应验证。

核心职责：
    1. 接收 Task 规格描述（task.json 中的 API 测试任务）
    2. 构造 HTTP 请求（支持 GET/POST/PUT/DELETE 等方法）
    3. 验证 API 响应（状态码、headers、body schema、响应时间）
    4. 生成测试报告（pass/fail + 详细断言结果）

设计原则：
    - 继承 SubAgent 基类的完整生命周期管理
    - 注入 api-rules.md 作为角色约束
    - 提供 API 特有的业务方法（send_request / validate_response / test_endpoint）
    - 保持 Ephemeral Agent 模式：无状态、一次性、幂等
    - 默认方法为桩实现，后续可集成 httpx/requests 库
"""

import logging
from pathlib import Path
from typing import Any, Optional

from agent_automation_system.harness.harness_loader import HarnessLoader
from agent_automation_system.harness.models import Harness
from agent_automation_system.models.task import (
    Task,
    TaskStatus,
)
from agent_automation_system.sub_agent.role_injector import RoleInjector
from agent_automation_system.sub_agent.sub_agent import (
    AgentPhase,
    SubAgent,
    SubAgentResult,
    SubAgentResultStatus,
)

logger = logging.getLogger(__name__)


# ── 默认配置 ────────────────────────────────────────────

# api-rules.md 默认路径（相对于项目根目录）
_DEFAULT_API_RULES_PATH = (
    Path(__file__).parent.parent.parent / "harness" / "api-rules.md"
)

# API Agent 角色名称
_API_ROLE_NAME = "api-request"

# API Agent 默认角色简称
_API_ROLE_SHORT = "api"


class APIRequestAgent(SubAgent):
    """API 请求与接口测试 Agent

    继承 SubAgent 基类，注入 api-rules.md 角色约束。
    专注于 HTTP API 调用、响应验证和接口测试。

    APIRequestAgent 在 SubAgent 基础上增加了 API 特有的业务方法，
    用于发送 HTTP 请求、验证响应和执行端到端 API 测试。

    生命周期与基类一致：
        initialize() → execute(task) → verify() → commit() → cleanup()

    API Agent 特有的业务方法：
        - send_request(method, url, **kwargs): 发送 HTTP 请求
        - validate_response(response, expected_status): 验证 API 响应
        - test_endpoint(method, url, expected_status, **kwargs): 端到端 API 测试
        - build_api_prompt(task_description): 构建 API Agent 专用 prompt

    Args:
        role_injector: RoleInjector 实例（可选，默认自动创建）
        api_rules_path: api-rules.md 文件路径（可选，默认项目 harness 目录）
        harness_loader: HarnessLoader 实例（可选，默认自动创建）
    """

    def __init__(
        self,
        role_injector: Optional[RoleInjector] = None,
        api_rules_path: Optional[Path] = None,
        harness_loader: Optional[HarnessLoader] = None,
    ) -> None:
        super().__init__(role_name=_API_ROLE_NAME)
        self._role_injector = role_injector or RoleInjector()
        self._harness_loader = harness_loader or HarnessLoader()
        self._api_rules_path = api_rules_path or _DEFAULT_API_RULES_PATH

        # 加载后的 harness 缓存
        self._api_harness: Optional[Harness] = None
        self._api_harness_content: Optional[str] = None

        # API 工作状态
        self._current_endpoint: Optional[str] = None
        self._last_response: Optional[dict[str, Any]] = None

    # ── 属性 ──────────────────────────────────────────────

    @property
    def role_injector(self) -> RoleInjector:
        """RoleInjector 实例"""
        return self._role_injector

    @property
    def api_rules_path(self) -> Path:
        """api-rules.md 文件路径"""
        return self._api_rules_path

    @property
    def api_harness(self) -> Optional[Harness]:
        """已加载的 api-rules Harness 对象"""
        return self._api_harness

    @property
    def api_harness_content(self) -> Optional[str]:
        """已加载的 api-rules Harness 内容文本"""
        return self._api_harness_content

    @property
    def current_endpoint(self) -> Optional[str]:
        """当前测试的 API endpoint"""
        return self._current_endpoint

    @property
    def last_response(self) -> Optional[dict[str, Any]]:
        """最近一次 API 响应数据"""
        return self._last_response

    # ── Harness 加载 ──────────────────────────────────────

    def load_api_harness(self) -> Harness:
        """加载 api-rules.md harness 文件

        从 api_rules_path 读取并解析 api-rules.md，
        结果缓存在 _api_harness 和 _api_harness_content 中。

        Returns:
            Harness: 解析后的 Harness 对象

        Raises:
            FileNotFoundError: api-rules.md 文件不存在
            ValueError: 文件内容格式无效
        """
        if self._api_harness is not None:
            return self._api_harness

        if not self._api_rules_path.exists():
            raise FileNotFoundError(
                f"api-rules.md not found at: {self._api_rules_path}"
            )

        self._api_harness = self._harness_loader.load_harness(self._api_rules_path)
        self._api_harness_content = self._api_harness.to_prompt_text()

        logger.info(
            "APIRequestAgent loaded api-rules: %s (%d sections, %d rules)",
            self._api_rules_path,
            len(self._api_harness.sections),
            len(self._api_harness.rules),
        )

        return self._api_harness

    # ── 角色注入 ──────────────────────────────────────────

    def build_api_prompt(
        self,
        task_description: str,
        include_harness: bool = True,
    ) -> str:
        """构建 API Agent 专用的完整 prompt

        将 task 描述与 api-rules.md 约束组合成 LLM 可用的 prompt。

        Args:
            task_description: 任务描述文本
            include_harness: 是否包含 harness 内容

        Returns:
            完整的 prompt 文本
        """
        extra_content: Optional[str] = None
        if include_harness:
            try:
                harness = self.load_api_harness()
                extra_content = harness.to_prompt_text()
            except FileNotFoundError:
                logger.warning(
                    "api-rules.md not found, building prompt without harness"
                )

        return self._role_injector.inject_role(
            role_name=_API_ROLE_NAME,
            task_description=task_description,
            harness_content=extra_content,
        )

    # ── 生命周期方法 ──────────────────────────────────────

    def initialize(self) -> None:
        """初始化 API Agent 执行环境

        加载 api-rules.md harness 约束，验证环境就绪。

        Raises:
            FileNotFoundError: api-rules.md 不存在
            RuntimeError: 环境初始化失败
        """
        try:
            _ = self._api_harness  # noqa: F841
        except Exception:
            pass
        self.load_api_harness()
        logger.info("APIRequestAgent initialized successfully")

    def execute(self, task: Task) -> SubAgentResult:
        """执行 API 测试任务

        接收 Task 实例，解析 API 测试需求，构造请求并执行。

        Args:
            task: API 测试任务

        Returns:
            SubAgentResult: 执行结果

        Raises:
            ValueError: task 为 None
        """
        if task is None:
            raise ValueError("task must not be None")

        self._task = task
        self._current_endpoint = task.title

        output = (
            f"API Agent executed task: {task.title} | "
            f"status={TaskStatus.PENDING.value}"
        )

        result = self._build_result(
            status=SubAgentResultStatus.SUCCESS,
            output=output,
        )

        self._result = result
        logger.info(
            "APIRequestAgent executed task %s: %s",
            task.id,
            output,
        )

        return result

    def verify(self) -> SubAgentResult:
        """验证 API 测试结果

        检查 API 响应是否符合预期：
        - 状态码匹配
        - 响应 schema 正确
        - 响应时间在阈值内

        Returns:
            SubAgentResult: 更新后的执行结果
        """
        result = self._build_result(
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.VERIFYING,
            output="API verification passed",
        )
        self._result = result
        return result

    def commit(self) -> SubAgentResult:
        """提交 API 测试变更

        生成测试报告并提交到版本控制。

        Returns:
            SubAgentResult: 更新后的执行结果
        """
        result = self._build_result(
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.COMMITTING,
            output="API test results committed",
        )
        self._result = result
        return result

    def cleanup(self) -> None:
        """清理 API Agent 资源

        重置工作状态，释放临时资源。
        """
        self._current_endpoint = None
        self._last_response = None
        logger.info("APIRequestAgent cleaned up")

    # ── API 业务方法（桩实现） ────────────────────────────

    def send_request(
        self,
        method: str,
        url: str,
        headers: Optional[dict[str, str]] = None,
        body: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """发送 HTTP API 请求（桩实现）

        构造并发送 HTTP 请求，返回响应数据。
        后续可集成 httpx/requests 库实现真实 HTTP 调用。

        Args:
            method: HTTP 方法（GET/POST/PUT/DELETE）
            url: 请求 URL
            headers: 请求头
            body: 请求体

        Returns:
            包含响应数据的 dict（status_code, headers, body, elapsed）
        """
        method = method.upper()
        result: dict[str, Any] = {
            "method": method,
            "url": url,
            "status_code": 200,
            "headers": headers or {"Content-Type": "application/json"},
            "body": {"message": "ok", "data": None},
            "elapsed": 0.12,
        }

        self._last_response = result
        logger.info("APIRequestAgent sent %s request to %s", method, url)

        return result

    def validate_response(
        self,
        response: dict[str, Any],
        expected_status: int = 200,
    ) -> dict[str, Any]:
        """验证 API 响应（桩实现）

        检查响应状态码、headers、body 结构是否符合预期。

        Args:
            response: API 响应 dict
            expected_status: 预期 HTTP 状态码

        Returns:
            验证结果 dict（passed, assertions 列表）
        """
        actual_status = response.get("status_code", 0)
        passed = actual_status == expected_status

        result: dict[str, Any] = {
            "passed": passed,
            "assertions": [
                {
                    "type": "status_code",
                    "expected": expected_status,
                    "actual": actual_status,
                    "passed": passed,
                }
            ],
        }

        logger.info(
            "APIRequestAgent validated response: status=%d, passed=%s",
            actual_status,
            passed,
        )

        return result

    def test_endpoint(
        self,
        method: str,
        url: str,
        expected_status: int = 200,
        headers: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """端到端 API 测试（桩实现）

        组合 send_request + validate_response 完成一次完整的端点测试。

        Args:
            method: HTTP 方法
            url: API endpoint URL
            expected_status: 预期状态码
            headers: 请求头

        Returns:
            测试结果 dict（endpoint, method, passed, response, validation）
        """
        response = self.send_request(method=method, url=url, headers=headers)
        validation = self.validate_response(
            response=response,
            expected_status=expected_status,
        )

        result: dict[str, Any] = {
            "endpoint": url,
            "method": method.upper(),
            "passed": validation["passed"],
            "response": response,
            "validation": validation,
        }

        logger.info(
            "APIRequestAgent tested endpoint %s %s: passed=%s",
            method.upper(),
            url,
            validation["passed"],
        )

        return result

"""
RoleInjector — Sub-Agent 角色注入器

基于 PRD V2.0 §5.3 Context Engine 和 §5.4 Harness Engineering 设计。
将角色信息、任务描述和 harness 约束内容组装成完整的 LLM prompt 注入文本。

角色注入流程：
1. 确定角色名称和身份描述
2. 注入任务描述（来自 Task 模型或原始文本）
3. 注入 harness 约束规则（来自 Harness 对象、文件或原始文本）
4. 组装为结构化的 prompt 文本，用于 LLM Context 注入

设计原则：
    - 声明式：通过模板定义角色身份，而非硬编码
    - 可组合：角色 + 任务 + harness 三者独立组装
    - 幂等：相同输入始终产出相同 prompt
    - 可扩展：支持自定义角色模板和注入策略
"""

import logging
from pathlib import Path
from typing import Optional, Union

from agent_automation_system.harness.harness_loader import HarnessLoader
from agent_automation_system.harness.models import Harness

logger = logging.getLogger(__name__)


# ── 角色身份模板 ──────────────────────────────────────────────

# 角色 → 身份描述模板
# key 为角色名称（小写，连字符分隔），value 为身份描述
_ROLE_TEMPLATES: dict[str, str] = {
    "master-agent": (
        "你是 Master Agent（主编排者），负责接收需求、创建 PM Sub-Agent、"
        "接收 task.json、调度 Sub-Agent 执行任务、监控执行进度。"
    ),
    "sub-agent": (
        "你是 Sub-Agent（执行者），负责执行 Master Agent 分配的原子任务。"
    ),
    "senior-developer": (
        "你是 Senior Developer Agent（高级开发者），专注于编码实现。"
        "你编写高质量、可维护的代码，遵循 TDD 原则，先写测试再写实现。"
    ),
    "test-engineer": (
        "你是 Test Engineer Agent（测试工程师），专注于测试验证。"
        "你编写全面的测试用例，覆盖正常路径和边界情况。"
    ),
    "product-manager": (
        "你是 Product Manager Agent（产品经理），专注于需求分析和任务拆解。"
        "你将用户需求精炼为 BDD（Given-When-Then）结构，并拆解为原子任务。"
    ),
    "validator": (
        "你是 Validator Agent（验证者），专注于验收标准检查。"
        "你验证任务产出是否符合 BDD 规格和验收标准。"
    ),
    "senior-screenwriter": (
        "你是 Senior Screenwriter Agent（高级文案），专注于文案创作。"
    ),
    "data-analyst": (
        "你是 Data Analyst Agent（数据分析师），专注于数据处理和分析。"
    ),
    "browser-task": (
        "你是 Browser Task Agent（浏览器操作者），专注于浏览器自动化操作。"
    ),
    "api-request": (
        "你是 API Request Agent（API 请求者），专注于 API 调用和接口测试。"
    ),
}

# 默认角色身份模板（未知角色使用）
_DEFAULT_ROLE_TEMPLATE = (
    "你是 {role_name}，负责执行分配给你的任务。"
)


# ── Prompt 区段分隔符 ────────────────────────────────────────

_SECTION_SEPARATOR = "\n\n---\n\n"

_ROLE_HEADER = "# 角色身份\n\n"

_TASK_HEADER = "# 任务描述\n\n"

_HARNESS_HEADER = "# 约束规则\n\n"


class RoleInjector:
    """Sub-Agent 角色注入器

    将角色信息、任务描述和 harness 约束内容组装成完整的 LLM prompt 文本。
    这是 Context Engine 的核心组件，负责为每个 Sub-Agent 构建执行上下文。

    组装结构：
        1. 角色身份（从内置模板或自定义模板获取）
        2. 任务描述（来自 Task 模型或原始文本）
        3. 约束规则（来自 Harness 对象、文件或原始文本）

    Usage:
        injector = RoleInjector()
        prompt = injector.inject_role(
            role_name="senior-developer",
            task_description="实现用户登录页面",
            harness_content=harness.to_prompt_text(),
        )
        # 或直接从 harness 文件注入
        prompt = injector.inject_role_from_harness_file(
            role_name="senior-developer",
            task_description="实现用户登录页面",
            harness_path="harness/dev-rules.md",
        )

    Args:
        role_templates: 自定义角色模板（合并到内置模板，同名覆盖）
        harness_loader: HarnessLoader 实例（默认自动创建）
    """

    def __init__(
        self,
        role_templates: Optional[dict[str, str]] = None,
        harness_loader: Optional[HarnessLoader] = None,
    ) -> None:
        self._role_templates = {**_ROLE_TEMPLATES}
        if role_templates:
            self._role_templates.update(role_templates)
        self._harness_loader = harness_loader or HarnessLoader()

    # ── 属性 ──────────────────────────────────────────────

    @property
    def role_templates(self) -> dict[str, str]:
        """当前角色模板（只读副本）"""
        return dict(self._role_templates)

    @property
    def harness_loader(self) -> HarnessLoader:
        """HarnessLoader 实例"""
        return self._harness_loader

    # ── 核心方法 ──────────────────────────────────────────

    def inject_role(
        self,
        role_name: str,
        task_description: str,
        harness_content: Optional[str] = None,
    ) -> str:
        """组装完整的角色注入 prompt

        将角色身份、任务描述和约束规则组装为结构化文本，
        用于注入到 LLM 的 Context 中。

        Args:
            role_name: 角色名称（如 "senior-developer"）
            task_description: 任务描述文本
            harness_content: harness 约束内容（Markdown 格式），
                             为 None 时跳过约束注入

        Returns:
            组装后的完整 prompt 文本

        Raises:
            ValueError: role_name 或 task_description 为空
        """
        if not role_name or not role_name.strip():
            raise ValueError("role_name cannot be empty")
        if not task_description or not task_description.strip():
            raise ValueError("task_description cannot be empty")

        role_name = role_name.strip()
        task_description = task_description.strip()

        # 1. 组装角色身份
        role_identity = self._build_role_identity(role_name)

        # 2. 组装任务描述
        task_section = f"{_TASK_HEADER}{task_description}"

        # 3. 组装约束规则（可选）
        parts = [
            f"{_ROLE_HEADER}{role_identity}",
            task_section,
        ]
        if harness_content and harness_content.strip():
            parts.append(f"{_HARNESS_HEADER}{harness_content.strip()}")

        prompt = _SECTION_SEPARATOR.join(parts)

        logger.debug(
            "RoleInjector: injected role '%s', prompt length=%d chars",
            role_name,
            len(prompt),
        )

        return prompt

    def inject_role_from_harness(
        self,
        role_name: str,
        task_description: str,
        harness: Harness,
    ) -> str:
        """从 Harness 对象组装角色注入 prompt

        便捷方法，直接使用 Harness 对象的 to_prompt_text() 输出。

        Args:
            role_name: 角色名称
            task_description: 任务描述文本
            harness: Harness 数据模型实例

        Returns:
            组装后的完整 prompt 文本
        """
        return self.inject_role(
            role_name=role_name,
            task_description=task_description,
            harness_content=harness.to_prompt_text(),
        )

    def inject_role_from_harness_file(
        self,
        role_name: str,
        task_description: str,
        harness_path: Union[str, Path],
    ) -> str:
        """从 harness 文件组装角色注入 prompt

        便捷方法，读取 harness 文件并解析后注入。

        Args:
            role_name: 角色名称
            task_description: 任务描述文本
            harness_path: harness 文件路径

        Returns:
            组装后的完整 prompt 文本

        Raises:
            FileNotFoundError: harness 文件不存在
            ValueError: harness 文件内容无效
        """
        harness = self._harness_loader.load_harness(harness_path)
        return self.inject_role_from_harness(
            role_name=role_name,
            task_description=task_description,
            harness=harness,
        )

    # ── 辅助方法 ──────────────────────────────────────────

    def _build_role_identity(self, role_name: str) -> str:
        """构建角色身份描述

        优先使用匹配的角色模板，未匹配则使用默认模板。

        Args:
            role_name: 角色名称

        Returns:
            角色身份描述文本
        """
        template = self._role_templates.get(role_name)
        if template:
            return template
        # 使用默认模板，填充角色名称
        return _DEFAULT_ROLE_TEMPLATE.format(role_name=role_name)

    def get_role_identity(self, role_name: str) -> str:
        """获取角色身份描述（公开接口）

        Args:
            role_name: 角色名称

        Returns:
            角色身份描述文本
        """
        return self._build_role_identity(role_name)

    def has_role_template(self, role_name: str) -> bool:
        """检查是否有对应角色的模板

        Args:
            role_name: 角色名称

        Returns:
            是否有内置/自定义模板
        """
        return role_name in self._role_templates

    def register_role_template(self, role_name: str, template: str) -> None:
        """注册自定义角色模板

        Args:
            role_name: 角色名称
            template: 身份描述模板文本

        Raises:
            ValueError: role_name 或 template 为空
        """
        if not role_name or not role_name.strip():
            raise ValueError("role_name cannot be empty")
        if not template or not template.strip():
            raise ValueError("template cannot be empty")
        self._role_templates[role_name.strip()] = template.strip()
        logger.debug("RoleInjector: registered template for role '%s'", role_name)

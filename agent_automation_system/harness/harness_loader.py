"""
HarnessLoader - Harness 约束文件加载器

基于 PRD V2.0 §5.4 Harness Engineering 设计。
解析 Markdown 格式的 harness 规则文件为结构化数据模型。

Harness md 文件约定格式：

    # {名称} Rules

    ## DO
    - 必须做的事项1
    - 必须做的事项2

    ## DON'T
    - 禁止做的事项1
    - 禁止做的事项2

    ## Constraints
    - 约束条件1: 值
    - 约束条件2: 值

    ## Verification
    - 验证标准1
    - 验证标准2

    ## Custom Section
    自由文本段落内容...

段落标题映射：
    DO / MUST → RuleType.DO
    DON'T / MUST NOT / FORBIDDEN → RuleType.DONT
    CONSTRAINTS / CONSTRAINT / 限制 → RuleType.CONSTRAINT
    VERIFICATION / VERIFY / 验证 → RuleType.VERIFICATION
    其他 → RuleType.CUSTOM
"""

import logging
import re
from pathlib import Path
from typing import Optional

from agent_automation_system.harness.models import (
    Harness,
    HarnessRule,
    HarnessSection,
    RuleType,
)

logger = logging.getLogger(__name__)


# 段落标题 → RuleType 映射（大小写不敏感）
_SECTION_TYPE_MAP: dict[str, RuleType] = {
    # DO 类
    "do": RuleType.DO,
    "must": RuleType.DO,
    "必须": RuleType.DO,
    # DON'T 类
    "don't": RuleType.DONT,
    "dont": RuleType.DONT,
    "must not": RuleType.DONT,
    "forbidden": RuleType.DONT,
    "禁止": RuleType.DONT,
    # CONSTRAINT 类
    "constraints": RuleType.CONSTRAINT,
    "constraint": RuleType.CONSTRAINT,
    "限制": RuleType.CONSTRAINT,
    # VERIFICATION 类
    "verification": RuleType.VERIFICATION,
    "verify": RuleType.VERIFICATION,
    "验证": RuleType.VERIFICATION,
}


def _infer_rule_type(section_title: str) -> RuleType:
    """根据段落标题推断规则类型

    Args:
        section_title: 段落标题（## 后的文本）

    Returns:
        匹配的 RuleType，未匹配则返回 CUSTOM
    """
    normalized = section_title.strip().lower()
    return _SECTION_TYPE_MAP.get(normalized, RuleType.CUSTOM)


def _parse_list_items(text: str) -> list[str]:
    """从文本中解析 Markdown 列表项

    支持 - 和 * 开头的列表项，也支持数字列表（1. 2. 等）。

    Args:
        text: 段落文本

    Returns:
        列表项内容列表（去除前缀符号）
    """
    items: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            continue
        # 匹配 - item 或 * item
        match = re.match(r"^[-*]\s+(.+)$", stripped)
        if match:
            items.append(match.group(1).strip())
            continue
        # 匹配数字列表 1. item
        match = re.match(r"^\d+\.\s+(.+)$", stripped)
        if match:
            items.append(match.group(1).strip())
            continue
    return items


def _infer_role_name(file_path: Path, harness_name: str) -> Optional[str]:
    """从文件名或 harness 标题推断关联的 Agent 角色名称

    约定：
        - dev-rules.md → senior-developer
        - qa-rules.md → test-engineer
        - pm-rules.md → product-manager
        - sub-rules.md → sub-agent
        - main-rules.md → master-agent
        - 标题中包含角色名则使用标题

    Args:
        file_path: harness 文件路径
        harness_name: # 标题中的名称

    Returns:
        推断的角色名称，无法推断则返回 None
    """
    # 文件名 → 角色映射
    filename_map: dict[str, str] = {
        "dev-rules.md": "senior-developer",
        "qa-rules.md": "test-engineer",
        "pm-rules.md": "product-manager",
        "sub-rules.md": "sub-agent",
        "main-rules.md": "master-agent",
        "validate-rules.md": "validator",
        "api-rules.md": "api-request",
    }
    filename = file_path.name.lower()
    if filename in filename_map:
        return filename_map[filename]

    # 从标题推断
    name_lower = harness_name.lower()
    title_role_map: dict[str, str] = {
        "senior developer": "senior-developer",
        "developer": "senior-developer",
        "test engineer": "test-engineer",
        "qa": "test-engineer",
        "product manager": "product-manager",
        "pm": "product-manager",
        "sub-agent": "sub-agent",
        "sub agent": "sub-agent",
        "master agent": "master-agent",
        "master": "master-agent",
        "validator": "validator",
        "validate": "validator",
    }
    for key, role in title_role_map.items():
        if key in name_lower:
            return role

    return None


class HarnessLoader:
    """Harness 约束文件加载器

    解析 Markdown 格式的 harness 规则文件为 Harness 数据模型。
    支持标准段落（DO/DON'T/Constraints/Verification）和自定义段落。

    Usage:
        loader = HarnessLoader()
        harness = loader.load_harness("harness/dev-rules.md")
        for rule in harness.get_do_rules():
            print(rule.content)

    Args:
        encoding: 文件编码，默认 utf-8
    """

    def __init__(self, encoding: str = "utf-8") -> None:
        self._encoding = encoding

    @property
    def encoding(self) -> str:
        """文件编码"""
        return self._encoding

    def load_harness(self, harness_path: str | Path) -> Harness:
        """加载并解析 harness 文件

        读取指定路径的 Markdown 文件，解析为 Harness 数据模型。
        解析流程：
        1. 读取文件内容
        2. 提取 # 标题作为 Harness 名称
        3. 按 ## 标题拆分段落
        4. 对每个段落推断 RuleType
        5. 解析段落中的列表项为 HarnessRule

        Args:
            harness_path: harness 文件路径

        Returns:
            Harness: 结构化的约束数据模型

        Raises:
            FileNotFoundError: 文件不存在
            ValueError: 文件内容为空或无 # 标题
        """
        path = Path(harness_path)

        if not path.exists():
            raise FileNotFoundError(f"Harness file not found: {path}")

        if not path.is_file():
            raise ValueError(f"Path is not a file: {path}")

        raw_content = path.read_text(encoding=self._encoding)

        if not raw_content.strip():
            raise ValueError(f"Harness file is empty: {path}")

        return self._parse_harness(raw_content, str(path))

    def load_harness_from_string(
        self,
        content: str,
        source_name: str = "<string>",
    ) -> Harness:
        """从字符串加载 harness 内容

        适用于测试或从其他来源获取的 harness 内容。

        Args:
            content: Markdown 格式的 harness 内容
            source_name: 来源标识（用于日志和调试）

        Returns:
            Harness: 结构化的约束数据模型

        Raises:
            ValueError: 内容为空
        """
        if not content.strip():
            raise ValueError("Harness content is empty")

        return self._parse_harness(content, source_name)

    def _parse_harness(self, raw_content: str, file_path: str) -> Harness:
        """解析 harness 内容

        Args:
            raw_content: 原始 Markdown 文本
            file_path: 文件路径（记录用）

        Returns:
            Harness 数据模型
        """
        # 提取 # 标题（一级标题作为 Harness 名称）
        name = "Untitled Harness"
        first_line_match = re.match(r"^#\s+(.+)$", raw_content, re.MULTILINE)
        if first_line_match:
            name = first_line_match.group(1).strip()

        # 按 ## 标题拆分段落
        sections = self._split_sections(raw_content)

        # 解析每个段落
        harness_sections: list[HarnessSection] = []
        all_rules: list[HarnessRule] = []

        for section_title, section_content in sections:
            rule_type = _infer_rule_type(section_title)
            list_items = _parse_list_items(section_content)

            rules: list[HarnessRule] = []
            for item in list_items:
                rule = HarnessRule(
                    rule_type=rule_type,
                    content=item,
                    section=section_title,
                )
                rules.append(rule)
                all_rules.append(rule)

            harness_section = HarnessSection(
                title=section_title,
                rule_type=rule_type,
                rules=rules,
                raw_content=section_content.strip(),
            )
            harness_sections.append(harness_section)

        # 如果没有任何 ## 段落，将整个内容作为 CUSTOM 段落
        if not harness_sections:
            list_items = _parse_list_items(raw_content)
            rules: list[HarnessRule] = []
            for item in list_items:
                rule = HarnessRule(
                    rule_type=RuleType.CUSTOM,
                    content=item,
                    section="General",
                )
                rules.append(rule)
                all_rules.append(rule)

            harness_sections.append(
                HarnessSection(
                    title="General",
                    rule_type=RuleType.CUSTOM,
                    rules=rules,
                    raw_content=raw_content.strip(),
                )
            )

        # 推断角色名称
        path_obj = Path(file_path) if file_path != "<string>" else Path("unknown.md")
        role_name = _infer_role_name(path_obj, name)

        harness = Harness(
            name=name,
            file_path=file_path,
            role_name=role_name,
            sections=harness_sections,
            rules=all_rules,
            raw_content=raw_content,
        )

        logger.debug(
            "Loaded harness '%s' from %s: %d sections, %d rules",
            name,
            file_path,
            len(harness_sections),
            len(all_rules),
        )

        return harness

    def _split_sections(self, content: str) -> list[tuple[str, str]]:
        """按 ## 标题拆分段落

        Args:
            content: Markdown 文本

        Returns:
            [(段落标题, 段落内容), ...] 列表
        """
        # 去掉 # 一级标题行
        content_without_h1 = re.sub(r"^# .+$", "", content, count=1, flags=re.MULTILINE)

        # 按 ## 标题拆分
        pattern = r"^##\s+(.+)$"
        matches = list(re.finditer(pattern, content_without_h1, re.MULTILINE))

        if not matches:
            # 没有 ## 段落，整体作为一个段落
            remaining = content_without_h1.strip()
            if remaining:
                return [("General", remaining)]
            return []

        sections: list[tuple[str, str]] = []

        for i, match in enumerate(matches):
            title = match.group(1).strip()
            start = match.end()
            end = matches[i + 1].start() if i + 1 < len(matches) else len(content_without_h1)
            section_content = content_without_h1[start:end].strip()
            sections.append((title, section_content))

        return sections

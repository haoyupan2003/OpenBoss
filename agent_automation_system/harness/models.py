"""
Harness 数据模型

基于 PRD V2.0 §5.4 Harness Engineering 设计。
定义约束规则的结构化数据模型。

Harness md 文件格式：
    # {role-name} Rules

    ## DO
    - 规则1
    - 规则2

    ## DON'T
    - 禁止1
    - 禁止2

    ## Constraints
    - 约束条件1
    - 约束条件2

    ## Verification
    - 验证标准1

    ## Custom Section
    自由文本段落...
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RuleType(str, Enum):
    """约束规则类型

    对应 PRD §5.4.3 Harness 在系统中的体现。
    每种类型对应不同的约束维度和检查策略。
    """

    DO = "do"                    # 必须做的事项（正向约束）
    DONT = "dont"                # 禁止做的事项（负向约束）
    CONSTRAINT = "constraint"    # 量化约束条件（如文件大小上限）
    VERIFICATION = "verification"  # 验证标准
    CUSTOM = "custom"            # 自定义段落


class HarnessRule(BaseModel):
    """单条约束规则

    解析 harness md 文件中列表项后的结构化表示。
    每条规则对应 md 文件中的一个 - 列表项或段落。

    Attributes:
        rule_type: 规则类型
        content: 规则内容文本
        section: 所属段落标题
        priority: 优先级（1=最高，数字越大越低），默认 0 表示未指定
        metadata: 扩展元数据
    """

    rule_type: RuleType = Field(
        ...,
        description="规则类型",
    )
    content: str = Field(
        ...,
        min_length=1,
        description="规则内容文本",
    )
    section: str = Field(
        ...,
        description="所属段落标题",
    )
    priority: int = Field(
        default=0,
        ge=0,
        description="优先级（0=未指定，1=最高）",
    )
    metadata: dict[str, str] = Field(
        default_factory=dict,
        description="扩展元数据",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "rule_type": "do",
                    "content": "Always write tests before implementation",
                    "section": "DO",
                    "priority": 0,
                    "metadata": {},
                }
            ]
        }
    }


class HarnessSection(BaseModel):
    """Harness 文件中的段落

    对应 md 文件中一个 ## 标题下的全部内容。
    包含该段落的规则列表和原始文本。

    Attributes:
        title: 段落标题（## 后的文本）
        rule_type: 规则类型（根据标题自动推断）
        rules: 该段落下的规则列表
        raw_content: 段落原始文本（保留格式）
    """

    title: str = Field(
        ...,
        min_length=1,
        description="段落标题",
    )
    rule_type: RuleType = Field(
        default=RuleType.CUSTOM,
        description="规则类型",
    )
    rules: list[HarnessRule] = Field(
        default_factory=list,
        description="规则列表",
    )
    raw_content: str = Field(
        default="",
        description="段落原始文本",
    )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "title": "DO",
                    "rule_type": "do",
                    "rules": [
                        {
                            "rule_type": "do",
                            "content": "Write tests first",
                            "section": "DO",
                        }
                    ],
                    "raw_content": "- Write tests first\n- Follow commit format",
                }
            ]
        }
    }


class Harness(BaseModel):
    """完整 Harness 文件数据模型

    对应一个 harness md 文件的完整结构化表示。
    由 HarnessLoader.load_harness() 解析生成。

    Attributes:
        name: Harness 名称（来自文件 # 标题）
        file_path: 源文件路径
        role_name: 关联的 Agent 角色名称（从文件名或标题推断）
        sections: 段落列表
        rules: 所有规则的扁平列表（便于遍历）
        raw_content: 文件原始文本
    """

    name: str = Field(
        ...,
        description="Harness 名称（来自文件 # 标题）",
    )
    file_path: str = Field(
        default="",
        description="源文件路径",
    )
    role_name: Optional[str] = Field(
        None,
        description="关联的 Agent 角色名称",
    )
    sections: list[HarnessSection] = Field(
        default_factory=list,
        description="段落列表",
    )
    rules: list[HarnessRule] = Field(
        default_factory=list,
        description="所有规则的扁平列表",
    )
    raw_content: str = Field(
        default="",
        description="文件原始文本",
    )

    def get_rules_by_type(self, rule_type: RuleType) -> list[HarnessRule]:
        """按类型筛选规则

        Args:
            rule_type: 规则类型

        Returns:
            匹配类型的规则列表
        """
        return [r for r in self.rules if r.rule_type == rule_type]

    def get_do_rules(self) -> list[HarnessRule]:
        """获取所有 DO 规则"""
        return self.get_rules_by_type(RuleType.DO)

    def get_dont_rules(self) -> list[HarnessRule]:
        """获取所有 DON'T 规则"""
        return self.get_rules_by_type(RuleType.DONT)

    def get_constraints(self) -> list[HarnessRule]:
        """获取所有约束条件"""
        return self.get_rules_by_type(RuleType.CONSTRAINT)

    def get_verification_rules(self) -> list[HarnessRule]:
        """获取所有验证标准"""
        return self.get_rules_by_type(RuleType.VERIFICATION)

    def to_prompt_text(self) -> str:
        """转换为可注入 LLM prompt 的文本

        将结构化规则还原为紧凑的 Markdown 格式，
        适合作为 Context Engine 的静态注入内容。

        Returns:
            Markdown 格式的约束文本
        """
        lines: list[str] = []
        for section in self.sections:
            if not section.rules and not section.raw_content:
                continue
            lines.append(f"## {section.title}")
            lines.append("")
            if section.rules:
                for rule in section.rules:
                    lines.append(f"- {rule.content}")
            else:
                # 无规则列表的段落，保留原始内容
                lines.append(section.raw_content)
            lines.append("")
        return "\n".join(lines).strip()

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "name": "Senior Developer Agent Rules",
                    "file_path": "harness/dev-rules.md",
                    "role_name": "senior-developer",
                    "rules": [
                        {
                            "rule_type": "do",
                            "content": "Write tests before implementation",
                            "section": "DO",
                        }
                    ],
                }
            ]
        }
    }

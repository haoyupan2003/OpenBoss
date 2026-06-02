"""
Dev Agent 测试编写数据模型

基于 PRD V2.0 §4.4 Dev Agent TDD 流程设计。
定义测试编写结果的结构化数据模型，供 SeniorDeveloperAgent.write_tests() 使用。

TDD 流程：
    Task（原子任务规格）
      → analyze_task()
        → TaskAnalysisResult（结构化分析结果）
          → write_tests()（基于分析结果编写测试，本模型）
            → implement_code()（基于测试用例实现代码）

设计原则：
    - 基于 BDD Given-When-Then 映射为测试用例
    - 测试用例名称遵循 test_{action}_{condition}_{expected} 命名
    - 测试内容包含完整的 pytest 测试文件结构
    - 无 BDD 时基于任务描述生成正向和异常测试
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TestCaseInfo(BaseModel):
    """单个测试用例信息

    描述 write_tests 生成的单个测试用例的元信息。

    Attributes:
        name: 测试函数名称（如 test_login_with_valid_credentials_returns_token）
        description: 测试用例中文描述
        category: 测试分类（positive/negative/edge_case/integration）
    """

    name: str = Field(
        ...,
        min_length=1,
        description="测试函数名称",
    )
    description: str = Field(
        default="",
        description="测试用例描述",
    )
    category: str = Field(
        default="positive",
        description="测试分类：positive/negative/edge_case/integration",
    )


class TestWriteResult(BaseModel):
    """测试编写结果

    由 SeniorDeveloperAgent.write_tests() 生成。
    包含测试文件路径、测试用例列表、测试文件内容等信息。

    Attributes:
        task_id: 关联的任务 ID
        test_file_path: 测试文件相对路径
        test_cases: 测试用例信息列表
        test_content: 测试文件完整内容
        test_count: 测试用例总数
        created_at: 结果创建时间
    """

    task_id: str = Field(
        ...,
        min_length=1,
        description="关联的任务 ID",
    )
    test_file_path: str = Field(
        ...,
        min_length=1,
        description="测试文件相对路径",
    )
    test_cases: list[TestCaseInfo] = Field(
        default_factory=list,
        description="测试用例信息列表",
    )
    test_content: str = Field(
        default="",
        description="测试文件完整内容",
    )
    test_count: int = Field(
        default=0,
        ge=0,
        description="测试用例总数",
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="结果创建时间",
    )

    @property
    def positive_count(self) -> int:
        """正向测试用例数量"""
        return sum(1 for tc in self.test_cases if tc.category == "positive")

    @property
    def negative_count(self) -> int:
        """异常/反向测试用例数量"""
        return sum(1 for tc in self.test_cases if tc.category == "negative")

    @property
    def edge_case_count(self) -> int:
        """边界测试用例数量"""
        return sum(1 for tc in self.test_cases if tc.category == "edge_case")

    @property
    def integration_count(self) -> int:
        """集成测试用例数量"""
        return sum(1 for tc in self.test_cases if tc.category == "integration")

    @property
    def test_names(self) -> list[str]:
        """所有测试函数名称列表"""
        return [tc.name for tc in self.test_cases]

    def to_text(self) -> str:
        """生成结构化文本表示

        将测试编写结果转为可读的文本格式，便于 prompt 注入或日志记录。

        Returns:
            结构化文本
        """
        lines = [
            f"## 测试编写结果：{self.task_id}",
            "",
            f"### 测试文件",
            f"  路径：{self.test_file_path}",
            f"  用例总数：{self.test_count}",
        ]

        if self.test_cases:
            lines.append("")
            lines.append("### 测试用例列表")
            for tc in self.test_cases:
                lines.append(f"  - {tc.name} [{tc.category}]")
                if tc.description:
                    lines.append(f"    {tc.description}")

        lines.append("")
        lines.append("### 统计")
        lines.append(f"  正向测试：{self.positive_count}")
        lines.append(f"  异常测试：{self.negative_count}")
        lines.append(f"  边界测试：{self.edge_case_count}")
        lines.append(f"  集成测试：{self.integration_count}")

        return "\n".join(lines)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "task_id": "task-001",
                    "test_file_path": "tests/test_task_001.py",
                    "test_cases": [
                        {
                            "name": "test_login_with_valid_credentials_returns_token",
                            "description": "正确凭证登录返回 token",
                            "category": "positive",
                        },
                        {
                            "name": "test_login_with_invalid_credentials_raises_error",
                            "description": "错误凭证登录抛出异常",
                            "category": "negative",
                        },
                    ],
                    "test_content": '"""Tests for task-001"""\nimport pytest\n\ndef test_login_with_valid_credentials_returns_token():\n    pass\n',
                    "test_count": 2,
                }
            ]
        }
    }

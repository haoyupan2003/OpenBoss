"""
Dev Agent 任务分析数据模型

基于 PRD V2.0 §4.4 Dev Agent 任务分析设计。
定义任务分析结果的结构化数据模型，供 SeniorDeveloperAgent 使用。

分析流程：
    Task（原子任务规格）
      → analyze_task()
        → TaskAnalysisResult（结构化分析结果）
          → write_tests()（P2-010，基于分析结果编写测试）
            → implement_code()（P2-011，基于分析结果实现代码）

设计原则：
    - 基于 BDD 和任务描述自动推断实现方案
    - 文件路径推断遵循项目约定（snake_case 命名）
    - 工作量估算基于复杂度和文件数量
    - 风险识别覆盖技术、依赖和范围三个方面
    - TDD 优先：测试策略先于实现方案规划
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class TaskAnalysisResult(BaseModel):
    """任务分析结果

    由 SeniorDeveloperAgent.analyze_task() 生成。
    包含实现方案、文件列表、依赖影响、工作量估算、
    风险识别、测试策略和技术方案。

    Attributes:
        task_id: 任务唯一标识
        implementation_plan: 实现方案描述
        files_to_create: 需要创建的新文件路径列表
        files_to_modify: 需要修改的已有文件路径列表
        dependencies: 依赖的任务 ID 列表
        estimated_effort: 预估工作量（分钟）
        risks: 识别的风险列表
        test_strategy: TDD 测试策略描述
        technical_approach: 技术方案描述
        created_at: 分析结果创建时间
    """

    task_id: str = Field(
        ...,
        min_length=1,
        description="任务唯一标识",
    )
    implementation_plan: str = Field(
        ...,
        min_length=1,
        description="实现方案描述",
    )
    files_to_create: list[str] = Field(
        default_factory=list,
        description="需要创建的新文件路径列表",
    )
    files_to_modify: list[str] = Field(
        default_factory=list,
        description="需要修改的已有文件路径列表",
    )
    dependencies: list[str] = Field(
        default_factory=list,
        description="依赖的任务 ID 列表",
    )
    estimated_effort: int = Field(
        default=30,
        ge=1,
        le=480,
        description="预估工作量（分钟）",
    )
    risks: list[str] = Field(
        default_factory=list,
        description="识别的风险列表",
    )
    test_strategy: str = Field(
        default="",
        description="TDD 测试策略描述",
    )
    technical_approach: str = Field(
        default="",
        description="技术方案描述",
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="分析结果创建时间",
    )

    @property
    def total_files(self) -> int:
        """涉及的文件总数"""
        return len(self.files_to_create) + len(self.files_to_modify)

    @property
    def has_risks(self) -> bool:
        """是否存在识别的风险"""
        return len(self.risks) > 0

    @property
    def has_dependencies(self) -> bool:
        """是否存在任务依赖"""
        return len(self.dependencies) > 0

    @property
    def effort_hours(self) -> float:
        """预估工作量（小时）"""
        return round(self.estimated_effort / 60, 1)

    def to_text(self) -> str:
        """生成结构化文本表示

        将分析结果转为可读的文本格式，便于 prompt 注入或日志记录。

        Returns:
            结构化文本
        """
        lines = [
            f"## 任务分析：{self.task_id}",
            "",
            f"### 实现方案",
            self.implementation_plan,
            "",
            f"### 文件变更",
        ]

        if self.files_to_create:
            lines.append(f"  新建文件（{len(self.files_to_create)}）：")
            for f in self.files_to_create:
                lines.append(f"    - {f}")

        if self.files_to_modify:
            lines.append(f"  修改文件（{len(self.files_to_modify)}）：")
            for f in self.files_to_modify:
                lines.append(f"    - {f}")

        if not self.files_to_create and not self.files_to_modify:
            lines.append("  （暂无明确文件变更）")

        if self.dependencies:
            lines.append("")
            lines.append(f"### 依赖任务")
            for dep in self.dependencies:
                lines.append(f"  - {dep}")

        lines.append("")
        lines.append(f"### 工作量估算")
        lines.append(f"  预估 {self.estimated_effort} 分钟（{self.effort_hours} 小时）")

        if self.test_strategy:
            lines.append("")
            lines.append(f"### 测试策略（TDD）")
            lines.append(f"  {self.test_strategy}")

        if self.technical_approach:
            lines.append("")
            lines.append(f"### 技术方案")
            lines.append(f"  {self.technical_approach}")

        if self.risks:
            lines.append("")
            lines.append(f"### 风险识别")
            for risk in self.risks:
                lines.append(f"  - {risk}")

        return "\n".join(lines)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "task_id": "task-001",
                    "implementation_plan": "实现用户登录 API，包含邮箱和手机号两种登录方式",
                    "files_to_create": [
                        "agent_automation_system/auth/login.py",
                        "tests/test_login.py",
                    ],
                    "files_to_modify": [
                        "agent_automation_system/auth/__init__.py",
                    ],
                    "dependencies": [],
                    "estimated_effort": 30,
                    "risks": [
                        "手机号登录需对接第三方短信服务，可能存在延迟",
                    ],
                    "test_strategy": "先编写登录接口的单元测试（成功/失败/异常），再实现登录逻辑",
                    "technical_approach": "使用 JWT 认证，邮箱登录走密码验证，手机号登录走验证码验证",
                }
            ]
        }
    }

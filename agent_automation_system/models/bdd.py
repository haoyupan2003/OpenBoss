"""
BDD（Behavior-Driven Development）数据模型

基于 PRD V2.0 §4.4 PM Agent 需求精炼设计。
定义 BDD 场景和草稿的结构化数据模型，供 ProductManagerAgent 使用。

BDD 精炼流程：
    raw_need（用户原始需求）
      → refine_requirement()
        → BDDDraft（结构化 BDD 草稿）
          → communicate_with_user()（P2-003）
            → CommunicationRound（沟通轮次记录）
              → confirmed BDD（用户确认后的 BDD）

设计原则：
    - Given-When-Then 格式强制约束
    - 支持多场景拆解（一个需求可拆为多个 BDD 场景）
    - 自动生成澄清问题（用于与用户沟通循环）
    - 幂等：相同输入产出相同结构
    - 沟通收敛：最多 MAX_ROUNDS 轮，超过自动确认
"""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator

from agent_automation_system.models.task import TaskPriority


class CommunicationStatus(str, Enum):
    """沟通轮次状态"""

    PENDING = "pending"          # 等待用户回复
    CONFIRMED = "confirmed"      # 用户已确认
    REJECTED = "rejected"        # 用户拒绝，需修改
    NEEDS_REVISION = "needs_revision"  # 需要修订
    ESCALATED = "escalated"      # 超过最大轮次，升级处理
    AUTO_CONFIRMED = "auto_confirmed"  # 无问题时自动确认


class BDDScenario(BaseModel):
    """单个 BDD 场景（Given-When-Then）

    对应一个完整的功能行为描述，由 Given（前置条件）+ When（触发动作）+
    Then（预期结果）三段组成。

    Attributes:
        title: 场景标题（简短描述行为）
        given: 前置条件 — 任务执行前系统应处于的状态
        when: 触发动作 — 用户操作或系统事件
        then: 预期结果 — 任务完成后系统应达到的状态
        priority: 场景优先级
    """

    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="场景标题（简短描述行为）",
    )
    given: str = Field(
        ...,
        min_length=1,
        description="前置条件：任务执行前系统应处于的状态",
    )
    when: str = Field(
        ...,
        min_length=1,
        description="触发动作：用户操作或系统事件",
    )
    then: str = Field(
        ...,
        min_length=1,
        description="预期结果：任务完成后系统应达到的状态",
    )
    priority: TaskPriority = Field(
        default=TaskPriority.MEDIUM,
        description="场景优先级",
    )

    def to_text(self) -> str:
        """转换为可读的 BDD 文本格式

        Returns:
            Given-When-Then 格式的文本
        """
        return (
            f"场景: {self.title}\n"
            f"  Given {self.given}\n"
            f"  When {self.when}\n"
            f"  Then {self.then}"
        )

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "title": "用户邮箱登录成功",
                    "given": "用户未登录，访问登录页面",
                    "when": "用户输入有效邮箱和密码并提交",
                    "then": "用户成功登录并跳转到首页",
                    "priority": "high",
                }
            ]
        }
    }


class BDDDraft(BaseModel):
    """BDD 需求精炼草稿

    由 ProductManagerAgent.refine_requirement() 生成，
    包含从用户原始需求提炼出的多个 BDD 场景、澄清问题和假设。

    Attributes:
        raw_need: 用户原始需求文本
        summary: 需求摘要（一句话概括核心需求）
        scenarios: BDD 场景列表
        questions: 待澄清问题列表（用于与用户沟通循环）
        assumptions: 假设列表（精炼过程中的假设，需用户确认）
        created_at: 创建时间
    """

    raw_need: str = Field(
        ...,
        min_length=1,
        description="用户原始需求文本",
    )
    summary: str = Field(
        ...,
        min_length=1,
        description="需求摘要（一句话概括核心需求）",
    )
    scenarios: list[BDDScenario] = Field(
        default_factory=list,
        description="BDD 场景列表",
    )
    questions: list[str] = Field(
        default_factory=list,
        description="待澄清问题列表",
    )
    assumptions: list[str] = Field(
        default_factory=list,
        description="假设列表（需用户确认）",
    )
    created_at: Optional[datetime] = Field(
        None,
        description="创建时间",
    )

    @field_validator("questions")
    @classmethod
    def validate_questions_not_empty_strings(cls, v: list[str]) -> list[str]:
        """确保问题列表不含空字符串"""
        return [q for q in v if q.strip()]

    @field_validator("assumptions")
    @classmethod
    def validate_assumptions_not_empty_strings(cls, v: list[str]) -> list[str]:
        """确保假设列表不含空字符串"""
        return [a for a in v if a.strip()]

    @property
    def scenario_count(self) -> int:
        """BDD 场景数量"""
        return len(self.scenarios)

    @property
    def has_questions(self) -> bool:
        """是否有待澄清问题"""
        return len(self.questions) > 0

    @property
    def high_priority_scenarios(self) -> list[BDDScenario]:
        """高优先级场景"""
        return [s for s in self.scenarios if s.priority == TaskPriority.HIGH]

    def to_text(self) -> str:
        """转换为可读的完整 BDD 草稿文本

        Returns:
            包含摘要、场景、问题和假设的完整文本
        """
        parts: list[str] = []

        parts.append(f"# 需求摘要: {self.summary}")
        parts.append("")

        if self.scenarios:
            parts.append("## BDD 场景")
            parts.append("")
            for i, scenario in enumerate(self.scenarios, 1):
                parts.append(f"### 场景 {i}: {scenario.title}")
                parts.append(f"- Given: {scenario.given}")
                parts.append(f"- When: {scenario.when}")
                parts.append(f"- Then: {scenario.then}")
                parts.append(f"- 优先级: {scenario.priority.value}")
                parts.append("")

        if self.questions:
            parts.append("## 待澄清问题")
            parts.append("")
            for i, question in enumerate(self.questions, 1):
                parts.append(f"{i}. {question}")
            parts.append("")

        if self.assumptions:
            parts.append("## 假设")
            parts.append("")
            for i, assumption in enumerate(self.assumptions, 1):
                parts.append(f"{i}. {assumption}")
            parts.append("")

        return "\n".join(parts)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "raw_need": "用户需要一个安全的登录功能",
                    "summary": "实现安全的用户登录功能",
                    "scenarios": [
                        {
                            "title": "邮箱登录成功",
                            "given": "用户未登录",
                            "when": "输入有效邮箱密码并提交",
                            "then": "登录成功跳转首页",
                            "priority": "high",
                        }
                    ],
                    "questions": ["是否需要支持第三方登录？"],
                    "assumptions": ["假设使用邮箱+密码方式登录"],
                    "created_at": "2026-05-19T12:00:00Z",
                }
            ]
        }
    }


class CommunicationRound(BaseModel):
    """用户沟通轮次记录

    记录一次 PM Agent 与用户的沟通交互。
    每轮包含 PM 提出的草稿/问题 + 用户的反馈。

    Attributes:
        round_number: 轮次序号（从 1 开始）
        draft_snapshot: 此轮展示给用户的 BDD 草稿文本
        questions_asked: 此轮向用户提出的问题列表
        user_feedback: 用户反馈文本（None 表示未回复）
        status: 此轮沟通状态
        started_at: 此轮开始时间
        completed_at: 此轮完成时间（用户回复后）
    """

    round_number: int = Field(
        ...,
        ge=1,
        description="轮次序号（从 1 开始）",
    )
    draft_snapshot: str = Field(
        ...,
        min_length=1,
        description="此轮展示给用户的 BDD 草稿文本",
    )
    questions_asked: list[str] = Field(
        default_factory=list,
        description="此轮向用户提出的问题列表",
    )
    user_feedback: Optional[str] = Field(
        None,
        description="用户反馈文本（None 表示未回复）",
    )
    status: CommunicationStatus = Field(
        default=CommunicationStatus.PENDING,
        description="此轮沟通状态",
    )
    started_at: Optional[datetime] = Field(
        None,
        description="此轮开始时间",
    )
    completed_at: Optional[datetime] = Field(
        None,
        description="此轮完成时间",
    )

    @property
    def is_completed(self) -> bool:
        """此轮是否已完成（用户已回复）"""
        return self.status in (
            CommunicationStatus.CONFIRMED,
            CommunicationStatus.REJECTED,
            CommunicationStatus.NEEDS_REVISION,
            CommunicationStatus.ESCALATED,
            CommunicationStatus.AUTO_CONFIRMED,
        )

    @property
    def has_feedback(self) -> bool:
        """是否有用户反馈"""
        return self.user_feedback is not None and self.user_feedback.strip() != ""

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "round_number": 1,
                    "draft_snapshot": "## BDD 场景\n- Given: ...",
                    "questions_asked": ["是否需要第三方登录？"],
                    "user_feedback": "需要支持微信登录",
                    "status": "needs_revision",
                    "started_at": "2026-05-19T12:00:00Z",
                    "completed_at": "2026-05-19T12:05:00Z",
                }
            ]
        }
    }


class CommunicationResult(BaseModel):
    """用户沟通循环结果

    communicate_with_user 的返回值，包含所有沟通轮次记录
    和最终确认的 BDD 描述。

    Attributes:
        rounds: 沟通轮次列表
        final_status: 最终沟通状态
        confirmed_bdd: 用户确认后的 BDD 描述文本（确认后非空）
        total_rounds: 总沟通轮数
        has_questions_unresolved: 是否仍有未解决问题
    """

    rounds: list[CommunicationRound] = Field(
        default_factory=list,
        description="沟通轮次列表",
    )
    final_status: CommunicationStatus = Field(
        default=CommunicationStatus.PENDING,
        description="最终沟通状态",
    )
    confirmed_bdd: Optional[str] = Field(
        None,
        description="用户确认后的 BDD 描述文本",
    )
    total_rounds: int = Field(
        default=0,
        ge=0,
        description="总沟通轮数",
    )
    has_questions_unresolved: bool = Field(
        default=False,
        description="是否仍有未解决问题",
    )

    @property
    def is_confirmed(self) -> bool:
        """用户是否已确认"""
        return self.final_status in (
            CommunicationStatus.CONFIRMED,
            CommunicationStatus.AUTO_CONFIRMED,
        )

    @property
    def needs_escalation(self) -> bool:
        """是否需要升级处理"""
        return self.final_status == CommunicationStatus.ESCALATED

    @property
    def last_round(self) -> Optional[CommunicationRound]:
        """最后一轮沟通记录"""
        return self.rounds[-1] if self.rounds else None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "rounds": [],
                    "final_status": "confirmed",
                    "confirmed_bdd": "## BDD 场景\n- Given: ...",
                    "total_rounds": 1,
                    "has_questions_unresolved": False,
                }
            ]
        }
    }


class DecomposeResult(BaseModel):
    """任务拆解结果

    由 ProductManagerAgent.decompose_requirement() 生成，
    包含从确认 BDD 拆解出的原子任务列表和拆解说明。

    Attributes:
        confirmed_bdd: 已确认的 BDD 描述文本
        tasks: 拆解后的原子任务字典列表（兼容 Task 模型字段）
        decomposition_notes: 拆解说明（记录拆解决策和推理）
        created_at: 创建时间
    """

    confirmed_bdd: str = Field(
        ...,
        min_length=1,
        description="已确认的 BDD 描述文本",
    )
    tasks: list[dict[str, Any]] = Field(
        default_factory=list,
        description="拆解后的原子任务字典列表",
    )
    decomposition_notes: list[str] = Field(
        default_factory=list,
        description="拆解说明（记录拆解决策）",
    )
    created_at: Optional[datetime] = Field(
        None,
        description="创建时间",
    )

    @field_validator("decomposition_notes")
    @classmethod
    def validate_notes_not_empty_strings(cls, v: list[str]) -> list[str]:
        """确保说明列表不含空字符串"""
        return [n for n in v if n.strip()]

    @property
    def total_tasks(self) -> int:
        """任务总数"""
        return len(self.tasks)

    @property
    def has_tasks(self) -> bool:
        """是否有拆解出的任务"""
        return len(self.tasks) > 0

    @property
    def task_ids(self) -> list[str]:
        """所有任务 ID 列表"""
        return [t.get("id", "") for t in self.tasks]

    @property
    def high_priority_tasks(self) -> list[dict[str, Any]]:
        """高优先级任务"""
        return [t for t in self.tasks if t.get("priority") == "high"]

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "confirmed_bdd": "## BDD 场景\n### 场景 1: 用户登录\n- Given: 未登录",
                    "tasks": [
                        {
                            "id": "task-001",
                            "title": "用户登录",
                            "description": "实现用户登录功能",
                            "priority": "high",
                        }
                    ],
                    "decomposition_notes": ["解析出 1 个场景，拆解为 1 个原子任务"],
                    "created_at": "2026-05-19T12:00:00Z",
                }
            ]
        }
    }


class TestScriptType(str, Enum):
    """测试脚本类型枚举"""
    __test__ = False  # 避免pytest收集

    PLAYWRIGHT = "playwright"      # UI 测试（Playwright）
    API = "api"                    # API 接口测试
    UNIT = "unit"                  # 单元测试
    INTEGRATION = "integration"    # 集成测试


class TestScriptResult(BaseModel):
    """测试脚本生成结果

    由 ProductManagerAgent.generate_test_script() 生成，
    包含生成的测试脚本内容、测试用例列表和文件写入路径。

    Attributes:
        task_id: 关联的任务 ID
        script_type: 测试脚本类型
        script_content: 生成的测试脚本内容
        test_cases: 测试用例名称列表
        imports_needed: 需要的 import 语句列表
        output_path: 写入的文件路径（None 表示未写入文件）
        created_at: 创建时间
    """

    __test__ = False  # 避免pytest收集

    task_id: str = Field(
        ...,
        min_length=1,
        description="关联的任务 ID",
    )
    script_type: TestScriptType = Field(
        default=TestScriptType.UNIT,
        description="测试脚本类型",
    )
    script_content: str = Field(
        ...,
        min_length=1,
        description="生成的测试脚本内容",
    )
    test_cases: list[str] = Field(
        default_factory=list,
        description="测试用例名称列表",
    )
    imports_needed: list[str] = Field(
        default_factory=list,
        description="需要的 import 语句列表",
    )
    output_path: Optional[str] = Field(
        None,
        description="写入的文件路径",
    )
    created_at: Optional[datetime] = Field(
        None,
        description="创建时间",
    )

    @field_validator("test_cases")
    @classmethod
    def validate_test_cases_not_empty_strings(cls, v: list[str]) -> list[str]:
        """确保测试用例列表不含空字符串"""
        return [tc for tc in v if tc.strip()]

    @property
    def has_content(self) -> bool:
        """脚本内容是否非空"""
        return len(self.script_content.strip()) > 0

    @property
    def test_case_count(self) -> int:
        """测试用例数量"""
        return len(self.test_cases)

    @property
    def is_saved_to_file(self) -> bool:
        """是否已写入文件"""
        return self.output_path is not None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "task_id": "task-001",
                    "script_type": "unit",
                    "script_content": "import pytest\n\ndef test_login():\n    ...",
                    "test_cases": ["test_login_success", "test_login_failure"],
                    "imports_needed": ["import pytest"],
                    "output_path": None,
                    "created_at": "2026-05-19T12:00:00Z",
                }
            ]
        }
    }


class TaskJsonResult(BaseModel):
    """task.json 生成结果

    由 ProductManagerAgent.generate_task_json() 生成，
    包含 TaskJSON 模型对象和文件写入路径（如果指定）。

    Attributes:
        task_json: TaskJSON 模型对象
        output_path: 写入的文件路径（None 表示未写入文件）
        json_text: JSON 文本内容
        created_at: 创建时间
    """

    task_json: Any = Field(
        ...,
        description="TaskJSON 模型对象",
    )
    output_path: Optional[str] = Field(
        None,
        description="写入的文件路径",
    )
    json_text: str = Field(
        ...,
        min_length=1,
        description="JSON 文本内容",
    )
    created_at: Optional[datetime] = Field(
        None,
        description="创建时间",
    )

    @property
    def total_tasks(self) -> int:
        """任务总数"""
        return self.task_json.total_tasks

    @property
    def project_name(self) -> str:
        """项目名称"""
        return self.task_json.project_name

    @property
    def is_saved_to_file(self) -> bool:
        """是否已写入文件"""
        return self.output_path is not None

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "project_name": "登录系统",
                    "total_tasks": 2,
                    "output_path": "/path/to/task.json",
                    "created_at": "2026-05-19T12:00:00Z",
                }
            ]
        }
    }

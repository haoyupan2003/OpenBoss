"""
Task 数据模型

基于 PRD V2.0 §6.2 task.json 格式规范定义。
每个 Task 代表一个原子任务，包含 BDD 描述、依赖关系、角色分配等信息。
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class TaskStatus(str, Enum):
    """任务状态枚举"""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


class TaskPriority(str, Enum):
    """任务优先级枚举"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskComplexity(str, Enum):
    """任务复杂度枚举"""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class BDDSpec(BaseModel):
    """BDD（Given-When-Then）规格描述"""

    given: str = Field(..., description="前置条件：任务执行前系统应处于的状态")
    when: str = Field(..., description="触发动作：用户操作或系统事件")
    then: str = Field(..., description="预期结果：任务完成后系统应达到的状态")


class Task(BaseModel):
    """原子任务数据模型

    对应 PRD §6.2 task.json 中的单个 task 条目。
    由 PM Agent 生成，Master Agent 用于调度，Sub-Agent 用于执行。

    Attributes:
        id: 任务唯一标识，格式 task-XXX
        title: 任务标题（简短描述）
        description: 任务详细描述
        bdd: BDD 规格描述（Given-When-Then）
        test_script: 对应的自动化测试脚本路径
        dependencies: 依赖的任务 ID 列表
        suggested_role: 建议执行的 Agent 角色
        priority: 任务优先级
        estimated_complexity: 预估复杂度
        status: 当前状态
        assigned_agent: 分配的 Agent 标识（运行时填充）
        retry_count: 重试次数
        error_message: 失败时的错误信息
        started_at: 开始执行时间
        finished_at: 执行完成时间
    """

    id: str = Field(
        ...,
        description="任务唯一标识，格式 task-XXX",
        pattern=r"^task-\d{3,}$",
    )
    title: str = Field(..., min_length=1, max_length=200, description="任务标题")
    description: str = Field(..., min_length=1, description="任务详细描述")
    bdd: Optional[BDDSpec] = Field(None, description="BDD 规格描述")
    test_script: Optional[str] = Field(None, description="对应的自动化测试脚本路径")
    dependencies: list[str] = Field(
        default_factory=list,
        description="依赖的任务 ID 列表",
    )
    suggested_role: str = Field(
        default="dev",
        description="建议执行的 Agent 角色（pm/dev/qa/validate）",
    )
    priority: TaskPriority = Field(
        default=TaskPriority.MEDIUM,
        description="任务优先级",
    )
    estimated_complexity: TaskComplexity = Field(
        default=TaskComplexity.MEDIUM,
        description="预估复杂度",
    )
    status: TaskStatus = Field(
        default=TaskStatus.PENDING,
        description="当前状态",
    )
    assigned_agent: Optional[str] = Field(
        None,
        description="分配的 Agent 标识（运行时填充）",
    )
    retry_count: int = Field(
        default=0,
        ge=0,
        description="重试次数",
    )
    error_message: Optional[str] = Field(
        None,
        description="失败时的错误信息",
    )
    started_at: Optional[datetime] = Field(
        None,
        description="开始执行时间",
    )
    finished_at: Optional[datetime] = Field(
        None,
        description="执行完成时间",
    )

    @field_validator("dependencies")
    @classmethod
    def validate_no_self_dependency(cls, v: list[str], info) -> list[str]:
        """确保任务不能依赖自身"""
        task_id = info.data.get("id")
        if task_id and task_id in v:
            raise ValueError(f"Task {task_id} cannot depend on itself")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "id": "task-001",
                    "title": "用户登录页面 UI 实现",
                    "description": "基于 Figma 设计稿实现用户登录页面",
                    "bdd": {
                        "given": "用户未登录，访问登录页面 URL /login",
                        "when": "页面加载完成",
                        "then": "展示登录表单",
                    },
                    "test_script": "tests/test_login_ui.py",
                    "dependencies": [],
                    "suggested_role": "senior-developer",
                    "priority": "high",
                    "estimated_complexity": "medium",
                    "status": "pending",
                }
            ]
        }
    }

"""
TaskJSON 数据模型

基于 PRD V2.0 §6.2 task.json 格式规范定义。
TaskJSON 是 task.json 文件的完整结构，由 PM Agent 生成。
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from agent_automation_system.models.task import Task


class TaskJSON(BaseModel):
    """task.json 文件完整数据模型

    对应 PRD §6.2 task.json 的顶层结构。
    由 Product Manager Agent 生成，Master Agent 读取后进行任务调度。

    Attributes:
        project_name: 项目名称
        description: 项目描述
        created_by: 创建者（通常为 PM Agent）
        created_at: 创建时间（ISO 8601 格式）
        total_tasks: 任务总数
        tasks: 任务列表
    """

    project_name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="项目名称",
    )
    description: Optional[str] = Field(
        None,
        description="项目描述",
    )
    created_by: str = Field(
        default="Product Manager Agent",
        description="创建者标识",
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="创建时间（ISO 8601 格式）",
    )
    total_tasks: int = Field(
        ...,
        ge=0,
        description="任务总数",
    )
    tasks: list[Task] = Field(
        default_factory=list,
        description="任务列表",
    )

    @model_validator(mode="after")
    def validate_total_tasks_matches(self) -> "TaskJSON":
        """校验 total_tasks 与实际 tasks 列表长度一致"""
        if self.total_tasks != len(self.tasks):
            raise ValueError(
                f"total_tasks ({self.total_tasks}) does not match "
                f"actual tasks count ({len(self.tasks)})"
            )
        return self

    @model_validator(mode="after")
    def validate_dependencies_exist(self) -> "TaskJSON":
        """校验所有依赖引用的任务 ID 在列表中存在"""
        task_ids = {t.id for t in self.tasks}
        for task in self.tasks:
            for dep_id in task.dependencies:
                if dep_id not in task_ids:
                    raise ValueError(
                        f"Task {task.id} depends on '{dep_id}', "
                        f"which does not exist in task list"
                    )
        return self

    @model_validator(mode="after")
    def validate_no_circular_dependencies(self) -> "TaskJSON":
        """校验任务依赖图中不存在循环依赖"""
        task_map = {t.id: t.dependencies for t in self.tasks}

        visited: set[str] = set()
        path: set[str] = set()

        def dfs(task_id: str) -> None:
            if task_id in path:
                raise ValueError(f"Circular dependency detected involving task '{task_id}'")
            if task_id in visited:
                return
            path.add(task_id)
            for dep_id in task_map.get(task_id, []):
                dfs(dep_id)
            path.remove(task_id)
            visited.add(task_id)

        for task_id in task_map:
            dfs(task_id)

        return self

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "project_name": "电商平台重构项目",
                    "created_by": "Product Manager Agent",
                    "created_at": "2026-05-13T10:30:00Z",
                    "total_tasks": 2,
                    "tasks": [
                        {
                            "id": "task-001",
                            "title": "用户登录页面 UI 实现",
                            "description": "基于 Figma 设计稿实现用户登录页面",
                            "dependencies": [],
                            "suggested_role": "senior-developer",
                            "priority": "high",
                            "status": "pending",
                        },
                        {
                            "id": "task-002",
                            "title": "登录表单测试",
                            "description": "编写登录表单自动化测试",
                            "dependencies": ["task-001"],
                            "suggested_role": "test-engineer",
                            "priority": "high",
                            "status": "pending",
                        },
                    ],
                }
            ]
        }
    }

"""
数据模型包

定义 OpenBoss 系统的所有核心数据结构。

模型列表：
- Task: 任务定义模型
- TaskJSON: task.json 容器模型
- BDDScenario: BDD 场景模型（Given-When-Then）
- BDDDraft: BDD 需求精炼草稿模型
- CommunicationRound: 用户沟通轮次记录模型
- CommunicationResult: 用户沟通循环结果模型
- CommunicationStatus: 沟通状态枚举
- DecomposeResult: 任务拆解结果模型
- TestScriptResult: 测试脚本生成结果模型
- TestScriptType: 测试脚本类型枚举
- ProgressEntry: 进度条目模型
- MemoryEntry: memory.md section 条目模型
"""

from agent_automation_system.models.bdd import (
    BDDDraft,
    BDDScenario,
    CommunicationResult,
    CommunicationRound,
    CommunicationStatus,
    DecomposeResult,
    TaskJsonResult,
    TestScriptResult,
    TestScriptType,
)
from agent_automation_system.models.dev_analysis import TaskAnalysisResult
from agent_automation_system.models.dev_implement import (
    ImplementResult,
    TddWorkflowResult,
    TddWorkflowStatus,
    TestRunResult,
)
from agent_automation_system.models.memory_entry import MemoryEntry
from agent_automation_system.models.progress import ProgressEntry, ProgressStatus
from agent_automation_system.models.task import Task, TaskComplexity, TaskPriority, TaskStatus
from agent_automation_system.models.task_json import TaskJSON
from agent_automation_system.models.test_write import TestCaseInfo, TestWriteResult

__all__ = [
    "BDDDraft",
    "BDDScenario",
    "CommunicationResult",
    "CommunicationRound",
    "CommunicationStatus",
    "DecomposeResult",
    "ImplementResult",
    "MemoryEntry",
    "ProgressEntry",
    "ProgressStatus",
    "Task",
    "TaskAnalysisResult",
    "TestCaseInfo",
    "TaskComplexity",
    "TaskPriority",
    "TaskJSON",
    "TaskJsonResult",
    "TddWorkflowResult",
    "TddWorkflowStatus",
    "TestRunResult",
    "TestScriptResult",
    "TestScriptType",
    "TestWriteResult",
    "TaskStatus",
]

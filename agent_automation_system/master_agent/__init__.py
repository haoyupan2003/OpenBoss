"""
Master Agent 模块

定义 MasterAgent 类 — 系统的核心调度中枢。
MasterAgent 负责接收需求、创建 PM Sub-Agent、读取 task.json、调度 Sub-Agent 执行任务。
"""

from agent_automation_system.master_agent.agent_factory import (
    EphemeralSubAgent,
    SubAgentFactory,
)
from agent_automation_system.master_agent.master_agent import (
    MasterAgent,
    MasterAgentState,
)

__all__ = [
    "EphemeralSubAgent",
    "MasterAgent",
    "MasterAgentState",
    "SubAgentFactory",
]

"""
Sub-Agent 模块

定义 SubAgent 基类接口、SubAgentResult 数据模型、生命周期管理和角色注入。
SubAgent 是 Master-Agent 调度的最小执行单元，遵循 Ephemeral Agent 模式。
"""

from agent_automation_system.sub_agent.dev_agent import SeniorDeveloperAgent
from agent_automation_system.sub_agent.pm_agent import ProductManagerAgent
from agent_automation_system.sub_agent.role_injector import RoleInjector
from agent_automation_system.sub_agent.sub_agent import (
    AgentPhase,
    SubAgent,
    SubAgentResult,
    SubAgentResultStatus,
)

__all__ = [
    "AgentPhase",
    "ProductManagerAgent",
    "RoleInjector",
    "SeniorDeveloperAgent",
    "SubAgent",
    "SubAgentResult",
    "SubAgentResultStatus",
]

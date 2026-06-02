"""
Harness 约束模块

基于 PRD V2.0 §5.4 Harness Engineering 设计。
提供 Markdown 格式约束文件的加载和解析能力。

核心组件：
- HarnessLoader: 约束文件加载器
- Harness: 完整约束数据模型
- HarnessSection: 段落数据模型
- HarnessRule: 单条规则数据模型
- RuleType: 规则类型枚举
"""

from agent_automation_system.harness.harness_loader import HarnessLoader
from agent_automation_system.harness.models import (
    Harness,
    HarnessRule,
    HarnessSection,
    RuleType,
)

__all__ = [
    "Harness",
    "HarnessLoader",
    "HarnessRule",
    "HarnessSection",
    "RuleType",
]

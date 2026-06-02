"""
tmux 集成模块

提供 OpenBoss 系统的 tmux 会话管理能力：
- TmuxManager: tmux 基础类（可用性检测、版本获取）
- 会话管理（创建/销毁/列表/查询）
- 窗口管理（创建/销毁/列表）
- 命令发送与输出捕获
"""

from agent_automation_system.tmux_manager.tmux_manager import TmuxManager

__all__ = [
    "TmuxManager",
]

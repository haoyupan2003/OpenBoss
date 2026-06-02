"""
CLI 模块 — Claude Code CLI 启动、交互、执行结果检测与超时控制

提供 Claude Code CLI 在 tmux 窗口中的启动、prompt 注入、
状态检测、优雅停止、执行结果检测以及超时控制能力。

核心组件：
- ClaudeCodeCLI: CLI 启动与交互管理器
- CLIStatus: CLI 运行状态枚举
- ResultDetector: 执行结果检测器
- ExecutionStatus: 执行状态枚举
- DetectionResult: 检测结果数据类
- TimeoutController: 超时控制器
- TimeoutStatus: 超时控制结果状态枚举
- TimeoutResult: 超时控制结果数据类
"""

from agent_automation_system.cli.claude_code_cli import ClaudeCodeCLI, CLIStatus
from agent_automation_system.cli.result_detector import (
    DetectionResult,
    ExecutionStatus,
    ResultDetector,
)
from agent_automation_system.cli.timeout_controller import (
    TimeoutController,
    TimeoutResult,
    TimeoutStatus,
)

__all__ = [
    "ClaudeCodeCLI",
    "CLIStatus",
    "DetectionResult",
    "ExecutionStatus",
    "ResultDetector",
    "TimeoutController",
    "TimeoutResult",
    "TimeoutStatus",
]

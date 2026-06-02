"""
文件读写包

提供 OpenBoss 系统的数据文件读写能力：
- task.json：任务定义文件（TaskFileManager）
- progress.txt：进度追踪文件（ProgressManager）
- memory.md：共享记忆文件（MemoryManager）
- logs/：日志管理（LogManager）
"""

from agent_automation_system.file_io.log_manager import LogCategory, LogManager, LogLevel
from agent_automation_system.file_io.memory_manager import MemoryManager
from agent_automation_system.file_io.progress_manager import ProgressManager
from agent_automation_system.file_io.task_file_manager import TaskFileManager

__all__ = [
    "LogCategory",
    "LogManager",
    "LogLevel",
    "MemoryManager",
    "ProgressManager",
    "TaskFileManager",
]

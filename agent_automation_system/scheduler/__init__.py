"""
Scheduler 模块 — 任务 DAG 分析与调度策略

提供任务依赖图（DAG）构建、拓扑排序、并行度分析和调度策略。
由 MasterAgent 在 PLANNING/DISPATCHING 阶段调用。

核心组件：
- TaskDAG: 任务 DAG 数据模型
- build_dag(): 从 Task 列表构建 DAG
- topological_sort(): 拓扑排序
- compute_max_parallelism(): 计算最大并行度
- detect_cycle(): 循环依赖检测
- ParallelScheduler: 并行批次调度器
- ConcurrencySemaphore: 并发控制信号量
- TaskQueue: FIFO + 优先级任务队列
- ExecutionMonitor: 并行执行状态监控
- RiskSorter: 高风险任务排序与延迟执行
- BDDMapper: BDD 场景到 Task 完整映射
- BDDValidator: BDD 行为验证器（Given-When-Then 匹配）
- TestRunner: pytest 测试执行器
- parse_test_output: pytest 输出解析器
"""

from agent_automation_system.scheduler.bdd_mapper import (
    BDDMapper,
)
from agent_automation_system.scheduler.bdd_validator import (
    BDDValidationResult,
    BDDValidator,
)
from agent_automation_system.scheduler.concurrency import (
    ConcurrencySemaphore,
)
from agent_automation_system.scheduler.dag import (
    CyclicDependencyError,
    TaskDAG,
    build_dag,
    compute_max_parallelism,
    detect_cycle,
    topological_sort,
)
from agent_automation_system.scheduler.execution_monitor import (
    AgentRunInfo,
    AgentRunStatus,
    ExecutionMonitor,
)
from agent_automation_system.scheduler.parallel_scheduler import (
    ParallelScheduler,
)
from agent_automation_system.scheduler.risk_sorter import (
    RiskSorter,
    TaskRiskLevel,
)
from agent_automation_system.scheduler.task_queue import (
    TaskQueue,
)
from agent_automation_system.scheduler.test_output_parser import (
    TestOutput,
    parse_test_output,
)
from agent_automation_system.scheduler.test_runner import (
    TestResult,
    TestRunner,
    TestRunnerError,
)

__all__ = [
    "AgentRunInfo",
    "AgentRunStatus",
    "BDDMapper",
    "BDDValidationResult",
    "BDDValidator",
    "ConcurrencySemaphore",
    "CyclicDependencyError",
    "ExecutionMonitor",
    "ParallelScheduler",
    "RiskSorter",
    "TaskDAG",
    "TaskQueue",
    "TaskRiskLevel",
    "TestOutput",
    "TestResult",
    "TestRunner",
    "TestRunnerError",
    "build_dag",
    "compute_max_parallelism",
    "detect_cycle",
    "parse_test_output",
    "topological_sort",
]

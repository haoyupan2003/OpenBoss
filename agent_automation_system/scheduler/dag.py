"""
TaskDAG — 任务依赖图（DAG）分析模块

基于 PRD V2.0 §4.3 Workflow Engine 中的任务调度设计。
将 Task 列表转换为有向无环图（DAG），提供拓扑排序、
并行度分析和循环依赖检测能力。

核心概念：
    - 节点：Task（通过 task.id 标识）
    - 边：Task.dependencies（有向边：依赖 → 被依赖）
    - 入度：任务的前置依赖数量
    - 出度：依赖此任务的后继任务数量

DAG 构建规则：
    - 所有 task.id 必须唯一
    - dependencies 中的 ID 必须指向存在的 task
    - 不允许循环依赖（A→B→C→A）
    - 不允许自依赖（Task 模型已校验）

调度分析：
    - 拓扑排序：确定合法执行顺序（Kahn 算法）
    - 并行度分析：计算每层可并行执行的任务数
    - 层级：拓扑排序的层次结构（同层任务可并行）
"""

import logging
from collections import deque
from typing import Optional

from agent_automation_system.models.task import Task, TaskPriority

logger = logging.getLogger(__name__)


class CyclicDependencyError(Exception):
    """循环依赖错误

    当任务依赖关系中存在环（A→B→C→A）时抛出。
    包含参与循环的任务 ID 列表，便于诊断。
    """

    def __init__(self, cycle_nodes: list[str]) -> None:
        self.cycle_nodes: list[str] = cycle_nodes
        cycle_str = " → ".join(cycle_nodes)
        super().__init__(
            f"Cyclic dependency detected: {cycle_str}"
        )


class TaskDAG:
    """任务依赖图（DAG）数据模型

    将 Task 列表转换为有向无环图，提供结构化的依赖分析。

    Attributes:
        tasks: 任务字典（task_id → Task）
        edges: 邻接表（task_id → 依赖它的后继 task_id 列表）
        in_degree: 入度表（task_id → 前置依赖数量）
        task_count: 任务总数
    """

    def __init__(
        self,
        tasks: dict[str, Task],
        edges: dict[str, list[str]],
        in_degree: dict[str, int],
    ) -> None:
        self._tasks = tasks
        self._edges = edges
        self._in_degree = in_degree

    @property
    def tasks(self) -> dict[str, Task]:
        """任务字典（只读副本）"""
        return dict(self._tasks)

    @property
    def edges(self) -> dict[str, list[str]]:
        """邻接表（只读副本）"""
        return {k: list(v) for k, v in self._edges.items()}

    @property
    def in_degree(self) -> dict[str, int]:
        """入度表（只读副本）"""
        return dict(self._in_degree)

    @property
    def task_count(self) -> int:
        """任务总数"""
        return len(self._tasks)

    def get_task(self, task_id: str) -> Optional[Task]:
        """根据 ID 获取任务

        Args:
            task_id: 任务 ID

        Returns:
            Task 实例，不存在则返回 None
        """
        return self._tasks.get(task_id)

    def get_successors(self, task_id: str) -> list[str]:
        """获取指定任务的后继任务 ID 列表

        Args:
            task_id: 任务 ID

        Returns:
            依赖此任务的后继 task_id 列表
        """
        return list(self._edges.get(task_id, []))

    def get_dependencies(self, task_id: str) -> list[str]:
        """获取指定任务的前置依赖 ID 列表

        Args:
            task_id: 任务 ID

        Returns:
            此任务依赖的前置 task_id 列表
        """
        task = self._tasks.get(task_id)
        if task is None:
            return []
        return list(task.dependencies)

    def get_root_tasks(self) -> list[str]:
        """获取入度为 0 的根任务 ID 列表

        根任务没有前置依赖，可以立即开始执行。

        Returns:
            入度为 0 的 task_id 列表
        """
        return [
            tid for tid, deg in self._in_degree.items()
            if deg == 0
        ]

    def get_leaf_tasks(self) -> list[str]:
        """获取出度为 0 的叶子任务 ID 列表

        叶子任务没有后继任务，是执行链的终点。

        Returns:
            没有后继的 task_id 列表
        """
        return [
            tid for tid in self._tasks
            if not self._edges.get(tid, [])
        ]


def build_dag(tasks: list[Task]) -> TaskDAG:
    """从 Task 列表构建任务 DAG

    解析每个任务的 dependencies 字段，构建邻接表和入度表。
    如果检测到循环依赖或无效依赖引用，抛出异常。

    构建步骤：
    1. 校验 task.id 唯一性
    2. 校验 dependencies 引用有效性
    3. 构建邻接表（被依赖 → 依赖它的后继列表）
    4. 计算入度表（每个任务的前置依赖数量）
    5. 检测循环依赖

    Args:
        tasks: Task 列表

    Returns:
        TaskDAG: 构建完成的任务依赖图

    Raises:
        ValueError: task.id 重复或 dependencies 引用不存在的任务
        CyclicDependencyError: 存在循环依赖
    """
    if not tasks:
        return TaskDAG(tasks={}, edges={}, in_degree={})

    # Step 1: 校验 task.id 唯一性
    task_dict: dict[str, Task] = {}
    for task in tasks:
        if task.id in task_dict:
            raise ValueError(
                f"Duplicate task ID: '{task.id}'. "
                f"Task IDs must be unique."
            )
        task_dict[task.id] = task

    # Step 2: 校验 dependencies 引用有效性
    for task in tasks:
        for dep_id in task.dependencies:
            if dep_id not in task_dict:
                raise ValueError(
                    f"Task '{task.id}' depends on non-existent "
                    f"task '{dep_id}'. "
                    f"All dependencies must reference existing tasks."
                )

    # Step 3: 构建邻接表
    edges: dict[str, list[str]] = {tid: [] for tid in task_dict}
    for task in tasks:
        for dep_id in task.dependencies:
            edges[dep_id].append(task.id)

    # Step 4: 计算入度表
    in_degree: dict[str, int] = {tid: 0 for tid in task_dict}
    for task in tasks:
        in_degree[task.id] = len(task.dependencies)

    # Step 5: 检测循环依赖
    cycle = detect_cycle_from_tables(task_dict, edges, in_degree)
    if cycle:
        raise CyclicDependencyError(cycle)

    logger.info(
        "Built DAG: %d tasks, %d edges, %d root tasks",
        len(task_dict),
        sum(len(v) for v in edges.values()),
        sum(1 for d in in_degree.values() if d == 0),
    )

    return TaskDAG(tasks=task_dict, edges=edges, in_degree=in_degree)


def topological_sort(dag: TaskDAG) -> list[str]:
    """对 DAG 进行拓扑排序（Kahn 算法）

    返回合法的执行顺序：被依赖的任务排在前面。
    同层级的任务按优先级排序（HIGH > MEDIUM > LOW）。

    算法步骤（Kahn）：
    1. 将入度为 0 的节点加入队列
    2. 弹出队列头部，加入结果
    3. 将其后继节点的入度减 1
    4. 入度变为 0 的后继加入队列
    5. 重复直到队列为空

    Args:
        dag: 任务 DAG

    Returns:
        拓扑排序后的 task_id 列表

    Raises:
        CyclicDependencyError: 图中存在环（结果不完整时）
    """
    if dag.task_count == 0:
        return []

    # 复制入度表（不修改原始 DAG）
    in_degree = dict(dag.in_degree)
    edges = dag.edges

    # 优先级排序权重
    priority_weight = {
        TaskPriority.HIGH: 0,
        TaskPriority.MEDIUM: 1,
        TaskPriority.LOW: 2,
    }

    # 初始化队列：入度为 0 的任务，按优先级排序
    queue: deque[str] = deque(
        sorted(
            (tid for tid, deg in in_degree.items() if deg == 0),
            key=lambda tid: priority_weight.get(
                dag.get_task(tid).priority
                if dag.get_task(tid) else TaskPriority.MEDIUM,
                1,
            ),
        )
    )

    result: list[str] = []

    while queue:
        current = queue.popleft()
        result.append(current)

        # 处理后继节点
        successors = edges.get(current, [])
        # 按优先级排序后继
        sorted_successors = sorted(
            successors,
            key=lambda tid: priority_weight.get(
                dag.get_task(tid).priority
                if dag.get_task(tid) else TaskPriority.MEDIUM,
                1,
            ),
        )

        for successor in sorted_successors:
            in_degree[successor] -= 1
            if in_degree[successor] == 0:
                queue.append(successor)

    # 如果结果不完整，说明有环
    if len(result) != dag.task_count:
        missing = [
            tid for tid in dag.tasks if tid not in result
        ]
        raise CyclicDependencyError(missing)

    logger.debug(
        "Topological sort completed: %d tasks ordered", len(result)
    )

    return result


def compute_max_parallelism(dag: TaskDAG) -> dict[str, int]:
    """计算 DAG 的并行度分析

    按拓扑层级分析每一层可并行执行的任务数。
    同一层的任务之间没有依赖关系，可并发调度。

    返回值包含：
    - layers: 层级数
    - max_width: 最大层宽（最大并行度）
    - layer_details: 每层的任务 ID 和任务数

    Args:
        dag: 任务 DAG

    Returns:
        并行度分析结果字典：
        - "layers": 层级总数
        - "max_width": 最大并行度
        - "layer_details": 每层详情 [{"level": int, "tasks": list, "count": int}]
    """
    if dag.task_count == 0:
        return {
            "layers": 0,
            "max_width": 0,
            "layer_details": [],
        }

    # 使用 BFS 计算每个节点的层级
    # 层级 = 最长依赖路径长度 + 1
    in_degree = dict(dag.in_degree)
    edges = dag.edges

    # 计算每个任务的层级
    task_level: dict[str, int] = {}

    # 入度为 0 的任务是第 0 层
    queue: deque[str] = deque()
    for tid, deg in in_degree.items():
        if deg == 0:
            task_level[tid] = 0
            queue.append(tid)

    while queue:
        current = queue.popleft()
        for successor in edges.get(current, []):
            # 后继层级 = max(当前层级 + 1, 已计算层级)
            new_level = task_level[current] + 1
            if successor in task_level:
                task_level[successor] = max(
                    task_level[successor], new_level
                )
            else:
                task_level[successor] = new_level
            in_degree[successor] -= 1
            if in_degree[successor] == 0:
                queue.append(successor)

    # 按层级分组
    layers: dict[int, list[str]] = {}
    for tid, level in task_level.items():
        if level not in layers:
            layers[level] = []
        layers[level].append(tid)

    # 构建结果
    max_level = max(task_level.values()) if task_level else 0
    layer_details = []
    max_width = 0

    for level in range(max_level + 1):
        tasks_in_level = layers.get(level, [])
        count = len(tasks_in_level)
        max_width = max(max_width, count)
        layer_details.append({
            "level": level,
            "tasks": tasks_in_level,
            "count": count,
        })

    result = {
        "layers": max_level + 1,
        "max_width": max_width,
        "layer_details": layer_details,
    }

    logger.info(
        "Parallelism analysis: %d layers, max width=%d",
        result["layers"],
        result["max_width"],
    )

    return result


def detect_cycle(tasks: list[Task]) -> Optional[list[str]]:
    """检测任务列表中是否存在循环依赖

    使用 DFS 着色法检测环：
    - WHITE (0): 未访问
    - GRAY (1): 正在访问（在当前递归栈中）
    - BLACK (2): 已完成访问

    当在 DFS 过程中遇到 GRAY 节点时，说明存在环。

    Args:
        tasks: Task 列表

    Returns:
        参与循环的 task_id 列表，无环则返回 None
    """
    if not tasks:
        return None

    task_dict = {t.id: t for t in tasks}
    color: dict[str, int] = {tid: 0 for tid in task_dict}  # 0=WHITE
    parent: dict[str, Optional[str]] = {tid: None for tid in task_dict}

    def dfs(node: str) -> Optional[list[str]]:
        color[node] = 1  # GRAY

        task = task_dict.get(node)
        if task:
            for dep_id in task.dependencies:
                if dep_id not in color:
                    # 依赖指向不存在的任务（跳过，build_dag 会处理）
                    continue

                if color[dep_id] == 1:  # GRAY → 发现环
                    # 回溯环路径
                    cycle = [dep_id, node]
                    current = node
                    while parent[current] is not None and parent[current] != dep_id:
                        current = parent[current]
                        cycle.append(current)
                    cycle.reverse()
                    return cycle

                if color[dep_id] == 0:  # WHITE → 继续搜索
                    parent[dep_id] = node
                    result = dfs(dep_id)
                    if result:
                        return result

        color[node] = 2  # BLACK
        return None

    for tid in task_dict:
        if color[tid] == 0:
            cycle = dfs(tid)
            if cycle:
                return cycle

    return None


def detect_cycle_from_tables(
    tasks: dict[str, Task],
    edges: dict[str, list[str]],
    in_degree: dict[str, int],
) -> Optional[list[str]]:
    """从邻接表和入度表检测循环依赖（Kahn 算法）

    Kahn 算法执行后如果还有节点未处理，说明存在环。

    Args:
        tasks: 任务字典
        edges: 邻接表
        in_degree: 入度表

    Returns:
        参与循环的 task_id 列表，无环则返回 None
    """
    if not tasks:
        return None

    # 复制入度表
    remaining_degree = dict(in_degree)
    queue: deque[str] = deque()

    for tid, deg in remaining_degree.items():
        if deg == 0:
            queue.append(tid)

    processed = 0
    while queue:
        current = queue.popleft()
        processed += 1

        for successor in edges.get(current, []):
            remaining_degree[successor] -= 1
            if remaining_degree[successor] == 0:
                queue.append(successor)

    # 未处理的节点构成环
    if processed < len(tasks):
        cycle_nodes = [
            tid for tid, deg in remaining_degree.items()
            if deg > 0
        ]
        return cycle_nodes

    return None

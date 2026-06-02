"""
P1-046: 任务 DAG 分析 — 单元测试

覆盖范围：
- TaskDAG 属性与方法 (8)
- build_dag 基本构建 (7)
- topological_sort 拓扑排序 (8)
- compute_max_parallelism 并行度分析 (6)
- detect_cycle 循环依赖检测 (6)
- CyclicDependencyError (2)
- 边界条件 (5)
- 与 MasterAgent 集成 (3)
合计: 45 项
"""

import pytest

from agent_automation_system.models.task import Task, TaskPriority, TaskStatus
from agent_automation_system.scheduler.dag import (
    CyclicDependencyError,
    TaskDAG,
    build_dag,
    compute_max_parallelism,
    detect_cycle,
    detect_cycle_from_tables,
    topological_sort,
)


# ── 测试辅助 ──────────────────────────────────────────────


def _make_task(
    task_id: str,
    title: str = "test",
    dependencies: list[str] | None = None,
    priority: TaskPriority = TaskPriority.MEDIUM,
) -> Task:
    """创建 Task 实例"""
    return Task(
        id=task_id,
        title=title,
        description=f"Task {task_id}",
        dependencies=dependencies or [],
        priority=priority,
    )


def _make_linear_tasks(count: int) -> list[Task]:
    """创建线性依赖链: task-001 → task-002 → ... → task-N"""
    tasks = []
    for i in range(1, count + 1):
        tid = f"task-{i:03d}"
        deps = [f"task-{i-1:03d}"] if i > 1 else []
        tasks.append(_make_task(tid, dependencies=deps))
    return tasks


def _make_diamond_tasks() -> list[Task]:
    """创建菱形依赖:
        task-001
       /       \\
  task-002  task-003
       \\       /
        task-004
    """
    return [
        _make_task("task-001"),
        _make_task("task-002", dependencies=["task-001"]),
        _make_task("task-003", dependencies=["task-001"]),
        _make_task("task-004", dependencies=["task-002", "task-003"]),
    ]


# ── TaskDAG 属性与方法 ────────────────────────────────────


class TestTaskDAGProperties:
    """TaskDAG 属性与方法测试"""

    def test_tasks_property(self):
        """tasks 属性返回只读副本"""
        tasks = [_make_task("task-001")]
        dag = build_dag(tasks)
        tasks_copy = dag.tasks
        assert "task-001" in tasks_copy
        # 修改副本不影响原始
        tasks_copy["task-999"] = _make_task("task-999")
        assert "task-999" not in dag.tasks

    def test_edges_property(self):
        """edges 属性返回只读副本"""
        tasks = [
            _make_task("task-001"),
            _make_task("task-002", dependencies=["task-001"]),
        ]
        dag = build_dag(tasks)
        edges_copy = dag.edges
        assert "task-001" in edges_copy
        edges_copy["task-001"].append("task-999")
        assert "task-999" not in dag.edges["task-001"]

    def test_in_degree_property(self):
        """in_degree 属性返回只读副本"""
        tasks = _make_diamond_tasks()
        dag = build_dag(tasks)
        in_deg = dag.in_degree
        assert in_deg["task-001"] == 0
        assert in_deg["task-004"] == 2

    def test_task_count(self):
        """task_count 返回任务总数"""
        tasks = _make_diamond_tasks()
        dag = build_dag(tasks)
        assert dag.task_count == 4

    def test_get_task(self):
        """get_task 获取指定任务"""
        tasks = [_make_task("task-001")]
        dag = build_dag(tasks)
        assert dag.get_task("task-001") is not None
        assert dag.get_task("task-999") is None

    def test_get_successors(self):
        """get_successors 获取后继任务"""
        tasks = _make_diamond_tasks()
        dag = build_dag(tasks)
        successors = dag.get_successors("task-001")
        assert set(successors) == {"task-002", "task-003"}

    def test_get_root_tasks(self):
        """get_root_tasks 获取入度为 0 的根任务"""
        tasks = _make_diamond_tasks()
        dag = build_dag(tasks)
        roots = dag.get_root_tasks()
        assert roots == ["task-001"]

    def test_get_leaf_tasks(self):
        """get_leaf_tasks 获取出度为 0 的叶子任务"""
        tasks = _make_diamond_tasks()
        dag = build_dag(tasks)
        leaves = dag.get_leaf_tasks()
        assert leaves == ["task-004"]


# ── build_dag 基本构建 ───────────────────────────────────


class TestBuildDag:
    """build_dag() 构建测试"""

    def test_empty_tasks(self):
        """空任务列表返回空 DAG"""
        dag = build_dag([])
        assert dag.task_count == 0

    def test_single_task_no_deps(self):
        """单个无依赖任务"""
        tasks = [_make_task("task-001")]
        dag = build_dag(tasks)
        assert dag.task_count == 1
        assert dag.in_degree["task-001"] == 0

    def test_linear_chain(self):
        """线性依赖链"""
        tasks = _make_linear_tasks(3)
        dag = build_dag(tasks)
        assert dag.task_count == 3
        assert dag.in_degree["task-001"] == 0
        assert dag.in_degree["task-002"] == 1
        assert dag.in_degree["task-003"] == 1

    def test_diamond_dependency(self):
        """菱形依赖"""
        tasks = _make_diamond_tasks()
        dag = build_dag(tasks)
        assert dag.in_degree["task-001"] == 0
        assert dag.in_degree["task-002"] == 1
        assert dag.in_degree["task-003"] == 1
        assert dag.in_degree["task-004"] == 2

    def test_duplicate_task_id_raises(self):
        """重复 task.id 抛出 ValueError"""
        tasks = [
            _make_task("task-001"),
            _make_task("task-001", title="duplicate"),
        ]
        with pytest.raises(ValueError, match="Duplicate task ID"):
            build_dag(tasks)

    def test_invalid_dependency_raises(self):
        """引用不存在的依赖抛出 ValueError"""
        tasks = [
            _make_task("task-001", dependencies=["task-999"]),
        ]
        with pytest.raises(ValueError, match="non-existent"):
            build_dag(tasks)

    def test_cyclic_dependency_raises(self):
        """循环依赖抛出 CyclicDependencyError"""
        tasks = [
            _make_task("task-001", dependencies=["task-002"]),
            _make_task("task-002", dependencies=["task-001"]),
        ]
        with pytest.raises(CyclicDependencyError, match="Cyclic dependency"):
            build_dag(tasks)


# ── topological_sort 拓扑排序 ─────────────────────────────


class TestTopologicalSort:
    """topological_sort() 拓扑排序测试"""

    def test_empty_dag(self):
        """空 DAG 返回空列表"""
        dag = build_dag([])
        assert topological_sort(dag) == []

    def test_single_task(self):
        """单个任务"""
        tasks = [_make_task("task-001")]
        dag = build_dag(tasks)
        result = topological_sort(dag)
        assert result == ["task-001"]

    def test_linear_chain(self):
        """线性依赖链排序"""
        tasks = _make_linear_tasks(3)
        dag = build_dag(tasks)
        result = topological_sort(dag)
        # task-001 必须在 task-002 之前，task-002 在 task-003 之前
        assert result.index("task-001") < result.index("task-002")
        assert result.index("task-002") < result.index("task-003")

    def test_diamond_dependency(self):
        """菱形依赖排序"""
        tasks = _make_diamond_tasks()
        dag = build_dag(tasks)
        result = topological_sort(dag)
        assert result.index("task-001") < result.index("task-002")
        assert result.index("task-001") < result.index("task-003")
        assert result.index("task-002") < result.index("task-004")
        assert result.index("task-003") < result.index("task-004")

    def test_priority_ordering(self):
        """同层级任务按优先级排序"""
        tasks = [
            _make_task("task-001", priority=TaskPriority.LOW),
            _make_task("task-002", priority=TaskPriority.HIGH),
            _make_task("task-003", priority=TaskPriority.MEDIUM),
        ]
        dag = build_dag(tasks)
        result = topological_sort(dag)
        # HIGH 优先排在前面
        assert result[0] == "task-002"
        assert result[1] == "task-003"
        assert result[2] == "task-001"

    def test_independent_tasks_order(self):
        """多个独立任务（无依赖）排序"""
        tasks = [
            _make_task("task-001"),
            _make_task("task-002"),
            _make_task("task-003"),
        ]
        dag = build_dag(tasks)
        result = topological_sort(dag)
        assert len(result) == 3
        assert set(result) == {"task-001", "task-002", "task-003"}

    def test_complex_dag(self):
        """复杂 DAG 排序正确性"""
        #   task-001 → task-003
        #   task-002 → task-003
        #   task-002 → task-004
        #   task-003 → task-005
        #   task-004 → task-005
        tasks = [
            _make_task("task-001"),
            _make_task("task-002"),
            _make_task("task-003", dependencies=["task-001", "task-002"]),
            _make_task("task-004", dependencies=["task-002"]),
            _make_task("task-005", dependencies=["task-003", "task-004"]),
        ]
        dag = build_dag(tasks)
        result = topological_sort(dag)
        assert len(result) == 5
        # 验证所有依赖顺序
        assert result.index("task-001") < result.index("task-003")
        assert result.index("task-002") < result.index("task-003")
        assert result.index("task-002") < result.index("task-004")
        assert result.index("task-003") < result.index("task-005")
        assert result.index("task-004") < result.index("task-005")

    def test_cycle_in_sort_raises(self):
        """有环时拓扑排序抛出异常"""
        # 手动构建含环的 DAG（绕过 build_dag 的循环检测）
        task = _make_task("task-001")
        dag = TaskDAG(
            tasks={"task-001": task},
            edges={"task-001": []},
            in_degree={"task-001": 1},  # 入度 1 但无根节点 → 有环
        )
        with pytest.raises(CyclicDependencyError):
            topological_sort(dag)


# ── compute_max_parallelism 并行度分析 ─────────────────────


class TestComputeMaxParallelism:
    """compute_max_parallelism() 并行度分析测试"""

    def test_empty_dag(self):
        """空 DAG 返回零值"""
        dag = build_dag([])
        result = compute_max_parallelism(dag)
        assert result["layers"] == 0
        assert result["max_width"] == 0

    def test_single_task(self):
        """单个任务：1 层，最大并行度 1"""
        tasks = [_make_task("task-001")]
        dag = build_dag(tasks)
        result = compute_max_parallelism(dag)
        assert result["layers"] == 1
        assert result["max_width"] == 1
        assert len(result["layer_details"]) == 1
        assert result["layer_details"][0]["count"] == 1

    def test_linear_chain(self):
        """线性链：3 层，最大并行度 1"""
        tasks = _make_linear_tasks(3)
        dag = build_dag(tasks)
        result = compute_max_parallelism(dag)
        assert result["layers"] == 3
        assert result["max_width"] == 1

    def test_diamond_dependency(self):
        """菱形依赖：3 层，最大并行度 2"""
        tasks = _make_diamond_tasks()
        dag = build_dag(tasks)
        result = compute_max_parallelism(dag)
        assert result["layers"] == 3
        assert result["max_width"] == 2
        # 第 0 层: task-001
        # 第 1 层: task-002, task-003
        # 第 2 层: task-004
        assert result["layer_details"][0]["count"] == 1
        assert result["layer_details"][1]["count"] == 2
        assert result["layer_details"][2]["count"] == 1

    def test_fully_parallel(self):
        """全并行（无依赖）：1 层，并行度 = 任务数"""
        tasks = [
            _make_task("task-001"),
            _make_task("task-002"),
            _make_task("task-003"),
            _make_task("task-004"),
        ]
        dag = build_dag(tasks)
        result = compute_max_parallelism(dag)
        assert result["layers"] == 1
        assert result["max_width"] == 4

    def test_wide_middle_layer(self):
        """中间层最宽"""
        tasks = [
            _make_task("task-001"),
            _make_task("task-002", dependencies=["task-001"]),
            _make_task("task-003", dependencies=["task-001"]),
            _make_task("task-004", dependencies=["task-001"]),
            _make_task("task-005", dependencies=["task-002", "task-003", "task-004"]),
        ]
        dag = build_dag(tasks)
        result = compute_max_parallelism(dag)
        assert result["layers"] == 3
        assert result["max_width"] == 3


# ── detect_cycle 循环依赖检测 ─────────────────────────────


class TestDetectCycle:
    """detect_cycle() 循环依赖检测测试"""

    def test_no_cycle(self):
        """无循环依赖"""
        tasks = _make_diamond_tasks()
        assert detect_cycle(tasks) is None

    def test_simple_cycle(self):
        """简单双向循环"""
        tasks = [
            _make_task("task-001", dependencies=["task-002"]),
            _make_task("task-002", dependencies=["task-001"]),
        ]
        cycle = detect_cycle(tasks)
        assert cycle is not None
        assert len(cycle) > 0

    def test_three_node_cycle(self):
        """三节点循环: 1→2→3→1"""
        tasks = [
            _make_task("task-001", dependencies=["task-003"]),
            _make_task("task-002", dependencies=["task-001"]),
            _make_task("task-003", dependencies=["task-002"]),
        ]
        cycle = detect_cycle(tasks)
        assert cycle is not None

    def test_empty_tasks(self):
        """空任务列表"""
        assert detect_cycle([]) is None

    def test_self_dependency_caught_by_model(self):
        """自依赖由 Task 模型校验拦截"""
        # Task 模型的 validate_no_self_dependency 会拦截
        with pytest.raises(ValueError):
            _make_task("task-001", dependencies=["task-001"])

    def test_longer_cycle(self):
        """更长的循环依赖链"""
        tasks = [
            _make_task("task-001", dependencies=["task-004"]),
            _make_task("task-002", dependencies=["task-001"]),
            _make_task("task-003", dependencies=["task-002"]),
            _make_task("task-004", dependencies=["task-003"]),
        ]
        cycle = detect_cycle(tasks)
        assert cycle is not None


# ── CyclicDependencyError ─────────────────────────────────


class TestCyclicDependencyError:
    """CyclicDependencyError 异常测试"""

    def test_error_message_contains_cycle(self):
        """错误消息包含循环路径"""
        err = CyclicDependencyError(["task-001", "task-002", "task-001"])
        assert "task-001" in str(err)
        assert "task-002" in str(err)
        assert "→" in str(err)

    def test_cycle_nodes_attribute(self):
        """cycle_nodes 属性包含循环节点"""
        nodes = ["task-001", "task-002"]
        err = CyclicDependencyError(nodes)
        assert err.cycle_nodes == nodes


# ── 边界条件 ──────────────────────────────────────────────


class TestEdgeCases:
    """边界条件测试"""

    def test_task_with_many_dependencies(self):
        """任务有多个依赖"""
        tasks = [
            _make_task("task-001"),
            _make_task("task-002"),
            _make_task("task-003"),
            _make_task("task-004", dependencies=["task-001", "task-002", "task-003"]),
        ]
        dag = build_dag(tasks)
        assert dag.in_degree["task-004"] == 3
        roots = dag.get_root_tasks()
        assert len(roots) == 3

    def test_single_long_chain(self):
        """单条长依赖链"""
        tasks = _make_linear_tasks(10)
        dag = build_dag(tasks)
        result = topological_sort(dag)
        assert len(result) == 10
        # 验证顺序
        for i in range(9):
            idx_current = result.index(f"task-{i+1:03d}")
            idx_next = result.index(f"task-{i+2:03d}")
            assert idx_current < idx_next

    def test_wide_dag(self):
        """宽 DAG（多根任务汇合到单叶子）"""
        tasks = [_make_task(f"task-{i:03d}") for i in range(1, 6)]
        tasks.append(
            _make_task("task-006", dependencies=[
                "task-001", "task-002", "task-003",
                "task-004", "task-005",
            ])
        )
        dag = build_dag(tasks)
        assert dag.in_degree["task-006"] == 5
        parallelism = compute_max_parallelism(dag)
        assert parallelism["max_width"] == 5

    def test_detect_cycle_from_tables_no_cycle(self):
        """detect_cycle_from_tables 无环"""
        tasks = _make_diamond_tasks()
        dag = build_dag(tasks)
        result = detect_cycle_from_tables(dag.tasks, dag.edges, dag.in_degree)
        assert result is None

    def test_detect_cycle_from_tables_with_cycle(self):
        """detect_cycle_from_tables 有环"""
        # 手动构造含环数据
        t1 = _make_task("task-001", dependencies=["task-002"])
        t2 = _make_task("task-002", dependencies=["task-001"])
        # 不用 build_dag（会抛异常），手动构建
        tasks = {"task-001": t1, "task-002": t2}
        edges = {"task-001": ["task-002"], "task-002": ["task-001"]}
        in_degree = {"task-001": 1, "task-002": 1}
        result = detect_cycle_from_tables(tasks, edges, in_degree)
        assert result is not None
        assert set(result) == {"task-001", "task-002"}


# ── 与 MasterAgent 集成 ──────────────────────────────────


class TestMasterAgentIntegration:
    """DAG 与 MasterAgent 集成测试"""

    def test_build_dag_from_master_task_json(self):
        """从 MasterAgent.task_json 构建 DAG"""
        from agent_automation_system.models.task_json import TaskJSON
        from agent_automation_system.master_agent.master_agent import MasterAgent

        tasks = [
            _make_task("task-001"),
            _make_task("task-002", dependencies=["task-001"]),
            _make_task("task-003", dependencies=["task-001"]),
            _make_task("task-004", dependencies=["task-002", "task-003"]),
        ]
        task_json = TaskJSON(
            project_name="test",
            total_tasks=4,
            tasks=tasks,
        )

        def factory(role):
            from unittest.mock import MagicMock
            from agent_automation_system.sub_agent.sub_agent import SubAgent
            a = MagicMock(spec=SubAgent)
            a.role_name = role
            return a

        master = MasterAgent(agent_factory=factory)
        master.receive_requirement("test")
        master.set_task_json(task_json)

        # 从 MasterAgent 的 task_json 构建 DAG
        dag = build_dag(list(master.task_json.tasks))
        assert dag.task_count == 4

        sorted_ids = topological_sort(dag)
        assert sorted_ids[0] == "task-001"
        assert sorted_ids[-1] == "task-004"

    def test_parallelism_informs_scheduling(self):
        """并行度分析指导调度决策"""
        tasks = [
            _make_task("task-001"),
            _make_task("task-002", dependencies=["task-001"]),
            _make_task("task-003", dependencies=["task-001"]),
            _make_task("task-004", dependencies=["task-002", "task-003"]),
        ]
        dag = build_dag(tasks)
        parallelism = compute_max_parallelism(dag)
        # 最大并行度为 2，意味着同时最多调度 2 个 Sub-Agent
        assert parallelism["max_width"] == 2

    def test_dispatchable_tasks_match_dag_roots(self):
        """MasterAgent 可调度任务与 DAG 根任务一致"""
        from agent_automation_system.models.task_json import TaskJSON
        from agent_automation_system.master_agent.master_agent import MasterAgent

        tasks = _make_diamond_tasks()
        task_json = TaskJSON(
            project_name="test",
            total_tasks=4,
            tasks=tasks,
        )

        def factory(role):
            from unittest.mock import MagicMock
            from agent_automation_system.sub_agent.sub_agent import SubAgent
            a = MagicMock(spec=SubAgent)
            a.role_name = role
            return a

        master = MasterAgent(agent_factory=factory)
        master.receive_requirement("test")
        master.set_task_json(task_json)

        # MasterAgent 的可调度任务
        dispatchable = master.get_dispatchable_tasks()
        dispatchable_ids = [t.id for t in dispatchable]

        # DAG 的根任务
        dag = build_dag(list(master.task_json.tasks))
        root_ids = dag.get_root_tasks()

        assert dispatchable_ids == root_ids

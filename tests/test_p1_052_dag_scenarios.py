"""
P1-052: DAG 分析 — 依赖图场景单元测试

补充 P1-046 之外的各种依赖图场景：
- 菱形依赖（Diamond）变体
- 扇出 / 扇入（Fan-out / Fan-in）
- 深层链式（Deep Chain）
- 多根多叶（Multi-root / Multi-leaf）
- 混合优先级排序
- 孤立任务（Isolated）
- 复杂真实图
- 并行度边界
- 拓扑排序稳定性
"""

import pytest

from agent_automation_system.models.task import Task, TaskPriority, TaskStatus, BDDSpec
from agent_automation_system.scheduler.dag import (
    CyclicDependencyError,
    TaskDAG,
    build_dag,
    compute_max_parallelism,
    detect_cycle,
    topological_sort,
)


# ── 辅助工具 ──────────────────────────────────────────────


def _task(
    task_id: str,
    deps: list[str] | None = None,
    priority: TaskPriority = TaskPriority.MEDIUM,
) -> Task:
    """快速创建测试 Task"""
    return Task(
        id=task_id,
        title=f"Task {task_id}",
        description=f"Description for {task_id}",
        bdd=BDDSpec(given="context", when="action", then="result"),
        dependencies=deps or [],
        priority=priority,
    )


# ── 菱形依赖变体 ──────────────────────────────────────────


class TestDiamondVariants:
    """菱形依赖图的各种变体"""

    def test_double_diamond(self):
        """双菱形：A→B,C → D → E,F → G"""
        tasks = [
            _task("task-001"),
            _task("task-002", deps=["task-001"]),
            _task("task-003", deps=["task-001"]),
            _task("task-004", deps=["task-002", "task-003"]),
            _task("task-005", deps=["task-004"]),
            _task("task-006", deps=["task-004"]),
            _task("task-007", deps=["task-005", "task-006"]),
        ]
        dag = build_dag(tasks)
        order = topological_sort(dag)

        assert order.index("task-001") < order.index("task-002")
        assert order.index("task-001") < order.index("task-003")
        assert order.index("task-002") < order.index("task-004")
        assert order.index("task-003") < order.index("task-004")
        assert order.index("task-004") < order.index("task-005")
        assert order.index("task-004") < order.index("task-006")
        assert order.index("task-005") < order.index("task-007")
        assert order.index("task-006") < order.index("task-007")

    def test_diamond_with_bypass(self):
        """菱形+旁路：A→B→C→D 且 A→D"""
        tasks = [
            _task("task-001"),
            _task("task-002", deps=["task-001"]),
            _task("task-003", deps=["task-002"]),
            _task("task-004", deps=["task-001", "task-003"]),
        ]
        dag = build_dag(tasks)
        order = topological_sort(dag)

        assert order.index("task-001") < order.index("task-002")
        assert order.index("task-002") < order.index("task-003")
        assert order.index("task-003") < order.index("task-004")

    def test_nested_diamond(self):
        """嵌套菱形：A→B,C → D→E,F → G"""
        tasks = [
            _task("task-001"),
            _task("task-002", deps=["task-001"]),
            _task("task-003", deps=["task-001"]),
            _task("task-004", deps=["task-002", "task-003"]),
            _task("task-005", deps=["task-004"]),
            _task("task-006", deps=["task-004"]),
            _task("task-007", deps=["task-005", "task-006"]),
        ]
        dag = build_dag(tasks)
        para = compute_max_parallelism(dag)

        # 第 0 层: task-001 (1)
        # 第 1 层: task-002, task-003 (2)
        # 第 2 层: task-004 (1)
        # 第 3 层: task-005, task-006 (2)
        # 第 4 层: task-007 (1)
        assert para["layers"] == 5
        assert para["max_width"] == 2


# ── 扇出 / 扇入 ───────────────────────────────────────────


class TestFanOutFanIn:
    """扇出（一个→多个）和扇入（多个→一个）"""

    def test_fan_out_single_to_many(self):
        """扇出：1→N"""
        tasks = [
            _task("task-001"),
            _task("task-002", deps=["task-001"]),
            _task("task-003", deps=["task-001"]),
            _task("task-004", deps=["task-001"]),
            _task("task-005", deps=["task-001"]),
        ]
        dag = build_dag(tasks)
        para = compute_max_parallelism(dag)

        assert para["max_width"] == 4  # 第 1 层 4 个并行
        assert dag.get_successors("task-001") == ["task-002", "task-003", "task-004", "task-005"]

    def test_fan_in_many_to_one(self):
        """扇入：N→1"""
        tasks = [
            _task("task-001"),
            _task("task-002"),
            _task("task-003"),
            _task("task-004"),
            _task("task-005", deps=["task-001", "task-002", "task-003", "task-004"]),
        ]
        dag = build_dag(tasks)
        para = compute_max_parallelism(dag)

        assert para["max_width"] == 4  # 第 0 层 4 个根并行
        assert dag.in_degree["task-005"] == 4
        assert dag.get_leaf_tasks() == ["task-005"]

    def test_fan_out_then_fan_in(self):
        """扇出再扇入：A→B,C,D→E"""
        tasks = [
            _task("task-001"),
            _task("task-002", deps=["task-001"]),
            _task("task-003", deps=["task-001"]),
            _task("task-004", deps=["task-001"]),
            _task("task-005", deps=["task-002", "task-003", "task-004"]),
        ]
        dag = build_dag(tasks)

        assert len(dag.get_root_tasks()) == 1
        assert len(dag.get_leaf_tasks()) == 1

    def test_multi_fan_out_stages(self):
        """多级扇出：A→B,C → D,E,F,G"""
        tasks = [
            _task("task-001"),
            _task("task-002", deps=["task-001"]),
            _task("task-003", deps=["task-001"]),
            _task("task-004", deps=["task-002"]),
            _task("task-005", deps=["task-002"]),
            _task("task-006", deps=["task-003"]),
            _task("task-007", deps=["task-003"]),
        ]
        dag = build_dag(tasks)
        para = compute_max_parallelism(dag)

        # 第 2 层 4 个并行
        assert para["max_width"] == 4
        assert para["layers"] == 3


# ── 深层链式 ───────────────────────────────────────────────


class TestDeepChain:
    """深层链式依赖"""

    def test_chain_of_10(self):
        """10 个任务的线性链"""
        tasks = [_task("task-001")]
        for i in range(2, 11):
            tasks.append(_task(f"task-{i:03d}", deps=[f"task-{i-1:03d}"]))

        dag = build_dag(tasks)
        order = topological_sort(dag)

        assert len(order) == 10
        for i in range(9):
            assert order.index(f"task-{i+1:03d}") < order.index(f"task-{i+2:03d}")

    def test_chain_parallelism_is_one(self):
        """线性链并行度为 1"""
        tasks = [_task("task-001")]
        for i in range(2, 6):
            tasks.append(_task(f"task-{i:03d}", deps=[f"task-{i-1:03d}"]))

        dag = build_dag(tasks)
        para = compute_max_parallelism(dag)

        assert para["max_width"] == 1
        assert para["layers"] == 5

    def test_two_parallel_chains(self):
        """两条并行链：A→B→C 和 D→E→F"""
        tasks = [
            _task("task-001"),
            _task("task-002", deps=["task-001"]),
            _task("task-003", deps=["task-002"]),
            _task("task-004"),
            _task("task-005", deps=["task-004"]),
            _task("task-006", deps=["task-005"]),
        ]
        dag = build_dag(tasks)
        para = compute_max_parallelism(dag)

        assert para["max_width"] == 2  # 两条链并行
        assert len(dag.get_root_tasks()) == 2
        assert len(dag.get_leaf_tasks()) == 2

    def test_chain_converging(self):
        """多条链汇聚：A→C, B→C, C→D"""
        tasks = [
            _task("task-001"),
            _task("task-002"),
            _task("task-003", deps=["task-001", "task-002"]),
            _task("task-004", deps=["task-003"]),
        ]
        dag = build_dag(tasks)
        order = topological_sort(dag)

        assert order.index("task-001") < order.index("task-003")
        assert order.index("task-002") < order.index("task-003")
        assert order.index("task-003") < order.index("task-004")


# ── 多根多叶 ───────────────────────────────────────────────


class TestMultiRootMultiLeaf:
    """多根节点和多叶节点场景"""

    def test_three_independent_roots(self):
        """3 个完全独立的根任务"""
        tasks = [
            _task("task-001"),
            _task("task-002"),
            _task("task-003"),
        ]
        dag = build_dag(tasks)

        assert len(dag.get_root_tasks()) == 3
        assert len(dag.get_leaf_tasks()) == 3
        assert dag.task_count == 3

    def test_roots_with_different_priorities(self):
        """多个根任务，优先级不同"""
        tasks = [
            _task("task-001", priority=TaskPriority.LOW),
            _task("task-002", priority=TaskPriority.HIGH),
            _task("task-003", priority=TaskPriority.MEDIUM),
        ]
        dag = build_dag(tasks)
        order = topological_sort(dag)

        assert order[0] == "task-002"  # HIGH first
        assert order[1] == "task-003"  # MEDIUM second
        assert order[2] == "task-001"  # LOW last

    def test_multiple_leaves_converge_to_root(self):
        """多叶节点各自汇聚到不同根"""
        tasks = [
            _task("task-001"),
            _task("task-002"),
            _task("task-003", deps=["task-001"]),
            _task("task-004", deps=["task-002"]),
        ]
        dag = build_dag(tasks)

        roots = dag.get_root_tasks()
        assert "task-001" in roots
        assert "task-002" in roots

    def test_forest_graph(self):
        """森林图：多棵独立的子树"""
        # 子树1: task-001 → task-002
        # 子树2: task-003 → task-004 → task-005
        # 子树3: task-006
        tasks = [
            _task("task-001"),
            _task("task-002", deps=["task-001"]),
            _task("task-003"),
            _task("task-004", deps=["task-003"]),
            _task("task-005", deps=["task-004"]),
            _task("task-006"),
        ]
        dag = build_dag(tasks)

        assert len(dag.get_root_tasks()) == 3
        para = compute_max_parallelism(dag)
        assert para["max_width"] == 3  # 第 0 层 3 个根


# ── 混合优先级排序 ─────────────────────────────────────────


class TestMixedPriority:
    """混合优先级在拓扑排序中的表现"""

    def test_priority_breaks_ties_at_same_level(self):
        """同层级按优先级排序"""
        tasks = [
            _task("task-001", priority=TaskPriority.LOW),
            _task("task-002", priority=TaskPriority.HIGH),
            _task("task-003", priority=TaskPriority.MEDIUM),
        ]
        dag = build_dag(tasks)
        order = topological_sort(dag)

        assert order == ["task-002", "task-003", "task-001"]

    def test_dependency_overrides_priority(self):
        """依赖关系优先于优先级：LOW 根 → HIGH 叶"""
        tasks = [
            _task("task-001", priority=TaskPriority.LOW),
            _task("task-002", deps=["task-001"], priority=TaskPriority.HIGH),
        ]
        dag = build_dag(tasks)
        order = topological_sort(dag)

        # task-001 必须先完成，尽管优先级低
        assert order == ["task-001", "task-002"]

    def test_priority_ordering_in_diamond(self):
        """菱形图中同层按优先级排"""
        tasks = [
            _task("task-001"),
            _task("task-002", deps=["task-001"], priority=TaskPriority.LOW),
            _task("task-003", deps=["task-001"], priority=TaskPriority.HIGH),
            _task("task-004", deps=["task-002", "task-003"]),
        ]
        dag = build_dag(tasks)
        order = topological_sort(dag)

        # task-001 → task-003(HIGH) → task-002(LOW) → task-004
        idx_002 = order.index("task-002")
        idx_003 = order.index("task-003")
        assert idx_003 < idx_002

    def test_all_same_priority(self):
        """全部同优先级，按依赖顺序"""
        tasks = [
            _task("task-001", priority=TaskPriority.MEDIUM),
            _task("task-002", deps=["task-001"], priority=TaskPriority.MEDIUM),
            _task("task-003", priority=TaskPriority.MEDIUM),
        ]
        dag = build_dag(tasks)
        order = topological_sort(dag)

        assert order.index("task-001") < order.index("task-002")

    def test_priority_across_layers(self):
        """跨层优先级：高优先级在深层"""
        tasks = [
            _task("task-001", priority=TaskPriority.LOW),
            _task("task-002", priority=TaskPriority.LOW),
            _task("task-003", deps=["task-001", "task-002"], priority=TaskPriority.HIGH),
        ]
        dag = build_dag(tasks)
        order = topological_sort(dag)

        # task-003 依赖前两个，必须在后面
        assert order[-1] == "task-003"


# ── 孤立任务 ───────────────────────────────────────────────


class TestIsolatedTasks:
    """孤立任务（无依赖也无被依赖）"""

    def test_single_isolated_task(self):
        """单个孤立任务"""
        tasks = [_task("task-001")]
        dag = build_dag(tasks)

        assert dag.get_root_tasks() == ["task-001"]
        assert dag.get_leaf_tasks() == ["task-001"]
        assert dag.in_degree["task-001"] == 0

    def test_isolated_with_connected(self):
        """孤立任务与连接任务共存"""
        tasks = [
            _task("task-001"),
            _task("task-002"),
            _task("task-003", deps=["task-002"]),
        ]
        dag = build_dag(tasks)

        roots = dag.get_root_tasks()
        assert "task-001" in roots  # 孤立
        assert "task-002" in roots  # 有后继但入度为 0

    def test_isolated_in_parallelism(self):
        """孤立任务计入并行度"""
        tasks = [
            _task("task-001"),
            _task("task-002"),
            _task("task-003"),
        ]
        dag = build_dag(tasks)
        para = compute_max_parallelism(dag)

        assert para["max_width"] == 3
        assert para["layers"] == 1


# ── 复杂真实图 ─────────────────────────────────────────────


class TestComplexRealGraph:
    """模拟真实项目任务依赖图"""

    def test_full_stack_project(self):
        """模拟全栈项目：设计→前端/后端/DB→集成→测试→部署"""
        tasks = [
            _task("task-001", priority=TaskPriority.HIGH),                    # 设计
            _task("task-002", deps=["task-001"]),                              # DB Schema
            _task("task-003", deps=["task-001"]),                              # 前端框架
            _task("task-004", deps=["task-001"]),                              # 后端框架
            _task("task-005", deps=["task-002"]),                              # 数据模型
            _task("task-006", deps=["task-003"]),                              # UI 组件
            _task("task-007", deps=["task-004", "task-005"]),                  # API 实现
            _task("task-008", deps=["task-006", "task-007"]),                  # 集成
            _task("task-009", deps=["task-008"]),                              # 测试
            _task("task-010", deps=["task-009"], priority=TaskPriority.HIGH),  # 部署
        ]
        dag = build_dag(tasks)
        order = topological_sort(dag)
        para = compute_max_parallelism(dag)

        assert len(order) == 10
        assert order[0] == "task-001"
        assert order[-1] == "task-010"
        assert para["max_width"] >= 3  # 中间层有多并行
        assert dag.get_root_tasks() == ["task-001"]
        assert dag.get_leaf_tasks() == ["task-010"]

    def test_microservices_graph(self):
        """微服务架构：共享基础设施→多个独立服务→API 网关→E2E 测试"""
        tasks = [
            _task("task-001"),                                    # 基础设施
            _task("task-002", deps=["task-001"]),                  # 用户服务
            _task("task-003", deps=["task-001"]),                  # 订单服务
            _task("task-004", deps=["task-001"]),                  # 支付服务
            _task("task-005", deps=["task-001"]),                  # 通知服务
            _task("task-006", deps=["task-002", "task-003"]),      # API 网关(1)
            _task("task-007", deps=["task-004", "task-005"]),      # API 网关(2)
            _task("task-008", deps=["task-006", "task-007"]),      # E2E 测试
        ]
        dag = build_dag(tasks)
        para = compute_max_parallelism(dag)

        assert para["max_width"] == 4  # 第 1 层 4 个服务并行
        assert len(dag.get_root_tasks()) == 1
        assert len(dag.get_leaf_tasks()) == 1

    def test_pipeline_with_parallel_stages(self):
        """流水线+并行阶段：编译→(lint|test|security)→发布"""
        tasks = [
            _task("task-001", priority=TaskPriority.HIGH),       # 编译
            _task("task-002", deps=["task-001"]),                  # Lint
            _task("task-003", deps=["task-001"]),                  # Unit Test
            _task("task-004", deps=["task-001"]),                  # Security
            _task("task-005", deps=["task-002", "task-003", "task-004"], priority=TaskPriority.HIGH),  # 发布
        ]
        dag = build_dag(tasks)
        order = topological_sort(dag)

        assert order[0] == "task-001"
        assert order[-1] == "task-005"


# ── 并行度边界 ─────────────────────────────────────────────


class TestParallelismBoundary:
    """并行度分析边界场景"""

    def test_single_layer_all_parallel(self):
        """所有任务在同一层：最大并行度 = 任务数"""
        tasks = [_task(f"task-{i:03d}") for i in range(1, 11)]
        dag = build_dag(tasks)
        para = compute_max_parallelism(dag)

        assert para["layers"] == 1
        assert para["max_width"] == 10

    def test_single_path_min_parallelism(self):
        """唯一路径：最大并行度 = 1"""
        tasks = [_task("task-001")]
        for i in range(2, 6):
            tasks.append(_task(f"task-{i:03d}", deps=[f"task-{i-1:03d}"]))

        dag = build_dag(tasks)
        para = compute_max_parallelism(dag)

        assert para["max_width"] == 1
        assert para["layers"] == 5

    def test_parallelism_layer_details(self):
        """layer_details 包含每层正确任务"""
        tasks = [
            _task("task-001"),
            _task("task-002", deps=["task-001"]),
            _task("task-003", deps=["task-001"]),
            _task("task-004", deps=["task-002", "task-003"]),
        ]
        dag = build_dag(tasks)
        para = compute_max_parallelism(dag)

        assert len(para["layer_details"]) == 3
        assert para["layer_details"][0]["count"] == 1
        assert para["layer_details"][1]["count"] == 2
        assert para["layer_details"][2]["count"] == 1


# ── 循环依赖增强场景 ───────────────────────────────────────


class TestCycleAdvanced:
    """循环依赖的增强场景"""

    def test_cycle_with_extra_independent_task(self):
        """有环的图同时包含独立无环节点"""
        tasks = [
            _task("task-001", deps=["task-002"]),
            _task("task-002", deps=["task-001"]),
            _task("task-003"),  # 独立
        ]
        with pytest.raises(CyclicDependencyError):
            build_dag(tasks)

    def test_cycle_in_larger_graph(self):
        """大图中隐藏的小环"""
        tasks = [
            _task("task-001"),
            _task("task-002", deps=["task-001"]),
            _task("task-003", deps=["task-002"]),
            _task("task-004", deps=["task-003"]),
            # task-004 → task-002 形成环
            _task("task-005", deps=["task-004", "task-002"]),  # task-002 通过 task-004 间接环
        ]
        # 这个其实不是环，task-005 同时依赖 task-004 和 task-002 是合法的
        dag = build_dag(tasks)
        order = topological_sort(dag)
        assert len(order) == 5

    def test_detect_cycle_standalone_function(self):
        """detect_cycle 独立函数检测环"""
        tasks = [
            _task("task-001", deps=["task-003"]),
            _task("task-002", deps=["task-001"]),
            _task("task-003", deps=["task-002"]),
        ]
        cycle = detect_cycle(tasks)
        assert cycle is not None
        assert len(cycle) > 0

    def test_no_false_positive_cycle(self):
        """复杂图不应误报环"""
        tasks = [
            _task("task-001"),
            _task("task-002", deps=["task-001"]),
            _task("task-003", deps=["task-001"]),
            _task("task-004", deps=["task-002"]),
            _task("task-005", deps=["task-002", "task-003"]),
            _task("task-006", deps=["task-003"]),
            _task("task-007", deps=["task-004", "task-005", "task-006"]),
        ]
        dag = build_dag(tasks)  # 不应抛异常
        assert dag.task_count == 7


# ── 拓扑排序稳定性 ─────────────────────────────────────────


class TestTopologicalSortStability:
    """拓扑排序的确定性和稳定性"""

    def test_same_graph_same_result(self):
        """相同图两次排序结果一致"""
        tasks = [
            _task("task-001"),
            _task("task-002", deps=["task-001"]),
            _task("task-003", deps=["task-001"]),
            _task("task-004", deps=["task-002", "task-003"]),
        ]
        dag = build_dag(tasks)

        order1 = topological_sort(dag)
        order2 = topological_sort(dag)

        assert order1 == order2

    def test_sort_preserves_all_tasks(self):
        """排序结果包含所有任务"""
        tasks = [_task(f"task-{i:03d}") for i in range(1, 21)]
        dag = build_dag(tasks)
        order = topological_sort(dag)

        assert len(order) == 20
        assert set(order) == {f"task-{i:03d}" for i in range(1, 21)}

    def test_sort_no_duplicates(self):
        """排序结果无重复"""
        tasks = [
            _task("task-001"),
            _task("task-002", deps=["task-001"]),
            _task("task-003", deps=["task-001"]),
        ]
        dag = build_dag(tasks)
        order = topological_sort(dag)

        assert len(order) == len(set(order))


# ── TaskDAG 查询方法增强 ──────────────────────────────────


class TestTaskDAGQueries:
    """TaskDAG 查询方法的各种场景"""

    def test_get_dependencies_returns_copy(self):
        """get_dependencies 返回副本"""
        tasks = [
            _task("task-001"),
            _task("task-002", deps=["task-001"]),
        ]
        dag = build_dag(tasks)

        deps = dag.get_dependencies("task-002")
        deps.append("task-999")

        assert "task-999" not in dag.get_dependencies("task-002")

    def test_get_successors_returns_copy(self):
        """get_successors 返回副本"""
        tasks = [
            _task("task-001"),
            _task("task-002", deps=["task-001"]),
        ]
        dag = build_dag(tasks)

        succs = dag.get_successors("task-001")
        succs.append("task-999")

        assert "task-999" not in dag.get_successors("task-001")

    def test_get_task_nonexistent_returns_none(self):
        """查询不存在的任务返回 None"""
        tasks = [_task("task-001")]
        dag = build_dag(tasks)

        assert dag.get_task("task-999") is None

    def test_get_dependencies_nonexistent_returns_empty(self):
        """查询不存在任务的依赖返回空列表"""
        tasks = [_task("task-001")]
        dag = build_dag(tasks)

        assert dag.get_dependencies("task-999") == []

    def test_properties_return_copies(self):
        """tasks/edges/in_degree 属性返回副本"""
        tasks = [
            _task("task-001"),
            _task("task-002", deps=["task-001"]),
        ]
        dag = build_dag(tasks)

        dag.tasks["task-999"] = None  # type: ignore
        assert "task-999" not in dag.tasks

    def test_task_count_matches(self):
        """task_count 等于任务数"""
        tasks = [_task(f"task-{i:03d}") for i in range(1, 8)]
        dag = build_dag(tasks)

        assert dag.task_count == 7


# ── build_dag 错误场景增强 ─────────────────────────────────


class TestBuildDagErrors:
    """build_dag 错误处理增强场景"""

    def test_multiple_duplicate_ids(self):
        """多个重复 ID"""
        tasks = [
            _task("task-001"),
            _task("task-001"),
            _task("task-002"),
        ]
        with pytest.raises(ValueError, match="Duplicate task ID"):
            build_dag(tasks)

    def test_dependency_on_future_task_id(self):
        """依赖不存在的任务 ID"""
        tasks = [
            _task("task-001", deps=["task-999"]),
        ]
        with pytest.raises(ValueError, match="non-existent"):
            build_dag(tasks)

    def test_empty_list_returns_empty_dag(self):
        """空任务列表返回空 DAG"""
        dag = build_dag([])

        assert dag.task_count == 0
        assert dag.get_root_tasks() == []
        assert dag.get_leaf_tasks() == []

    def test_topological_sort_empty_dag(self):
        """空 DAG 的拓扑排序返回空列表"""
        dag = build_dag([])
        order = topological_sort(dag)

        assert order == []

    def test_compute_max_parallelism_empty_dag(self):
        """空 DAG 的并行度分析"""
        dag = build_dag([])
        para = compute_max_parallelism(dag)

        assert para["layers"] == 0
        assert para["max_width"] == 0
        assert para["layer_details"] == []

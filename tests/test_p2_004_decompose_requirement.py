"""
P2-004 测试：任务拆解 decompose_requirement

验证 ProductManagerAgent.decompose_requirement 的完整功能。
测试覆盖：
1. DecomposeResult 数据模型
2. decompose_requirement 核心流程
3. BDD 场景解析
4. 任务字典创建
5. 依赖推断
6. 角色建议
7. 复杂度估算
8. 拆解 prompt
9. 边界条件与异常处理
10. 生命周期集成
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from agent_automation_system.models.bdd import (
    BDDDraft,
    BDDScenario,
    DecomposeResult,
)
from agent_automation_system.models.task import TaskPriority
from agent_automation_system.sub_agent.pm_agent import ProductManagerAgent


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def pm_agent():
    """创建默认 ProductManagerAgent 实例"""
    return ProductManagerAgent()


@pytest.fixture
def structured_bdd_text():
    """创建结构化 BDD 文本（BDDDraft.to_text() 格式）"""
    return (
        "# 需求摘要: 用户管理系统\n"
        "\n"
        "## BDD 场景\n"
        "\n"
        "### 场景 1: 用户注册\n"
        "- Given: 用户未注册\n"
        "- When: 用户填写注册表单并提交\n"
        "- Then: 创建用户账号并返回成功\n"
        "- 优先级: high\n"
        "\n"
        "### 场景 2: 用户登录\n"
        "- Given: 用户已注册\n"
        "- When: 用户输入有效凭证并提交\n"
        "- Then: 用户成功登录并获取认证令牌\n"
        "- 优先级: high\n"
        "\n"
        "### 场景 3: 查询用户信息\n"
        "- Given: 用户已登录\n"
        "- When: 用户请求个人信息页面\n"
        "- Then: 展示用户详细信息\n"
        "- 优先级: medium\n"
    )


@pytest.fixture
def simple_bdd_text():
    """创建简单 BDD 文本（单场景）"""
    return (
        "### 场景 1: 登录功能\n"
        "- Given: 用户未登录\n"
        "- When: 用户输入邮箱和密码提交\n"
        "- Then: 登录成功跳转首页\n"
        "- 优先级: high\n"
    )


@pytest.fixture
def bdd_text_with_test_scenario():
    """创建包含测试场景的 BDD 文本"""
    return (
        "# 需求摘要: 登录与测试\n"
        "\n"
        "## BDD 场景\n"
        "\n"
        "### 场景 1: 登录功能实现\n"
        "- Given: 用户未登录\n"
        "- When: 用户提交登录表单\n"
        "- Then: 登录成功获取权限\n"
        "- 优先级: high\n"
        "\n"
        "### 场景 2: 登录功能测试\n"
        "- Given: 登录功能已实现\n"
        "- When: 执行登录测试用例\n"
        "- Then: 所有测试通过\n"
        "- 优先级: medium\n"
    )


@pytest.fixture
def bdd_text_with_crud():
    """创建包含 CRUD 操作的 BDD 文本（用于测试依赖推断）"""
    return (
        "# 需求摘要: 商品管理\n"
        "\n"
        "## BDD 场景\n"
        "\n"
        "### 场景 1: 创建商品\n"
        "- Given: 管理员已登录\n"
        "- When: 管理员填写商品信息并提交\n"
        "- Then: 商品创建成功并添加到商品列表\n"
        "- 优先级: high\n"
        "\n"
        "### 场景 2: 查询商品列表\n"
        "- Given: 商品已创建\n"
        "- When: 用户请求商品列表页面\n"
        "- Then: 展示所有商品信息\n"
        "- 优先级: medium\n"
        "\n"
        "### 场景 3: 商品功能测试\n"
        "- Given: 商品功能已实现\n"
        "- When: 执行商品相关测试\n"
        "- Then: 所有测试通过\n"
        "- 优先级: medium\n"
    )


# ══════════════════════════════════════════════════════════
# 1. DecomposeResult 数据模型
# ══════════════════════════════════════════════════════════


class TestDecomposeResultModel:
    """DecomposeResult 数据模型"""

    def test_create_minimal(self):
        """创建最小 DecomposeResult"""
        result = DecomposeResult(confirmed_bdd="BDD 描述")
        assert result.confirmed_bdd == "BDD 描述"
        assert result.tasks == []
        assert result.decomposition_notes == []
        assert result.total_tasks == 0

    def test_create_with_tasks(self):
        """创建包含任务的 DecomposeResult"""
        tasks = [
            {"id": "task-001", "title": "任务1", "priority": "high"},
            {"id": "task-002", "title": "任务2", "priority": "medium"},
        ]
        result = DecomposeResult(
            confirmed_bdd="BDD 描述",
            tasks=tasks,
            decomposition_notes=["说明1"],
        )
        assert result.total_tasks == 2
        assert result.has_tasks is True
        assert result.task_ids == ["task-001", "task-002"]

    def test_has_tasks_false_when_empty(self):
        """无任务时 has_tasks 为 False"""
        result = DecomposeResult(confirmed_bdd="BDD 描述")
        assert result.has_tasks is False

    def test_high_priority_tasks(self):
        """高优先级任务筛选"""
        tasks = [
            {"id": "task-001", "priority": "high"},
            {"id": "task-002", "priority": "medium"},
            {"id": "task-003", "priority": "high"},
        ]
        result = DecomposeResult(confirmed_bdd="BDD", tasks=tasks)
        assert len(result.high_priority_tasks) == 2

    def test_validate_notes_no_empty_strings(self):
        """说明列表过滤空字符串"""
        result = DecomposeResult(
            confirmed_bdd="BDD",
            decomposition_notes=["有效说明", "", "  ", "另一个说明"],
        )
        assert len(result.decomposition_notes) == 2

    def test_created_at(self):
        """创建时间属性"""
        now = datetime.now()
        result = DecomposeResult(
            confirmed_bdd="BDD",
            created_at=now,
        )
        assert result.created_at == now

    def test_confirmed_bdd_required(self):
        """confirmed_bdd 为必填字段"""
        with pytest.raises(Exception):
            DecomposeResult()  # type: ignore


# ══════════════════════════════════════════════════════════
# 2. decompose_requirement 核心流程
# ══════════════════════════════════════════════════════════


class TestDecomposeRequirementCore:
    """decompose_requirement 核心流程"""

    def test_returns_decompose_result(self, pm_agent, structured_bdd_text):
        """返回 DecomposeResult 实例"""
        result = pm_agent.decompose_requirement(structured_bdd_text)
        assert isinstance(result, DecomposeResult)

    def test_saves_confirmed_bdd(self, pm_agent, structured_bdd_text):
        """保存确认 BDD 到 _confirmed_bdd"""
        pm_agent.decompose_requirement(structured_bdd_text)
        assert pm_agent.confirmed_bdd == structured_bdd_text.strip()

    def test_result_contains_confirmed_bdd(self, pm_agent, simple_bdd_text):
        """结果包含原始确认 BDD"""
        result = pm_agent.decompose_requirement(simple_bdd_text)
        assert result.confirmed_bdd == simple_bdd_text.strip()

    def test_result_has_tasks(self, pm_agent, structured_bdd_text):
        """结果包含拆解出的任务"""
        result = pm_agent.decompose_requirement(structured_bdd_text)
        assert result.has_tasks is True
        assert result.total_tasks == 3

    def test_result_has_decomposition_notes(self, pm_agent, structured_bdd_text):
        """结果包含拆解说明"""
        result = pm_agent.decompose_requirement(structured_bdd_text)
        assert len(result.decomposition_notes) > 0

    def test_result_has_created_at(self, pm_agent, simple_bdd_text):
        """结果包含创建时间"""
        result = pm_agent.decompose_requirement(simple_bdd_text)
        assert result.created_at is not None
        assert isinstance(result.created_at, datetime)

    def test_empty_bdd_raises_error(self, pm_agent):
        """空 BDD 文本抛出 ValueError"""
        with pytest.raises(ValueError, match="confirmed_bdd cannot be empty"):
            pm_agent.decompose_requirement("")

    def test_whitespace_only_bdd_raises_error(self, pm_agent):
        """仅含空白字符的 BDD 抛出 ValueError"""
        with pytest.raises(ValueError, match="confirmed_bdd cannot be empty"):
            pm_agent.decompose_requirement("   \n  ")


# ══════════════════════════════════════════════════════════
# 3. BDD 场景解析
# ══════════════════════════════════════════════════════════


class TestBddScenarioParsing:
    """BDD 场景解析"""

    def test_parse_structured_format(self, pm_agent, structured_bdd_text):
        """解析 BDDDraft.to_text() 结构化格式"""
        scenarios = pm_agent._parse_bdd_scenarios(structured_bdd_text)
        assert len(scenarios) == 3
        assert scenarios[0]["title"] == "用户注册"
        assert scenarios[0]["given"] == "用户未注册"
        assert scenarios[0]["when"] == "用户填写注册表单并提交"
        assert scenarios[0]["then"] == "创建用户账号并返回成功"

    def test_parse_single_scenario(self, pm_agent, simple_bdd_text):
        """解析单场景 BDD 文本"""
        scenarios = pm_agent._parse_bdd_scenarios(simple_bdd_text)
        assert len(scenarios) == 1
        assert scenarios[0]["title"] == "登录功能"

    def test_parse_list_format(self, pm_agent):
        """解析 "- Given: / When: / Then:" 列表格式"""
        bdd_text = (
            "- Given: 用户未登录\n"
            "- When: 提交登录表单\n"
            "- Then: 登录成功\n"
        )
        scenarios = pm_agent._parse_bdd_scenarios(bdd_text)
        assert len(scenarios) == 1
        assert scenarios[0]["given"] == "用户未登录"

    def test_parse_bare_format(self, pm_agent):
        """解析裸格式（Given ... When ... Then ...）"""
        bdd_text = "Given 用户未登录 When 提交登录表单 Then 登录成功"
        scenarios = pm_agent._parse_bdd_scenarios(bdd_text)
        assert len(scenarios) >= 1

    def test_parse_multiple_list_format(self, pm_agent):
        """解析多场景列表格式"""
        bdd_text = (
            "- Given: 未注册\n- When: 注册\n- Then: 注册成功\n"
            "- Given: 已注册\n- When: 登录\n- Then: 登录成功\n"
        )
        scenarios = pm_agent._parse_bdd_scenarios(bdd_text)
        assert len(scenarios) == 2

    def test_parse_empty_text(self, pm_agent):
        """空文本返回空列表"""
        scenarios = pm_agent._parse_bdd_scenarios("")
        assert scenarios == []

    def test_parse_no_bdd_markers(self, pm_agent):
        """无 BDD 标记的文本返回空列表"""
        scenarios = pm_agent._parse_bdd_scenarios("这是一段普通文本，没有BDD标记")
        assert scenarios == []

    def test_parse_priority(self, pm_agent, structured_bdd_text):
        """解析场景优先级"""
        scenarios = pm_agent._parse_bdd_scenarios(structured_bdd_text)
        assert scenarios[0]["priority"] == "high"
        assert scenarios[1]["priority"] == "high"
        assert scenarios[2]["priority"] == "medium"

    def test_parse_scenario_block(self, pm_agent):
        """解析单个场景块"""
        block = " 用户登录\n- Given: 未登录\n- When: 提交表单\n- Then: 成功"
        scenario = pm_agent._parse_scenario_block(block)
        assert scenario is not None
        assert scenario["title"] == "用户登录"
        assert scenario["given"] == "未登录"

    def test_parse_incomplete_scenario_returns_none(self, pm_agent):
        """不完整的场景块返回 None"""
        block = " 标题\n- Given: 前提\n- When: 动作\n"
        scenario = pm_agent._parse_scenario_block(block)
        assert scenario is None  # 缺少 Then


# ══════════════════════════════════════════════════════════
# 4. 任务字典创建
# ══════════════════════════════════════════════════════════


class TestTaskDictCreation:
    """任务字典创建"""

    def test_create_task_dict_structure(self, pm_agent):
        """任务字典包含必要字段"""
        scenario = {
            "title": "登录",
            "given": "未登录",
            "when": "提交表单",
            "then": "成功",
            "priority": "high",
        }
        task = pm_agent._create_task_dict(scenario, 1)
        assert "id" in task
        assert "title" in task
        assert "description" in task
        assert "bdd" in task
        assert "dependencies" in task
        assert "suggested_role" in task
        assert "priority" in task
        assert "estimated_complexity" in task
        assert "status" in task

    def test_task_id_format(self, pm_agent):
        """任务 ID 格式为 task-XXX"""
        scenario = {
            "title": "测试",
            "given": "前提",
            "when": "动作",
            "then": "结果",
            "priority": "medium",
        }
        task = pm_agent._create_task_dict(scenario, 1)
        assert task["id"] == "task-001"
        task2 = pm_agent._create_task_dict(scenario, 10)
        assert task2["id"] == "task-010"

    def test_task_bdd_structure(self, pm_agent):
        """任务 BDD 结构包含 given/when/then"""
        scenario = {
            "title": "注册",
            "given": "未注册",
            "when": "提交注册",
            "then": "注册成功",
            "priority": "high",
        }
        task = pm_agent._create_task_dict(scenario, 1)
        assert task["bdd"]["given"] == "未注册"
        assert task["bdd"]["when"] == "提交注册"
        assert task["bdd"]["then"] == "注册成功"

    def test_task_description_includes_given(self, pm_agent):
        """任务描述包含 Given 信息"""
        scenario = {
            "title": "登录",
            "given": "用户未登录",
            "when": "提交表单",
            "then": "成功",
            "priority": "high",
        }
        task = pm_agent._create_task_dict(scenario, 1)
        assert "用户未登录" in task["description"]

    def test_task_status_pending(self, pm_agent):
        """任务初始状态为 pending"""
        scenario = {
            "title": "测试",
            "given": "前提",
            "when": "动作",
            "then": "结果",
            "priority": "medium",
        }
        task = pm_agent._create_task_dict(scenario, 1)
        assert task["status"] == "pending"

    def test_create_default_task(self, pm_agent):
        """创建默认任务（无场景可解析时）"""
        task = pm_agent._create_default_task("需要实现一个功能")
        assert task["id"] == "task-001"
        assert task["priority"] == "high"
        assert task["status"] == "pending"
        assert "bdd" in task

    def test_create_default_task_extracts_title(self, pm_agent):
        """默认任务从文本提取标题"""
        bdd_text = "# 需求摘要: 登录系统\n其他内容"
        task = pm_agent._create_default_task(bdd_text)
        assert "登录系统" in task["title"]


# ══════════════════════════════════════════════════════════
# 5. 依赖推断
# ══════════════════════════════════════════════════════════


class TestDependencyInference:
    """依赖推断"""

    def test_single_task_no_deps(self, pm_agent):
        """单任务无依赖"""
        tasks = [
            {"id": "task-001", "title": "任务1", "bdd": {"when": "做A", "then": "完成A"}, "dependencies": []},
        ]
        result = pm_agent._infer_dependencies(tasks)
        assert result[0]["dependencies"] == []

    def test_first_task_no_deps(self, pm_agent, structured_bdd_text):
        """第一个任务无依赖"""
        result = pm_agent.decompose_requirement(structured_bdd_text)
        first_task = result.tasks[0]
        assert first_task["dependencies"] == []

    def test_test_task_depends_on_impl(self, pm_agent, bdd_text_with_test_scenario):
        """测试任务依赖实现任务"""
        result = pm_agent.decompose_requirement(bdd_text_with_test_scenario)
        test_task = result.tasks[1]
        assert "测试" in test_task["title"]
        # 测试任务应有依赖
        assert len(test_task["dependencies"]) > 0

    def test_query_depends_on_create(self, pm_agent, bdd_text_with_crud):
        """查询任务依赖创建任务"""
        result = pm_agent.decompose_requirement(bdd_text_with_crud)
        # 查询商品列表应该依赖创建商品
        query_task = result.tasks[1]
        assert "查询" in query_task["title"]
        # 依赖中应包含创建任务
        assert len(query_task["dependencies"]) > 0

    def test_given_keywords_match_then(self, pm_agent):
        """Given 关键词匹配 Then 产出时产生依赖"""
        tasks = [
            {
                "id": "task-001",
                "title": "创建用户",
                "bdd": {"when": "创建用户", "then": "用户创建成功，获得认证权限"},
                "dependencies": [],
            },
            {
                "id": "task-002",
                "title": "登录",
                "bdd": {"given": "用户已注册，已有认证权限", "when": "登录", "then": "成功"},
                "dependencies": [],
            },
        ]
        result = pm_agent._infer_dependencies(tasks)
        # task-002 的 Given 提到"认证权限"，task-001 的 Then 包含"认证权限"
        assert "task-001" in result[1]["dependencies"]

    def test_no_self_dependency(self, pm_agent):
        """任务不能依赖自身"""
        tasks = [
            {
                "id": "task-001",
                "title": "任务1",
                "bdd": {"when": "做A", "then": "完成A", "given": ""},
                "dependencies": [],
            },
            {
                "id": "task-002",
                "title": "任务2",
                "bdd": {"when": "做B", "then": "完成B", "given": ""},
                "dependencies": [],
            },
        ]
        result = pm_agent._infer_dependencies(tasks)
        for task in result:
            assert task["id"] not in task["dependencies"]

    def test_dependency_ids_are_valid(self, pm_agent, bdd_text_with_crud):
        """依赖 ID 都是有效的任务 ID"""
        result = pm_agent.decompose_requirement(bdd_text_with_crud)
        all_ids = set(result.task_ids)
        for task in result.tasks:
            for dep_id in task["dependencies"]:
                assert dep_id in all_ids

    def test_multiple_dependencies(self, pm_agent):
        """一个任务可以有多个依赖"""
        tasks = [
            {
                "id": "task-001",
                "title": "创建商品",
                "bdd": {"when": "创建商品", "then": "商品创建成功", "given": ""},
                "dependencies": [],
            },
            {
                "id": "task-002",
                "title": "创建订单",
                "bdd": {"when": "创建订单", "then": "订单创建成功", "given": "商品"},
                "dependencies": [],
            },
            {
                "id": "task-003",
                "title": "查询订单列表",
                "bdd": {"given": "订单已创建", "when": "查询订单列表", "then": "展示订单", "given_ori": "订单"},
                "dependencies": [],
            },
        ]
        result = pm_agent._infer_dependencies(tasks)
        # 查询订单至少依赖创建订单
        assert len(result[2]["dependencies"]) > 0


# ══════════════════════════════════════════════════════════
# 6. 角色建议
# ══════════════════════════════════════════════════════════


class TestRoleSuggestion:
    """角色建议"""

    def test_test_task_gets_qa(self, pm_agent):
        """测试任务建议 qa 角色"""
        task = {"title": "登录功能测试", "description": "测试登录"}
        assert pm_agent._suggest_role(task) == "qa"

    def test_ui_task_gets_senior_developer(self, pm_agent):
        """UI 任务建议 senior-developer 角色"""
        task = {"title": "登录页面实现", "description": "实现登录页面UI"}
        assert pm_agent._suggest_role(task) == "senior-developer"

    def test_api_task_gets_dev(self, pm_agent):
        """API 任务建议 dev 角色"""
        task = {"title": "登录接口实现", "description": "实现登录API接口"}
        assert pm_agent._suggest_role(task) == "dev"

    def test_validate_task_gets_validate(self, pm_agent):
        """验收任务建议 validate 角色"""
        task = {"title": "功能验收", "description": "对功能进行验收确认"}
        assert pm_agent._suggest_role(task) == "validate"

    def test_default_role_is_dev(self, pm_agent):
        """默认角色为 dev"""
        task = {"title": "通用任务", "description": "完成某个功能"}
        assert pm_agent._suggest_role(task) == "dev"

    def test_role_from_decompose_result(self, pm_agent, bdd_text_with_test_scenario):
        """拆解结果中角色正确分配"""
        result = pm_agent.decompose_requirement(bdd_text_with_test_scenario)
        # 测试任务应为 qa 角色
        test_tasks = [t for t in result.tasks if "测试" in t["title"]]
        if test_tasks:
            assert test_tasks[0]["suggested_role"] == "qa"


# ══════════════════════════════════════════════════════════
# 7. 复杂度估算
# ══════════════════════════════════════════════════════════


class TestComplexityEstimation:
    """复杂度估算"""

    def test_high_complexity_for_integration(self, pm_agent):
        """集成/第三方相关为高复杂度"""
        task = {
            "description": "对接第三方支付接口",
            "bdd": {"when": "集成支付", "then": "支付成功"},
        }
        assert pm_agent._estimate_complexity(task) == "high"

    def test_high_complexity_for_security(self, pm_agent):
        """安全/加密相关为高复杂度"""
        task = {
            "description": "实现数据加密存储",
            "bdd": {"when": "加密", "then": "安全存储"},
        }
        assert pm_agent._estimate_complexity(task) == "high"

    def test_low_complexity_for_simple_ops(self, pm_agent):
        """简单操作为低复杂度"""
        task = {
            "description": "配置系统参数",
            "bdd": {"when": "修改配置", "then": "配置更新"},
        }
        assert pm_agent._estimate_complexity(task) == "low"

    def test_medium_complexity_default(self, pm_agent):
        """默认为中等复杂度"""
        task = {
            "description": "实现用户登录功能",
            "bdd": {"when": "登录", "then": "登录成功"},
        }
        assert pm_agent._estimate_complexity(task) == "medium"

    def test_complexity_in_decompose_result(self, pm_agent, structured_bdd_text):
        """拆解结果中包含复杂度评估"""
        result = pm_agent.decompose_requirement(structured_bdd_text)
        for task in result.tasks:
            assert task["estimated_complexity"] in ("low", "medium", "high")

    def test_concurrent_high_complexity(self, pm_agent):
        """并发相关为高复杂度"""
        task = {
            "description": "实现并发处理逻辑",
            "bdd": {"when": "并发处理", "then": "处理完成"},
        }
        assert pm_agent._estimate_complexity(task) == "high"


# ══════════════════════════════════════════════════════════
# 8. 拆解 Prompt
# ══════════════════════════════════════════════════════════


class TestDecomposePrompt:
    """拆解 Prompt 构建"""

    def test_prompt_contains_confirmed_bdd(self, pm_agent):
        """prompt 包含确认 BDD 文本"""
        prompt = pm_agent.get_decompose_prompt("用户登录 BDD 描述")
        assert "用户登录 BDD 描述" in prompt

    def test_prompt_contains_decompose_instruction(self, pm_agent):
        """prompt 包含拆解指令"""
        prompt = pm_agent.get_decompose_prompt("BDD 描述")
        assert "拆解任务" in prompt
        assert "原子" in prompt

    def test_prompt_contains_role_identity(self, pm_agent):
        """prompt 包含角色身份"""
        prompt = pm_agent.get_decompose_prompt("BDD 描述")
        assert "角色身份" in prompt

    def test_prompt_mentions_task_format(self, pm_agent):
        """prompt 包含任务编号格式要求"""
        prompt = pm_agent.get_decompose_prompt("BDD 描述")
        assert "task-001" in prompt


# ══════════════════════════════════════════════════════════
# 9. 边界条件与异常处理
# ══════════════════════════════════════════════════════════


class TestEdgeCasesAndErrors:
    """边界条件与异常处理"""

    def test_non_bdd_text_creates_default_task(self, pm_agent):
        """非 BDD 格式文本创建默认任务"""
        result = pm_agent.decompose_requirement("这是一段普通的需求描述，没有任何BDD标记")
        assert result.total_tasks == 1
        assert result.tasks[0]["id"] == "task-001"

    def test_very_short_bdd(self, pm_agent):
        """非常短的 BDD 文本"""
        result = pm_agent.decompose_requirement("### 场景 1: 登录\n- Given: 未登录\n- When: 登录\n- Then: 成功")
        assert result.total_tasks >= 1

    def test_bdd_with_user_feedback_section(self, pm_agent):
        """包含用户反馈段的 BDD 文本"""
        bdd_text = (
            "### 场景 1: 登录\n"
            "- Given: 未登录\n"
            "- When: 提交表单\n"
            "- Then: 成功\n"
            "\n"
            "## 用户反馈（已纳入）\n"
            "\n"
            "需要支持微信登录\n"
        )
        result = pm_agent.decompose_requirement(bdd_text)
        assert result.total_tasks >= 1

    def test_bdd_with_questions_section(self, pm_agent):
        """包含待澄清问题段的 BDD 文本"""
        bdd_text = (
            "### 场景 1: 登录\n"
            "- Given: 未登录\n"
            "- When: 提交表单\n"
            "- Then: 成功\n"
            "\n"
            "## 待澄清问题\n"
            "\n"
            "1. 是否需要第三方登录？\n"
        )
        result = pm_agent.decompose_requirement(bdd_text)
        assert result.total_tasks >= 1

    def test_multiple_decomposes_overwrite(self, pm_agent):
        """多次调用 decompose 覆盖之前的结果"""
        pm_agent.decompose_requirement(
            "### 场景 1: A\n- Given: x\n- When: y\n- Then: z\n"
        )
        assert pm_agent.confirmed_bdd is not None
        pm_agent.decompose_requirement(
            "### 场景 1: B\n- Given: a\n- When: b\n- Then: c\n"
        )
        assert "场景 1: B" in pm_agent.confirmed_bdd

    def test_extract_action_keywords(self, pm_agent):
        """提取动作关键词"""
        keywords = pm_agent._extract_action_keywords("创建用户并获取认证权限")
        assert "用户" in keywords
        assert "认证" in keywords
        assert "权限" in keywords

    def test_extract_action_keywords_empty(self, pm_agent):
        """无匹配关键词返回空集合"""
        keywords = pm_agent._extract_action_keywords("这是一段没有关键词的文字")
        assert len(keywords) == 0

    def test_decomposition_notes_content(self, pm_agent, structured_bdd_text):
        """拆解说明包含关键信息"""
        result = pm_agent.decompose_requirement(structured_bdd_text)
        notes_text = " ".join(result.decomposition_notes)
        assert "场景" in notes_text or "原子任务" in notes_text


# ══════════════════════════════════════════════════════════
# 10. 生命周期集成
# ══════════════════════════════════════════════════════════


class TestLifecycleIntegration:
    """生命周期集成（refine → communicate → decompose）"""

    def test_refine_communicate_decompose_flow(self, pm_agent):
        """完整流程：精炼 → 沟通 → 拆解"""
        # 1. 精炼需求
        draft = pm_agent.refine_requirement("用户需要一个登录功能，支持邮箱登录")
        assert isinstance(draft, BDDDraft)

        # 2. 沟通确认（自动确认，因为有问题时会回调为空）
        comm_result = pm_agent.communicate_with_user(draft)
        assert comm_result.is_confirmed or comm_result.needs_escalation

        # 3. 拆解任务
        if comm_result.confirmed_bdd:
            decompose_result = pm_agent.decompose_requirement(
                comm_result.confirmed_bdd
            )
            assert isinstance(decompose_result, DecomposeResult)
            assert decompose_result.has_tasks

    def test_decompose_after_refine(self, pm_agent):
        """精炼后直接拆解（跳过沟通）"""
        draft = pm_agent.refine_requirement("实现商品管理功能")
        bdd_text = draft.to_text()
        result = pm_agent.decompose_requirement(bdd_text)
        assert result.has_tasks
        assert result.confirmed_bdd == bdd_text.strip()

    def test_decompose_preserves_bdd(self, pm_agent):
        """拆解结果中每个任务保留 BDD 规格"""
        draft = pm_agent.refine_requirement("实现用户注册和登录功能")
        bdd_text = draft.to_text()
        result = pm_agent.decompose_requirement(bdd_text)
        for task in result.tasks:
            assert "bdd" in task
            bdd = task["bdd"]
            assert "given" in bdd
            assert "when" in bdd
            assert "then" in bdd

    def test_decompose_task_ids_sequential(self, pm_agent, structured_bdd_text):
        """任务 ID 按序排列"""
        result = pm_agent.decompose_requirement(structured_bdd_text)
        for i, task in enumerate(result.tasks, 1):
            assert task["id"] == f"task-{i:03d}"

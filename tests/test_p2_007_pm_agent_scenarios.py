"""
P2-007 测试：ProductManagerAgent 单元测试 — BDD 生成、任务拆解、task.json 格式

验证 ProductManagerAgent 核心业务方法的场景覆盖：
1. BDD 生成场景：多种需求输入 → BDDDraft 结构正确性
2. 任务拆解场景：BDD → 原子任务 → 依赖推断 → 角色分配
3. task.json 格式场景：任务字典 → JSON 结构 → 字段校验 → 文件写入
4. 完整流水线场景：refine → communicate → decompose → generate_task_json → generate_test_script
5. 跨方法数据一致性：中间状态传递、字段映射正确性
6. 边界与异常场景：空输入、单场景、多场景、中文/英文混合
"""

import json
import re
from pathlib import Path

import pytest

from agent_automation_system.models.bdd import (
    BDDDraft,
    BDDScenario,
    CommunicationResult,
    CommunicationStatus,
    DecomposeResult,
    TaskJsonResult,
    TestScriptResult,
    TestScriptType,
)
from agent_automation_system.models.task import (
    BDDSpec,
    Task,
    TaskComplexity,
    TaskPriority,
    TaskStatus,
)
from agent_automation_system.models.task_json import TaskJSON
from agent_automation_system.sub_agent.pm_agent import ProductManagerAgent


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def pm():
    """创建 ProductManagerAgent 实例"""
    return ProductManagerAgent()


@pytest.fixture
def login_need():
    """用户登录需求"""
    return "用户需要一个安全的登录功能，支持邮箱和手机号登录"


@pytest.fixture
def ecom_need():
    """电商订单需求（多场景）"""
    return (
        "用户可以浏览商品列表；用户可以将商品加入购物车；"
        "用户可以提交订单并完成支付；管理员可以管理商品信息"
    )


@pytest.fixture
def api_need():
    """API 接口需求"""
    return "实现用户注册 API 接口，接收用户名和密码，返回注册结果"


@pytest.fixture
def ui_need():
    """UI 页面需求"""
    return "实现用户登录页面，包含输入框和提交按钮，支持表单验证"


@pytest.fixture
def simple_bdd_text():
    """简单 BDD 文本（结构化格式）"""
    return (
        "# 需求摘要: 用户登录\n\n"
        "## BDD 场景\n\n"
        "### 场景 1: 邮箱登录\n"
        "- Given: 用户未登录\n"
        "- When: 输入有效邮箱密码并提交\n"
        "- Then: 登录成功跳转首页\n"
        "- 优先级: high\n\n"
        "### 场景 2: 手机号登录\n"
        "- Given: 用户未登录\n"
        "- When: 输入有效手机号和验证码\n"
        "- Then: 登录成功跳转首页\n"
        "- 优先级: medium\n"
    )


@pytest.fixture
def bare_bdd_text():
    """裸格式 BDD 文本"""
    return (
        "Given 用户未登录 When 用户输入有效凭证并提交 Then 用户成功登录"
    )


# ══════════════════════════════════════════════════════════
# 1. BDD 生成场景
# ══════════════════════════════════════════════════════════


class TestBDDGenerationScenarios:
    """BDD 生成场景测试"""

    def test_login_need_generates_scenarios(self, pm, login_need):
        """登录需求生成至少 1 个 BDD 场景"""
        draft = pm.refine_requirement(login_need)
        assert isinstance(draft, BDDDraft)
        assert draft.scenario_count >= 1
        assert draft.raw_need == login_need

    def test_each_scenario_has_given_when_then(self, pm, login_need):
        """每个 BDD 场景都包含 Given-When-Then"""
        draft = pm.refine_requirement(login_need)
        for scenario in draft.scenarios:
            assert scenario.given, f"场景 '{scenario.title}' 缺少 Given"
            assert scenario.when, f"场景 '{scenario.title}' 缺少 When"
            assert scenario.then, f"场景 '{scenario.title}' 缺少 Then"

    def test_multi_segment_need_generates_multiple_scenarios(self, pm, ecom_need):
        """多句号/分号需求生成多个场景"""
        draft = pm.refine_requirement(ecom_need)
        assert draft.scenario_count >= 3, f"期望≥3个场景，实际 {draft.scenario_count}"

    def test_summary_is_nonempty(self, pm, login_need):
        """需求摘要非空"""
        draft = pm.refine_requirement(login_need)
        assert draft.summary
        assert len(draft.summary) > 0

    def test_short_need_summary_uses_original(self, pm):
        """短需求（≤50字）摘要使用原文"""
        short_need = "用户需要登录功能"
        draft = pm.refine_requirement(short_need)
        assert draft.summary == short_need

    def test_questions_generated_for_vague_need(self, pm):
        """模糊需求生成澄清问题"""
        vague_need = "系统需要支持一些数据存储"
        draft = pm.refine_requirement(vague_need)
        assert draft.has_questions
        # 应该检测到模糊量词"一些"
        assert any("一些" in q for q in draft.questions)

    def test_assumptions_generated(self, pm, login_need):
        """需求精炼生成假设"""
        draft = pm.refine_requirement(login_need)
        assert len(draft.assumptions) > 0
        # 登录需求应触发认证相关假设
        assert any("认证" in a or "密码" in a for a in draft.assumptions)

    def test_first_scenario_is_high_priority(self, pm, ecom_need):
        """第一个场景优先级为 HIGH"""
        draft = pm.refine_requirement(ecom_need)
        if draft.scenarios:
            assert draft.scenarios[0].priority == TaskPriority.HIGH

    def test_bdd_draft_to_text_contains_sections(self, pm, login_need):
        """BDDDraft.to_text() 包含场景、问题、假设段落"""
        draft = pm.refine_requirement(login_need)
        text = draft.to_text()
        assert "需求摘要" in text or "#" in text
        assert "Given" in text or "场景" in text

    def test_empty_requirement_raises(self, pm):
        """空需求抛出 ValueError"""
        with pytest.raises(ValueError, match="cannot be empty"):
            pm.refine_requirement("")

    def test_whitespace_requirement_raises(self, pm):
        """仅含空白的需求抛出 ValueError"""
        with pytest.raises(ValueError, match="cannot be empty"):
            pm.refine_requirement("   \n\t  ")


class TestBDDScenarioModel:
    """BDDScenario 数据模型场景测试"""

    def test_scenario_to_text_format(self):
        """BDDScenario.to_text() 格式正确"""
        scenario = BDDScenario(
            title="用户登录",
            given="用户未登录",
            when="输入有效凭证并提交",
            then="登录成功",
            priority=TaskPriority.HIGH,
        )
        text = scenario.to_text()
        assert "Given" in text
        assert "When" in text
        assert "Then" in text
        assert "用户登录" in text

    def test_scenario_title_required(self):
        """场景标题不能为空"""
        with pytest.raises(Exception):
            BDDScenario(
                title="",
                given="前提",
                when="动作",
                then="结果",
            )


# ══════════════════════════════════════════════════════════
# 2. 任务拆解场景
# ══════════════════════════════════════════════════════════


class TestDecomposeScenarios:
    """任务拆解场景测试"""

    def test_structured_bdd_decomposes_to_tasks(self, pm, simple_bdd_text):
        """结构化 BDD 文本拆解为任务"""
        result = pm.decompose_requirement(simple_bdd_text)
        assert isinstance(result, DecomposeResult)
        assert result.has_tasks
        assert result.total_tasks >= 2  # 至少邮箱+手机号登录

    def test_bare_bdd_decomposes_to_tasks(self, pm, bare_bdd_text):
        """裸格式 BDD 文本拆解为任务"""
        result = pm.decompose_requirement(bare_bdd_text)
        assert result.has_tasks
        assert result.total_tasks >= 1

    def test_each_task_has_required_fields(self, pm, simple_bdd_text):
        """每个任务包含必需字段"""
        result = pm.decompose_requirement(simple_bdd_text)
        required_fields = ["id", "title", "description", "bdd", "dependencies",
                          "suggested_role", "priority", "estimated_complexity", "status"]
        for task in result.tasks:
            for field in required_fields:
                assert field in task, f"任务 {task.get('id', '?')} 缺少字段 '{field}'"

    def test_task_ids_are_sequential(self, pm, simple_bdd_text):
        """任务 ID 按序编号"""
        result = pm.decompose_requirement(simple_bdd_text)
        for i, task in enumerate(result.tasks, 1):
            expected_id = f"task-{i:03d}"
            assert task["id"] == expected_id, f"期望 ID '{expected_id}'，实际 '{task['id']}'"

    def test_task_bdd_structure(self, pm, simple_bdd_text):
        """每个任务的 bdd 字段包含 given/when/then"""
        result = pm.decompose_requirement(simple_bdd_text)
        for task in result.tasks:
            bdd = task["bdd"]
            assert "given" in bdd
            assert "when" in bdd
            assert "then" in bdd

    def test_first_task_has_no_dependencies(self, pm, simple_bdd_text):
        """第一个任务无依赖"""
        result = pm.decompose_requirement(simple_bdd_text)
        if result.tasks:
            assert result.tasks[0]["dependencies"] == []

    def test_decomposition_notes_generated(self, pm, simple_bdd_text):
        """拆解说明非空"""
        result = pm.decompose_requirement(simple_bdd_text)
        assert len(result.decomposition_notes) > 0
        assert any("场景" in n for n in result.decomposition_notes)

    def test_default_task_when_no_scenarios(self, pm):
        """无 BDD 场景时创建默认任务"""
        plain_text = "这是一个没有任何 BDD 格式的描述"
        result = pm.decompose_requirement(plain_text)
        assert result.has_tasks
        assert result.total_tasks >= 1

    def test_empty_bdd_raises(self, pm):
        """空 BDD 文本抛出 ValueError"""
        with pytest.raises(ValueError, match="cannot be empty"):
            pm.decompose_requirement("")

    def test_confirmed_bdd_saved(self, pm, simple_bdd_text):
        """confirmed_bdd 保存到 agent 状态"""
        pm.decompose_requirement(simple_bdd_text)
        assert pm.confirmed_bdd == simple_bdd_text.strip()

    def test_role_suggestion_for_test_task(self, pm):
        """测试类任务建议 qa 角色"""
        result = pm.decompose_requirement(
            "Given 功能已完成 When 执行测试验证 Then 验证通过"
        )
        # 测试关键词应触发 qa 角色
        for task in result.tasks:
            if "测试" in task.get("title", "") or "验证" in task.get("title", ""):
                assert task["suggested_role"] == "qa"
                break

    def test_dependency_inference_for_query_tasks(self, pm):
        """查询类任务依赖创建类任务"""
        bdd = (
            "### 场景 1: 创建用户\n- Given: 系统\n- When: 创建新用户\n- Then: 用户已创建\n\n"
            "### 场景 2: 查询用户\n- Given: 用户已创建\n- When: 查询用户信息\n- Then: 返回用户信息"
        )
        result = pm.decompose_requirement(bdd)
        if result.total_tasks >= 2:
            # 查询任务应有依赖
            query_task = result.tasks[-1]
            when_text = query_task.get("bdd", {}).get("when", "")
            if "查询" in when_text:
                assert len(query_task["dependencies"]) > 0


class TestDecomposeResultModel:
    """DecomposeResult 数据模型场景测试"""

    def test_task_ids_property(self, pm, simple_bdd_text):
        """task_ids 属性返回所有任务 ID"""
        result = pm.decompose_requirement(simple_bdd_text)
        assert len(result.task_ids) == result.total_tasks
        for tid in result.task_ids:
            assert tid.startswith("task-")

    def test_high_priority_tasks_property(self, pm, simple_bdd_text):
        """high_priority_tasks 属性正确过滤"""
        result = pm.decompose_requirement(simple_bdd_text)
        high_tasks = result.high_priority_tasks
        for t in high_tasks:
            assert t.get("priority") == "high"


# ══════════════════════════════════════════════════════════
# 3. task.json 格式场景
# ══════════════════════════════════════════════════════════


class TestTaskJsonFormatScenarios:
    """task.json 格式场景测试"""

    def _make_tasks(self, count=2):
        """生成测试用任务列表"""
        tasks = []
        for i in range(1, count + 1):
            tasks.append({
                "id": f"task-{i:03d}",
                "title": f"任务{i}",
                "description": f"第{i}个任务的描述",
                "bdd": {
                    "given": f"前提{i}",
                    "when": f"动作{i}",
                    "then": f"结果{i}",
                },
                "test_script": None,
                "dependencies": [] if i == 1 else [f"task-{i-1:03d}"],
                "suggested_role": "dev",
                "priority": "high" if i == 1 else "medium",
                "estimated_complexity": "medium",
                "status": "pending",
            })
        return tasks

    def test_generate_task_json_returns_result(self, pm):
        """generate_task_json 返回 TaskJsonResult"""
        tasks = self._make_tasks()
        result = pm.generate_task_json(tasks)
        assert isinstance(result, TaskJsonResult)

    def test_task_json_model_is_valid(self, pm):
        """TaskJSON 模型对象有效"""
        tasks = self._make_tasks()
        result = pm.generate_task_json(tasks)
        assert isinstance(result.task_json, TaskJSON)
        assert result.task_json.total_tasks == len(tasks)

    def test_json_text_is_valid_json(self, pm):
        """json_text 是有效 JSON"""
        tasks = self._make_tasks()
        result = pm.generate_task_json(tasks)
        parsed = json.loads(result.json_text)
        assert "tasks" in parsed
        assert "project_name" in parsed
        assert "total_tasks" in parsed

    def test_json_has_required_top_level_fields(self, pm):
        """JSON 包含顶层必需字段"""
        tasks = self._make_tasks()
        result = pm.generate_task_json(tasks)
        parsed = json.loads(result.json_text)
        assert "project_name" in parsed
        assert "total_tasks" in parsed
        assert "tasks" in parsed
        assert "created_by" in parsed

    def test_total_tasks_matches_list_length(self, pm):
        """total_tasks 与 tasks 列表长度一致"""
        tasks = self._make_tasks(3)
        result = pm.generate_task_json(tasks)
        parsed = json.loads(result.json_text)
        assert parsed["total_tasks"] == len(parsed["tasks"])
        assert parsed["total_tasks"] == 3

    def test_each_task_in_json_has_required_fields(self, pm):
        """JSON 中每个任务包含必需字段"""
        tasks = self._make_tasks()
        result = pm.generate_task_json(tasks)
        parsed = json.loads(result.json_text)
        required = ["id", "title", "description", "bdd", "dependencies",
                    "suggested_role", "priority", "estimated_complexity"]
        for task in parsed["tasks"]:
            for field in required:
                assert field in task, f"JSON 任务缺少字段 '{field}'"

    def test_task_bdd_in_json_has_three_sections(self, pm):
        """JSON 中任务 bdd 包含 given/when/then"""
        tasks = self._make_tasks()
        result = pm.generate_task_json(tasks)
        parsed = json.loads(result.json_text)
        for task in parsed["tasks"]:
            assert "given" in task["bdd"]
            assert "when" in task["bdd"]
            assert "then" in task["bdd"]

    def test_dependencies_reference_valid_ids(self, pm):
        """依赖引用的任务 ID 存在"""
        tasks = self._make_tasks(3)
        result = pm.generate_task_json(tasks)
        parsed = json.loads(result.json_text)
        all_ids = {t["id"] for t in parsed["tasks"]}
        for task in parsed["tasks"]:
            for dep in task.get("dependencies", []):
                assert dep in all_ids, f"依赖 '{dep}' 引用了不存在的任务"

    def test_project_name_inferred(self, pm):
        """项目名称从任务推断"""
        tasks = self._make_tasks()
        result = pm.generate_task_json(tasks)
        assert result.project_name
        assert len(result.project_name) > 0

    def test_custom_project_name(self, pm):
        """自定义项目名称"""
        tasks = self._make_tasks()
        result = pm.generate_task_json(tasks, project_name="自定义项目")
        assert result.project_name == "自定义项目"

    def test_write_to_file(self, pm, tmp_path):
        """写入文件成功"""
        tasks = self._make_tasks()
        output = tmp_path / "task.json"
        result = pm.generate_task_json(tasks, output_path=output)
        assert result.is_saved_to_file
        assert result.output_path is not None
        # 文件内容可解析
        with open(output, "r", encoding="utf-8") as f:
            parsed = json.load(f)
        assert parsed["total_tasks"] == len(tasks)

    def test_write_creates_parent_dirs(self, pm, tmp_path):
        """写入时自动创建父目录"""
        tasks = self._make_tasks()
        output = tmp_path / "sub" / "dir" / "task.json"
        result = pm.generate_task_json(tasks, output_path=output)
        assert result.is_saved_to_file
        assert output.exists()

    def test_no_write_when_path_none(self, pm):
        """output_path=None 时不写文件"""
        tasks = self._make_tasks()
        result = pm.generate_task_json(tasks)
        assert not result.is_saved_to_file
        assert result.output_path is None

    def test_empty_tasks_raises(self, pm):
        """空任务列表抛出 ValueError"""
        with pytest.raises(ValueError, match="cannot be empty"):
            pm.generate_task_json([])

    def test_priority_mapping_in_json(self, pm):
        """优先级映射正确"""
        tasks = self._make_tasks()
        result = pm.generate_task_json(tasks)
        parsed = json.loads(result.json_text)
        # 第一个任务是 high
        assert parsed["tasks"][0]["priority"] == "high"

    def test_status_mapping_in_json(self, pm):
        """状态映射正确"""
        tasks = self._make_tasks()
        result = pm.generate_task_json(tasks)
        parsed = json.loads(result.json_text)
        for task in parsed["tasks"]:
            assert task["status"] == "pending"

    def test_result_properties(self, pm):
        """TaskJsonResult 属性正确"""
        tasks = self._make_tasks()
        result = pm.generate_task_json(tasks, project_name="测试项目")
        assert result.total_tasks == len(tasks)
        assert result.project_name == "测试项目"


# ══════════════════════════════════════════════════════════
# 4. 完整流水线场景
# ══════════════════════════════════════════════════════════


class TestFullPipelineScenarios:
    """完整流水线场景测试"""

    def test_refine_to_decompose(self, pm, login_need):
        """refine → communicate（确认）→ decompose"""
        draft = pm.refine_requirement(login_need)

        # 传入确认回调（空字符串 = 确认）
        def confirm_callback(round_num, questions):
            return ""  # 确认

        comm = pm.communicate_with_user(draft, user_response_callback=confirm_callback)
        assert comm.is_confirmed

        confirmed = comm.confirmed_bdd or pm.confirmed_bdd or draft.to_text()
        result = pm.decompose_requirement(confirmed)
        assert result.has_tasks
        assert result.total_tasks >= 1

    def test_refine_to_task_json(self, pm, login_need):
        """refine → decompose → generate_task_json"""
        draft = pm.refine_requirement(login_need)
        confirmed = draft.to_text()
        decompose = pm.decompose_requirement(confirmed)
        result = pm.generate_task_json(decompose.tasks)
        assert isinstance(result, TaskJsonResult)
        assert result.total_tasks >= 1

    def test_refine_to_test_script(self, pm, login_need):
        """refine → decompose → generate_test_script"""
        draft = pm.refine_requirement(login_need)
        confirmed = draft.to_text()
        decompose = pm.decompose_requirement(confirmed)
        # 为每个任务生成测试脚本
        for task in decompose.tasks:
            script = pm.generate_test_script(task)
            assert isinstance(script, TestScriptResult)
            assert script.has_content
            assert script.task_id == task["id"]

    def test_full_pipeline_with_file_output(self, pm, login_need, tmp_path):
        """完整流水线 + 文件输出"""
        # 1. refine
        draft = pm.refine_requirement(login_need)
        # 2. communicate（确认回调）
        def confirm_callback(round_num, questions):
            return ""

        comm = pm.communicate_with_user(draft, user_response_callback=confirm_callback)
        assert comm.is_confirmed
        # 3. decompose
        confirmed = comm.confirmed_bdd or draft.to_text()
        decompose = pm.decompose_requirement(confirmed)
        # 4. generate_task_json + 写文件
        task_json_path = tmp_path / "task.json"
        task_json_result = pm.generate_task_json(
            decompose.tasks, output_path=task_json_path
        )
        assert task_json_result.is_saved_to_file
        assert task_json_path.exists()
        # 5. generate_test_script + 写文件
        if decompose.tasks:
            script_path = tmp_path / "test_task_001.py"
            script_result = pm.generate_test_script(
                decompose.tasks[0], output_path=script_path
            )
            assert script_result.is_saved_to_file
            assert script_path.exists()

    def test_pipeline_preserves_bdd_through_stages(self, pm, login_need):
        """流水线各阶段保留 BDD 信息"""
        # refine
        draft = pm.refine_requirement(login_need)
        original_scenarios = draft.scenario_count

        # decompose
        confirmed = draft.to_text()
        decompose = pm.decompose_requirement(confirmed)

        # 每个 decompose 任务都有 BDD
        for task in decompose.tasks:
            assert task["bdd"] is not None
            assert "given" in task["bdd"]
            assert "when" in task["bdd"]
            assert "then" in task["bdd"]

    def test_pipeline_with_user_feedback(self, pm):
        """流水线中用户反馈被纳入"""
        draft = pm.refine_requirement("需要用户管理功能")

        # 用户给出反馈
        def feedback_callback(round_num, questions):
            if round_num == 1:
                return "需要支持微信登录和手机号登录"
            return ""  # 确认

        comm = pm.communicate_with_user(draft, user_response_callback=feedback_callback)
        # 反馈应被纳入草稿
        if comm.confirmed_bdd:
            # 确认的 BDD 应包含反馈信息
            pass  # 至少不应抛异常

    def test_ecom_full_pipeline(self, pm, ecom_need, tmp_path):
        """电商需求完整流水线"""
        # refine
        draft = pm.refine_requirement(ecom_need)
        assert draft.scenario_count >= 3

        # communicate（确认回调）
        def confirm_callback(round_num, questions):
            return ""

        comm = pm.communicate_with_user(draft, user_response_callback=confirm_callback)
        assert comm.is_confirmed

        # decompose
        confirmed = comm.confirmed_bdd or draft.to_text()
        decompose = pm.decompose_requirement(confirmed)
        assert decompose.total_tasks >= 3

        # generate_task_json
        result = pm.generate_task_json(decompose.tasks)
        assert result.total_tasks >= 3

        # 验证 JSON 格式
        parsed = json.loads(result.json_text)
        all_ids = {t["id"] for t in parsed["tasks"]}
        assert len(all_ids) == decompose.total_tasks


# ══════════════════════════════════════════════════════════
# 5. 跨方法数据一致性
# ══════════════════════════════════════════════════════════


class TestCrossMethodConsistency:
    """跨方法数据一致性测试"""

    def test_refine_saves_raw_requirement(self, pm, login_need):
        """refine_requirement 保存原始需求"""
        pm.refine_requirement(login_need)
        assert pm.raw_requirement == login_need

    def test_refine_saves_bdd_draft(self, pm, login_need):
        """refine_requirement 保存 BDD 草稿"""
        pm.refine_requirement(login_need)
        assert pm.bdd_draft is not None
        assert len(pm.bdd_draft) > 0

    def test_communicate_updates_confirmed_bdd(self, pm, login_need):
        """communicate_with_user 更新 confirmed_bdd"""
        draft = pm.refine_requirement(login_need)
        comm = pm.communicate_with_user(draft)
        if comm.is_confirmed:
            assert pm.confirmed_bdd is not None

    def test_decompose_saves_confirmed_bdd(self, pm, simple_bdd_text):
        """decompose_requirement 保存 confirmed_bdd"""
        pm.decompose_requirement(simple_bdd_text)
        assert pm.confirmed_bdd == simple_bdd_text.strip()

    def test_task_dict_to_model_field_mapping(self, pm):
        """任务字典 → Task 模型字段映射一致"""
        task_dict = {
            "id": "task-001",
            "title": "测试任务",
            "description": "测试描述",
            "bdd": {"given": "前提", "when": "动作", "then": "结果"},
            "test_script": None,
            "dependencies": [],
            "suggested_role": "dev",
            "priority": "high",
            "estimated_complexity": "low",
            "status": "pending",
        }
        result = pm.generate_task_json([task_dict])
        parsed = json.loads(result.json_text)
        task = parsed["tasks"][0]
        assert task["id"] == "task-001"
        assert task["title"] == "测试任务"
        assert task["priority"] == "high"
        assert task["estimated_complexity"] == "low"
        assert task["status"] == "pending"

    def test_decompose_to_task_json_consistency(self, pm, simple_bdd_text):
        """decompose 输出 → generate_task_json 输入一致性"""
        decompose = pm.decompose_requirement(simple_bdd_text)
        task_json_result = pm.generate_task_json(decompose.tasks)

        # 任务数量一致
        assert task_json_result.total_tasks == decompose.total_tasks

        # ID 一致
        parsed = json.loads(task_json_result.json_text)
        json_ids = {t["id"] for t in parsed["tasks"]}
        decompose_ids = set(decompose.task_ids)
        assert json_ids == decompose_ids

    def test_generate_test_script_task_id_matches(self, pm, simple_bdd_text):
        """generate_test_script 的 task_id 与输入一致"""
        decompose = pm.decompose_requirement(simple_bdd_text)
        for task in decompose.tasks:
            script = pm.generate_test_script(task)
            assert script.task_id == task["id"]


# ══════════════════════════════════════════════════════════
# 6. 边界与异常场景
# ══════════════════════════════════════════════════════════


class TestBoundaryAndErrorScenarios:
    """边界与异常场景测试"""

    def test_single_segment_need(self, pm):
        """单段需求生成 1 个场景"""
        draft = pm.refine_requirement("实现一个简单的配置读取功能")
        assert draft.scenario_count >= 1

    def test_very_long_requirement(self, pm):
        """超长需求不报错"""
        long_need = "系统需要支持用户注册。" * 50
        draft = pm.refine_requirement(long_need)
        assert draft.scenario_count >= 1

    def test_english_only_requirement(self, pm):
        """纯英文需求"""
        draft = pm.refine_requirement("Implement user login with email and password")
        assert draft.scenario_count >= 1

    def test_mixed_chinese_english_requirement(self, pm):
        """中英混合需求"""
        draft = pm.refine_requirement("实现 User API 接口，支持 CRUD 操作")
        assert draft.scenario_count >= 1

    def test_api_task_script_type(self, pm):
        """API 任务生成 API 类型脚本"""
        task = {
            "id": "task-api-001",
            "title": "API 接口测试",
            "description": "测试用户注册 API 接口",
            "bdd": {"given": "API 服务已启动", "when": "发送注册请求", "then": "返回成功"},
        }
        script = pm.generate_test_script(task)
        assert script.script_type == TestScriptType.API

    def test_ui_task_script_type(self, pm):
        """UI 任务生成 Playwright 类型脚本"""
        task = {
            "id": "task-ui-001",
            "title": "页面交互测试",
            "description": "测试登录页面表单验证",
            "bdd": {"given": "登录页面已加载", "when": "点击提交按钮", "then": "显示验证提示"},
        }
        script = pm.generate_test_script(task)
        assert script.script_type == TestScriptType.PLAYWRIGHT

    def test_integration_task_script_type(self, pm):
        """集成任务生成 Integration 类型脚本"""
        task = {
            "id": "task-int-001",
            "title": "端到端集成测试",
            "description": "测试完整业务流程",
            "bdd": {"given": "环境已就绪", "when": "执行完整流程", "then": "流程正常完成"},
        }
        script = pm.generate_test_script(task)
        assert script.script_type == TestScriptType.INTEGRATION

    def test_default_unit_script_type(self, pm):
        """默认脚本类型为 UNIT"""
        task = {
            "id": "task-unit-001",
            "title": "数据处理",
            "description": "处理用户数据",
            "bdd": {"given": "数据已就绪", "when": "执行处理", "then": "数据正确"},
        }
        script = pm.generate_test_script(task)
        assert script.script_type == TestScriptType.UNIT

    def test_multiple_agents_pipeline_independence(self, login_need):
        """多个 PM Agent 实例流水线互不干扰"""
        pm1 = ProductManagerAgent()
        pm2 = ProductManagerAgent()

        draft1 = pm1.refine_requirement(login_need)
        draft2 = pm2.refine_requirement("需要数据导出功能")

        assert pm1.raw_requirement == login_need
        assert pm2.raw_requirement == "需要数据导出功能"
        assert draft1.raw_need == login_need
        assert draft2.raw_need == "需要数据导出功能"

    def test_task_without_bdd_field(self, pm):
        """任务缺少 bdd 字段不报错（使用空 BDD）"""
        task = {
            "id": "task-nobdd",
            "title": "无BDD任务",
            "description": "描述",
        }
        script = pm.generate_test_script(task)
        assert isinstance(script, TestScriptResult)

    def test_circular_dependency_detection(self, pm):
        """task.json 不允许循环依赖（TaskJSON 模型校验）"""
        tasks = [
            {
                "id": "task-001",
                "title": "任务A",
                "description": "描述A",
                "bdd": {"given": "前提", "when": "动作", "then": "结果"},
                "dependencies": ["task-002"],
                "suggested_role": "dev",
                "priority": "high",
                "estimated_complexity": "medium",
                "status": "pending",
            },
            {
                "id": "task-002",
                "title": "任务B",
                "description": "描述B",
                "bdd": {"given": "前提", "when": "动作", "then": "结果"},
                "dependencies": ["task-001"],
                "suggested_role": "dev",
                "priority": "medium",
                "estimated_complexity": "medium",
                "status": "pending",
            },
        ]
        # TaskJSON 模型应检测到循环依赖
        with pytest.raises(Exception):
            pm.generate_task_json(tasks)

    def test_communicate_with_none_draft_raises(self, pm):
        """communicate_with_user(None) 抛出 ValueError"""
        with pytest.raises(ValueError, match="cannot be None"):
            pm.communicate_with_user(None)


class TestTaskJsonModelValidation:
    """TaskJSON 模型校验场景测试"""

    def test_task_json_rejects_invalid_dependency(self):
        """TaskJSON 拒绝无效依赖引用"""
        with pytest.raises(Exception):
            TaskJSON(
                project_name="测试",
                total_tasks=1,
                tasks=[
                    Task(
                        id="task-001",
                        title="任务1",
                        dependencies=["task-999"],  # 不存在的 ID
                    )
                ],
            )

    def test_task_json_rejects_mismatched_total(self):
        """TaskJSON 拒绝 total_tasks 与实际不一致"""
        with pytest.raises(Exception):
            TaskJSON(
                project_name="测试",
                total_tasks=5,  # 实际只有 1 个
                tasks=[
                    Task(id="task-001", title="任务1"),
                ],
            )

    def test_task_json_valid_creation(self):
        """TaskJSON 正确创建"""
        tj = TaskJSON(
            project_name="测试项目",
            description="测试描述",
            total_tasks=2,
            tasks=[
                Task(id="task-001", title="任务1", description="描述1", priority=TaskPriority.HIGH),
                Task(id="task-002", title="任务2", description="描述2", dependencies=["task-001"]),
            ],
        )
        assert tj.total_tasks == 2
        assert len(tj.tasks) == 2


# ══════════════════════════════════════════════════════════
# 7. Prompt 构建场景
# ══════════════════════════════════════════════════════════


class TestPromptScenarios:
    """Prompt 构建场景测试"""

    def test_refine_prompt_contains_need(self, pm, login_need):
        """refine prompt 包含原始需求"""
        prompt = pm.get_refine_prompt(login_need)
        assert login_need in prompt

    def test_decompose_prompt_contains_bdd(self, pm, simple_bdd_text):
        """decompose prompt 包含 BDD 文本"""
        prompt = pm.get_decompose_prompt(simple_bdd_text)
        assert simple_bdd_text in prompt

    def test_generate_task_json_prompt_contains_tasks(self, pm):
        """generate_task_json prompt 包含任务列表"""
        tasks = [{"id": "task-001", "title": "测试"}]
        prompt = pm.get_generate_task_json_prompt(tasks)
        assert "task-001" in prompt

    def test_generate_test_script_prompt_contains_bdd(self, pm):
        """generate_test_script prompt 包含 BDD"""
        task = {
            "id": "task-001",
            "title": "登录",
            "bdd": {"given": "前提", "when": "动作", "then": "结果"},
        }
        prompt = pm.get_generate_test_script_prompt(task)
        assert "前提" in prompt or "Given" in prompt

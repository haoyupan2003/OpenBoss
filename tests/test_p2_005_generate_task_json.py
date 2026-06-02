"""
P2-005 测试：task.json 生成 generate_task_json

验证 ProductManagerAgent.generate_task_json 的完整功能。
测试覆盖：
1. TaskJsonResult 数据模型
2. generate_task_json 核心流程
3. 任务字典 → Task 模型转换
4. 项目名称推断
5. TaskJSON 模型校验
6. JSON 序列化
7. 文件写入
8. 生成 Prompt
9. 边界条件与异常处理
10. 生命周期集成
"""

import json
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

from agent_automation_system.models.bdd import (
    BDDDraft,
    DecomposeResult,
    TaskJsonResult,
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
def pm_agent():
    """创建默认 ProductManagerAgent 实例"""
    return ProductManagerAgent()


@pytest.fixture
def single_task_dict():
    """创建单个任务字典"""
    return {
        "id": "task-001",
        "title": "用户登录",
        "description": "在用户未登录的情况下，用户输入邮箱和密码提交，以使登录成功跳转首页",
        "bdd": {
            "given": "用户未登录",
            "when": "用户输入邮箱和密码提交",
            "then": "登录成功跳转首页",
        },
        "test_script": None,
        "dependencies": [],
        "suggested_role": "dev",
        "priority": "high",
        "estimated_complexity": "medium",
        "status": "pending",
    }


@pytest.fixture
def multi_task_dicts():
    """创建多个任务字典（含依赖关系）"""
    return [
        {
            "id": "task-001",
            "title": "用户注册",
            "description": "实现用户注册功能",
            "bdd": {
                "given": "用户未注册",
                "when": "用户填写注册表单并提交",
                "then": "创建用户账号并返回成功",
            },
            "dependencies": [],
            "suggested_role": "dev",
            "priority": "high",
            "estimated_complexity": "medium",
            "status": "pending",
        },
        {
            "id": "task-002",
            "title": "用户登录",
            "description": "实现用户登录功能",
            "bdd": {
                "given": "用户已注册",
                "when": "用户输入有效凭证并提交",
                "then": "用户成功登录并获取认证令牌",
            },
            "dependencies": ["task-001"],
            "suggested_role": "dev",
            "priority": "high",
            "estimated_complexity": "medium",
            "status": "pending",
        },
        {
            "id": "task-003",
            "title": "用户登录测试",
            "description": "编写用户登录功能测试",
            "bdd": {
                "given": "登录功能已实现",
                "when": "执行登录测试用例",
                "then": "所有测试通过",
            },
            "dependencies": ["task-002"],
            "suggested_role": "qa",
            "priority": "medium",
            "estimated_complexity": "low",
            "status": "pending",
        },
    ]


@pytest.fixture
def task_dicts_without_bdd():
    """创建不含 BDD 的任务字典列表"""
    return [
        {
            "id": "task-001",
            "title": "配置环境",
            "description": "配置开发环境",
            "dependencies": [],
            "suggested_role": "dev",
            "priority": "high",
            "estimated_complexity": "low",
            "status": "pending",
        },
    ]


# ══════════════════════════════════════════════════════════
# 1. TaskJsonResult 数据模型
# ══════════════════════════════════════════════════════════


class TestTaskJsonResultModel:
    """TaskJsonResult 数据模型"""

    def test_create_with_all_fields(self, single_task_dict):
        """创建包含所有字段的 TaskJsonResult"""
        task_model = Task(
            id="task-001",
            title="测试",
            description="描述",
        )
        task_json_obj = TaskJSON(
            project_name="测试项目",
            total_tasks=1,
            tasks=[task_model],
        )
        result = TaskJsonResult(
            task_json=task_json_obj,
            json_text='{"test": true}',
            output_path="/path/to/task.json",
            created_at=datetime.now(),
        )
        assert result.task_json is task_json_obj
        assert result.json_text == '{"test": true}'
        assert result.output_path == "/path/to/task.json"

    def test_total_tasks_property(self, single_task_dict):
        """total_tasks 属性"""
        task_model = Task(id="task-001", title="测试", description="描述")
        task_json_obj = TaskJSON(
            project_name="项目",
            total_tasks=1,
            tasks=[task_model],
        )
        result = TaskJsonResult(
            task_json=task_json_obj,
            json_text="{}",
        )
        assert result.total_tasks == 1

    def test_project_name_property(self):
        """project_name 属性"""
        task_model = Task(id="task-001", title="测试", description="描述")
        task_json_obj = TaskJSON(
            project_name="我的项目",
            total_tasks=1,
            tasks=[task_model],
        )
        result = TaskJsonResult(
            task_json=task_json_obj,
            json_text="{}",
        )
        assert result.project_name == "我的项目"

    def test_is_saved_to_file_true(self):
        """is_saved_to_file 为 True"""
        task_model = Task(id="task-001", title="测试", description="描述")
        task_json_obj = TaskJSON(
            project_name="项目",
            total_tasks=1,
            tasks=[task_model],
        )
        result = TaskJsonResult(
            task_json=task_json_obj,
            json_text="{}",
            output_path="/path/to/task.json",
        )
        assert result.is_saved_to_file is True

    def test_is_saved_to_file_false(self):
        """is_saved_to_file 为 False（未写入文件）"""
        task_model = Task(id="task-001", title="测试", description="描述")
        task_json_obj = TaskJSON(
            project_name="项目",
            total_tasks=1,
            tasks=[task_model],
        )
        result = TaskJsonResult(
            task_json=task_json_obj,
            json_text="{}",
        )
        assert result.is_saved_to_file is False


# ══════════════════════════════════════════════════════════
# 2. generate_task_json 核心流程
# ══════════════════════════════════════════════════════════


class TestGenerateTaskJsonCore:
    """generate_task_json 核心流程"""

    def test_returns_task_json_result(self, pm_agent, single_task_dict):
        """返回 TaskJsonResult 实例"""
        result = pm_agent.generate_task_json([single_task_dict])
        assert isinstance(result, TaskJsonResult)

    def test_result_contains_task_json_model(self, pm_agent, single_task_dict):
        """结果包含 TaskJSON 模型对象"""
        result = pm_agent.generate_task_json([single_task_dict])
        assert isinstance(result.task_json, TaskJSON)

    def test_result_contains_json_text(self, pm_agent, single_task_dict):
        """结果包含 JSON 文本"""
        result = pm_agent.generate_task_json([single_task_dict])
        assert isinstance(result.json_text, str)
        assert len(result.json_text) > 0

    def test_json_text_is_valid_json(self, pm_agent, single_task_dict):
        """JSON 文本是有效的 JSON"""
        result = pm_agent.generate_task_json([single_task_dict])
        parsed = json.loads(result.json_text)
        assert "project_name" in parsed
        assert "tasks" in parsed

    def test_result_has_created_at(self, pm_agent, single_task_dict):
        """结果包含创建时间"""
        result = pm_agent.generate_task_json([single_task_dict])
        assert result.created_at is not None

    def test_custom_project_name(self, pm_agent, single_task_dict):
        """自定义项目名称"""
        result = pm_agent.generate_task_json(
            [single_task_dict], project_name="我的项目"
        )
        assert result.project_name == "我的项目"

    def test_custom_project_description(self, pm_agent, single_task_dict):
        """自定义项目描述"""
        result = pm_agent.generate_task_json(
            [single_task_dict],
            project_name="项目",
            project_description="项目描述文本",
        )
        assert result.task_json.description == "项目描述文本"

    def test_empty_tasks_raises_error(self, pm_agent):
        """空任务列表抛出 ValueError"""
        with pytest.raises(ValueError, match="tasks cannot be empty"):
            pm_agent.generate_task_json([])

    def test_multi_tasks(self, pm_agent, multi_task_dicts):
        """多任务生成"""
        result = pm_agent.generate_task_json(multi_task_dicts)
        assert result.total_tasks == 3


# ══════════════════════════════════════════════════════════
# 3. 任务字典 → Task 模型转换
# ══════════════════════════════════════════════════════════


class TestTaskConversion:
    """任务字典 → Task 模型转换"""

    def test_convert_single_task(self, pm_agent, single_task_dict):
        """转换单个任务字典"""
        models = pm_agent._convert_tasks_to_models([single_task_dict])
        assert len(models) == 1
        assert isinstance(models[0], Task)
        assert models[0].id == "task-001"
        assert models[0].title == "用户登录"

    def test_convert_multi_tasks(self, pm_agent, multi_task_dicts):
        """转换多个任务字典"""
        models = pm_agent._convert_tasks_to_models(multi_task_dicts)
        assert len(models) == 3
        assert models[0].id == "task-001"
        assert models[1].id == "task-002"
        assert models[2].id == "task-003"

    def test_priority_mapping(self, pm_agent):
        """优先级映射"""
        assert pm_agent._map_priority("high") == TaskPriority.HIGH
        assert pm_agent._map_priority("medium") == TaskPriority.MEDIUM
        assert pm_agent._map_priority("low") == TaskPriority.LOW
        assert pm_agent._map_priority("unknown") == TaskPriority.MEDIUM

    def test_complexity_mapping(self, pm_agent):
        """复杂度映射"""
        assert pm_agent._map_complexity("high") == TaskComplexity.HIGH
        assert pm_agent._map_complexity("medium") == TaskComplexity.MEDIUM
        assert pm_agent._map_complexity("low") == TaskComplexity.LOW

    def test_status_mapping(self, pm_agent):
        """状态映射"""
        assert pm_agent._map_status("pending") == TaskStatus.PENDING
        assert pm_agent._map_status("in_progress") == TaskStatus.IN_PROGRESS
        assert pm_agent._map_status("completed") == TaskStatus.COMPLETED
        assert pm_agent._map_status("failed") == TaskStatus.FAILED

    def test_bdd_conversion(self, pm_agent, single_task_dict):
        """BDD 字典转 BDDSpec"""
        models = pm_agent._convert_tasks_to_models([single_task_dict])
        assert models[0].bdd is not None
        assert isinstance(models[0].bdd, BDDSpec)
        assert models[0].bdd.given == "用户未登录"
        assert models[0].bdd.when == "用户输入邮箱和密码提交"
        assert models[0].bdd.then == "登录成功跳转首页"

    def test_no_bdd_conversion(self, pm_agent, task_dicts_without_bdd):
        """无 BDD 字典时 bdd 为 None"""
        models = pm_agent._convert_tasks_to_models(task_dicts_without_bdd)
        assert models[0].bdd is None

    def test_dependencies_preserved(self, pm_agent, multi_task_dicts):
        """依赖关系保留"""
        models = pm_agent._convert_tasks_to_models(multi_task_dicts)
        assert models[0].dependencies == []
        assert models[1].dependencies == ["task-001"]
        assert models[2].dependencies == ["task-002"]

    def test_suggested_role_preserved(self, pm_agent, multi_task_dicts):
        """建议角色保留"""
        models = pm_agent._convert_tasks_to_models(multi_task_dicts)
        assert models[0].suggested_role == "dev"
        assert models[2].suggested_role == "qa"


# ══════════════════════════════════════════════════════════
# 4. 项目名称推断
# ══════════════════════════════════════════════════════════


class TestProjectNameInference:
    """项目名称推断"""

    def test_infer_from_title(self, pm_agent):
        """从任务标题推断项目名称"""
        tasks = [{"id": "task-001", "title": "用户登录", "description": ""}]
        name = pm_agent._infer_project_name(tasks)
        assert "用户登录" in name

    def test_infer_from_description(self, pm_agent):
        """从任务描述推断项目名称"""
        tasks = [{"id": "task-001", "title": "", "description": "电商平台功能开发"}]
        name = pm_agent._infer_project_name(tasks)
        assert "电商平台" in name

    def test_infer_default_name(self, pm_agent):
        """无有效信息时使用默认名称"""
        tasks = [{"id": "task-001", "title": "", "description": ""}]
        name = pm_agent._infer_project_name(tasks)
        assert name == "OpenBoss Project"

    def test_infer_empty_tasks(self, pm_agent):
        """空任务列表使用默认名称"""
        name = pm_agent._infer_project_name([])
        assert name == "OpenBoss Project"

    def test_infer_appends_project_suffix(self, pm_agent):
        """推断名称追加"项目"后缀"""
        tasks = [{"id": "task-001", "title": "登录功能", "description": ""}]
        name = pm_agent._infer_project_name(tasks)
        assert name.endswith("项目")


# ══════════════════════════════════════════════════════════
# 5. TaskJSON 模型校验
# ══════════════════════════════════════════════════════════


class TestTaskJsonValidation:
    """TaskJSON 模型校验"""

    def test_valid_task_json(self, pm_agent, multi_task_dicts):
        """合法的 TaskJSON 通过校验"""
        result = pm_agent.generate_task_json(multi_task_dicts)
        assert result.task_json.total_tasks == 3

    def test_total_tasks_matches(self, pm_agent, multi_task_dicts):
        """total_tasks 与实际数量一致"""
        result = pm_agent.generate_task_json(multi_task_dicts)
        assert result.task_json.total_tasks == len(result.task_json.tasks)

    def test_dependencies_exist_validation(self, pm_agent, multi_task_dicts):
        """依赖引用校验通过"""
        result = pm_agent.generate_task_json(multi_task_dicts)
        task_ids = {t.id for t in result.task_json.tasks}
        for task in result.task_json.tasks:
            for dep in task.dependencies:
                assert dep in task_ids

    def test_invalid_dependency_raises_error(self, pm_agent):
        """无效依赖引用触发 ValueError"""
        tasks = [
            {
                "id": "task-001",
                "title": "任务",
                "description": "描述",
                "dependencies": ["task-999"],  # 不存在的依赖
                "priority": "high",
                "estimated_complexity": "medium",
                "status": "pending",
            },
        ]
        with pytest.raises(ValueError, match="does not exist"):
            pm_agent.generate_task_json(tasks)

    def test_circular_dependency_raises_error(self, pm_agent):
        """循环依赖触发 ValueError"""
        tasks = [
            {
                "id": "task-001",
                "title": "任务A",
                "description": "描述A",
                "dependencies": ["task-002"],
                "priority": "high",
                "estimated_complexity": "medium",
                "status": "pending",
            },
            {
                "id": "task-002",
                "title": "任务B",
                "description": "描述B",
                "dependencies": ["task-001"],
                "priority": "high",
                "estimated_complexity": "medium",
                "status": "pending",
            },
        ]
        with pytest.raises(ValueError, match="[Cc]ircular"):
            pm_agent.generate_task_json(tasks)

    def test_self_dependency_raises_error(self, pm_agent):
        """自依赖触发 ValueError"""
        tasks = [
            {
                "id": "task-001",
                "title": "任务",
                "description": "描述",
                "dependencies": ["task-001"],
                "priority": "high",
                "estimated_complexity": "medium",
                "status": "pending",
            },
        ]
        with pytest.raises(ValueError, match="cannot depend on itself"):
            pm_agent.generate_task_json(tasks)


# ══════════════════════════════════════════════════════════
# 6. JSON 序列化
# ══════════════════════════════════════════════════════════


class TestJsonSerialization:
    """JSON 序列化"""

    def test_serialize_produces_valid_json(self, pm_agent, single_task_dict):
        """序列化产出合法 JSON"""
        result = pm_agent.generate_task_json([single_task_dict])
        parsed = json.loads(result.json_text)
        assert isinstance(parsed, dict)

    def test_json_contains_project_name(self, pm_agent, single_task_dict):
        """JSON 包含 project_name"""
        result = pm_agent.generate_task_json(
            [single_task_dict], project_name="测试项目"
        )
        parsed = json.loads(result.json_text)
        assert parsed["project_name"] == "测试项目"

    def test_json_contains_tasks_array(self, pm_agent, single_task_dict):
        """JSON 包含 tasks 数组"""
        result = pm_agent.generate_task_json([single_task_dict])
        parsed = json.loads(result.json_text)
        assert isinstance(parsed["tasks"], list)
        assert len(parsed["tasks"]) == 1

    def test_json_contains_total_tasks(self, pm_agent, multi_task_dicts):
        """JSON 包含 total_tasks"""
        result = pm_agent.generate_task_json(multi_task_dicts)
        parsed = json.loads(result.json_text)
        assert parsed["total_tasks"] == 3

    def test_json_task_has_bdd(self, pm_agent, single_task_dict):
        """JSON 中任务包含 BDD"""
        result = pm_agent.generate_task_json([single_task_dict])
        parsed = json.loads(result.json_text)
        task = parsed["tasks"][0]
        assert "bdd" in task
        assert task["bdd"]["given"] == "用户未登录"

    def test_json_chinese_not_escaped(self, pm_agent, single_task_dict):
        """JSON 中中文不被转义"""
        result = pm_agent.generate_task_json([single_task_dict])
        assert "用户登录" in result.json_text
        assert "\\u" not in result.json_text  # 无 Unicode 转义

    def test_json_is_indented(self, pm_agent, single_task_dict):
        """JSON 格式化缩进"""
        result = pm_agent.generate_task_json([single_task_dict])
        assert "\n" in result.json_text
        assert "  " in result.json_text  # 2 空格缩进

    def test_json_contains_created_by(self, pm_agent, single_task_dict):
        """JSON 包含 created_by"""
        result = pm_agent.generate_task_json([single_task_dict])
        parsed = json.loads(result.json_text)
        assert parsed["created_by"] == "Product Manager Agent"


# ══════════════════════════════════════════════════════════
# 7. 文件写入
# ══════════════════════════════════════════════════════════


class TestFileWrite:
    """文件写入"""

    def test_write_to_file(self, pm_agent, single_task_dict, tmp_path):
        """写入到文件"""
        output = tmp_path / "task.json"
        result = pm_agent.generate_task_json(
            [single_task_dict], output_path=output
        )
        assert result.is_saved_to_file is True
        assert output.exists()

    def test_written_file_is_valid_json(self, pm_agent, single_task_dict, tmp_path):
        """写入的文件是合法 JSON"""
        output = tmp_path / "task.json"
        result = pm_agent.generate_task_json(
            [single_task_dict], output_path=output
        )
        content = output.read_text(encoding="utf-8")
        parsed = json.loads(content)
        assert "project_name" in parsed

    def test_output_path_in_result(self, pm_agent, single_task_dict, tmp_path):
        """结果包含输出路径"""
        output = tmp_path / "task.json"
        result = pm_agent.generate_task_json(
            [single_task_dict], output_path=output
        )
        assert result.output_path is not None
        assert "task.json" in result.output_path

    def test_no_output_path_means_no_file(self, pm_agent, single_task_dict):
        """不指定输出路径时不写入文件"""
        result = pm_agent.generate_task_json([single_task_dict])
        assert result.is_saved_to_file is False
        assert result.output_path is None

    def test_creates_parent_directory(self, pm_agent, single_task_dict, tmp_path):
        """自动创建父目录"""
        output = tmp_path / "subdir" / "deep" / "task.json"
        result = pm_agent.generate_task_json(
            [single_task_dict], output_path=output
        )
        assert output.exists()

    def test_written_file_encoding_utf8(self, pm_agent, single_task_dict, tmp_path):
        """写入文件使用 UTF-8 编码"""
        output = tmp_path / "task.json"
        pm_agent.generate_task_json([single_task_dict], output_path=output)
        content = output.read_text(encoding="utf-8")
        assert "用户登录" in content


# ══════════════════════════════════════════════════════════
# 8. 生成 Prompt
# ══════════════════════════════════════════════════════════


class TestGenerateTaskJsonPrompt:
    """生成 Prompt 构建"""

    def test_prompt_contains_tasks(self, pm_agent, single_task_dict):
        """prompt 包含任务列表"""
        prompt = pm_agent.get_generate_task_json_prompt([single_task_dict])
        assert "task-001" in prompt

    def test_prompt_contains_instruction(self, pm_agent, single_task_dict):
        """prompt 包含生成指令"""
        prompt = pm_agent.get_generate_task_json_prompt([single_task_dict])
        assert "task.json" in prompt
        assert "project_name" in prompt

    def test_prompt_contains_role_identity(self, pm_agent, single_task_dict):
        """prompt 包含角色身份"""
        prompt = pm_agent.get_generate_task_json_prompt([single_task_dict])
        assert "角色身份" in prompt

    def test_prompt_mentions_validation(self, pm_agent, single_task_dict):
        """prompt 包含校验要求"""
        prompt = pm_agent.get_generate_task_json_prompt([single_task_dict])
        assert "循环依赖" in prompt or "依赖" in prompt


# ══════════════════════════════════════════════════════════
# 9. 边界条件与异常处理
# ══════════════════════════════════════════════════════════


class TestEdgeCasesAndErrors:
    """边界条件与异常处理"""

    def test_task_dict_missing_optional_fields(self, pm_agent):
        """任务字典缺少可选字段时使用默认值"""
        tasks = [
            {
                "id": "task-001",
                "title": "最小任务",
                "description": "描述",
            },
        ]
        result = pm_agent.generate_task_json(tasks)
        assert result.total_tasks == 1
        task = result.task_json.tasks[0]
        assert task.suggested_role == "dev"
        assert task.priority == TaskPriority.MEDIUM

    def test_task_dict_with_none_bdd(self, pm_agent):
        """bdd 字段为 None"""
        tasks = [
            {
                "id": "task-001",
                "title": "任务",
                "description": "描述",
                "bdd": None,
                "priority": "high",
                "estimated_complexity": "medium",
                "status": "pending",
            },
        ]
        result = pm_agent.generate_task_json(tasks)
        assert result.task_json.tasks[0].bdd is None

    def test_case_insensitive_priority(self, pm_agent):
        """优先级大小写不敏感"""
        assert pm_agent._map_priority("HIGH") == TaskPriority.HIGH
        assert pm_agent._map_priority("High") == TaskPriority.HIGH

    def test_case_insensitive_complexity(self, pm_agent):
        """复杂度大小写不敏感"""
        assert pm_agent._map_complexity("LOW") == TaskComplexity.LOW
        assert pm_agent._map_complexity("High") == TaskComplexity.HIGH

    def test_case_insensitive_status(self, pm_agent):
        """状态大小写不敏感"""
        assert pm_agent._map_status("PENDING") == TaskStatus.PENDING
        assert pm_agent._map_status("Failed") == TaskStatus.FAILED

    def test_unknown_priority_defaults_to_medium(self, pm_agent):
        """未知优先级默认 MEDIUM"""
        assert pm_agent._map_priority("urgent") == TaskPriority.MEDIUM

    def test_unknown_status_defaults_to_pending(self, pm_agent):
        """未知状态默认 PENDING"""
        assert pm_agent._map_status("unknown") == TaskStatus.PENDING

    def test_overwrite_existing_file(self, pm_agent, single_task_dict, tmp_path):
        """覆盖已有文件"""
        output = tmp_path / "task.json"
        output.write_text('{"old": true}', encoding="utf-8")
        result = pm_agent.generate_task_json(
            [single_task_dict], output_path=output
        )
        content = output.read_text(encoding="utf-8")
        assert "old" not in content
        assert "project_name" in content

    def test_multiple_generate_calls(self, pm_agent, single_task_dict):
        """多次调用 generate 生成不同结果"""
        result1 = pm_agent.generate_task_json(
            [single_task_dict], project_name="项目1"
        )
        result2 = pm_agent.generate_task_json(
            [single_task_dict], project_name="项目2"
        )
        assert result1.project_name != result2.project_name


# ══════════════════════════════════════════════════════════
# 10. 生命周期集成
# ══════════════════════════════════════════════════════════


class TestLifecycleIntegration:
    """生命周期集成（refine → communicate → decompose → generate_task_json）"""

    def test_full_pipeline(self, pm_agent, tmp_path):
        """完整流程：精炼 → 沟通 → 拆解 → 生成 task.json"""
        # 1. 精炼
        draft = pm_agent.refine_requirement("用户需要登录和注册功能")

        # 2. 沟通（自动确认 — 提供回调返回空字符串=确认）
        def confirm_callback(round_num, questions):
            return ""  # 空字符串 = 确认

        comm_result = pm_agent.communicate_with_user(draft, confirm_callback)
        assert comm_result.is_confirmed

        # 3. 拆解
        decompose_result = pm_agent.decompose_requirement(
            comm_result.confirmed_bdd
        )
        assert decompose_result.has_tasks

        # 4. 生成 task.json
        output = tmp_path / "task.json"
        json_result = pm_agent.generate_task_json(
            decompose_result.tasks,
            project_name="用户管理系统",
            output_path=output,
        )
        assert json_result.total_tasks >= 1
        assert json_result.is_saved_to_file
        assert output.exists()

    def test_decompose_to_task_json_consistency(self, pm_agent):
        """拆解结果与 task.json 任务数一致"""
        draft = pm_agent.refine_requirement("实现商品管理功能")

        def confirm_callback(round_num, questions):
            return ""

        comm_result = pm_agent.communicate_with_user(draft, confirm_callback)
        decompose_result = pm_agent.decompose_requirement(
            comm_result.confirmed_bdd
        )
        json_result = pm_agent.generate_task_json(
            decompose_result.tasks,
            project_name="商品管理",
        )
        assert decompose_result.total_tasks == json_result.total_tasks

    def test_generated_json_has_all_task_fields(self, pm_agent):
        """生成的 JSON 任务包含所有必要字段"""
        draft = pm_agent.refine_requirement("实现登录功能")

        def confirm_callback(round_num, questions):
            return ""

        comm_result = pm_agent.communicate_with_user(draft, confirm_callback)
        decompose_result = pm_agent.decompose_requirement(
            comm_result.confirmed_bdd
        )
        json_result = pm_agent.generate_task_json(
            decompose_result.tasks,
            project_name="登录系统",
        )
        parsed = json.loads(json_result.json_text)
        for task in parsed["tasks"]:
            assert "id" in task
            assert "title" in task
            assert "description" in task
            assert "dependencies" in task
            assert "suggested_role" in task
            assert "priority" in task
            assert "estimated_complexity" in task
            assert "status" in task

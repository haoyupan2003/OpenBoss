"""
P2-006 测试：generate_test_script — 测试脚本编写

验证 ProductManagerAgent.generate_test_script 的完整功能。
测试覆盖：
1. TestScriptType 枚举
2. TestScriptResult 数据模型
3. generate_test_script 核心流程
4. 脚本类型判断（_determine_script_type）
5. import 语句生成（_generate_imports）
6. 测试类名生成（_generate_test_class_name）
7. 测试用例生成（_generate_test_cases_from_bdd）
8. 脚本组装（_assemble_script）
9. 文件写入
10. generate_test_script_prompt
11. 边界条件与异常
12. 生命周期集成
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_automation_system.models.bdd import (
    TestScriptResult,
    TestScriptType,
)
from agent_automation_system.sub_agent.pm_agent import ProductManagerAgent


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def pm_agent():
    """创建默认 ProductManagerAgent 实例"""
    return ProductManagerAgent()


@pytest.fixture
def ui_task():
    """创建 UI 类型任务字典"""
    return {
        "id": "task-001",
        "title": "用户登录页面",
        "description": "实现用户登录页面，包含表单输入和提交",
        "bdd": {
            "given": "用户未登录，访问登录页面",
            "when": "用户输入有效邮箱和密码并提交",
            "then": "用户成功登录并跳转到首页",
        },
        "dependencies": [],
        "priority": "high",
        "estimated_complexity": "medium",
        "status": "pending",
    }


@pytest.fixture
def api_task():
    """创建 API 类型任务字典"""
    return {
        "id": "task-002",
        "title": "用户注册接口",
        "description": "实现用户注册 REST API 接口",
        "bdd": {
            "given": "用户不存在于系统中",
            "when": "发送注册请求到 API 端点",
            "then": "创建新用户并返回 201 状态码",
        },
        "dependencies": [],
        "priority": "high",
        "estimated_complexity": "medium",
        "status": "pending",
    }


@pytest.fixture
def integration_task():
    """创建集成测试类型任务字典"""
    return {
        "id": "task-003",
        "title": "订单集成流程",
        "description": "实现订单创建到支付完成的端到端集成流程",
        "bdd": {
            "given": "用户已登录且有购物车商品",
            "when": "用户提交订单并完成支付流程",
            "then": "订单创建成功且库存扣减",
        },
        "dependencies": ["task-001"],
        "priority": "medium",
        "estimated_complexity": "high",
        "status": "pending",
    }


@pytest.fixture
def unit_task():
    """创建单元测试类型任务字典"""
    return {
        "id": "task-004",
        "title": "密码加密工具",
        "description": "实现密码加密和验证工具函数",
        "bdd": {
            "given": "系统提供加密工具模块",
            "when": "调用加密函数处理明文密码",
            "then": "返回加密后的哈希值",
        },
        "dependencies": [],
        "priority": "medium",
        "estimated_complexity": "low",
        "status": "pending",
    }


@pytest.fixture
def minimal_task():
    """创建最小化任务字典"""
    return {
        "id": "task-005",
        "title": "简单任务",
        "description": "简单功能",
        "bdd": {
            "given": "初始状态",
            "when": "执行操作",
            "then": "得到结果",
        },
    }


# ══════════════════════════════════════════════════════════
# 1. TestScriptType 枚举
# ══════════════════════════════════════════════════════════


class TestTestScriptType:
    """TestScriptType 枚举测试"""

    def test_enum_values(self):
        """枚举包含四种脚本类型"""
        assert TestScriptType.PLAYWRIGHT.value == "playwright"
        assert TestScriptType.API.value == "api"
        assert TestScriptType.UNIT.value == "unit"
        assert TestScriptType.INTEGRATION.value == "integration"

    def test_enum_count(self):
        """枚举共 4 个值"""
        assert len(TestScriptType) == 4

    def test_enum_is_string(self):
        """枚举值是字符串"""
        assert isinstance(TestScriptType.PLAYWRIGHT, str)
        assert TestScriptType.PLAYWRIGHT == "playwright"

    def test_enum_from_value(self):
        """从字符串值创建枚举"""
        assert TestScriptType("playwright") == TestScriptType.PLAYWRIGHT
        assert TestScriptType("api") == TestScriptType.API
        assert TestScriptType("unit") == TestScriptType.UNIT
        assert TestScriptType("integration") == TestScriptType.INTEGRATION


# ══════════════════════════════════════════════════════════
# 2. TestScriptResult 数据模型
# ══════════════════════════════════════════════════════════


class TestTestScriptResult:
    """TestScriptResult 数据模型测试"""

    def test_create_basic_result(self):
        """创建基本结果"""
        result = TestScriptResult(
            task_id="task-001",
            script_type=TestScriptType.UNIT,
            script_content="import pytest\n",
            test_cases=["test_example"],
            imports_needed=["import pytest"],
        )
        assert result.task_id == "task-001"
        assert result.script_type == TestScriptType.UNIT
        assert result.script_content == "import pytest\n"

    def test_default_values(self):
        """默认值正确"""
        result = TestScriptResult(
            task_id="task-001",
            script_content="content",
        )
        assert result.script_type == TestScriptType.UNIT
        assert result.test_cases == []
        assert result.imports_needed == []
        assert result.output_path is None
        assert result.created_at is None

    def test_has_content_property(self):
        """has_content 属性"""
        result = TestScriptResult(
            task_id="task-001",
            script_content="import pytest\n",
        )
        assert result.has_content is True

        empty_result = TestScriptResult(
            task_id="task-002",
            script_content="   ",
        )
        assert empty_result.has_content is False

    def test_test_case_count_property(self):
        """test_case_count 属性"""
        result = TestScriptResult(
            task_id="task-001",
            script_content="content",
            test_cases=["test_a", "test_b", "test_c"],
        )
        assert result.test_case_count == 3

    def test_is_saved_to_file_property(self):
        """is_saved_to_file 属性"""
        result = TestScriptResult(
            task_id="task-001",
            script_content="content",
        )
        assert result.is_saved_to_file is False

        saved_result = TestScriptResult(
            task_id="task-002",
            script_content="content",
            output_path="/tmp/test.py",
        )
        assert saved_result.is_saved_to_file is True

    def test_empty_test_cases_filtered(self):
        """空字符串测试用例被过滤"""
        result = TestScriptResult(
            task_id="task-001",
            script_content="content",
            test_cases=["test_a", "", "test_b", "  "],
        )
        assert result.test_cases == ["test_a", "test_b"]

    def test_task_id_required(self):
        """task_id 不能为空"""
        with pytest.raises(Exception):
            TestScriptResult(
                task_id="",
                script_content="content",
            )

    def test_script_content_required(self):
        """script_content 不能为空"""
        with pytest.raises(Exception):
            TestScriptResult(
                task_id="task-001",
                script_content="",
            )


# ══════════════════════════════════════════════════════════
# 3. generate_test_script 核心流程
# ══════════════════════════════════════════════════════════


class TestGenerateTestScriptCore:
    """generate_test_script 核心流程测试"""

    def test_returns_test_script_result(self, pm_agent, unit_task):
        """返回 TestScriptResult 实例"""
        result = pm_agent.generate_test_script(unit_task)
        assert isinstance(result, TestScriptResult)

    def test_result_has_correct_task_id(self, pm_agent, unit_task):
        """结果包含正确的 task_id"""
        result = pm_agent.generate_test_script(unit_task)
        assert result.task_id == "task-004"

    def test_result_has_script_content(self, pm_agent, unit_task):
        """结果包含脚本内容"""
        result = pm_agent.generate_test_script(unit_task)
        assert result.has_content
        assert "import pytest" in result.script_content

    def test_result_has_test_cases(self, pm_agent, unit_task):
        """结果包含测试用例"""
        result = pm_agent.generate_test_script(unit_task)
        assert result.test_case_count > 0

    def test_result_has_imports(self, pm_agent, unit_task):
        """结果包含 import 列表"""
        result = pm_agent.generate_test_script(unit_task)
        assert len(result.imports_needed) > 0
        assert "import pytest" in result.imports_needed

    def test_result_has_created_at(self, pm_agent, unit_task):
        """结果包含创建时间"""
        result = pm_agent.generate_test_script(unit_task)
        assert result.created_at is not None
        assert isinstance(result.created_at, datetime)

    def test_result_not_saved_by_default(self, pm_agent, unit_task):
        """默认不写入文件"""
        result = pm_agent.generate_test_script(unit_task)
        assert result.output_path is None
        assert result.is_saved_to_file is False

    def test_empty_task_raises_error(self, pm_agent):
        """空任务字典抛出 ValueError"""
        with pytest.raises(ValueError, match="task cannot be empty"):
            pm_agent.generate_test_script({})

    def test_none_task_raises_error(self, pm_agent):
        """None 任务抛出 ValueError"""
        with pytest.raises(ValueError):
            pm_agent.generate_test_script(None)

    def test_task_without_id_raises_error(self, pm_agent):
        """缺少 id 字段的任务抛出 ValueError"""
        with pytest.raises(ValueError, match="id"):
            pm_agent.generate_test_script({"title": "test"})


# ══════════════════════════════════════════════════════════
# 4. 脚本类型判断（_determine_script_type）
# ══════════════════════════════════════════════════════════


class TestDetermineScriptType:
    """脚本类型判断测试"""

    def test_ui_task_returns_playwright(self, pm_agent, ui_task):
        """UI 任务返回 Playwright 类型"""
        result = pm_agent.generate_test_script(ui_task)
        assert result.script_type == TestScriptType.PLAYWRIGHT

    def test_api_task_returns_api(self, pm_agent, api_task):
        """API 任务返回 API 类型"""
        result = pm_agent.generate_test_script(api_task)
        assert result.script_type == TestScriptType.API

    def test_integration_task_returns_integration(self, pm_agent, integration_task):
        """集成任务返回 Integration 类型"""
        result = pm_agent.generate_test_script(integration_task)
        assert result.script_type == TestScriptType.INTEGRATION

    def test_unit_task_returns_unit(self, pm_agent, unit_task):
        """普通任务返回 Unit 类型"""
        result = pm_agent.generate_test_script(unit_task)
        assert result.script_type == TestScriptType.UNIT

    def test_page_keyword_triggers_playwright(self, pm_agent):
        """'页面' 关键词触发 Playwright"""
        task = {"id": "t1", "title": "页面展示", "description": "展示页面",
                "bdd": {"given": "状态", "when": "操作", "then": "结果"}}
        result = pm_agent.generate_test_script(task)
        assert result.script_type == TestScriptType.PLAYWRIGHT

    def test_interface_keyword_triggers_api(self, pm_agent):
        """'接口' 关键词触发 API"""
        task = {"id": "t1", "title": "数据接口", "description": "提供接口",
                "bdd": {"given": "状态", "when": "操作", "then": "结果"}}
        result = pm_agent.generate_test_script(task)
        assert result.script_type == TestScriptType.API

    def test_e2e_keyword_triggers_integration(self, pm_agent):
        """'端到端' 关键词触发 Integration"""
        task = {"id": "t1", "title": "端到端流程", "description": "完整流程",
                "bdd": {"given": "状态", "when": "操作", "then": "结果"}}
        result = pm_agent.generate_test_script(task)
        assert result.script_type == TestScriptType.INTEGRATION

    def test_bdd_when_affects_type(self, pm_agent):
        """BDD When 中的关键词也影响类型判断"""
        task = {"id": "t1", "title": "功能", "description": "普通功能",
                "bdd": {"given": "状态", "when": "调用API接口", "then": "结果"}}
        result = pm_agent.generate_test_script(task)
        assert result.script_type == TestScriptType.API


# ══════════════════════════════════════════════════════════
# 5. import 语句生成（_generate_imports）
# ══════════════════════════════════════════════════════════


class TestGenerateImports:
    """import 语句生成测试"""

    def test_unit_imports(self, pm_agent):
        """Unit 类型只有 pytest"""
        imports = pm_agent._generate_imports(TestScriptType.UNIT)
        assert "import pytest" in imports
        assert len(imports) == 1

    def test_playwright_imports(self, pm_agent):
        """Playwright 类型包含 playwright 导入"""
        imports = pm_agent._generate_imports(TestScriptType.PLAYWRIGHT)
        assert "import pytest" in imports
        assert any("playwright" in imp for imp in imports)

    def test_api_imports(self, pm_agent):
        """API 类型包含 requests 导入"""
        imports = pm_agent._generate_imports(TestScriptType.API)
        assert "import pytest" in imports
        assert any("requests" in imp for imp in imports)

    def test_integration_imports(self, pm_agent):
        """Integration 类型包含 mock 导入"""
        imports = pm_agent._generate_imports(TestScriptType.INTEGRATION)
        assert "import pytest" in imports
        assert any("mock" in imp for imp in imports)


# ══════════════════════════════════════════════════════════
# 6. 测试类名生成（_generate_test_class_name）
# ══════════════════════════════════════════════════════════


class TestGenerateTestClass:
    """测试类名生成测试"""

    def test_english_title(self, pm_agent):
        """英文标题生成 PascalCase 类名"""
        task = {"id": "task-001", "title": "User Login Page"}
        class_name = pm_agent._generate_test_class_name(task)
        assert class_name.startswith("Test")
        assert "User" in class_name or "Login" in class_name

    def test_chinese_title_fallback_to_id(self, pm_agent):
        """中文标题回退到 task_id 生成类名"""
        task = {"id": "task-001", "title": "用户登录功能"}
        class_name = pm_agent._generate_test_class_name(task)
        assert class_name.startswith("Test")

    def test_mixed_title_uses_english_parts(self, pm_agent):
        """中英混合标题使用英文部分"""
        task = {"id": "task-001", "title": "Login 登录 API"}
        class_name = pm_agent._generate_test_class_name(task)
        assert "Login" in class_name or "Api" in class_name

    def test_empty_title_uses_task_id(self, pm_agent):
        """空标题使用 task_id"""
        task = {"id": "task-001", "title": ""}
        class_name = pm_agent._generate_test_class_name(task)
        assert "Task001" in class_name or "001" in class_name

    def test_special_characters_cleaned(self, pm_agent):
        """特殊字符被清理"""
        task = {"id": "task-001", "title": "Login/Test@Feature"}
        class_name = pm_agent._generate_test_class_name(task)
        # 不应包含特殊字符
        assert "/" not in class_name
        assert "@" not in class_name

    def test_task_id_to_class_name(self, pm_agent):
        """task_id 转换为类名"""
        assert "Test" in pm_agent._task_id_to_class_name("task-001")
        assert "Task001" in pm_agent._task_id_to_class_name("task-001")


# ══════════════════════════════════════════════════════════
# 7. 测试用例生成（_generate_test_cases_from_bdd）
# ══════════════════════════════════════════════════════════


class TestGenerateTestCases:
    """测试用例生成测试"""

    def test_generates_at_least_one_case(self, pm_agent):
        """至少生成一个测试用例"""
        bdd = {"given": "初始状态", "when": "执行操作", "then": "得到结果"}
        cases = pm_agent._generate_test_cases_from_bdd(bdd, TestScriptType.UNIT)
        assert len(cases) >= 1

    def test_main_case_has_all_fields(self, pm_agent):
        """主测试用例包含完整字段"""
        bdd = {"given": "初始状态", "when": "执行操作", "then": "得到结果"}
        cases = pm_agent._generate_test_cases_from_bdd(bdd, TestScriptType.UNIT)
        main = cases[0]
        assert "name" in main
        assert "setup" in main
        assert "action" in main
        assert "assertion" in main

    def test_success_keyword_adds_failure_case(self, pm_agent):
        """When 含'成功/有效'关键词时追加反向用例"""
        bdd = {"given": "状态", "when": "输入有效凭证并提交", "then": "登录成功"}
        cases = pm_agent._generate_test_cases_from_bdd(bdd, TestScriptType.UNIT)
        # 应有正向 + 反向用例
        assert len(cases) >= 2
        case_names = [c["name"] for c in cases]
        has_failure = any("failure" in n for n in case_names)
        assert has_failure

    def test_input_keyword_adds_empty_case(self, pm_agent):
        """When 含'输入/提交'关键词时追加空输入用例"""
        bdd = {"given": "状态", "when": "输入用户名提交", "then": "注册成功"}
        cases = pm_agent._generate_test_cases_from_bdd(bdd, TestScriptType.UNIT)
        case_names = [c["name"] for c in cases]
        has_empty = any("empty" in n for n in case_names)
        assert has_empty

    def test_test_method_name_generation(self, pm_agent):
        """测试方法名生成"""
        name = pm_agent._generate_test_method_name("用户登录成功", "success")
        assert name.startswith("test_")
        assert "login" in name
        assert "success" in name

    def test_test_method_name_english(self, pm_agent):
        """英文 When 生成方法名"""
        name = pm_agent._generate_test_method_name("create user account", "success")
        assert name.startswith("test_")
        assert "success" in name

    def test_test_method_name_no_match(self, pm_agent):
        """无匹配关键词时使用默认名"""
        name = pm_agent._generate_test_method_name("do something", "success")
        assert name.startswith("test_")


# ══════════════════════════════════════════════════════════
# 8. 脚本组装（_assemble_script）
# ══════════════════════════════════════════════════════════


class TestAssembleScript:
    """脚本组装测试"""

    def test_script_contains_imports(self, pm_agent, unit_task):
        """脚本包含 import 语句"""
        result = pm_agent.generate_test_script(unit_task)
        assert "import pytest" in result.script_content

    def test_script_contains_class(self, pm_agent, unit_task):
        """脚本包含测试类"""
        result = pm_agent.generate_test_script(unit_task)
        assert "class Test" in result.script_content

    def test_script_contains_test_methods(self, pm_agent, unit_task):
        """脚本包含测试方法"""
        result = pm_agent.generate_test_script(unit_task)
        assert "def test_" in result.script_content

    def test_script_contains_docstring(self, pm_agent, unit_task):
        """脚本包含文件头注释"""
        result = pm_agent.generate_test_script(unit_task)
        assert '"""' in result.script_content
        assert "task-004" in result.script_content

    def test_playwright_script_has_fixture(self, pm_agent, ui_task):
        """Playwright 脚本包含 fixture"""
        result = pm_agent.generate_test_script(ui_task)
        assert "@pytest.fixture" in result.script_content

    def test_api_script_has_base_url(self, pm_agent, api_task):
        """API 脚本包含 base_url"""
        result = pm_agent.generate_test_script(api_task)
        assert "base_url" in result.script_content or "requests" in result.script_content

    def test_unit_script_has_arrange_act_assert(self, pm_agent, unit_task):
        """Unit 脚本包含 Arrange/Act/Assert 注释"""
        result = pm_agent.generate_test_script(unit_task)
        assert "Arrange" in result.script_content or "Assert" in result.script_content

    def test_empty_cases_get_placeholder(self, pm_agent):
        """无测试用例时生成占位方法"""
        script = pm_agent._assemble_script(
            imports=["import pytest"],
            class_name="TestPlaceholder",
            test_cases=[],
            script_type=TestScriptType.UNIT,
            task={"id": "task-000", "title": "empty"},
        )
        assert "test_placeholder" in script


# ══════════════════════════════════════════════════════════
# 9. 文件写入
# ══════════════════════════════════════════════════════════


class TestFileWrite:
    """文件写入测试"""

    def test_write_to_file(self, pm_agent, unit_task, tmp_path):
        """写入测试脚本到文件"""
        output_path = tmp_path / "test_task_004.py"
        result = pm_agent.generate_test_script(unit_task, output_path=output_path)
        assert result.is_saved_to_file
        assert result.output_path is not None
        # 文件确实存在
        assert Path(result.output_path).exists()

    def test_file_content_matches(self, pm_agent, unit_task, tmp_path):
        """文件内容与脚本内容一致"""
        output_path = tmp_path / "test_task_004.py"
        result = pm_agent.generate_test_script(unit_task, output_path=output_path)
        file_content = Path(result.output_path).read_text(encoding="utf-8")
        assert file_content == result.script_content

    def test_creates_parent_directory(self, pm_agent, unit_task, tmp_path):
        """自动创建父目录"""
        output_path = tmp_path / "subdir" / "nested" / "test_task.py"
        result = pm_agent.generate_test_script(unit_task, output_path=output_path)
        assert result.is_saved_to_file
        assert Path(result.output_path).exists()

    def test_no_write_when_path_none(self, pm_agent, unit_task):
        """output_path 为 None 时不写入"""
        result = pm_agent.generate_test_script(unit_task, output_path=None)
        assert result.output_path is None
        assert result.is_saved_to_file is False

    def test_write_returns_absolute_path(self, pm_agent, unit_task, tmp_path):
        """写入后返回绝对路径"""
        output_path = tmp_path / "test_task.py"
        result = pm_agent.generate_test_script(unit_task, output_path=output_path)
        assert Path(result.output_path).is_absolute()


# ══════════════════════════════════════════════════════════
# 10. generate_test_script_prompt
# ══════════════════════════════════════════════════════════


class TestGenerateTestScriptPrompt:
    """测试脚本编写 Prompt 测试"""

    def test_prompt_contains_task_info(self, pm_agent, unit_task):
        """prompt 包含任务信息"""
        prompt = pm_agent.get_generate_test_script_prompt(unit_task)
        assert "task-004" in prompt

    def test_prompt_contains_bdd(self, pm_agent, unit_task):
        """prompt 包含 BDD 规格"""
        prompt = pm_agent.get_generate_test_script_prompt(unit_task)
        assert "Given" in prompt
        assert "When" in prompt
        assert "Then" in prompt

    def test_prompt_contains_requirements(self, pm_agent, unit_task):
        """prompt 包含编写要求"""
        prompt = pm_agent.get_generate_test_script_prompt(unit_task)
        assert "pytest" in prompt
        assert "测试脚本" in prompt or "test script" in prompt.lower()

    def test_prompt_without_bdd(self, pm_agent):
        """无 BDD 时 prompt 仍可生成"""
        task = {"id": "task-001", "title": "test", "description": "desc"}
        prompt = pm_agent.get_generate_test_script_prompt(task)
        assert "task-001" in prompt


# ══════════════════════════════════════════════════════════
# 11. 边界条件与异常
# ══════════════════════════════════════════════════════════


class TestEdgeCases:
    """边界条件与异常测试"""

    def test_task_without_bdd(self, pm_agent):
        """无 BDD 字段时使用空默认值"""
        task = {"id": "task-001", "title": "简单任务", "description": "描述"}
        result = pm_agent.generate_test_script(task)
        assert isinstance(result, TestScriptResult)
        assert result.has_content

    def test_task_with_empty_bdd(self, pm_agent):
        """BDD 字段为空字典时"""
        task = {"id": "task-001", "title": "任务", "description": "描述", "bdd": {}}
        result = pm_agent.generate_test_script(task)
        assert isinstance(result, TestScriptResult)

    def test_task_with_partial_bdd(self, pm_agent):
        """BDD 字段不完整时"""
        task = {"id": "task-001", "title": "任务", "description": "描述",
                "bdd": {"given": "状态"}}
        result = pm_agent.generate_test_script(task)
        assert isinstance(result, TestScriptResult)

    def test_very_long_title(self, pm_agent):
        """超长标题"""
        task = {"id": "task-001", "title": "A" * 200,
                "description": "描述", "bdd": {"given": "G", "when": "W", "then": "T"}}
        result = pm_agent.generate_test_script(task)
        assert isinstance(result, TestScriptResult)

    def test_unicode_title(self, pm_agent):
        """Unicode 标题"""
        task = {"id": "task-001", "title": "🚀 功能测试",
                "description": "描述", "bdd": {"given": "G", "when": "W", "then": "T"}}
        result = pm_agent.generate_test_script(task)
        assert isinstance(result, TestScriptResult)

    def test_multiple_calls_independent(self, pm_agent, ui_task, api_task):
        """多次调用相互独立"""
        result1 = pm_agent.generate_test_script(ui_task)
        result2 = pm_agent.generate_test_script(api_task)
        assert result1.task_id != result2.task_id
        assert result1.script_type != result2.script_type

    def test_special_chars_in_bdd(self, pm_agent):
        """BDD 中含特殊字符"""
        task = {"id": "task-001", "title": "测试",
                "description": "描述",
                "bdd": {"given": "用户 @admin 在 系统中", "when": "执行 操作 #1", "then": "结果 OK!"}}
        result = pm_agent.generate_test_script(task)
        assert isinstance(result, TestScriptResult)

    def test_all_script_types_produce_valid_content(self, pm_agent):
        """所有脚本类型都产出有效内容"""
        base_task = {
            "id": "task-001",
            "description": "描述",
            "bdd": {"given": "状态", "when": "操作", "then": "结果"},
        }
        for script_type_keyword, expected_type in [
            ("页面UI组件", TestScriptType.PLAYWRIGHT),
            ("API接口请求", TestScriptType.API),
            ("端到端集成", TestScriptType.INTEGRATION),
            ("工具函数计算", TestScriptType.UNIT),
        ]:
            task = {**base_task, "title": script_type_keyword}
            result = pm_agent.generate_test_script(task)
            assert result.script_type == expected_type
            assert result.has_content
            assert result.test_case_count > 0


# ══════════════════════════════════════════════════════════
# 12. 生命周期集成
# ══════════════════════════════════════════════════════════


class TestLifecycleIntegration:
    """生命周期集成测试"""

    def test_refine_to_test_script(self, pm_agent):
        """refine → communicate → decompose → generate_task_json → generate_test_script"""
        # 1. 精炼需求
        draft = pm_agent.refine_requirement("用户需要一个登录功能，支持邮箱登录")

        # 2. 沟通确认（无问题自动确认）
        comm_result = pm_agent.communicate_with_user(draft, lambda r, q: "")

        # 3. 拆解任务
        decompose_result = pm_agent.decompose_requirement(comm_result.confirmed_bdd)
        assert decompose_result.has_tasks

        # 4. 生成 task.json
        task_json_result = pm_agent.generate_task_json(decompose_result.tasks)
        assert task_json_result.total_tasks > 0

        # 5. 为第一个任务生成测试脚本
        first_task = decompose_result.tasks[0]
        test_result = pm_agent.generate_test_script(first_task)
        assert isinstance(test_result, TestScriptResult)
        assert test_result.has_content
        assert test_result.test_case_count > 0

    def test_generate_test_scripts_for_all_tasks(self, pm_agent):
        """为所有拆解任务生成测试脚本"""
        draft = pm_agent.refine_requirement("实现用户注册和登录功能")
        comm_result = pm_agent.communicate_with_user(draft, lambda r, q: "")
        decompose_result = pm_agent.decompose_requirement(comm_result.confirmed_bdd)

        test_results = []
        for task in decompose_result.tasks:
            result = pm_agent.generate_test_script(task)
            test_results.append(result)

        assert len(test_results) == len(decompose_result.tasks)
        assert all(r.has_content for r in test_results)

    def test_full_pipeline_with_file_output(self, pm_agent, tmp_path):
        """完整管线含文件输出"""
        draft = pm_agent.refine_requirement("创建用户管理功能")
        comm_result = pm_agent.communicate_with_user(draft, lambda r, q: "")
        decompose_result = pm_agent.decompose_requirement(comm_result.confirmed_bdd)

        # 为每个任务生成测试脚本并写入文件
        for i, task in enumerate(decompose_result.tasks):
            output_path = tmp_path / f"test_task_{i:03d}.py"
            result = pm_agent.generate_test_script(task, output_path=output_path)
            assert result.is_saved_to_file
            assert Path(result.output_path).exists()

"""
P2-010 测试：SeniorDeveloperAgent.write_tests 实现

验证 write_tests 完整实现，覆盖：
1. TestWriteResult / TestCaseInfo 数据模型
2. write_tests 核心流程
3. 测试用例生成（BDD / 无 BDD / 高复杂度 / 特定内容）
4. 测试文件内容构建
5. 内部辅助方法
6. 与 get_implement_prompt 的集成
7. 边界条件与异常处理
"""

import re
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_automation_system.harness.models import (
    Harness,
    HarnessRule,
    HarnessSection,
    RuleType,
)
from agent_automation_system.models.dev_analysis import TaskAnalysisResult
from agent_automation_system.models.task import (
    BDDSpec,
    Task,
    TaskComplexity,
    TaskPriority,
    TaskStatus,
)
from agent_automation_system.models.test_write import TestCaseInfo, TestWriteResult
from agent_automation_system.sub_agent.dev_agent import (
    SeniorDeveloperAgent,
    _DEFAULT_MAX_IMPLEMENTATION_MINUTES,
)
from agent_automation_system.sub_agent.role_injector import RoleInjector
from agent_automation_system.sub_agent.sub_agent import (
    AgentPhase,
    SubAgentResult,
    SubAgentResultStatus,
)


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def dev_agent():
    """创建默认 SeniorDeveloperAgent 实例"""
    return SeniorDeveloperAgent()


@pytest.fixture
def dev_agent_with_mock_harness():
    """创建带 mock harness 的 SeniorDeveloperAgent 实例"""
    agent = SeniorDeveloperAgent()
    mock_harness = Harness(
        name="Senior Developer Agent Rules",
        file_path="/harness/dev-rules.md",
        role_name="senior-developer",
        sections=[
            HarnessSection(
                title="DO",
                rule_type=RuleType.DO,
                rules=[
                    HarnessRule(
                        rule_type=RuleType.DO,
                        content="Write test cases first following TDD methodology",
                        section="DO",
                    ),
                ],
                raw_content="- Write test cases first",
            ),
        ],
    )
    agent._dev_harness = mock_harness
    agent._dev_harness_content = mock_harness.to_prompt_text()
    return agent


@pytest.fixture
def sample_task():
    """创建示例 Task（含 BDD）"""
    return Task(
        id="task-001",
        title="实现用户登录 API",
        description="实现用户登录接口，支持邮箱和手机号登录",
        bdd=BDDSpec(
            given="用户已注册账号",
            when="提交正确的登录凭证",
            then="返回认证 token 和用户信息",
        ),
        dependencies=[],
        suggested_role="senior-developer",
        priority=TaskPriority.HIGH,
        estimated_complexity=TaskComplexity.MEDIUM,
        status=TaskStatus.PENDING,
    )


@pytest.fixture
def task_without_bdd():
    """创建无 BDD 的 Task"""
    return Task(
        id="task-010",
        title="简单配置修改",
        description="修改配置文件中的默认值",
        priority=TaskPriority.LOW,
        estimated_complexity=TaskComplexity.LOW,
        status=TaskStatus.PENDING,
    )


@pytest.fixture
def high_complexity_task():
    """创建高复杂度 Task"""
    return Task(
        id="task-020",
        title="实现并发任务调度 service",
        description="实现支持并发的任务调度服务，需要线程安全",
        bdd=BDDSpec(
            given="调度器已初始化",
            when="提交多个并发任务",
            then="所有任务按优先级顺序执行",
        ),
        dependencies=["task-001"],
        priority=TaskPriority.HIGH,
        estimated_complexity=TaskComplexity.HIGH,
        status=TaskStatus.PENDING,
    )


# ── 1. TestCaseInfo 数据模型 ───────────────────────────────


class TestTestCaseInfoModel:
    """验证 TestCaseInfo 数据模型"""

    def test_create_with_required_fields(self):
        """创建 TestCaseInfo 仅需 name"""
        tc = TestCaseInfo(name="test_login_succeeds")
        assert tc.name == "test_login_succeeds"
        assert tc.description == ""
        assert tc.category == "positive"

    def test_create_with_all_fields(self):
        """创建 TestCaseInfo 含全部字段"""
        tc = TestCaseInfo(
            name="test_login_fails",
            description="错误凭证登录失败",
            category="negative",
        )
        assert tc.name == "test_login_fails"
        assert tc.description == "错误凭证登录失败"
        assert tc.category == "negative"

    def test_name_required(self):
        """name 字段必填"""
        with pytest.raises(Exception):
            TestCaseInfo()

    def test_name_min_length(self):
        """name 不能为空字符串"""
        with pytest.raises(Exception):
            TestCaseInfo(name="")

    def test_category_defaults_positive(self):
        """category 默认为 positive"""
        tc = TestCaseInfo(name="test_something")
        assert tc.category == "positive"

    def test_various_categories(self):
        """各类 category 均可创建"""
        for cat in ["positive", "negative", "edge_case", "integration"]:
            tc = TestCaseInfo(name=f"test_{cat}", category=cat)
            assert tc.category == cat


# ── 2. TestWriteResult 数据模型 ────────────────────────────


class TestTestWriteResultModel:
    """验证 TestWriteResult 数据模型"""

    def test_create_with_required_fields(self):
        """创建 TestWriteResult 仅需 task_id 和 test_file_path"""
        result = TestWriteResult(
            task_id="task-001",
            test_file_path="tests/test_task_001.py",
        )
        assert result.task_id == "task-001"
        assert result.test_file_path == "tests/test_task_001.py"
        assert result.test_cases == []
        assert result.test_content == ""
        assert result.test_count == 0

    def test_create_with_all_fields(self):
        """创建 TestWriteResult 含全部字段"""
        tc1 = TestCaseInfo(
            name="test_positive", description="正向", category="positive"
        )
        tc2 = TestCaseInfo(
            name="test_negative", description="异常", category="negative"
        )
        result = TestWriteResult(
            task_id="task-001",
            test_file_path="tests/test_task_001.py",
            test_cases=[tc1, tc2],
            test_content="import pytest\n",
            test_count=2,
        )
        assert result.task_id == "task-001"
        assert len(result.test_cases) == 2
        assert result.test_count == 2

    def test_positive_count(self):
        """正向测试计数"""
        tc1 = TestCaseInfo(name="t1", category="positive")
        tc2 = TestCaseInfo(name="t2", category="positive")
        tc3 = TestCaseInfo(name="t3", category="negative")
        result = TestWriteResult(
            task_id="task-001",
            test_file_path="tests/test.py",
            test_cases=[tc1, tc2, tc3],
            test_count=3,
        )
        assert result.positive_count == 2
        assert result.negative_count == 1

    def test_edge_case_count(self):
        """边界测试计数"""
        tc = TestCaseInfo(name="t1", category="edge_case")
        result = TestWriteResult(
            task_id="task-001",
            test_file_path="tests/test.py",
            test_cases=[tc],
            test_count=1,
        )
        assert result.edge_case_count == 1

    def test_integration_count(self):
        """集成测试计数"""
        tc = TestCaseInfo(name="t1", category="integration")
        result = TestWriteResult(
            task_id="task-001",
            test_file_path="tests/test.py",
            test_cases=[tc],
            test_count=1,
        )
        assert result.integration_count == 1

    def test_test_names_property(self):
        """test_names 返回所有名称"""
        tc1 = TestCaseInfo(name="test_a")
        tc2 = TestCaseInfo(name="test_b")
        result = TestWriteResult(
            task_id="task-001",
            test_file_path="tests/test.py",
            test_cases=[tc1, tc2],
            test_count=2,
        )
        assert result.test_names == ["test_a", "test_b"]

    def test_to_text_contains_basic_info(self):
        """to_text 包含基本信息"""
        result = TestWriteResult(
            task_id="task-001",
            test_file_path="tests/test_task_001.py",
            test_cases=[
                TestCaseInfo(name="test_positive", category="positive"),
                TestCaseInfo(name="test_negative", category="negative"),
            ],
            test_count=2,
        )
        text = result.to_text()
        assert "task-001" in text
        assert "test_task_001.py" in text
        assert "test_positive" in text
        assert "test_negative" in text
        assert "正向测试" in text
        assert "异常测试" in text

    def test_task_id_required(self):
        """task_id 必填"""
        with pytest.raises(Exception):
            TestWriteResult(test_file_path="tests/test.py")

    def test_test_file_path_required(self):
        """test_file_path 必填"""
        with pytest.raises(Exception):
            TestWriteResult(task_id="task-001")

    def test_test_count_ge_zero(self):
        """test_count 不能为负"""
        with pytest.raises(Exception):
            TestWriteResult(
                task_id="task-001",
                test_file_path="tests/test.py",
                test_count=-1,
            )

    def test_created_at_auto_set(self):
        """created_at 自动设置"""
        result = TestWriteResult(
            task_id="task-001",
            test_file_path="tests/test.py",
        )
        assert result.created_at is not None
        assert isinstance(result.created_at, datetime)


# ── 3. write_tests 核心流程 ────────────────────────────────


class TestWriteTestsCore:
    """验证 write_tests 核心流程"""

    def test_returns_test_write_result(self, dev_agent, sample_task):
        """write_tests 返回 TestWriteResult"""
        result = dev_agent.write_tests(sample_task)
        assert isinstance(result, TestWriteResult)

    def test_result_task_id_matches(self, dev_agent, sample_task):
        """结果 task_id 与输入一致"""
        result = dev_agent.write_tests(sample_task)
        assert result.task_id == sample_task.id

    def test_result_test_file_path(self, dev_agent, sample_task):
        """测试文件路径格式正确"""
        result = dev_agent.write_tests(sample_task)
        assert result.test_file_path == "tests/test_task_001.py"

    def test_result_has_test_cases(self, dev_agent, sample_task):
        """结果包含测试用例"""
        result = dev_agent.write_tests(sample_task)
        assert len(result.test_cases) > 0

    def test_result_test_count_matches(self, dev_agent, sample_task):
        """test_count 与 test_cases 长度一致"""
        result = dev_agent.write_tests(sample_task)
        assert result.test_count == len(result.test_cases)

    def test_result_has_test_content(self, dev_agent, sample_task):
        """结果包含测试文件内容"""
        result = dev_agent.write_tests(sample_task)
        assert result.test_content != ""
        assert len(result.test_content) > 0

    def test_none_task_raises_value_error(self, dev_agent):
        """None 任务抛出 ValueError"""
        with pytest.raises(ValueError, match="task cannot be None"):
            dev_agent.write_tests(None)

    def test_result_created_at_set(self, dev_agent, sample_task):
        """结果 created_at 已设置"""
        result = dev_agent.write_tests(sample_task)
        assert result.created_at is not None

    def test_test_content_contains_imports(self, dev_agent, sample_task):
        """测试内容包含 import pytest"""
        result = dev_agent.write_tests(sample_task)
        assert "import pytest" in result.test_content

    def test_test_content_contains_test_functions(self, dev_agent, sample_task):
        """测试内容包含测试函数定义"""
        result = dev_agent.write_tests(sample_task)
        # 至少应包含一个 def test_ 开头的函数
        assert "def test_" in result.test_content


# ── 4. 测试用例生成（BDD 驱动）────────────────────────────


class TestTestCaseGenerationBDD:
    """验证基于 BDD 的测试用例生成"""

    def test_bdd_generates_positive_test(self, dev_agent, sample_task):
        """BDD 任务生成正向测试"""
        result = dev_agent.write_tests(sample_task)
        positive_cases = [tc for tc in result.test_cases if tc.category == "positive"]
        assert len(positive_cases) >= 1

    def test_bdd_generates_negative_test(self, dev_agent, sample_task):
        """BDD 任务生成异常测试"""
        result = dev_agent.write_tests(sample_task)
        negative_cases = [tc for tc in result.test_cases if tc.category == "negative"]
        assert len(negative_cases) >= 1

    def test_bdd_positive_test_has_description(self, dev_agent, sample_task):
        """正向测试有描述"""
        result = dev_agent.write_tests(sample_task)
        positive_cases = [tc for tc in result.test_cases if tc.category == "positive"]
        assert positive_cases[0].description != ""

    def test_bdd_test_names_start_with_test(self, dev_agent, sample_task):
        """测试函数名以 test_ 开头"""
        result = dev_agent.write_tests(sample_task)
        for tc in result.test_cases:
            assert tc.name.startswith("test_")


# ── 5. 测试用例生成（无 BDD）───────────────────────────────


class TestTestCaseGenerationNoBDD:
    """验证无 BDD 时的测试用例生成"""

    def test_no_bdd_generates_positive(self, dev_agent, task_without_bdd):
        """无 BDD 也生成正向测试"""
        result = dev_agent.write_tests(task_without_bdd)
        positive = [tc for tc in result.test_cases if tc.category == "positive"]
        assert len(positive) >= 1

    def test_no_bdd_generates_negative(self, dev_agent, task_without_bdd):
        """无 BDD 也生成异常测试"""
        result = dev_agent.write_tests(task_without_bdd)
        negative = [tc for tc in result.test_cases if tc.category == "negative"]
        assert len(negative) >= 1

    def test_no_bdd_test_names_valid(self, dev_agent, task_without_bdd):
        """无 BDD 测试函数名有效"""
        result = dev_agent.write_tests(task_without_bdd)
        for tc in result.test_cases:
            assert tc.name.startswith("test_")
            # 函数名只包含合法字符
            assert re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", tc.name)


# ── 6. 高复杂度和专项测试 ────────────────────────────────


class TestHighComplexityAndSpecialTests:
    """验证高复杂度和特定内容的测试追加"""

    def test_high_complexity_adds_edge_case(self, dev_agent, high_complexity_task):
        """高复杂度追加边界测试"""
        result = dev_agent.write_tests(high_complexity_task)
        edge_cases = [tc for tc in result.test_cases if tc.category == "edge_case"]
        assert len(edge_cases) >= 1

    def test_api_task_adds_integration(self, dev_agent):
        """API 任务追加集成测试"""
        task = Task(
            id="task-030",
            title="实现用户查询 API 接口",
            description="实现 REST API 查询接口",
            bdd=BDDSpec(
                given="数据已存在",
                when="发送查询请求",
                then="返回查询结果",
            ),
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.write_tests(task)
        integration = [tc for tc in result.test_cases if tc.category == "integration"]
        assert len(integration) >= 1

    def test_concurrent_task_adds_integration(self, dev_agent, high_complexity_task):
        """并发任务追加集成测试"""
        result = dev_agent.write_tests(high_complexity_task)
        integration = [tc for tc in result.test_cases if tc.category == "integration"]
        assert len(integration) >= 1

    def test_low_complexity_no_edge_case(self, dev_agent, task_without_bdd):
        """低复杂度无边界测试"""
        result = dev_agent.write_tests(task_without_bdd)
        edge_cases = [tc for tc in result.test_cases if tc.category == "edge_case"]
        assert len(edge_cases) == 0

    def test_high_complexity_has_more_tests(self, dev_agent, high_complexity_task, sample_task):
        """高复杂度任务生成更多测试"""
        high_result = dev_agent.write_tests(high_complexity_task)
        normal_result = dev_agent.write_tests(sample_task)
        assert high_result.test_count >= normal_result.test_count


# ── 7. 测试文件内容构建 ────────────────────────────────


class TestTestContentBuilding:
    """验证测试文件内容构建"""

    def test_content_starts_with_docstring(self, dev_agent, sample_task):
        """内容以文档字符串开头"""
        result = dev_agent.write_tests(sample_task)
        assert result.test_content.startswith('"""')

    def test_content_contains_task_id(self, dev_agent, sample_task):
        """内容包含任务 ID"""
        result = dev_agent.write_tests(sample_task)
        assert sample_task.id in result.test_content

    def test_content_contains_task_title(self, dev_agent, sample_task):
        """内容包含任务标题"""
        result = dev_agent.write_tests(sample_task)
        assert sample_task.title in result.test_content

    def test_content_contains_import_pytest(self, dev_agent, sample_task):
        """内容包含 import pytest"""
        result = dev_agent.write_tests(sample_task)
        assert "import pytest" in result.test_content

    def test_content_contains_mock_import(self, dev_agent, sample_task):
        """内容包含 from unittest.mock import"""
        result = dev_agent.write_tests(sample_task)
        assert "from unittest.mock import" in result.test_content

    def test_content_contains_fixture(self, dev_agent, sample_task):
        """内容包含 fixture 定义"""
        result = dev_agent.write_tests(sample_task)
        assert "@pytest.fixture" in result.test_content

    def test_content_bdd_has_setup_fixture(self, dev_agent, sample_task):
        """有 BDD 时内容包含 bdd_setup fixture"""
        result = dev_agent.write_tests(sample_task)
        assert "bdd_setup" in result.test_content

    def test_content_no_bdd_no_setup_fixture(self, dev_agent, task_without_bdd):
        """无 BDD 时不包含 bdd_setup fixture"""
        result = dev_agent.write_tests(task_without_bdd)
        assert "bdd_setup" not in result.test_content

    def test_content_contains_arrange_act_assert(self, dev_agent, sample_task):
        """正向测试包含 Arrange/Act/Assert 骨架"""
        result = dev_agent.write_tests(sample_task)
        content = result.test_content
        assert "Arrange" in content or "Act" in content or "Assert" in content

    def test_content_model_task_has_model_import_comment(self, dev_agent):
        """模型类任务包含 model import 注释"""
        task = Task(
            id="task-040",
            title="实现用户数据模型",
            description="创建用户模型类",
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.write_tests(task)
        assert "models" in result.test_content

    def test_content_api_task_has_api_import_comment(self, dev_agent):
        """API 任务包含 api import 注释"""
        task = Task(
            id="task-050",
            title="实现 REST API 接口",
            description="创建 API 端点",
            bdd=BDDSpec(
                given="服务运行中",
                when="发送 HTTP 请求",
                then="返回正确响应",
            ),
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.write_tests(task)
        assert "api" in result.test_content

    def test_each_test_case_appears_in_content(self, dev_agent, sample_task):
        """每个测试用例名出现在测试内容中"""
        result = dev_agent.write_tests(sample_task)
        for tc in result.test_cases:
            assert tc.name in result.test_content


# ── 8. 内部辅助方法 ──────────────────────────────────────


class TestInternalHelperMethods:
    """验证 write_tests 内部辅助方法"""

    def test_build_test_function_name_with_english(self, dev_agent):
        """_build_test_function_name 提取英文关键词"""
        name = dev_agent._build_test_function_name(
            "submit valid form", "returns success", "success"
        )
        assert "test_" in name
        assert "submit" in name
        assert "valid" in name or "form" in name

    def test_build_test_function_name_success_suffix(self, dev_agent):
        """success outcome 返回 returns_expected 后缀"""
        name = dev_agent._build_test_function_name(
            "call API", "returns data", "success"
        )
        assert "returns_expected" in name

    def test_build_test_function_name_failure_suffix(self, dev_agent):
        """failure outcome 返回 raises_error 后缀"""
        name = dev_agent._build_test_function_name(
            "call API", "raises error", "failure"
        )
        assert "raises_error" in name

    def test_build_test_function_name_chinese_fallback(self, dev_agent):
        """中文 When 使用 _extract_chinese_action"""
        name = dev_agent._build_test_function_name(
            "提交登录表单", "返回错误", "failure"
        )
        assert name.startswith("test_")

    def test_extract_action_from_title_english(self, dev_agent):
        """_extract_action_from_title 提取英文"""
        action = dev_agent._extract_action_from_title("Implement login API")
        assert "implement" in action
        assert "login" in action

    def test_extract_action_from_title_chinese(self, dev_agent):
        """_extract_action_from_title 映射中文"""
        action = dev_agent._extract_action_from_title("实现用户登录")
        assert action == "implement"

    def test_extract_action_from_title_add(self, dev_agent):
        """_extract_action_from_title 映射'添加'"""
        action = dev_agent._extract_action_from_title("添加配置项")
        assert action == "add"

    def test_extract_action_from_title_create(self, dev_agent):
        """_extract_action_from_title 映射'创建'"""
        action = dev_agent._extract_action_from_title("创建新服务")
        assert action == "create"

    def test_extract_action_from_title_fallback(self, dev_agent):
        """_extract_action_from_title 无匹配回退"""
        action = dev_agent._extract_action_from_title("未知操作")
        assert action == "action"

    def test_extract_chinese_action_submit(self, dev_agent):
        """_extract_chinese_action 识别'提交'"""
        action = dev_agent._extract_chinese_action("提交表单")
        assert action == "submit"

    def test_extract_chinese_action_execute(self, dev_agent):
        """_extract_chinese_action 识别'执行'"""
        action = dev_agent._extract_chinese_action("执行命令")
        assert action == "execute"

    def test_extract_chinese_action_fallback(self, dev_agent):
        """_extract_chinese_action 无匹配回退"""
        action = dev_agent._extract_chinese_action("随意操作")
        assert action == "action"

    def test_build_test_params_with_fixture(self, dev_agent, sample_task):
        """_build_test_params 包含 task fixture"""
        tc = TestCaseInfo(name="test_something", category="positive")
        params = dev_agent._build_test_params(tc, sample_task)
        assert "task_001_fixture" in params

    def test_build_test_params_positive_with_bdd_setup(self, dev_agent, sample_task):
        """正向测试有 BDD 时包含 bdd_setup"""
        tc = TestCaseInfo(name="test_something", category="positive")
        params = dev_agent._build_test_params(tc, sample_task)
        assert "bdd_setup" in params

    def test_build_test_params_negative_no_bdd_setup(self, dev_agent, sample_task):
        """异常测试不包含 bdd_setup"""
        tc = TestCaseInfo(name="test_something", category="negative")
        params = dev_agent._build_test_params(tc, sample_task)
        assert "bdd_setup" not in params

    def test_generate_test_cases_bdd_positive_negative(self, dev_agent, sample_task):
        """_generate_test_cases BDD 任务至少有正向和异常"""
        cases = dev_agent._generate_test_cases(sample_task)
        categories = [tc.category for tc in cases]
        assert "positive" in categories
        assert "negative" in categories

    def test_generate_test_cases_no_bdd(self, dev_agent, task_without_bdd):
        """_generate_test_cases 无 BDD 也有正向和异常"""
        cases = dev_agent._generate_test_cases(task_without_bdd)
        categories = [tc.category for tc in cases]
        assert "positive" in categories
        assert "negative" in categories


# ── 9. Prompt 集成 ──────────────────────────────────────


class TestPromptIntegration:
    """验证 write_tests 与 prompt 的集成"""

    def test_get_implement_prompt_references_tests(
        self, dev_agent_with_mock_harness, sample_task
    ):
        """get_implement_prompt 引用 TDD 流程"""
        prompt = dev_agent_with_mock_harness.get_implement_prompt(sample_task)
        assert "TDD" in prompt or "测试" in prompt or "test" in prompt.lower()

    def test_write_tests_result_usable_in_implement_prompt(
        self, dev_agent, sample_task
    ):
        """write_tests 结果可用于构建 implement prompt"""
        test_result = dev_agent.write_tests(sample_task)
        assert test_result.test_content is not None
        assert test_result.test_count > 0
        # 可以将 test_result.to_text() 注入到 implement prompt
        text = test_result.to_text()
        assert sample_task.id in text


# ── 10. 边界条件与异常处理 ──────────────────────────────


class TestBoundaryConditions:
    """验证边界条件和异常处理"""

    def test_task_with_empty_bdd_fields(self, dev_agent):
        """BDD 字段为空字符串时的处理"""
        task = Task(
            id="task-060",
            title="配置任务",
            description="配置管理",
            bdd=BDDSpec(given="", when="", then=""),
            priority=TaskPriority.LOW,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.write_tests(task)
        assert isinstance(result, TestWriteResult)
        assert result.test_count > 0

    def test_multiple_write_tests_independent(self, dev_agent, sample_task, task_without_bdd):
        """多次 write_tests 调用互不影响"""
        result1 = dev_agent.write_tests(sample_task)
        result2 = dev_agent.write_tests(task_without_bdd)
        assert result1.task_id != result2.task_id
        assert result1.test_file_path != result2.test_file_path

    def test_task_with_many_dependencies(self, dev_agent):
        """多依赖任务不崩溃"""
        task = Task(
            id="task-070",
            title="集成测试模块",
            description="集成多个模块的测试",
            dependencies=["task-001", "task-002", "task-003"],
            priority=TaskPriority.HIGH,
            estimated_complexity=TaskComplexity.HIGH,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.write_tests(task)
        assert isinstance(result, TestWriteResult)
        assert result.test_count > 0

    def test_task_with_special_chars_in_title(self, dev_agent):
        """标题含特殊字符不崩溃"""
        task = Task(
            id="task-080",
            title="处理 <特殊> 字符 & 符号",
            description="处理特殊字符输入",
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.write_tests(task)
        assert isinstance(result, TestWriteResult)

    def test_write_tests_content_is_valid_python(self, dev_agent, sample_task):
        """生成的测试内容是有效 Python 语法"""
        result = dev_agent.write_tests(sample_task)
        # 尝试编译检查语法
        compile(result.test_content, result.test_file_path, "exec")

    def test_test_names_are_unique(self, dev_agent, high_complexity_task):
        """所有测试函数名唯一"""
        result = dev_agent.write_tests(high_complexity_task)
        names = [tc.name for tc in result.test_cases]
        assert len(names) == len(set(names))

    def test_test_file_path_follows_convention(self, dev_agent):
        """测试文件路径遵循约定格式"""
        task = Task(
            id="task-099",
            title="测试路径",
            description="验证路径",
            priority=TaskPriority.LOW,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.write_tests(task)
        assert result.test_file_path == "tests/test_task_099.py"

    def test_result_serialization(self, dev_agent, sample_task):
        """TestWriteResult 可序列化"""
        result = dev_agent.write_tests(sample_task)
        # Pydantic 模型可转 dict
        data = result.model_dump()
        assert "task_id" in data
        assert "test_cases" in data
        assert "test_content" in data
        # 可转 JSON
        json_str = result.model_dump_json()
        assert json_str is not None

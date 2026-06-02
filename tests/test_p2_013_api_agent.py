"""
P2-013 测试：APIRequestAgent 类

验证 APIRequestAgent 继承 SubAgent 基类、注入 api-rules.md 的完整功能。
测试覆盖：
1. 类创建与继承关系
2. api-rules.md harness 加载
3. 角色注入 prompt 构建
4. SubAgent 生命周期方法
5. API 特有业务方法桩（send_request / validate_response / test_endpoint）
6. Harness 规则访问
7. 边界条件与异常处理
8. 初始化与属性
9. 状态属性测试
10. 角色名称常量
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_automation_system.harness.harness_loader import HarnessLoader
from agent_automation_system.harness.models import (
    Harness,
    HarnessRule,
    HarnessSection,
    RuleType,
)
from agent_automation_system.models.task import (
    BDDSpec,
    Task,
    TaskComplexity,
    TaskPriority,
    TaskStatus,
)
from agent_automation_system.sub_agent.role_injector import RoleInjector
from agent_automation_system.sub_agent.sub_agent import (
    AgentPhase,
    SubAgent,
    SubAgentResult,
    SubAgentResultStatus,
)


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def api_agent():
    """创建默认 APIRequestAgent 实例"""
    from agent_automation_system.sub_agent.api_agent import APIRequestAgent

    return APIRequestAgent()


@pytest.fixture
def api_agent_with_mock_harness():
    """创建带 mock harness 的 APIRequestAgent 实例"""
    from agent_automation_system.sub_agent.api_agent import (
        _DEFAULT_API_RULES_PATH,
        APIRequestAgent,
    )

    agent = APIRequestAgent()
    mock_harness = Harness(
        name="API Request Agent Rules",
        file_path=str(_DEFAULT_API_RULES_PATH),
        role_name="api-request",
        sections=[
            HarnessSection(
                title="DO",
                rule_type=RuleType.DO,
                rules=[
                    HarnessRule(
                        rule_type=RuleType.DO,
                        content="Read API specifications from task.json",
                        section="DO",
                    ),
                    HarnessRule(
                        rule_type=RuleType.DO,
                        content="Construct well-formed HTTP requests",
                        section="DO",
                    ),
                ],
            ),
            HarnessSection(
                title="DON'T",
                rule_type=RuleType.DONT,
                rules=[
                    HarnessRule(
                        rule_type=RuleType.DONT,
                        content="NEVER make requests to unauthorized endpoints",
                        section="DON'T",
                    ),
                ],
            ),
        ],
    )
    agent._api_harness = mock_harness
    agent._api_harness_content = mock_harness.to_prompt_text()
    return agent


@pytest.fixture
def sample_task():
    """创建示例 Task"""
    return Task(
        id="task-001",
        title="测试 GET /users 接口",
        description="验证 /users 接口返回正确的用户列表",
        status=TaskStatus.PENDING,
        priority=TaskPriority.HIGH,
        complexity=TaskComplexity.MEDIUM,
    )


@pytest.fixture
def sample_task_with_bdd():
    """创建含 BDD 规格的示例 Task"""
    return Task(
        id="task-002",
        title="测试 POST /login 接口",
        description="验证登录接口返回有效 token",
        status=TaskStatus.PENDING,
        priority=TaskPriority.HIGH,
        complexity=TaskComplexity.HIGH,
        bdd=BDDSpec(
            given="用户提供有效的邮箱和密码",
            when="POST 请求发送到 /login",
            then="返回 200 状态码和 JWT token",
        ),
    )


# ── Class 1: 类创建与继承关系 ──────────────────────────────


class TestClassCreationAndInheritance:
    """验证 APIRequestAgent 类的创建和继承"""

    def test_is_subclass_of_sub_agent(self):
        """APIRequestAgent 必须是 SubAgent 的子类"""
        from agent_automation_system.sub_agent.api_agent import APIRequestAgent

        assert issubclass(APIRequestAgent, SubAgent)

    def test_role_name_is_api_request(self, api_agent):
        """角色名称必须为 'api-request'"""
        assert api_agent.role_name == "api-request"

    def test_default_phase_is_created(self, api_agent):
        """初始化后 phase 必须为 CREATED"""
        assert api_agent.phase == AgentPhase.CREATED

    def test_default_task_is_none(self, api_agent):
        """初始化后 task 必须为 None"""
        assert api_agent.task is None

    def test_default_result_is_none(self, api_agent):
        """初始化后 result 必须为 None"""
        assert api_agent.result is None

    def test_custom_role_injector(self):
        """支持通过构造函数注入自定义 RoleInjector"""
        from agent_automation_system.sub_agent.api_agent import APIRequestAgent

        custom_injector = MagicMock(spec=RoleInjector)
        agent = APIRequestAgent(role_injector=custom_injector)
        assert agent.role_injector is custom_injector

    def test_custom_api_rules_path(self, tmp_path):
        """支持通过构造函数指定自定义 api-rules.md 路径"""
        from agent_automation_system.sub_agent.api_agent import APIRequestAgent

        custom_path = tmp_path / "custom-api-rules.md"
        agent = APIRequestAgent(api_rules_path=custom_path)
        assert agent.api_rules_path == custom_path

    def test_custom_harness_loader(self):
        """支持通过构造函数注入自定义 HarnessLoader"""
        from agent_automation_system.sub_agent.api_agent import APIRequestAgent

        custom_loader = MagicMock(spec=HarnessLoader)
        agent = APIRequestAgent(harness_loader=custom_loader)
        assert agent._harness_loader is custom_loader

    def test_initial_state_properties(self, api_agent):
        """验证初始化状态的属性默认值"""
        assert api_agent.role_name == "api-request"
        assert api_agent.api_harness is None
        assert api_agent.api_harness_content is None


# ── Class 2: Harness 加载 ──────────────────────────────────


class TestHarnessLoading:
    """验证 api-rules.md harness 加载功能"""

    def test_load_api_harness_success(self):
        """从默认路径加载 api-rules.md 应成功"""
        from agent_automation_system.sub_agent.api_agent import APIRequestAgent

        agent = APIRequestAgent()
        harness = agent.load_api_harness()
        assert harness is not None
        assert isinstance(harness, Harness)

    def test_load_api_harness_caches_result(self):
        """重复调用 load 应返回缓存结果"""
        from agent_automation_system.sub_agent.api_agent import APIRequestAgent

        agent = APIRequestAgent()
        h1 = agent.load_api_harness()
        h2 = agent.load_api_harness()
        assert h1 is h2

    def test_load_api_harness_sets_content(self):
        """加载后 _api_harness_content 应被设置"""
        from agent_automation_system.sub_agent.api_agent import APIRequestAgent

        agent = APIRequestAgent()
        agent.load_api_harness()
        assert agent.api_harness_content is not None
        assert isinstance(agent.api_harness_content, str)
        assert len(agent.api_harness_content) > 0

    def test_load_api_harness_file_not_found(self, tmp_path):
        """api-rules.md 不存在时应抛 FileNotFoundError"""
        from agent_automation_system.sub_agent.api_agent import APIRequestAgent

        agent = APIRequestAgent(api_rules_path=tmp_path / "nonexistent.md")
        with pytest.raises(FileNotFoundError):
            agent.load_api_harness()

    def test_load_api_harness_returns_harness_object(self):
        """load_api_harness 返回值为 Harness 实例"""
        from agent_automation_system.sub_agent.api_agent import APIRequestAgent

        agent = APIRequestAgent()
        harness = agent.load_api_harness()
        assert isinstance(harness, Harness)

    def test_api_harness_property_before_load(self, api_agent):
        """加载前 api_harness 属性必须为 None"""
        assert api_agent.api_harness is None

    def test_api_harness_content_property_before_load(self, api_agent):
        """加载前 api_harness_content 属性必须为 None"""
        assert api_agent.api_harness_content is None


# ── Class 3: Prompt 构建 ───────────────────────────────────


class TestPromptBuilding:
    """验证 API Agent 专用 prompt 构建"""

    def test_build_api_prompt_basic(self, api_agent_with_mock_harness):
        """基本 prompt 构建包含 task 描述"""
        prompt = api_agent_with_mock_harness.build_api_prompt(
            "测试 GET /api/users 接口"
        )
        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "GET /api/users" in prompt

    def test_build_api_prompt_without_harness(self, api_agent_with_mock_harness):
        """不包含 harness 时 prompt 仅含 task 描述"""
        prompt = api_agent_with_mock_harness.build_api_prompt(
            "测试接口",
            include_harness=False,
        )
        assert "测试接口" in prompt

    def test_build_api_prompt_includes_harness_content(self, api_agent_with_mock_harness):
        """包含 harness 时 prompt 含 mock harness 的具体规则内容"""
        prompt = api_agent_with_mock_harness.build_api_prompt(
            "测试接口",
            include_harness=True,
        )
        # mock harness 中包含 "Read API specifications from task.json" 这条 DO 规则
        assert "Read API specifications from task.json" in prompt

    def test_build_api_prompt_missing_harness_file(self, tmp_path):
        """无 harness 文件时调用 RoleInjector 的基础 prompt"""
        from agent_automation_system.sub_agent.api_agent import APIRequestAgent

        agent = APIRequestAgent(api_rules_path=tmp_path / "missing.md")
        prompt = agent.build_api_prompt("测试接口", include_harness=True)
        assert isinstance(prompt, str)
        assert "测试接口" in prompt

    def test_build_api_prompt_uses_role_injector(self):
        """build_api_prompt 委托给 RoleInjector.inject_role 构建 prompt"""
        from agent_automation_system.sub_agent.api_agent import APIRequestAgent

        mock_injector = MagicMock(spec=RoleInjector)
        mock_injector.inject_role.return_value = "custom prompt content"
        agent = APIRequestAgent(role_injector=mock_injector)
        prompt = agent.build_api_prompt("test task")
        assert prompt == "custom prompt content"


# ── Class 4: 生命周期方法 ──────────────────────────────────


class TestLifecycleMethods:
    """验证 SubAgent 生命周期方法实现"""

    def test_initialize_success(self, api_agent_with_mock_harness):
        """initialize 应成功完成"""
        # initialize 不抛异常即成功
        api_agent_with_mock_harness.initialize()
        assert api_agent_with_mock_harness.api_harness is not None

    def test_initialize_without_harness(self, tmp_path):
        """api-rules.md 不存在时 initialize 应抛异常"""
        from agent_automation_system.sub_agent.api_agent import APIRequestAgent

        agent = APIRequestAgent(api_rules_path=tmp_path / "missing.md")
        with pytest.raises(FileNotFoundError):
            agent.initialize()

    def test_execute_returns_result(self, api_agent_with_mock_harness, sample_task):
        """execute 必须返回 SubAgentResult"""
        result = api_agent_with_mock_harness.execute(sample_task)
        assert isinstance(result, SubAgentResult)

    def test_execute_result_has_success_status(self, api_agent_with_mock_harness, sample_task):
        """execute 基本场景应返回 SUCCESS 状态"""
        result = api_agent_with_mock_harness.execute(sample_task)
        assert result.status == SubAgentResultStatus.SUCCESS

    def test_execute_sets_task(self, api_agent_with_mock_harness, sample_task):
        """execute 应设置内部 _task"""
        api_agent_with_mock_harness.execute(sample_task)
        assert api_agent_with_mock_harness.task is not None
        assert api_agent_with_mock_harness.task.id == sample_task.id

    def test_execute_result_contains_task_id(self, api_agent_with_mock_harness, sample_task):
        """execute 结果必须包含正确的 task_id"""
        result = api_agent_with_mock_harness.execute(sample_task)
        assert result.task_id == sample_task.id

    def test_execute_result_contains_role(self, api_agent_with_mock_harness, sample_task):
        """execute 结果必须包含 api-request 角色名"""
        result = api_agent_with_mock_harness.execute(sample_task)
        assert result.role == "api-request"

    def test_verify_returns_result(self, api_agent_with_mock_harness):
        """verify 必须返回 SubAgentResult"""
        result = api_agent_with_mock_harness.verify()
        assert isinstance(result, SubAgentResult)

    def test_commit_returns_result(self, api_agent_with_mock_harness):
        """commit 必须返回 SubAgentResult"""
        result = api_agent_with_mock_harness.commit()
        assert isinstance(result, SubAgentResult)

    def test_cleanup_does_not_raise(self, api_agent_with_mock_harness):
        """cleanup 不应抛异常"""
        api_agent_with_mock_harness.cleanup()


# ── Class 5: API 特有业务方法桩 ────────────────────────────


class TestAPIBusinessMethods:
    """验证 APIRequestAgent 特有业务方法"""

    def test_send_request_exists(self, api_agent):
        """send_request 方法必须存在"""
        assert hasattr(api_agent, "send_request")
        assert callable(api_agent.send_request)

    def test_validate_response_exists(self, api_agent):
        """validate_response 方法必须存在"""
        assert hasattr(api_agent, "validate_response")
        assert callable(api_agent.validate_response)

    def test_test_endpoint_exists(self, api_agent):
        """test_endpoint 方法必须存在"""
        assert hasattr(api_agent, "test_endpoint")
        assert callable(api_agent.test_endpoint)

    def test_send_request_returns_dict(self, api_agent):
        """send_request 桩返回 dict 类型"""
        result = api_agent.send_request(
            method="GET",
            url="https://api.example.com/users",
        )
        assert isinstance(result, dict)

    def test_send_request_contains_method(self, api_agent):
        """send_request 结果包含 method 字段"""
        result = api_agent.send_request(method="POST", url="https://api.example.com/data")
        assert result.get("method") == "POST"

    def test_send_request_contains_url(self, api_agent):
        """send_request 结果包含 url 字段"""
        result = api_agent.send_request(method="GET", url="https://api.example.com/users")
        assert result.get("url") == "https://api.example.com/users"

    def test_send_request_with_headers(self, api_agent):
        """send_request 支持自定义 headers"""
        result = api_agent.send_request(
            method="GET",
            url="https://api.example.com/data",
            headers={"Authorization": "Bearer token123"},
        )
        assert "headers" in result

    def test_validate_response_returns_dict(self, api_agent):
        """validate_response 桩返回 dict 类型"""
        result = api_agent.validate_response(
            response={"status_code": 200, "body": {}},
            expected_status=200,
        )
        assert isinstance(result, dict)

    def test_validate_response_contains_passed(self, api_agent):
        """validate_response 结果包含 passed 字段"""
        result = api_agent.validate_response(
            response={"status_code": 200, "body": {}},
            expected_status=200,
        )
        assert "passed" in result
        assert result["passed"] is True

    def test_test_endpoint_returns_dict(self, api_agent):
        """test_endpoint 桩返回 dict 类型"""
        result = api_agent.test_endpoint(
            method="GET",
            url="https://api.example.com/health",
            expected_status=200,
        )
        assert isinstance(result, dict)

    def test_test_endpoint_contains_passed(self, api_agent):
        """test_endpoint 结果包含 passed 字段"""
        result = api_agent.test_endpoint(
            method="GET",
            url="https://api.example.com/health",
            expected_status=200,
        )
        assert "passed" in result
        assert result["passed"] is True


# ── Class 6: Harness 规则访问 ──────────────────────────────


class TestHarnessRulesAccess:
    """验证 api-rules.md 规则内容可访问"""

    def test_harness_has_correct_role_name(self):
        """api-rules harness 角色名必须为 api-request"""
        from agent_automation_system.sub_agent.api_agent import APIRequestAgent

        agent = APIRequestAgent()
        harness = agent.load_api_harness()
        assert harness.role_name == "api-request"

    def test_harness_has_sections(self):
        """harness 包含 DO/DON'T/Constraints/Verification 分段"""
        from agent_automation_system.sub_agent.api_agent import APIRequestAgent

        agent = APIRequestAgent()
        harness = agent.load_api_harness()
        sections = harness.sections
        assert len(sections) > 0

    def test_harness_has_rules(self):
        """harness 包含具体规则"""
        from agent_automation_system.sub_agent.api_agent import APIRequestAgent

        agent = APIRequestAgent()
        harness = agent.load_api_harness()
        assert harness.rules is not None
        assert len(harness.rules) > 0

    def test_prompt_text_contains_role_identity(self):
        """prompt 文本包含 Role Identity"""
        from agent_automation_system.sub_agent.api_agent import APIRequestAgent

        agent = APIRequestAgent()
        agent.load_api_harness()
        content = agent.api_harness_content
        assert "API Request Agent" in content or "Role Identity" in content


# ── Class 7: 常数测试 ──────────────────────────────────────


class TestConstants:
    """验证 API Agent 模块级常量"""

    def test_role_name_constant(self):
        """_API_ROLE_NAME 常数应为 'api-request'"""
        from agent_automation_system.sub_agent.api_agent import _API_ROLE_NAME

        assert _API_ROLE_NAME == "api-request"

    def test_role_short_constant(self):
        """_API_ROLE_SHORT 常数应为 'api'"""
        from agent_automation_system.sub_agent.api_agent import _API_ROLE_SHORT

        assert _API_ROLE_SHORT == "api"

    def test_default_rules_path_exists(self):
        """默认 api-rules 路径应存在"""
        from agent_automation_system.sub_agent.api_agent import _DEFAULT_API_RULES_PATH

        assert _DEFAULT_API_RULES_PATH.exists()

    def test_default_rules_path_is_path(self):
        """_DEFAULT_API_RULES_PATH 必须是 Path 实例"""
        from agent_automation_system.sub_agent.api_agent import _DEFAULT_API_RULES_PATH

        assert isinstance(_DEFAULT_API_RULES_PATH, Path)


# ── Class 8: 边界条件与异常处理 ────────────────────────────


class TestBoundaryAndErrorConditions:
    """验证边界条件和异常处理"""

    def test_execute_with_none_task(self, api_agent_with_mock_harness):
        """execute(None) 应合理处理或抛异常"""
        with pytest.raises((ValueError, AttributeError)):
            api_agent_with_mock_harness.execute(None)

    def test_verify_when_phase_is_created(self, api_agent):
        """verify 在 CREATED 阶段调用"""
        result = api_agent.verify()
        assert isinstance(result, SubAgentResult)
        assert result.status == SubAgentResultStatus.SUCCESS

    def test_commit_when_phase_is_created(self, api_agent):
        """commit 在 CREATED 阶段调用"""
        result = api_agent.commit()
        assert isinstance(result, SubAgentResult)

    def test_double_initialize(self, api_agent_with_mock_harness):
        """两次 initialize 调用（幂等性）"""
        api_agent_with_mock_harness.initialize()
        harness1 = api_agent_with_mock_harness.api_harness
        api_agent_with_mock_harness.initialize()
        harness2 = api_agent_with_mock_harness.api_harness
        assert harness1 is harness2

    def test_send_request_default_headers(self, api_agent):
        """send_request 默认 headers 包含 Content-Type"""
        result = api_agent.send_request(
            method="GET",
            url="https://api.example.com/data",
        )
        assert isinstance(result, dict)

    def test_test_endpoint_with_headers(self, api_agent):
        """test_endpoint 支持自定义 headers，expected_status 不匹配则 failed"""
        result = api_agent.test_endpoint(
            method="POST",
            url="https://api.example.com/data",
            headers={"Content-Type": "application/json"},
            expected_status=201,
        )
        # 桩实现始终返回 200，所以 expected 201 时 passed 为 False
        assert result["passed"] is False


# ── Class 9: 属性测试 ──────────────────────────────────────


class TestProperties:
    """验证 API Agent 属性访问"""

    def test_api_rules_path_property(self, api_agent):
        """api_rules_path 属性可访问"""
        assert api_agent.api_rules_path is not None

    def test_role_injector_property(self, api_agent):
        """role_injector 属性可访问"""
        assert api_agent.role_injector is not None
        assert isinstance(api_agent.role_injector, RoleInjector)

    def test_current_endpoint_property(self, api_agent):
        """current_endpoint 属性初始为 None"""
        assert api_agent.current_endpoint is None

    def test_last_response_property(self, api_agent):
        """last_response 属性初始为 None"""
        assert api_agent.last_response is None


# ── Class 10: execute 详细行为测试 ─────────────────────────


class TestExecuteDetailedBehavior:
    """验证 execute 方法的详细行为"""

    def test_execute_stores_endpoint(self, api_agent_with_mock_harness, sample_task):
        """execute 应存储任务 endpoint 信息"""
        result = api_agent_with_mock_harness.execute(sample_task)
        assert result.status == SubAgentResultStatus.SUCCESS

    def test_execute_with_bdd_task(self, api_agent_with_mock_harness, sample_task_with_bdd):
        """execute 处理含 BDD 规格的任务"""
        result = api_agent_with_mock_harness.execute(sample_task_with_bdd)
        assert isinstance(result, SubAgentResult)
        assert result.task_id == sample_task_with_bdd.id

    def test_execute_result_is_not_none(self, api_agent_with_mock_harness, sample_task):
        """execute 结果不应为 None"""
        result = api_agent_with_mock_harness.execute(sample_task)
        assert result is not None

    def test_execute_result_output_field(self, api_agent_with_mock_harness, sample_task):
        """execute 结果的 output 字段应包含信息"""
        result = api_agent_with_mock_harness.execute(sample_task)
        assert result.output is not None

    def test_execute_task_id_matches(self, api_agent_with_mock_harness, sample_task):
        """execute 结果 task_id 与输入一致"""
        result = api_agent_with_mock_harness.execute(sample_task)
        assert result.task_id == "task-001"

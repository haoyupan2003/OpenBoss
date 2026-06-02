"""
P2-008 测试：SeniorDeveloperAgent 类

验证 SeniorDeveloperAgent 继承 SubAgent 基类、注入 dev-rules.md 的完整功能。
测试覆盖：
1. 类创建与继承关系
2. dev-rules.md harness 加载
3. 角色注入 prompt 构建
4. SubAgent 生命周期方法
5. Dev 特有业务方法桩
6. Harness 规则访问
7. 边界条件与异常处理
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
from agent_automation_system.models.dev_analysis import TaskAnalysisResult
from agent_automation_system.models.dev_implement import ImplementResult, TestRunResult
from agent_automation_system.models.task import BDDSpec, Task, TaskPriority, TaskComplexity, TaskStatus
from agent_automation_system.models.test_write import TestWriteResult
from agent_automation_system.sub_agent.dev_agent import (
    SeniorDeveloperAgent,
    _COMMIT_MESSAGE_FORMAT,
    _DEFAULT_DEV_RULES_PATH,
    _DEFAULT_MAX_IMPLEMENTATION_MINUTES,
    _DEV_ROLE_NAME,
    _DEV_ROLE_SHORT,
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
def dev_agent():
    """创建默认 SeniorDeveloperAgent 实例"""
    return SeniorDeveloperAgent()


@pytest.fixture
def dev_agent_with_mock_harness():
    """创建带 mock harness 的 SeniorDeveloperAgent 实例"""
    agent = SeniorDeveloperAgent()
    mock_harness = Harness(
        name="Senior Developer Agent Rules",
        file_path=str(_DEFAULT_DEV_RULES_PATH),
        role_name="senior-developer",
        sections=[
            HarnessSection(
                title="DO",
                rule_type=RuleType.DO,
                rules=[
                    HarnessRule(
                        rule_type=RuleType.DO,
                        content="Read task description and acceptance criteria from task.json before writing any code",
                        section="DO",
                    ),
                    HarnessRule(
                        rule_type=RuleType.DO,
                        content="Write test cases first following TDD methodology",
                        section="DO",
                    ),
                    HarnessRule(
                        rule_type=RuleType.DO,
                        content="Implement only what the task requires — no gold-plating",
                        section="DO",
                    ),
                ],
                raw_content="- Read task description\n- Write test cases first\n- Implement only what is required",
            ),
            HarnessSection(
                title="DON'T",
                rule_type=RuleType.DONT,
                rules=[
                    HarnessRule(
                        rule_type=RuleType.DONT,
                        content="NEVER implement features beyond the task specification",
                        section="DON'T",
                    ),
                    HarnessRule(
                        rule_type=RuleType.DONT,
                        content="NEVER skip writing tests before implementation",
                        section="DON'T",
                    ),
                ],
                raw_content="- NEVER implement features beyond specification\n- NEVER skip writing tests",
            ),
            HarnessSection(
                title="Constraints",
                rule_type=RuleType.CONSTRAINT,
                rules=[
                    HarnessRule(
                        rule_type=RuleType.CONSTRAINT,
                        content="ALWAYS git commit with format: [task-{id}] senior-developer: {description}",
                        section="Constraints",
                    ),
                    HarnessRule(
                        rule_type=RuleType.CONSTRAINT,
                        content="Max implementation time per task: 30 minutes",
                        section="Constraints",
                    ),
                ],
                raw_content="- ALWAYS git commit with format\n- Max implementation time 30 minutes",
            ),
            HarnessSection(
                title="Verification",
                rule_type=RuleType.VERIFICATION,
                rules=[
                    HarnessRule(
                        rule_type=RuleType.VERIFICATION,
                        content="Test script must pass before marking task as completed",
                        section="Verification",
                    ),
                ],
                raw_content="- Test script must pass before marking completed",
            ),
        ],
    )
    agent._dev_harness = mock_harness
    agent._dev_harness_content = mock_harness.to_prompt_text()
    return agent


@pytest.fixture
def sample_task():
    """创建示例 Task"""
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


# ── 1. 类创建与继承关系 ──────────────────────────────────


class TestClassCreationAndInheritance:
    """验证 SeniorDeveloperAgent 类的基本创建和继承关系"""

    def test_is_subclass_of_sub_agent(self):
        """SeniorDeveloperAgent 应继承 SubAgent"""
        assert issubclass(SeniorDeveloperAgent, SubAgent)

    def test_role_name_is_senior_developer(self, dev_agent):
        """角色名称应为 senior-developer"""
        assert dev_agent.role_name == "senior-developer"

    def test_default_phase_is_created(self, dev_agent):
        """初始阶段应为 CREATED"""
        assert dev_agent.phase == AgentPhase.CREATED

    def test_default_task_is_none(self, dev_agent):
        """初始任务应为 None"""
        assert dev_agent.task is None

    def test_default_result_is_none(self, dev_agent):
        """初始结果应为 None"""
        assert dev_agent.result is None

    def test_custom_role_injector(self):
        """可以注入自定义 RoleInjector"""
        mock_injector = MagicMock(spec=RoleInjector)
        mock_injector.inject_role.return_value = "mock prompt"
        agent = SeniorDeveloperAgent(role_injector=mock_injector)
        assert agent.role_injector is mock_injector

    def test_custom_dev_rules_path(self, tmp_path):
        """可以指定自定义 dev-rules 路径"""
        custom_path = tmp_path / "custom-dev-rules.md"
        custom_path.write_text("# Custom Dev Rules\n## DO\n- Rule 1")
        agent = SeniorDeveloperAgent(dev_rules_path=custom_path)
        assert agent.dev_rules_path == custom_path

    def test_custom_harness_loader(self):
        """可以注入自定义 HarnessLoader"""
        mock_loader = MagicMock(spec=HarnessLoader)
        agent = SeniorDeveloperAgent(harness_loader=mock_loader)
        assert agent._harness_loader is mock_loader

    def test_initial_state_properties(self, dev_agent):
        """初始工作状态应为 None"""
        assert dev_agent.current_task_description is None
        assert dev_agent.implementation_plan is None
        assert dev_agent.test_results is None
        assert dev_agent.commit_message is None


# ── 2. Harness 加载 ──────────────────────────────────────


class TestHarnessLoading:
    """验证 dev-rules.md harness 加载功能"""

    def test_load_dev_harness_success(self):
        """成功加载 dev-rules.md"""
        agent = SeniorDeveloperAgent()
        harness = agent.load_dev_harness()
        assert harness is not None
        assert isinstance(harness, Harness)

    def test_load_dev_harness_caches_result(self):
        """重复加载返回缓存结果"""
        agent = SeniorDeveloperAgent()
        harness1 = agent.load_dev_harness()
        harness2 = agent.load_dev_harness()
        assert harness1 is harness2

    def test_load_dev_harness_sets_content(self):
        """加载后设置 harness_content"""
        agent = SeniorDeveloperAgent()
        agent.load_dev_harness()
        assert agent.dev_harness_content is not None
        assert isinstance(agent.dev_harness_content, str)
        assert len(agent.dev_harness_content) > 0

    def test_load_dev_harness_file_not_found(self, tmp_path):
        """文件不存在时抛出 FileNotFoundError"""
        agent = SeniorDeveloperAgent(
            dev_rules_path=tmp_path / "nonexistent.md"
        )
        with pytest.raises(FileNotFoundError, match="dev-rules.md not found"):
            agent.load_dev_harness()

    def test_load_dev_harness_returns_harness_object(self):
        """返回 Harness 对象包含正确的段落数"""
        agent = SeniorDeveloperAgent()
        harness = agent.load_dev_harness()
        assert len(harness.sections) > 0
        assert len(harness.rules) > 0

    def test_dev_harness_property_before_load(self, dev_agent):
        """加载前 dev_harness 属性为 None"""
        assert dev_agent.dev_harness is None

    def test_dev_harness_content_property_before_load(self, dev_agent):
        """加载前 dev_harness_content 属性为 None"""
        assert dev_agent.dev_harness_content is None


# ── 3. 角色注入 Prompt 构建 ────────────────────────────────


class TestPromptBuilding:
    """验证 Dev Agent 专用的 prompt 构建"""

    def test_build_dev_prompt_basic(self, dev_agent_with_mock_harness):
        """基本 prompt 构建包含角色身份和任务描述"""
        prompt = dev_agent_with_mock_harness.build_dev_prompt(
            "实现登录功能"
        )
        # RoleInjector 使用中文模板："你是 Senior Developer Agent（高级开发者）"
        assert "Senior Developer" in prompt or "TDD" in prompt or "实现登录功能" in prompt
        assert "实现登录功能" in prompt

    def test_build_dev_prompt_without_harness(self, dev_agent_with_mock_harness):
        """不含 harness 时只包含角色和任务"""
        prompt = dev_agent_with_mock_harness.build_dev_prompt(
            "实现登录功能", include_harness=False
        )
        # RoleInjector 使用中文角色模板
        assert "Senior Developer" in prompt or "开发者" in prompt
        assert "实现登录功能" in prompt

    def test_build_dev_prompt_includes_harness_content(self, dev_agent_with_mock_harness):
        """含 harness 时 prompt 包含约束规则"""
        prompt = dev_agent_with_mock_harness.build_dev_prompt(
            "实现登录功能"
        )
        # 应包含 harness 内容
        assert "DO" in prompt or "TDD" in prompt or "test" in prompt.lower()

    def test_build_dev_prompt_missing_harness_file(self, tmp_path):
        """harness 文件不存在时构建 prompt 不崩溃"""
        agent = SeniorDeveloperAgent(
            dev_rules_path=tmp_path / "nonexistent.md"
        )
        prompt = agent.build_dev_prompt("实现功能")
        # RoleInjector 使用中文角色模板
        assert "Senior Developer" in prompt or "开发者" in prompt
        assert "实现功能" in prompt

    def test_build_dev_prompt_uses_role_injector(self):
        """prompt 构建使用 RoleInjector"""
        mock_injector = MagicMock(spec=RoleInjector)
        mock_injector.inject_role.return_value = "injected prompt"
        agent = SeniorDeveloperAgent(role_injector=mock_injector)
        agent._dev_harness_content = "test harness"
        prompt = agent.build_dev_prompt("test task")
        mock_injector.inject_role.assert_called_once_with(
            role_name=_DEV_ROLE_NAME,
            task_description="test task",
            harness_content="test harness",
        )
        assert prompt == "injected prompt"


# ── 4. 生命周期方法 ──────────────────────────────────────


class TestLifecycleMethods:
    """验证 SubAgent 生命周期方法"""

    def test_initialize_success(self, dev_agent_with_mock_harness):
        """initialize 不抛异常"""
        dev_agent_with_mock_harness.initialize()

    def test_initialize_without_harness(self, tmp_path):
        """harness 文件不存在时 initialize 不崩溃"""
        agent = SeniorDeveloperAgent(
            dev_rules_path=tmp_path / "nonexistent.md"
        )
        agent.initialize()  # 不应抛异常

    def test_execute_returns_result(self, dev_agent_with_mock_harness, sample_task):
        """execute 返回 SubAgentResult"""
        dev_agent_with_mock_harness._task = sample_task
        result = dev_agent_with_mock_harness.execute(sample_task)
        assert isinstance(result, SubAgentResult)
        assert result.status == SubAgentResultStatus.SUCCESS

    def test_execute_saves_task_description(self, dev_agent_with_mock_harness, sample_task):
        """execute 保存任务描述"""
        dev_agent_with_mock_harness._task = sample_task
        dev_agent_with_mock_harness.execute(sample_task)
        assert dev_agent_with_mock_harness.current_task_description == sample_task.description

    def test_execute_result_contains_metadata(self, dev_agent_with_mock_harness, sample_task):
        """execute 结果包含 prompt 长度等元数据"""
        dev_agent_with_mock_harness._task = sample_task
        result = dev_agent_with_mock_harness.execute(sample_task)
        assert "prompt_length" in result.metadata
        assert "harness_loaded" in result.metadata

    def test_verify_returns_success(self, dev_agent_with_mock_harness, sample_task):
        """verify 返回 SUCCESS"""
        dev_agent_with_mock_harness._task = sample_task
        result = dev_agent_with_mock_harness.verify()
        assert result.status == SubAgentResultStatus.SUCCESS

    def test_commit_returns_success(self, dev_agent_with_mock_harness, sample_task):
        """commit 返回 SUCCESS"""
        dev_agent_with_mock_harness._task = sample_task
        result = dev_agent_with_mock_harness.commit()
        assert result.status == SubAgentResultStatus.SUCCESS

    def test_cleanup_no_exception(self, dev_agent_with_mock_harness):
        """cleanup 不抛异常"""
        dev_agent_with_mock_harness.cleanup()

    def test_full_lifecycle_via_run(self, dev_agent_with_mock_harness, sample_task):
        """完整 run() 生命周期成功执行"""
        result = dev_agent_with_mock_harness.run(sample_task)
        assert result.status == SubAgentResultStatus.SUCCESS
        # run() 结束后 agent.phase 应为 CLEANED_UP（cleanup 自动转换）
        assert dev_agent_with_mock_harness.phase == AgentPhase.CLEANED_UP


# ── 5. Dev 特有业务方法桩 ────────────────────────────────


class TestBusinessMethodStubs:
    """验证 Dev 特有业务方法桩的基本功能"""

    def test_analyze_task_returns_dict(self, dev_agent, sample_task):
        """analyze_task 返回 TaskAnalysisResult"""
        result = dev_agent.analyze_task(sample_task)
        assert isinstance(result, TaskAnalysisResult)

    def test_analyze_task_has_required_fields(self, dev_agent, sample_task):
        """analyze_task 结果包含必要字段"""
        result = dev_agent.analyze_task(sample_task)
        assert result.implementation_plan
        assert isinstance(result.files_to_create, list)
        assert isinstance(result.files_to_modify, list)
        assert isinstance(result.dependencies, list)
        assert result.estimated_effort > 0

    def test_analyze_task_saves_description(self, dev_agent, sample_task):
        """analyze_task 保存任务描述"""
        dev_agent.analyze_task(sample_task)
        assert dev_agent.current_task_description == sample_task.description

    def test_analyze_task_saves_plan(self, dev_agent, sample_task):
        """analyze_task 保存实现方案"""
        dev_agent.analyze_task(sample_task)
        assert dev_agent.implementation_plan is not None

    def test_write_tests_returns_dict(self, dev_agent, sample_task):
        """write_tests 返回 TestWriteResult"""
        result = dev_agent.write_tests(sample_task)
        assert isinstance(result, TestWriteResult)

    def test_write_tests_has_required_fields(self, dev_agent, sample_task):
        """write_tests 结果包含必要字段"""
        result = dev_agent.write_tests(sample_task)
        assert result.test_file_path
        assert isinstance(result.test_cases, list)
        assert result.test_content is not None

    def test_implement_code_returns_dict(self, dev_agent, sample_task):
        """implement_code 返回 ImplementResult"""
        result = dev_agent.implement_code(sample_task)
        assert isinstance(result, ImplementResult)

    def test_implement_code_has_required_fields(self, dev_agent, sample_task):
        """implement_code 结果包含必要字段"""
        result = dev_agent.implement_code(sample_task)
        assert isinstance(result.files_changed, list)
        assert result.implementation_summary is not None
        assert isinstance(result.lines_added, int)
        assert isinstance(result.lines_removed, int)

    def test_run_tests_returns_dict(self, dev_agent, sample_task):
        """run_tests 返回 TestRunResult"""
        result = dev_agent.run_tests(sample_task)
        assert isinstance(result, TestRunResult)

    def test_run_tests_has_required_fields(self, dev_agent, sample_task):
        """run_tests 结果包含必要字段"""
        result = dev_agent.run_tests(sample_task)
        assert isinstance(result.passed, bool)
        assert isinstance(result.total, int)
        assert isinstance(result.passed_count, int)
        assert isinstance(result.failed_count, int)
        assert isinstance(result.error_details, str)

    def test_run_tests_saves_results(self, dev_agent, sample_task):
        """run_tests 缓存测试结果"""
        dev_agent.run_tests(sample_task)
        assert dev_agent.test_results is not None

    def test_build_commit_message_returns_string(self, dev_agent, sample_task):
        """build_commit_message 返回字符串"""
        result = dev_agent.build_commit_message(sample_task)
        assert isinstance(result, str)

    def test_build_commit_message_format(self, dev_agent, sample_task):
        """commit message 格式正确：[task-{id}] senior-developer: {desc}"""
        message = dev_agent.build_commit_message(sample_task)
        assert message.startswith("[task-")
        assert "senior-developer:" in message

    def test_build_commit_message_contains_task_id(self, dev_agent, sample_task):
        """commit message 包含 task ID"""
        message = dev_agent.build_commit_message(sample_task)
        # task-001 → message 应包含 001
        assert "001" in message

    def test_build_commit_message_saves_message(self, dev_agent, sample_task):
        """build_commit_message 缓存结果"""
        dev_agent.build_commit_message(sample_task)
        assert dev_agent.commit_message is not None

    def test_build_commit_message_short_title(self, dev_agent):
        """短标题完整显示"""
        task = Task(
            id="task-005",
            title="修复 Bug",
            description="修复登录 bug",
            priority=TaskPriority.HIGH,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        message = dev_agent.build_commit_message(task)
        assert "修复 Bug" in message

    def test_build_commit_message_long_title(self, dev_agent):
        """长标题截断显示"""
        long_title = "A" * 100
        task = Task(
            id="task-006",
            title=long_title,
            description="description",
            priority=TaskPriority.HIGH,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        message = dev_agent.build_commit_message(task)
        # 描述部分不超过 50 字符
        # 提取 senior-developer: 后面的部分
        desc_part = message.split("senior-developer: ", 1)[1] if "senior-developer: " in message else ""
        assert len(desc_part) <= 50


# ── 6. Harness 规则访问 ──────────────────────────────────


class TestHarnessRulesAccess:
    """验证通过 Harness 访问 dev-rules 规则"""

    def test_harness_has_do_section(self, dev_agent_with_mock_harness):
        """harness 包含 DO 段落"""
        harness = dev_agent_with_mock_harness.dev_harness
        do_sections = [s for s in harness.sections if s.rule_type == RuleType.DO]
        assert len(do_sections) > 0

    def test_harness_has_dont_section(self, dev_agent_with_mock_harness):
        """harness 包含 DON'T 段落"""
        harness = dev_agent_with_mock_harness.dev_harness
        dont_sections = [s for s in harness.sections if s.rule_type == RuleType.DONT]
        assert len(dont_sections) > 0

    def test_harness_has_constraints_section(self, dev_agent_with_mock_harness):
        """harness 包含 Constraints 段落"""
        harness = dev_agent_with_mock_harness.dev_harness
        constraint_sections = [
            s for s in harness.sections if s.rule_type == RuleType.CONSTRAINT
        ]
        assert len(constraint_sections) > 0

    def test_harness_has_verification_section(self, dev_agent_with_mock_harness):
        """harness 包含 Verification 段落"""
        harness = dev_agent_with_mock_harness.dev_harness
        verify_sections = [
            s for s in harness.sections if s.rule_type == RuleType.VERIFICATION
        ]
        assert len(verify_sections) > 0

    def test_harness_rules_contain_tdd(self, dev_agent_with_mock_harness):
        """harness 规则中包含 TDD 相关内容"""
        harness = dev_agent_with_mock_harness.dev_harness
        # 从 sections 中收集所有规则内容
        all_content = " ".join(
            r.content for s in harness.sections for r in s.rules
        )
        assert "TDD" in all_content or "test" in all_content.lower()

    def test_harness_rules_contain_commit_format(self, dev_agent_with_mock_harness):
        """harness 规则中包含 commit 格式约束"""
        harness = dev_agent_with_mock_harness.dev_harness
        # 从 sections 中收集所有规则内容
        all_content = " ".join(
            r.content for s in harness.sections for r in s.rules
        )
        assert "commit" in all_content.lower() or "task-" in all_content

    def test_real_dev_rules_harness_loads(self):
        """实际 dev-rules.md 文件可以正常加载"""
        agent = SeniorDeveloperAgent()
        harness = agent.load_dev_harness()
        assert harness is not None
        assert len(harness.sections) >= 4  # 至少 4 个段落
        assert len(harness.rules) >= 20  # 至少 20 条规则


# ── 7. 边界条件与异常处理 ────────────────────────────────


class TestBoundaryAndErrorConditions:
    """验证边界条件和异常处理"""

    def test_multiple_agents_independent(self):
        """多个 Dev Agent 实例相互独立"""
        agent1 = SeniorDeveloperAgent()
        agent2 = SeniorDeveloperAgent()
        assert agent1 is not agent2
        assert agent1.current_task_description is None
        assert agent2.current_task_description is None

    def test_task_description_preserved_across_methods(self, dev_agent, sample_task):
        """任务描述在多个方法调用间保持"""
        dev_agent.analyze_task(sample_task)
        desc1 = dev_agent.current_task_description
        dev_agent.build_commit_message(sample_task)
        desc2 = dev_agent.current_task_description
        assert desc1 == desc2 == sample_task.description

    def test_analyze_task_with_none_task(self, dev_agent):
        """analyze_task 处理 None 任务抛出 ValueError"""
        with pytest.raises(ValueError, match="task cannot be None"):
            dev_agent.analyze_task(None)

    def test_write_tests_with_none_task(self, dev_agent):
        """write_tests 处理 None 任务抛出 ValueError"""
        with pytest.raises(ValueError, match="task cannot be None"):
            dev_agent.write_tests(None)

    def test_implement_code_with_none_task(self, dev_agent):
        """implement_code 处理 None 任务抛出 ValueError"""
        with pytest.raises(ValueError, match="task cannot be None"):
            dev_agent.implement_code(None)

    def test_run_tests_with_none_task(self, dev_agent):
        """run_tests 处理 None 任务抛出 ValueError"""
        with pytest.raises(ValueError, match="task cannot be None"):
            dev_agent.run_tests(None)

    def test_build_commit_message_with_none_task(self, dev_agent):
        """build_commit_message 传入 None 任务应抛出 ValueError（P2-012 正式实现）"""
        with pytest.raises(ValueError, match="task must not be None"):
            dev_agent.build_commit_message(None)

    def test_task_without_bdd(self, dev_agent):
        """处理无 BDD 规格的任务"""
        task = Task(
            id="task-010",
            title="简单配置",
            description="修改配置文件",
            priority=TaskPriority.LOW,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.analyze_task(task)
        assert isinstance(result, TaskAnalysisResult)

    def test_task_without_dependencies(self, dev_agent, sample_task):
        """处理无依赖的任务"""
        result = dev_agent.analyze_task(sample_task)
        assert result.dependencies == []

    def test_task_with_dependencies(self, dev_agent):
        """处理有依赖的任务"""
        task = Task(
            id="task-002",
            title="实现用户查询 API",
            description="实现查询接口",
            dependencies=["task-001"],
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.analyze_task(task)
        assert "task-001" in result.dependencies

    def test_default_max_implementation_time(self):
        """默认最大实现时间配置"""
        assert _DEFAULT_MAX_IMPLEMENTATION_MINUTES == 30

    def test_commit_message_format_template(self):
        """commit message 格式模板正确"""
        assert "{task_id}" in _COMMIT_MESSAGE_FORMAT
        assert "{description}" in _COMMIT_MESSAGE_FORMAT
        assert "senior-developer:" in _COMMIT_MESSAGE_FORMAT


# ── 8. 内部辅助方法 ──────────────────────────────────────


class TestInternalHelpers:
    """验证内部辅助方法"""

    def test_build_task_description_basic(self, dev_agent, sample_task):
        """_build_task_description 包含基本信息"""
        desc = dev_agent._build_task_description(sample_task)
        assert sample_task.id in desc
        assert sample_task.title in desc

    def test_build_task_description_includes_bdd(self, dev_agent, sample_task):
        """_build_task_description 包含 BDD 规格"""
        desc = dev_agent._build_task_description(sample_task)
        assert "Given:" in desc
        assert "When:" in desc
        assert "Then:" in desc

    def test_build_task_description_includes_priority(self, dev_agent, sample_task):
        """_build_task_description 包含优先级"""
        desc = dev_agent._build_task_description(sample_task)
        assert "Priority:" in desc

    def test_build_task_description_includes_complexity(self, dev_agent, sample_task):
        """_build_task_description 包含复杂度"""
        desc = dev_agent._build_task_description(sample_task)
        assert "Complexity:" in desc

    def test_build_task_description_includes_dependencies(self, dev_agent):
        """_build_task_description 包含依赖信息"""
        task = Task(
            id="task-003",
            title="有依赖的任务",
            description="描述",
            dependencies=["task-001", "task-002"],
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        desc = dev_agent._build_task_description(task)
        assert "Dependencies:" in desc
        assert "task-001" in desc
        assert "task-002" in desc

    def test_build_task_description_without_bdd(self, dev_agent):
        """无 BDD 规格时不包含 BDD 段"""
        task = Task(
            id="task-004",
            title="无 BDD 任务",
            description="描述",
            priority=TaskPriority.LOW,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        desc = dev_agent._build_task_description(task)
        assert "BDD Spec:" not in desc


# ── 9. Prompt 构建（业务方法）──────────────────────────────


class TestPromptScenarios:
    """验证各类业务 prompt 构建"""

    def test_get_analyze_prompt(self, dev_agent_with_mock_harness, sample_task):
        """任务分析 prompt 包含关键内容"""
        prompt = dev_agent_with_mock_harness.get_analyze_prompt(sample_task)
        assert "senior-developer" in prompt
        assert sample_task.id in prompt
        assert "TDD" in prompt or "test" in prompt.lower()

    def test_get_implement_prompt(self, dev_agent_with_mock_harness, sample_task):
        """代码实现 prompt 包含关键内容"""
        prompt = dev_agent_with_mock_harness.get_implement_prompt(sample_task)
        assert "senior-developer" in prompt
        assert sample_task.id in prompt
        assert "TDD" in prompt or "实现" in prompt

    def test_get_implement_prompt_contains_time_limit(self, dev_agent_with_mock_harness, sample_task):
        """实现 prompt 包含时间限制"""
        prompt = dev_agent_with_mock_harness.get_implement_prompt(sample_task)
        assert str(_DEFAULT_MAX_IMPLEMENTATION_MINUTES) in prompt

    def test_get_analyze_prompt_includes_bdd(self, dev_agent_with_mock_harness, sample_task):
        """分析 prompt 包含 BDD 规格"""
        prompt = dev_agent_with_mock_harness.get_analyze_prompt(sample_task)
        assert "Given" in prompt or "When" in prompt or "Then" in prompt


# ── 10. 配置常量 ──────────────────────────────────────────


class TestConfigurationConstants:
    """验证配置常量"""

    def test_dev_role_name(self):
        """角色名称常量"""
        assert _DEV_ROLE_NAME == "senior-developer"

    def test_dev_role_short(self):
        """角色简称常量"""
        assert _DEV_ROLE_SHORT == "dev"

    def test_default_dev_rules_path(self):
        """默认 harness 路径指向项目 harness 目录"""
        assert _DEFAULT_DEV_RULES_PATH.name == "dev-rules.md"
        assert _DEFAULT_DEV_RULES_PATH.parent.name == "harness"

    def test_commit_message_format(self):
        """commit message 格式包含必要占位符"""
        formatted = _COMMIT_MESSAGE_FORMAT.format(
            task_id="001", description="实现功能"
        )
        assert formatted == "[task-001] senior-developer: 实现功能"

"""
P2-001 测试：ProductManagerAgent 类

验证 ProductManagerAgent 继承 SubAgent 基类、注入 pm-rules.md 的完整功能。
测试覆盖：
1. 类创建与继承关系
2. pm-rules.md harness 加载
3. 角色注入 prompt 构建
4. SubAgent 生命周期方法
5. PM 特有业务方法桩
6. Harness 规则访问
7. 边界条件与异常处理
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_automation_system.harness.harness_loader import HarnessLoader
from agent_automation_system.harness.models import Harness, HarnessRule, HarnessSection, RuleType
from agent_automation_system.models.task import BDDSpec, Task, TaskPriority
from agent_automation_system.sub_agent.pm_agent import (
    ProductManagerAgent,
    _DEFAULT_PM_RULES_PATH,
    _PM_ROLE_NAME,
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
def pm_agent():
    """创建默认 ProductManagerAgent 实例"""
    return ProductManagerAgent()


@pytest.fixture
def pm_agent_with_mock_harness():
    """创建带 mock harness 的 ProductManagerAgent 实例"""
    agent = ProductManagerAgent()
    # 构造一个假的 Harness 对象
    mock_harness = Harness(
        name="Product Manager Agent Rules",
        file_path=str(_DEFAULT_PM_RULES_PATH),
        role_name="product-manager",
        sections=[
            HarnessSection(
                title="DO",
                rule_type=RuleType.DO,
                rules=[
                    HarnessRule(
                        rule_type=RuleType.DO,
                        content="Receive user requirements and clarify ambiguities",
                        section="DO",
                    ),
                    HarnessRule(
                        rule_type=RuleType.DO,
                        content="Use Given-When-Then format",
                        section="DO",
                    ),
                ],
                raw_content="- Receive user requirements\n- Use Given-When-Then format",
            ),
            HarnessSection(
                title="DON'T",
                rule_type=RuleType.DONT,
                rules=[
                    HarnessRule(
                        rule_type=RuleType.DONT,
                        content="NEVER proceed with ambiguous requirements",
                        section="DON'T",
                    ),
                ],
                raw_content="- NEVER proceed with ambiguous requirements",
            ),
            HarnessSection(
                title="Constraints",
                rule_type=RuleType.CONSTRAINT,
                rules=[
                    HarnessRule(
                        rule_type=RuleType.CONSTRAINT,
                        content="Every atomic task MUST have at least one test script",
                        section="Constraints",
                    ),
                ],
                raw_content="- Every atomic task MUST have at least one test script",
            ),
            HarnessSection(
                title="Verification",
                rule_type=RuleType.VERIFICATION,
                rules=[
                    HarnessRule(
                        rule_type=RuleType.VERIFICATION,
                        content="Each task in task.json must have a testable acceptance criterion",
                        section="Verification",
                    ),
                ],
                raw_content="- Each task must have a testable acceptance criterion",
            ),
        ],
        rules=[
            HarnessRule(rule_type=RuleType.DO, content="Receive user requirements and clarify ambiguities", section="DO"),
            HarnessRule(rule_type=RuleType.DO, content="Use Given-When-Then format", section="DO"),
            HarnessRule(rule_type=RuleType.DONT, content="NEVER proceed with ambiguous requirements", section="DON'T"),
            HarnessRule(rule_type=RuleType.CONSTRAINT, content="Every atomic task MUST have at least one test script", section="Constraints"),
            HarnessRule(rule_type=RuleType.VERIFICATION, content="Each task in task.json must have a testable acceptance criterion", section="Verification"),
        ],
        raw_content="# Product Manager Agent Rules\n\n## DO\n- Receive user requirements\n- Use Given-When-Then format",
    )
    agent._pm_harness = mock_harness
    agent._pm_harness_content = mock_harness.to_prompt_text()
    return agent


@pytest.fixture
def sample_task():
    """创建示例 PM 任务"""
    return Task(
        id="task-001",
        title="需求分析：用户登录功能",
        description="用户需要一个安全的登录功能，支持邮箱和手机号登录",
        bdd=BDDSpec(
            given="用户未登录，访问登录页面",
            when="用户输入有效凭证并提交",
            then="用户成功登录并跳转到首页",
        ),
        suggested_role="product-manager",
        priority=TaskPriority.HIGH,
    )


@pytest.fixture
def harness_dir(tmp_path):
    """创建包含 pm-rules.md 的临时 harness 目录"""
    harness_path = tmp_path / "pm-rules.md"
    harness_path.write_text("""# Product Manager Agent Rules

## Role Identity
You are the Product Manager Agent.

## DO
- Receive user requirements and clarify ambiguities through structured BDD communication
- Use Given-When-Then format to describe expected behavior for each feature

## DON'T
- NEVER proceed with ambiguous or incomplete requirements
- NEVER skip the BDD Given-When-Then format

## Constraints
- Every atomic task MUST have at least one test script as acceptance criteria
- task.json must follow the project schema

## Verification
- Each task in task.json must have a testable acceptance criterion
- BDD scenarios must be syntactically valid Given-When-Then format
""")
    return tmp_path


# ══════════════════════════════════════════════════════════
# 1. 类创建与继承关系
# ══════════════════════════════════════════════════════════


class TestProductManagerAgentCreation:
    """ProductManagerAgent 类创建与继承关系"""

    def test_is_subagent_subclass(self):
        """ProductManagerAgent 是 SubAgent 的子类"""
        agent = ProductManagerAgent()
        assert isinstance(agent, SubAgent)

    def test_default_role_name(self, pm_agent):
        """默认角色名称为 product-manager"""
        assert pm_agent.role_name == "product-manager"
        assert pm_agent.role_name == _PM_ROLE_NAME

    def test_initial_phase_created(self, pm_agent):
        """初始阶段为 CREATED"""
        assert pm_agent.phase == AgentPhase.CREATED

    def test_no_task_initially(self, pm_agent):
        """初始无分配任务"""
        assert pm_agent.task is None

    def test_no_result_initially(self, pm_agent):
        """初始无执行结果"""
        assert pm_agent.result is None

    def test_custom_pm_rules_path(self, tmp_path):
        """可自定义 pm-rules.md 路径"""
        custom_path = tmp_path / "custom-pm-rules.md"
        custom_path.write_text("# Custom PM Rules\n\n## DO\n- Custom rule\n")
        agent = ProductManagerAgent(pm_rules_path=custom_path)
        assert agent.pm_rules_path == custom_path

    def test_custom_role_injector(self):
        """可自定义 RoleInjector"""
        injector = RoleInjector()
        agent = ProductManagerAgent(role_injector=injector)
        assert agent.role_injector is injector

    def test_custom_harness_loader(self):
        """可自定义 HarnessLoader"""
        loader = HarnessLoader()
        agent = ProductManagerAgent(harness_loader=loader)
        assert agent._harness_loader is loader


# ══════════════════════════════════════════════════════════
# 2. pm-rules.md Harness 加载
# ══════════════════════════════════════════════════════════


class TestPmHarnessLoading:
    """pm-rules.md Harness 加载"""


    def test_load_pm_harness_success(self, harness_dir):
        """成功加载 pm-rules.md"""
        pm_path = harness_dir / "pm-rules.md"
        agent = ProductManagerAgent(pm_rules_path=pm_path)
        harness = agent.load_pm_harness()

        assert harness is not None
        assert isinstance(harness, Harness)
        assert agent.pm_harness is harness
        assert agent.pm_harness_content is not None

    def test_load_pm_harness_cached(self, harness_dir):
        """重复加载返回缓存结果"""
        pm_path = harness_dir / "pm-rules.md"
        agent = ProductManagerAgent(pm_rules_path=pm_path)
        harness1 = agent.load_pm_harness()
        harness2 = agent.load_pm_harness()
        assert harness1 is harness2  # 同一个对象

    def test_load_pm_harness_file_not_found(self, tmp_path):
        """pm-rules.md 不存在时抛出 FileNotFoundError"""
        agent = ProductManagerAgent(
            pm_rules_path=tmp_path / "nonexistent.md"
        )
        with pytest.raises(FileNotFoundError, match="pm-rules.md not found"):
            agent.load_pm_harness()

    def test_harness_has_sections(self, harness_dir):
        """加载的 harness 包含多个段落"""
        pm_path = harness_dir / "pm-rules.md"
        agent = ProductManagerAgent(pm_rules_path=pm_path)
        harness = agent.load_pm_harness()

        section_titles = [s.title for s in harness.sections]
        assert "DO" in section_titles
        assert "DON'T" in section_titles

    def test_harness_has_rules(self, harness_dir):
        """加载的 harness 包含规则"""
        pm_path = harness_dir / "pm-rules.md"
        agent = ProductManagerAgent(pm_rules_path=pm_path)
        harness = agent.load_pm_harness()

        assert len(harness.rules) > 0

    def test_harness_role_name(self, harness_dir):
        """harness 角色名称为 product-manager"""
        pm_path = harness_dir / "pm-rules.md"
        agent = ProductManagerAgent(pm_rules_path=pm_path)
        harness = agent.load_pm_harness()

        assert harness.role_name == "product-manager"

    def test_load_real_pm_rules_if_exists(self):
        """如果项目 harness/pm-rules.md 存在，加载真实文件"""
        if _DEFAULT_PM_RULES_PATH.exists():
            agent = ProductManagerAgent()
            harness = agent.load_pm_harness()
            assert harness is not None
            assert len(harness.rules) > 0
        else:
            pytest.skip("Real pm-rules.md not found")


# ══════════════════════════════════════════════════════════
# 3. 角色注入 Prompt 构建
# ══════════════════════════════════════════════════════════


class TestPmPromptBuilding:
    """PM Agent 角色注入 Prompt 构建"""

    def test_build_prompt_contains_role_identity(self, pm_agent_with_mock_harness):
        """prompt 包含角色身份段落"""
        prompt = pm_agent_with_mock_harness.build_pm_prompt("分析用户登录需求")
        assert "角色身份" in prompt
        assert "product-manager" in prompt or "Product Manager" in prompt

    def test_build_prompt_contains_task_description(self, pm_agent_with_mock_harness):
        """prompt 包含任务描述"""
        desc = "分析用户登录需求，产出 BDD 规格"
        prompt = pm_agent_with_mock_harness.build_pm_prompt(desc)
        assert "任务描述" in prompt
        assert desc in prompt

    def test_build_prompt_contains_harness(self, pm_agent_with_mock_harness):
        """prompt 包含约束规则"""
        prompt = pm_agent_with_mock_harness.build_pm_prompt("测试任务")
        assert "约束规则" in prompt
        assert "DO" in prompt

    def test_build_prompt_without_harness(self, pm_agent):
        """不注入 harness 时 prompt 仅含角色+任务"""
        prompt = pm_agent.build_pm_prompt("测试任务", include_harness=False)
        assert "角色身份" in prompt
        assert "任务描述" in prompt
        # 无约束规则段落
        assert "约束规则" not in prompt

    def test_build_prompt_auto_loads_harness(self, harness_dir):
        """build_pm_prompt 自动加载 harness（如未加载）"""
        pm_path = harness_dir / "pm-rules.md"
        agent = ProductManagerAgent(pm_rules_path=pm_path)
        assert agent.pm_harness is None  # 尚未加载

        prompt = agent.build_pm_prompt("测试任务")
        assert agent.pm_harness is not None  # 已自动加载
        assert "约束规则" in prompt

    def test_build_prompt_handles_missing_harness(self, tmp_path):
        """harness 文件不存在时不报错，跳过约束注入"""
        agent = ProductManagerAgent(
            pm_rules_path=tmp_path / "nonexistent.md"
        )
        prompt = agent.build_pm_prompt("测试任务")
        assert "角色身份" in prompt
        assert "任务描述" in prompt
        # 约束规则段落不存在（harness 加载失败）
        assert "约束规则" not in prompt


# ══════════════════════════════════════════════════════════
# 4. SubAgent 生命周期方法
# ══════════════════════════════════════════════════════════


class TestPmLifecycle:
    """ProductManagerAgent 生命周期方法"""

    def test_initialize_loads_harness(self, harness_dir):
        """initialize() 加载 pm-rules harness"""
        pm_path = harness_dir / "pm-rules.md"
        agent = ProductManagerAgent(pm_rules_path=pm_path)
        agent.initialize()
        assert agent.pm_harness is not None

    def test_initialize_handles_missing_harness(self, tmp_path):
        """initialize() 处理 harness 文件缺失（不抛异常）"""
        agent = ProductManagerAgent(
            pm_rules_path=tmp_path / "nonexistent.md"
        )
        # 不应抛出异常
        agent.initialize()
        assert agent.pm_harness is None

    def test_execute_returns_success(self, pm_agent_with_mock_harness, sample_task):
        """execute() 返回 SUCCESS"""
        result = pm_agent_with_mock_harness.execute(sample_task)
        assert result.status == SubAgentResultStatus.SUCCESS
        assert "PM task" in result.output

    def test_execute_sets_raw_requirement(self, pm_agent_with_mock_harness, sample_task):
        """execute() 保存原始需求"""
        pm_agent_with_mock_harness.execute(sample_task)
        assert pm_agent_with_mock_harness.raw_requirement == sample_task.description

    def test_execute_result_has_metadata(self, pm_agent_with_mock_harness, sample_task):
        """execute() 结果包含 metadata"""
        result = pm_agent_with_mock_harness.execute(sample_task)
        assert "prompt_length" in result.metadata
        assert "harness_loaded" in result.metadata
        assert result.metadata["harness_loaded"] is True

    def test_verify_returns_success(self, pm_agent_with_mock_harness):
        """verify() 返回 SUCCESS"""
        result = pm_agent_with_mock_harness.verify()
        assert result.status == SubAgentResultStatus.SUCCESS

    def test_commit_returns_success(self, pm_agent_with_mock_harness):
        """commit() 返回 SUCCESS"""
        result = pm_agent_with_mock_harness.commit()
        assert result.status == SubAgentResultStatus.SUCCESS

    def test_cleanup_no_error(self, pm_agent_with_mock_harness):
        """cleanup() 不抛异常"""
        pm_agent_with_mock_harness.cleanup()  # 不应抛异常

    def test_full_lifecycle_run(self, harness_dir, sample_task):
        """完整生命周期 run()"""
        pm_path = harness_dir / "pm-rules.md"
        agent = ProductManagerAgent(pm_rules_path=pm_path)
        result = agent.run(sample_task)

        assert result.status == SubAgentResultStatus.SUCCESS
        assert agent.phase == AgentPhase.CLEANED_UP

    def test_full_lifecycle_phases(self, harness_dir, sample_task):
        """完整生命周期经历正确的阶段转换"""
        pm_path = harness_dir / "pm-rules.md"
        agent = ProductManagerAgent(pm_rules_path=pm_path)
        phases = []
        original_transition = agent._transition_to

        def track_transition(new_phase):
            phases.append(new_phase)
            original_transition(new_phase)

        agent._transition_to = track_transition
        agent.run(sample_task)

        assert AgentPhase.INITIALIZED in phases
        assert AgentPhase.EXECUTING in phases
        assert AgentPhase.VERIFYING in phases
        assert AgentPhase.COMMITTING in phases
        assert AgentPhase.COMPLETED in phases
        assert AgentPhase.CLEANED_UP in phases


# ══════════════════════════════════════════════════════════
# 5. PM 特有业务方法桩
# ══════════════════════════════════════════════════════════


class TestPmBusinessMethodStubs:
    """PM 特有业务方法桩（P2-003 ~ P2-006 逐步实现）"""

    def test_refine_requirement_works(self, pm_agent):
        """refine_requirement 已实现（P2-002），返回 BDDDraft"""
        from agent_automation_system.models.bdd import BDDDraft
        draft = pm_agent.refine_requirement("用户需要登录功能")
        assert isinstance(draft, BDDDraft)

    def test_communicate_with_user_works(self, pm_agent):
        """communicate_with_user 已实现（P2-003），返回 CommunicationResult"""
        from agent_automation_system.models.bdd import BDDDraft, CommunicationResult
        draft = pm_agent.refine_requirement("简单需求")
        result = pm_agent.communicate_with_user(draft)
        assert isinstance(result, CommunicationResult)

    def test_decompose_requirement_works(self, pm_agent):
        """decompose_requirement 已实现（P2-004），返回 DecomposeResult"""
        from agent_automation_system.models.bdd import DecomposeResult
        result = pm_agent.decompose_requirement("确认的 BDD 描述")
        assert isinstance(result, DecomposeResult)

    def test_generate_task_json_works(self, pm_agent):
        """generate_task_json 已实现（P2-005），返回 TaskJsonResult"""
        from agent_automation_system.models.bdd import TaskJsonResult
        tasks = [
            {"id": "task-001", "title": "任务1", "description": "描述1",
             "bdd": {"given": "前提", "when": "动作", "then": "结果"},
             "dependencies": [], "priority": "high", "estimated_complexity": "medium", "status": "pending"},
        ]
        result = pm_agent.generate_task_json(tasks)
        assert isinstance(result, TaskJsonResult)

    def test_generate_test_script_works(self, pm_agent):
        """generate_test_script 已实现（P2-006），返回 TestScriptResult"""
        from agent_automation_system.models.bdd import TestScriptResult
        task = {
            "id": "task-001",
            "title": "用户登录",
            "description": "实现用户登录功能",
            "bdd": {"given": "用户未登录", "when": "输入有效凭证并提交", "then": "登录成功"},
            "dependencies": [], "priority": "high", "estimated_complexity": "medium", "status": "pending",
        }
        result = pm_agent.generate_test_script(task)
        assert isinstance(result, TestScriptResult)

    def test_refine_requirement_saves_raw_need(self, pm_agent):
        """refine_requirement 保存原始需求"""
        pm_agent.refine_requirement("用户需要登录功能")
        assert pm_agent.raw_requirement == "用户需要登录功能"


# ══════════════════════════════════════════════════════════
# 6. Harness 规则访问
# ══════════════════════════════════════════════════════════


class TestHarnessRulesAccess:
    """Harness 规则访问"""

    def test_get_rules_summary(self, pm_agent_with_mock_harness):
        """获取规则摘要"""
        summary = pm_agent_with_mock_harness.get_harness_rules_summary()
        assert "do" in summary
        assert "dont" in summary
        assert "constraints" in summary
        assert "verification" in summary
        assert "total" in summary
        assert summary["do"] == 2
        assert summary["dont"] == 1
        assert summary["total"] == 5

    def test_get_rules_summary_not_loaded(self, pm_agent):
        """harness 未加载时获取摘要抛出 RuntimeError"""
        with pytest.raises(RuntimeError, match="pm-rules harness not loaded"):
            pm_agent.get_harness_rules_summary()

    def test_harness_do_rules(self, pm_agent_with_mock_harness):
        """获取 DO 规则"""
        rules = pm_agent_with_mock_harness.pm_harness.get_do_rules()
        assert len(rules) == 2
        assert all(r.rule_type == RuleType.DO for r in rules)

    def test_harness_dont_rules(self, pm_agent_with_mock_harness):
        """获取 DON'T 规则"""
        rules = pm_agent_with_mock_harness.pm_harness.get_dont_rules()
        assert len(rules) == 1
        assert rules[0].rule_type == RuleType.DONT

    def test_harness_constraints(self, pm_agent_with_mock_harness):
        """获取约束规则"""
        rules = pm_agent_with_mock_harness.pm_harness.get_constraints()
        assert len(rules) == 1
        assert rules[0].rule_type == RuleType.CONSTRAINT


# ══════════════════════════════════════════════════════════
# 7. 边界条件与异常处理
# ══════════════════════════════════════════════════════════


class TestEdgeCasesAndErrors:
    """边界条件与异常处理"""

    def test_build_task_description_without_bdd(self, pm_agent):
        """无 BDD 规格时构建任务描述"""
        task = Task(
            id="task-002",
            title="简单需求",
            description="简单的需求描述",
        )
        desc = pm_agent._build_task_description(task)
        assert "需求分析任务" in desc
        assert task.title in desc
        assert task.description in desc

    def test_build_task_description_with_bdd(self, pm_agent, sample_task):
        """有 BDD 规格时构建任务描述"""
        desc = pm_agent._build_task_description(sample_task)
        assert "BDD 规格" in desc
        assert "Given:" in desc
        assert "When:" in desc
        assert "Then:" in desc

    def test_multiple_agents_independent(self, harness_dir):
        """多个 PM Agent 实例相互独立"""
        pm_path = harness_dir / "pm-rules.md"
        agent1 = ProductManagerAgent(pm_rules_path=pm_path)
        agent2 = ProductManagerAgent(pm_rules_path=pm_path)

        agent1.load_pm_harness()
        # agent2 未加载
        assert agent1.pm_harness is not None
        assert agent2.pm_harness is None

    def test_default_pm_rules_path(self):
        """默认 pm-rules 路径指向项目 harness 目录"""
        assert _DEFAULT_PM_RULES_PATH.name == "pm-rules.md"
        assert "harness" in str(_DEFAULT_PM_RULES_PATH)

    def test_role_name_constant(self):
        """PM 角色名称常量"""
        assert _PM_ROLE_NAME == "product-manager"

    def test_execute_without_harness(self, sample_task):
        """无 harness 时 execute 仍可运行"""
        agent = ProductManagerAgent(
            pm_rules_path=Path("/nonexistent/pm-rules.md")
        )
        result = agent.execute(sample_task)
        assert result.status == SubAgentResultStatus.SUCCESS
        assert result.metadata["harness_loaded"] is False

    def test_run_without_harness(self, tmp_path, sample_task):
        """无 harness 时完整 run() 仍可运行"""
        agent = ProductManagerAgent(
            pm_rules_path=tmp_path / "nonexistent.md"
        )
        result = agent.run(sample_task)
        assert result.status == SubAgentResultStatus.SUCCESS
        # result.phase 记录的是 commit 阶段（最后一个业务阶段），
        # agent.phase 则经过 cleanup 后为 CLEANED_UP
        assert agent.phase == AgentPhase.CLEANED_UP

    def test_pM_agent_with_mock_harness_has_content(self, pm_agent_with_mock_harness):
        """mock harness 的内容非空"""
        assert pm_agent_with_mock_harness.pm_harness_content is not None
        assert len(pm_agent_with_mock_harness.pm_harness_content) > 0

    def test_bdd_draft_default_none(self, pm_agent):
        """bdd_draft 默认为 None"""
        assert pm_agent.bdd_draft is None

    def test_confirmed_bdd_default_none(self, pm_agent):
        """confirmed_bdd 默认为 None"""
        assert pm_agent.confirmed_bdd is None

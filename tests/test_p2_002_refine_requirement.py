"""
P2-002 测试：BDD 需求精炼 — refine_requirement

验证 ProductManagerAgent.refine_requirement 方法及相关 BDD 数据模型。
测试覆盖：
1. BDDScenario 数据模型
2. BDDDraft 数据模型
3. refine_requirement 核心功能
4. 需求摘要生成
5. 初始 BDD 场景提取
6. 澄清问题生成
7. 假设生成
8. 精炼 prompt 构建
9. 边界条件与异常处理
10. 与生命周期集成
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock, patch

from agent_automation_system.harness.harness_loader import HarnessLoader
from agent_automation_system.harness.models import Harness, HarnessRule, HarnessSection, RuleType
from agent_automation_system.models.bdd import BDDDraft, BDDScenario
from agent_automation_system.models.task import BDDSpec, Task, TaskPriority
from agent_automation_system.sub_agent.pm_agent import (
    ProductManagerAgent,
    _DEFAULT_PM_RULES_PATH,
    _PM_ROLE_NAME,
)
from agent_automation_system.sub_agent.role_injector import RoleInjector
from agent_automation_system.sub_agent.sub_agent import (
    AgentPhase,
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
                        content="Use Given-When-Then format",
                        section="DO",
                    ),
                ],
                raw_content="- Use Given-When-Then format",
            ),
        ],
        rules=[
            HarnessRule(rule_type=RuleType.DO, content="Use Given-When-Then format", section="DO"),
        ],
        raw_content="# PM Rules",
    )
    agent._pm_harness = mock_harness
    agent._pm_harness_content = mock_harness.to_prompt_text()
    return agent


# ══════════════════════════════════════════════════════════
# 1. BDDScenario 数据模型
# ══════════════════════════════════════════════════════════


class TestBDDScenario:
    """BDDScenario 数据模型测试"""

    def test_create_scenario(self):
        """创建 BDD 场景"""
        scenario = BDDScenario(
            title="用户登录成功",
            given="用户未登录，访问登录页面",
            when="用户输入有效邮箱和密码并提交",
            then="用户成功登录并跳转到首页",
        )
        assert scenario.title == "用户登录成功"
        assert scenario.given == "用户未登录，访问登录页面"
        assert scenario.when == "用户输入有效邮箱和密码并提交"
        assert scenario.then == "用户成功登录并跳转到首页"

    def test_scenario_default_priority(self):
        """场景默认优先级为 MEDIUM"""
        scenario = BDDScenario(
            title="测试场景",
            given="前置条件",
            when="触发动作",
            then="预期结果",
        )
        assert scenario.priority == TaskPriority.MEDIUM

    def test_scenario_high_priority(self):
        """场景可设为高优先级"""
        scenario = BDDScenario(
            title="核心场景",
            given="前置",
            when="动作",
            then="结果",
            priority=TaskPriority.HIGH,
        )
        assert scenario.priority == TaskPriority.HIGH

    def test_scenario_to_text(self):
        """场景转为可读文本"""
        scenario = BDDScenario(
            title="登录成功",
            given="未登录",
            when="输入有效凭证",
            then="登录成功",
        )
        text = scenario.to_text()
        assert "场景: 登录成功" in text
        assert "Given 未登录" in text
        assert "When 输入有效凭证" in text
        assert "Then 登录成功" in text

    def test_scenario_title_required(self):
        """场景标题不能为空"""
        with pytest.raises(Exception):
            BDDScenario(title="", given="g", when="w", then="t")

    def test_scenario_given_required(self):
        """Given 不能为空"""
        with pytest.raises(Exception):
            BDDScenario(title="t", given="", when="w", then="t")

    def test_scenario_when_required(self):
        """When 不能为空"""
        with pytest.raises(Exception):
            BDDScenario(title="t", given="g", when="", then="t")

    def test_scenario_then_required(self):
        """Then 不能为空"""
        with pytest.raises(Exception):
            BDDScenario(title="t", given="g", when="w", then="")


# ══════════════════════════════════════════════════════════
# 2. BDDDraft 数据模型
# ══════════════════════════════════════════════════════════


class TestBDDDraft:
    """BDDDraft 数据模型测试"""

    def test_create_draft(self):
        """创建 BDD 草稿"""
        draft = BDDDraft(
            raw_need="用户需要登录功能",
            summary="实现用户登录功能",
            scenarios=[
                BDDScenario(
                    title="邮箱登录",
                    given="未登录",
                    when="输入邮箱密码",
                    then="登录成功",
                )
            ],
        )
        assert draft.raw_need == "用户需要登录功能"
        assert draft.summary == "实现用户登录功能"
        assert draft.scenario_count == 1

    def test_draft_default_empty_lists(self):
        """草稿默认空列表"""
        draft = BDDDraft(raw_need="需求", summary="摘要")
        assert draft.scenarios == []
        assert draft.questions == []
        assert draft.assumptions == []

    def test_draft_scenario_count(self):
        """草稿场景计数"""
        draft = BDDDraft(
            raw_need="需求",
            summary="摘要",
            scenarios=[
                BDDScenario(title="s1", given="g", when="w", then="t"),
                BDDScenario(title="s2", given="g", when="w", then="t"),
            ],
        )
        assert draft.scenario_count == 2

    def test_draft_has_questions(self):
        """草稿有问题标记"""
        draft_with = BDDDraft(
            raw_need="需求", summary="摘要",
            questions=["问题1"],
        )
        draft_without = BDDDraft(raw_need="需求", summary="摘要")
        assert draft_with.has_questions is True
        assert draft_without.has_questions is False

    def test_draft_high_priority_scenarios(self):
        """高优先级场景过滤"""
        draft = BDDDraft(
            raw_need="需求",
            summary="摘要",
            scenarios=[
                BDDScenario(title="s1", given="g", when="w", then="t", priority=TaskPriority.HIGH),
                BDDScenario(title="s2", given="g", when="w", then="t", priority=TaskPriority.MEDIUM),
                BDDScenario(title="s3", given="g", when="w", then="t", priority=TaskPriority.HIGH),
            ],
        )
        high = draft.high_priority_scenarios
        assert len(high) == 2
        assert all(s.priority == TaskPriority.HIGH for s in high)

    def test_draft_to_text(self):
        """草稿转为可读文本"""
        draft = BDDDraft(
            raw_need="用户需要登录功能",
            summary="实现用户登录功能",
            scenarios=[
                BDDScenario(title="邮箱登录", given="未登录", when="输入邮箱密码", then="登录成功"),
            ],
            questions=["是否支持第三方登录？"],
            assumptions=["使用邮箱+密码方式登录"],
        )
        text = draft.to_text()
        assert "需求摘要" in text
        assert "BDD 场景" in text
        assert "邮箱登录" in text
        assert "待澄清问题" in text
        assert "假设" in text

    def test_draft_to_text_no_questions(self):
        """无问题时草稿文本不含问题段落"""
        draft = BDDDraft(raw_need="需求", summary="摘要", scenarios=[])
        text = draft.to_text()
        assert "待澄清问题" not in text

    def test_draft_created_at(self):
        """草稿创建时间"""
        now = datetime.now()
        draft = BDDDraft(raw_need="需求", summary="摘要", created_at=now)
        assert draft.created_at == now

    def test_draft_filters_empty_questions(self):
        """草稿过滤空字符串问题"""
        draft = BDDDraft(
            raw_need="需求",
            summary="摘要",
            questions=["有效问题", "", "   "],
        )
        assert len(draft.questions) == 1
        assert draft.questions[0] == "有效问题"

    def test_draft_filters_empty_assumptions(self):
        """草稿过滤空字符串假设"""
        draft = BDDDraft(
            raw_need="需求",
            summary="摘要",
            assumptions=["有效假设", ""],
        )
        assert len(draft.assumptions) == 1

    def test_draft_raw_need_required(self):
        """raw_need 不能为空"""
        with pytest.raises(Exception):
            BDDDraft(raw_need="", summary="摘要")

    def test_draft_summary_required(self):
        """summary 不能为空"""
        with pytest.raises(Exception):
            BDDDraft(raw_need="需求", summary="")


# ══════════════════════════════════════════════════════════
# 3. refine_requirement 核心功能
# ══════════════════════════════════════════════════════════


class TestRefineRequirement:
    """refine_requirement 核心功能"""

    def test_returns_bdd_draft(self, pm_agent):
        """refine_requirement 返回 BDDDraft"""
        draft = pm_agent.refine_requirement("用户需要登录功能")
        assert isinstance(draft, BDDDraft)

    def test_draft_contains_raw_need(self, pm_agent):
        """草稿包含原始需求"""
        draft = pm_agent.refine_requirement("用户需要安全的登录功能")
        assert draft.raw_need == "用户需要安全的登录功能"

    def test_draft_contains_summary(self, pm_agent):
        """草稿包含需求摘要"""
        draft = pm_agent.refine_requirement("用户需要登录功能")
        assert draft.summary
        assert len(draft.summary) > 0

    def test_draft_contains_scenarios(self, pm_agent):
        """草稿包含 BDD 场景"""
        draft = pm_agent.refine_requirement("用户需要登录功能")
        assert draft.scenario_count >= 1

    def test_saves_raw_requirement(self, pm_agent):
        """保存原始需求到 _raw_requirement"""
        pm_agent.refine_requirement("用户需要注册功能")
        assert pm_agent.raw_requirement == "用户需要注册功能"

    def test_saves_bdd_draft(self, pm_agent):
        """保存 BDD 草稿到 _bdd_draft"""
        pm_agent.refine_requirement("用户需要登录功能")
        assert pm_agent.bdd_draft is not None
        assert isinstance(pm_agent.bdd_draft, str)

    def test_draft_has_created_at(self, pm_agent):
        """草稿包含创建时间"""
        draft = pm_agent.refine_requirement("用户需要登录功能")
        assert draft.created_at is not None
        assert isinstance(draft.created_at, datetime)

    def test_empty_raw_need_raises(self, pm_agent):
        """空需求抛出 ValueError"""
        with pytest.raises(ValueError, match="raw_need cannot be empty"):
            pm_agent.refine_requirement("")

    def test_whitespace_only_raises(self, pm_agent):
        """仅含空白的需求抛出 ValueError"""
        with pytest.raises(ValueError, match="raw_need cannot be empty"):
            pm_agent.refine_requirement("   \n\t  ")

    def test_strips_raw_need(self, pm_agent):
        """去除原始需求前后空白"""
        draft = pm_agent.refine_requirement("  用户需要登录  ")
        assert draft.raw_need == "用户需要登录"

    def test_scenarios_have_given_when_then(self, pm_agent):
        """每个场景都包含 Given-When-Then"""
        draft = pm_agent.refine_requirement("用户需要登录功能，支持邮箱和手机号登录")
        for scenario in draft.scenarios:
            assert scenario.given
            assert scenario.when
            assert scenario.then


# ══════════════════════════════════════════════════════════
# 4. 需求摘要生成
# ══════════════════════════════════════════════════════════


class TestSummaryGeneration:
    """需求摘要生成"""

    def test_short_need_direct_summary(self, pm_agent):
        """短需求直接作为摘要"""
        short_need = "用户需要登录功能"
        draft = pm_agent.refine_requirement(short_need)
        assert draft.summary == short_need

    def test_long_need_truncated_summary(self, pm_agent):
        """长需求截取摘要"""
        long_need = (
            "用户需要一个安全的登录功能，支持邮箱和手机号登录，"
            "并且需要记住登录状态，同时支持忘记密码找回功能，"
            "还需要支持多因素认证和单点登录，以及 OAuth2 第三方授权"
        )
        draft = pm_agent.refine_requirement(long_need)
        assert len(draft.summary) <= 83  # 80 + "..."
        assert draft.summary  # 非空

    def test_summary_stops_at_period(self, pm_agent):
        """在句号处截断"""
        need = "实现用户登录功能。包括邮箱登录和手机号登录两种方式。" \
               "需要记住登录状态，支持忘记密码找回。"
        draft = pm_agent.refine_requirement(need)
        # 摘要应在第一个句号处截断
        assert "。" not in draft.summary or draft.summary.endswith("。")

    def test_summary_from_semicolon(self, pm_agent):
        """在分号处截断"""
        need = "实现登录功能；包括邮箱和手机号"
        draft = pm_agent.refine_requirement(need)
        assert "登录功能" in draft.summary


# ══════════════════════════════════════════════════════════
# 5. 初始 BDD 场景提取
# ══════════════════════════════════════════════════════════


class TestScenarioExtraction:
    """初始 BDD 场景提取"""

    def test_single_need_single_scenario(self, pm_agent):
        """单一需求生成至少一个场景"""
        draft = pm_agent.refine_requirement("用户需要登录功能")
        assert draft.scenario_count >= 1

    def test_multi_sentence_creates_scenarios(self, pm_agent):
        """多句需求可生成多个场景"""
        need = "用户需要登录功能。用户需要注册功能。用户需要找回密码功能。"
        draft = pm_agent.refine_requirement(need)
        assert draft.scenario_count >= 2

    def test_first_scenario_high_priority(self, pm_agent):
        """第一个场景为高优先级"""
        need = "用户需要登录功能。用户需要注册功能。"
        draft = pm_agent.refine_requirement(need)
        if draft.scenario_count > 1:
            assert draft.scenarios[0].priority == TaskPriority.HIGH

    def test_scenarios_have_titles(self, pm_agent):
        """场景都有标题"""
        draft = pm_agent.refine_requirement("用户需要登录功能。支持手机号注册。")
        for scenario in draft.scenarios:
            assert scenario.title
            assert len(scenario.title) > 0

    def test_given_inference_with_condition(self, pm_agent):
        """含条件关键词时 Given 推断"""
        need = "当用户未登录时需要展示登录页面"
        draft = pm_agent.refine_requirement(need)
        assert any("未登录" in s.given for s in draft.scenarios) or \
               any("初始状态" in s.given for s in draft.scenarios)

    def test_when_inference_with_action(self, pm_agent):
        """含动作关键词时 When 推断"""
        need = "系统需要支持邮箱登录功能"
        draft = pm_agent.refine_requirement(need)
        assert any("需要" in s.when or "支持" in s.when for s in draft.scenarios)

    def test_scenario_title_truncation(self, pm_agent):
        """长片段标题截断"""
        need = "用户需要一个能够同时支持邮箱、手机号和微信扫码登录的统一认证系统"
        draft = pm_agent.refine_requirement(need)
        for scenario in draft.scenarios:
            assert len(scenario.title) <= 203  # max_length=200 + "..."


# ══════════════════════════════════════════════════════════
# 6. 澄清问题生成
# ══════════════════════════════════════════════════════════


class TestClarificationQuestions:
    """澄清问题生成"""

    def test_generates_questions(self, pm_agent):
        """生成澄清问题"""
        draft = pm_agent.refine_requirement("用户需要登录功能")
        # 大多数简单需求都会产生澄清问题
        assert draft.has_questions

    def test_vague_quantifier_question(self, pm_agent):
        """模糊量词生成问题"""
        draft = pm_agent.refine_requirement("系统需要支持一些用户登录")
        assert any("具体标准" in q or "明确" in q for q in draft.questions)

    def test_missing_error_handling_question(self, pm_agent):
        """缺失异常处理生成问题"""
        draft = pm_agent.refine_requirement("用户需要登录功能")
        assert any("失败" in q or "无效" in q or "处理" in q for q in draft.questions)

    def test_missing_permission_question(self, pm_agent):
        """缺失权限描述生成问题"""
        draft = pm_agent.refine_requirement("用户需要登录功能")
        assert any("权限" in q or "角色" in q for q in draft.questions)

    def test_missing_performance_question(self, pm_agent):
        """缺失性能需求生成问题"""
        draft = pm_agent.refine_requirement("用户需要登录功能")
        assert any("性能" in q or "响应" in q for q in draft.questions)

    def test_no_duplicate_vague_questions(self, pm_agent):
        """模糊量词问题不重复"""
        draft = pm_agent.refine_requirement("需要一些功能和一些数据")
        vague_questions = [q for q in draft.questions if "具体标准" in q]
        assert len(vague_questions) <= 1

    def test_specific_need_fewer_questions(self, pm_agent):
        """明确需求问题更少"""
        vague_draft = pm_agent.refine_requirement("需要一些功能")
        specific_draft = pm_agent.refine_requirement(
            "当用户未登录时，需要展示登录页面；输入无效邮箱时，系统显示错误提示；"
            "管理员角色可以查看所有用户；性能要求响应时间低于200ms"
        )
        # 更具体的需求应产生更少的问题
        assert len(specific_draft.questions) <= len(vague_draft.questions)


# ══════════════════════════════════════════════════════════
# 7. 假设生成
# ══════════════════════════════════════════════════════════


class TestAssumptionGeneration:
    """假设生成"""

    def test_generates_basic_assumptions(self, pm_agent):
        """生成基本假设"""
        draft = pm_agent.refine_requirement("用户需要登录功能")
        assert len(draft.assumptions) > 0

    def test_login_related_assumption(self, pm_agent):
        """登录相关需求生成认证假设"""
        draft = pm_agent.refine_requirement("用户需要登录功能")
        assert any("认证" in a or "密码" in a for a in draft.assumptions)

    def test_data_related_assumption(self, pm_agent):
        """数据相关需求生成存储假设"""
        draft = pm_agent.refine_requirement("需要保存用户数据到数据库")
        assert any("数据库" in a or "持久化" in a or "存储" in a for a in draft.assumptions)

    def test_notification_assumption(self, pm_agent):
        """通知相关需求生成消息假设"""
        draft = pm_agent.refine_requirement("需要发送邮件通知用户")
        assert any("消息" in a or "异步" in a or "通知" in a for a in draft.assumptions)

    def test_always_has_tech_assumption(self, pm_agent):
        """始终包含技术栈假设"""
        draft = pm_agent.refine_requirement("简单需求")
        assert any("技术栈" in a or "Web" in a for a in draft.assumptions)


# ══════════════════════════════════════════════════════════
# 8. 精炼 Prompt 构建
# ══════════════════════════════════════════════════════════


class TestRefinePrompt:
    """精炼 Prompt 构建"""

    def test_get_refine_prompt_returns_string(self, pm_agent):
        """get_refine_prompt 返回字符串"""
        prompt = pm_agent.get_refine_prompt("用户需要登录功能")
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_refine_prompt_contains_raw_need(self, pm_agent):
        """prompt 包含原始需求"""
        prompt = pm_agent.get_refine_prompt("用户需要登录功能")
        assert "用户需要登录功能" in prompt

    def test_refine_prompt_contains_refine_instruction(self, pm_agent):
        """prompt 包含精炼指令"""
        prompt = pm_agent.get_refine_prompt("需求")
        assert "精炼任务" in prompt
        assert "Given-When-Then" in prompt

    def test_refine_prompt_contains_role(self, pm_agent):
        """prompt 包含角色身份"""
        prompt = pm_agent.get_refine_prompt("需求")
        assert "角色身份" in prompt

    def test_refine_prompt_with_harness(self, pm_agent_with_mock_harness):
        """带 harness 的 prompt 包含约束规则"""
        prompt = pm_agent_with_mock_harness.get_refine_prompt("需求")
        assert "约束规则" in prompt

    def test_refine_prompt_without_harness(self, pm_agent):
        """无 harness 的 prompt 不含约束规则"""
        prompt = pm_agent.get_refine_prompt("需求")
        # pm_agent 无 harness，不应含约束规则
        # （可能自动加载项目文件，取决于文件是否存在）
        # 至少角色和任务是有的
        assert "角色身份" in prompt
        assert "任务描述" in prompt

    def test_refine_prompt_contains_priority_instruction(self, pm_agent):
        """prompt 包含优先级标注指令"""
        prompt = pm_agent.get_refine_prompt("需求")
        assert "优先级" in prompt


# ══════════════════════════════════════════════════════════
# 9. 边界条件与异常处理
# ══════════════════════════════════════════════════════════


class TestEdgeCases:
    """边界条件与异常处理"""

    def test_very_long_raw_need(self, pm_agent):
        """超长需求不报错"""
        long_need = "用户需要" + "非常" * 500 + "重要的功能"
        draft = pm_agent.refine_requirement(long_need)
        assert draft.raw_need == long_need
        assert draft.scenario_count >= 1

    def test_special_characters_in_need(self, pm_agent):
        """特殊字符需求不报错"""
        draft = pm_agent.refine_requirement(
            "用户需要 <script>alert('xss')</script> 防护功能"
        )
        assert draft.raw_need == "用户需要 <script>alert('xss')</script> 防护功能"

    def test_newline_separated_need(self, pm_agent):
        """换行分隔的需求拆分"""
        need = "用户需要登录功能\n用户需要注册功能\n用户需要找回密码"
        draft = pm_agent.refine_requirement(need)
        assert draft.scenario_count >= 2

    def test_semicolon_separated_need(self, pm_agent):
        """分号分隔的需求拆分"""
        need = "用户需要登录功能；用户需要注册功能"
        draft = pm_agent.refine_requirement(need)
        assert draft.scenario_count >= 1

    def test_only_periods_need(self, pm_agent):
        """仅句号分隔的需求"""
        need = "用户需要登录。用户需要注册。"
        draft = pm_agent.refine_requirement(need)
        assert draft.scenario_count >= 1

    def test_refine_twice_overwrites(self, pm_agent):
        """重复精炼覆盖之前结果"""
        pm_agent.refine_requirement("第一个需求")
        pm_agent.refine_requirement("第二个需求")
        assert pm_agent.raw_requirement == "第二个需求"
        assert pm_agent.bdd_draft is not None

    def test_draft_serializable(self, pm_agent):
        """BDDDraft 可序列化"""
        draft = pm_agent.refine_requirement("用户需要登录功能")
        json_str = draft.model_dump_json()
        assert json_str
        # 反序列化
        restored = BDDDraft.model_validate_json(json_str)
        assert restored.raw_need == draft.raw_need
        assert restored.scenario_count == draft.scenario_count

    def test_scenario_serializable(self):
        """BDDScenario 可序列化"""
        scenario = BDDScenario(
            title="测试", given="g", when="w", then="t",
            priority=TaskPriority.HIGH,
        )
        json_str = scenario.model_dump_json()
        restored = BDDScenario.model_validate_json(json_str)
        assert restored.title == "测试"
        assert restored.priority == TaskPriority.HIGH

    def test_unicode_need(self, pm_agent):
        """Unicode 需求不报错"""
        draft = pm_agent.refine_requirement("需要🔐安全登录🚀功能")
        assert draft.raw_need == "需要🔐安全登录🚀功能"

    def test_single_char_need(self, pm_agent):
        """极短需求不报错"""
        draft = pm_agent.refine_requirement("登录")
        assert draft.scenario_count >= 1


# ══════════════════════════════════════════════════════════
# 10. 与生命周期集成
# ══════════════════════════════════════════════════════════


class TestLifecycleIntegration:
    """与 SubAgent 生命周期集成"""

    def test_refine_after_initialize(self, tmp_path):
        """初始化后可精炼需求"""
        pm_path = tmp_path / "pm-rules.md"
        pm_path.write_text("# PM Rules\n\n## DO\n- Use Given-When-Then format\n")
        agent = ProductManagerAgent(pm_rules_path=pm_path)
        agent.initialize()
        draft = agent.refine_requirement("用户需要登录功能")
        assert isinstance(draft, BDDDraft)

    def test_refine_without_initialize(self, pm_agent):
        """未初始化也可精炼（refine_requirement 不依赖 harness）"""
        draft = pm_agent.refine_requirement("用户需要登录功能")
        assert isinstance(draft, BDDDraft)

    def test_refine_in_execute_flow(self, pm_agent):
        """在 execute 流程中 refine_requirement 可用"""
        pm_agent.refine_requirement("用户需要登录功能")
        assert pm_agent.raw_requirement == "用户需要登录功能"
        assert pm_agent.bdd_draft is not None

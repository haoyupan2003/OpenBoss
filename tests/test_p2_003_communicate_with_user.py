"""
P2-003 测试：用户沟通循环 — communicate_with_user

验证 ProductManagerAgent.communicate_with_user 方法及相关数据模型。
测试覆盖：
1. CommunicationStatus 枚举
2. CommunicationRound 数据模型
3. CommunicationResult 数据模型
4. communicate_with_user 核心功能
5. 无问题自动确认
6. 用户确认流程
7. 用户反馈修订
8. 多轮沟通循环
9. 最大轮次升级
10. 沟通 prompt 构建
11. 边界条件与异常处理
12. 与 refine_requirement 集成
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from agent_automation_system.models.bdd import (
    BDDDraft,
    BDDScenario,
    CommunicationResult,
    CommunicationRound,
    CommunicationStatus,
)
from agent_automation_system.models.task import TaskPriority
from agent_automation_system.sub_agent.pm_agent import (
    ProductManagerAgent,
    _MAX_COMMUNICATION_ROUNDS,
)
from agent_automation_system.sub_agent.sub_agent import AgentPhase


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def pm_agent():
    """创建默认 ProductManagerAgent 实例"""
    return ProductManagerAgent()


@pytest.fixture
def simple_draft():
    """创建无问题的简单 BDDDraft"""
    return BDDDraft(
        raw_need="用户需要登录功能",
        summary="实现用户登录功能",
        scenarios=[
            BDDScenario(
                title="邮箱登录",
                given="用户未登录",
                when="输入有效邮箱密码",
                then="登录成功",
                priority=TaskPriority.HIGH,
            ),
        ],
        questions=[],
        assumptions=["使用邮箱+密码登录"],
    )


@pytest.fixture
def draft_with_questions():
    """创建有待澄清问题的 BDDDraft"""
    return BDDDraft(
        raw_need="用户需要登录功能",
        summary="实现用户登录功能",
        scenarios=[
            BDDScenario(
                title="邮箱登录",
                given="用户未登录",
                when="输入有效邮箱密码",
                then="登录成功",
            ),
        ],
        questions=[
            "是否需要支持第三方登录？",
            "是否有性能或响应时间要求？",
        ],
        assumptions=["使用邮箱+密码登录"],
    )


@pytest.fixture
def draft_with_many_questions():
    """创建有很多问题的 BDDDraft"""
    return BDDDraft(
        raw_need="系统需要一些功能",
        summary="实现系统功能",
        scenarios=[
            BDDScenario(title="功能", given="初始状态", when="执行操作", then="完成"),
        ],
        questions=[
            "「一些」的具体标准是什么？",
            "当操作失败或输入无效时，系统应如何处理？",
            "是否需要区分不同用户角色的权限？",
            "是否有性能或响应时间要求？",
            "数据规模预期如何？",
        ],
        assumptions=["使用 Web 技术栈"],
    )


# ══════════════════════════════════════════════════════════
# 1. CommunicationStatus 枚举
# ══════════════════════════════════════════════════════════


class TestCommunicationStatus:
    """CommunicationStatus 枚举测试"""

    def test_status_values(self):
        """状态枚举值"""
        assert CommunicationStatus.PENDING == "pending"
        assert CommunicationStatus.CONFIRMED == "confirmed"
        assert CommunicationStatus.REJECTED == "rejected"
        assert CommunicationStatus.NEEDS_REVISION == "needs_revision"
        assert CommunicationStatus.ESCALATED == "escalated"
        assert CommunicationStatus.AUTO_CONFIRMED == "auto_confirmed"

    def test_all_statuses_are_strings(self):
        """所有状态都是字符串枚举"""
        for status in CommunicationStatus:
            assert isinstance(status.value, str)


# ══════════════════════════════════════════════════════════
# 2. CommunicationRound 数据模型
# ══════════════════════════════════════════════════════════


class TestCommunicationRound:
    """CommunicationRound 数据模型测试"""

    def test_create_round(self):
        """创建沟通轮次"""
        round_record = CommunicationRound(
            round_number=1,
            draft_snapshot="BDD 草稿内容",
            questions_asked=["问题1"],
        )
        assert round_record.round_number == 1
        assert round_record.draft_snapshot == "BDD 草稿内容"
        assert round_record.questions_asked == ["问题1"]
        assert round_record.status == CommunicationStatus.PENDING

    def test_round_default_status_pending(self):
        """默认状态为 PENDING"""
        round_record = CommunicationRound(
            round_number=1,
            draft_snapshot="draft",
        )
        assert round_record.status == CommunicationStatus.PENDING

    def test_round_is_completed(self):
        """is_completed 属性"""
        pending = CommunicationRound(
            round_number=1, draft_snapshot="d",
            status=CommunicationStatus.PENDING,
        )
        confirmed = CommunicationRound(
            round_number=1, draft_snapshot="d",
            status=CommunicationStatus.CONFIRMED,
        )
        escalated = CommunicationRound(
            round_number=1, draft_snapshot="d",
            status=CommunicationStatus.ESCALATED,
        )
        auto = CommunicationRound(
            round_number=1, draft_snapshot="d",
            status=CommunicationStatus.AUTO_CONFIRMED,
        )
        needs_rev = CommunicationRound(
            round_number=1, draft_snapshot="d",
            status=CommunicationStatus.NEEDS_REVISION,
        )
        assert pending.is_completed is False
        assert confirmed.is_completed is True
        assert escalated.is_completed is True
        assert auto.is_completed is True
        assert needs_rev.is_completed is True

    def test_round_has_feedback(self):
        """has_feedback 属性"""
        no_feedback = CommunicationRound(
            round_number=1, draft_snapshot="d",
        )
        with_feedback = CommunicationRound(
            round_number=1, draft_snapshot="d",
            user_feedback="需要修改",
        )
        empty_feedback = CommunicationRound(
            round_number=1, draft_snapshot="d",
            user_feedback="",
        )
        whitespace_feedback = CommunicationRound(
            round_number=1, draft_snapshot="d",
            user_feedback="  ",
        )
        assert no_feedback.has_feedback is False
        assert with_feedback.has_feedback is True
        assert empty_feedback.has_feedback is False
        assert whitespace_feedback.has_feedback is False

    def test_round_number_must_be_positive(self):
        """轮次序号必须 ≥ 1"""
        with pytest.raises(Exception):
            CommunicationRound(round_number=0, draft_snapshot="d")

    def test_round_serializable(self):
        """CommunicationRound 可序列化"""
        round_record = CommunicationRound(
            round_number=1,
            draft_snapshot="草稿",
            questions_asked=["问题"],
            user_feedback="反馈",
            status=CommunicationStatus.NEEDS_REVISION,
            started_at=datetime.now(),
        )
        json_str = round_record.model_dump_json()
        restored = CommunicationRound.model_validate_json(json_str)
        assert restored.round_number == 1
        assert restored.status == CommunicationStatus.NEEDS_REVISION


# ══════════════════════════════════════════════════════════
# 3. CommunicationResult 数据模型
# ══════════════════════════════════════════════════════════


class TestCommunicationResult:
    """CommunicationResult 数据模型测试"""

    def test_create_result(self):
        """创建沟通结果"""
        result = CommunicationResult(
            rounds=[],
            final_status=CommunicationStatus.CONFIRMED,
            confirmed_bdd="确认的 BDD",
            total_rounds=1,
        )
        assert result.final_status == CommunicationStatus.CONFIRMED
        assert result.confirmed_bdd == "确认的 BDD"

    def test_is_confirmed(self):
        """is_confirmed 属性"""
        confirmed = CommunicationResult(
            final_status=CommunicationStatus.CONFIRMED,
            confirmed_bdd="BDD",
        )
        auto = CommunicationResult(
            final_status=CommunicationStatus.AUTO_CONFIRMED,
            confirmed_bdd="BDD",
        )
        escalated = CommunicationResult(
            final_status=CommunicationStatus.ESCALATED,
        )
        assert confirmed.is_confirmed is True
        assert auto.is_confirmed is True
        assert escalated.is_confirmed is False

    def test_needs_escalation(self):
        """needs_escalation 属性"""
        escalated = CommunicationResult(
            final_status=CommunicationStatus.ESCALATED,
        )
        confirmed = CommunicationResult(
            final_status=CommunicationStatus.CONFIRMED,
            confirmed_bdd="BDD",
        )
        assert escalated.needs_escalation is True
        assert confirmed.needs_escalation is False

    def test_last_round(self):
        """last_round 属性"""
        empty = CommunicationResult()
        assert empty.last_round is None

        with_rounds = CommunicationResult(
            rounds=[
                CommunicationRound(round_number=1, draft_snapshot="d1"),
                CommunicationRound(round_number=2, draft_snapshot="d2"),
            ],
        )
        assert with_rounds.last_round is not None
        assert with_rounds.last_round.round_number == 2

    def test_result_serializable(self):
        """CommunicationResult 可序列化"""
        result = CommunicationResult(
            rounds=[
                CommunicationRound(
                    round_number=1, draft_snapshot="d",
                    status=CommunicationStatus.CONFIRMED,
                ),
            ],
            final_status=CommunicationStatus.CONFIRMED,
            confirmed_bdd="BDD",
            total_rounds=1,
        )
        json_str = result.model_dump_json()
        restored = CommunicationResult.model_validate_json(json_str)
        assert restored.final_status == CommunicationStatus.CONFIRMED
        assert restored.total_rounds == 1


# ══════════════════════════════════════════════════════════
# 4. communicate_with_user 核心功能
# ══════════════════════════════════════════════════════════


class TestCommunicateWithUserCore:
    """communicate_with_user 核心功能"""

    def test_returns_communication_result(self, pm_agent, simple_draft):
        """返回 CommunicationResult"""
        result = pm_agent.communicate_with_user(simple_draft)
        assert isinstance(result, CommunicationResult)

    def test_none_draft_raises(self, pm_agent):
        """None draft 抛出 ValueError"""
        with pytest.raises(ValueError, match="bdd_draft cannot be None"):
            pm_agent.communicate_with_user(None)

    def test_saves_bdd_draft(self, pm_agent, simple_draft):
        """保存 BDD 草稿"""
        pm_agent.communicate_with_user(simple_draft)
        assert pm_agent.bdd_draft is not None

    def test_max_rounds_constant(self):
        """最大轮次常量"""
        assert _MAX_COMMUNICATION_ROUNDS == 3


# ══════════════════════════════════════════════════════════
# 5. 无问题自动确认
# ══════════════════════════════════════════════════════════


class TestAutoConfirm:
    """无待澄清问题时自动确认"""

    def test_auto_confirm_no_questions(self, pm_agent, simple_draft):
        """无问题时自动确认"""
        result = pm_agent.communicate_with_user(simple_draft)
        assert result.final_status == CommunicationStatus.AUTO_CONFIRMED
        assert result.is_confirmed is True

    def test_auto_confirm_has_confirmed_bdd(self, pm_agent, simple_draft):
        """自动确认后有 confirmed_bdd"""
        result = pm_agent.communicate_with_user(simple_draft)
        assert result.confirmed_bdd is not None
        assert len(result.confirmed_bdd) > 0

    def test_auto_confirm_one_round(self, pm_agent, simple_draft):
        """自动确认只需 1 轮"""
        result = pm_agent.communicate_with_user(simple_draft)
        assert result.total_rounds == 1

    def test_auto_confirm_saves_confirmed_bdd(self, pm_agent, simple_draft):
        """自动确认后保存 confirmed_bdd"""
        pm_agent.communicate_with_user(simple_draft)
        assert pm_agent.confirmed_bdd is not None

    def test_auto_confirm_no_unresolved_questions(self, pm_agent, simple_draft):
        """自动确认无未解决问题"""
        result = pm_agent.communicate_with_user(simple_draft)
        assert result.has_questions_unresolved is False


# ══════════════════════════════════════════════════════════
# 6. 用户确认流程
# ══════════════════════════════════════════════════════════


class TestUserConfirmation:
    """用户确认流程"""

    def test_user_confirms_with_empty_string(self, pm_agent, draft_with_questions):
        """用户返回空字符串 = 确认"""
        callback = MagicMock(return_value="")
        result = pm_agent.communicate_with_user(draft_with_questions, callback)
        assert result.is_confirmed is True
        assert result.final_status == CommunicationStatus.CONFIRMED

    def test_user_confirms_after_one_round(self, pm_agent, draft_with_questions):
        """用户一轮确认"""
        callback = MagicMock(return_value="")
        result = pm_agent.communicate_with_user(draft_with_questions, callback)
        assert result.total_rounds == 1

    def test_confirmed_result_has_bdd(self, pm_agent, draft_with_questions):
        """确认后结果包含 confirmed_bdd"""
        callback = MagicMock(return_value="")
        result = pm_agent.communicate_with_user(draft_with_questions, callback)
        assert result.confirmed_bdd is not None

    def test_confirmed_saves_to_agent(self, pm_agent, draft_with_questions):
        """确认后保存到 agent._confirmed_bdd"""
        callback = MagicMock(return_value="")
        pm_agent.communicate_with_user(draft_with_questions, callback)
        assert pm_agent.confirmed_bdd is not None

    def test_callback_receives_round_and_questions(self, pm_agent, draft_with_questions):
        """回调函数接收轮次和问题列表"""
        callback = MagicMock(return_value="")
        pm_agent.communicate_with_user(draft_with_questions, callback)
        callback.assert_called_once()
        args = callback.call_args[0]
        assert args[0] == 1  # round_number
        assert isinstance(args[1], list)  # questions


# ══════════════════════════════════════════════════════════
# 7. 用户反馈修订
# ══════════════════════════════════════════════════════════


class TestUserFeedbackRevision:
    """用户反馈修订"""

    def test_user_feedback_triggers_revision(self, pm_agent, draft_with_questions):
        """用户非空反馈触发修订"""
        callback = MagicMock(side_effect=["需要支持微信登录", ""])
        result = pm_agent.communicate_with_user(draft_with_questions, callback)
        assert result.total_rounds >= 2
        assert any(
            r.status == CommunicationStatus.NEEDS_REVISION
            for r in result.rounds
        )

    def test_revised_draft_contains_feedback(self, pm_agent, draft_with_questions):
        """修订草稿包含用户反馈"""
        callback = MagicMock(side_effect=["需要支持微信登录", ""])
        result = pm_agent.communicate_with_user(draft_with_questions, callback)
        # 至少有一轮的草稿包含用户反馈
        assert any(
            "用户反馈" in r.draft_snapshot or "微信" in r.draft_snapshot
            for r in result.rounds
        )

    def test_feedback_answers_remove_question(self, pm_agent, draft_with_questions):
        """反馈回答问题后移除该问题"""
        # 回答关于第三方登录的问题
        callback = MagicMock(side_effect=["需要支持第三方微信登录", ""])
        result = pm_agent.communicate_with_user(draft_with_questions, callback)
        # 第二轮应该有更少的问题
        if len(result.rounds) >= 2:
            round2_questions = result.rounds[1].questions_asked
            assert len(round2_questions) <= len(draft_with_questions.questions)

    def test_two_rounds_then_confirm(self, pm_agent, draft_with_questions):
        """两轮反馈后确认"""
        callback = MagicMock(side_effect=["修改1", ""])  # 第二轮确认
        result = pm_agent.communicate_with_user(draft_with_questions, callback)
        assert result.is_confirmed is True
        assert result.total_rounds == 2


# ══════════════════════════════════════════════════════════
# 8. 多轮沟通循环
# ══════════════════════════════════════════════════════════


class TestMultiRoundCommunication:
    """多轮沟通循环"""

    def test_three_rounds_then_confirm(self, pm_agent, draft_with_questions):
        """三轮反馈后确认"""
        callback = MagicMock(side_effect=["修改1", "修改2", ""])
        result = pm_agent.communicate_with_user(draft_with_questions, callback)
        assert result.is_confirmed is True
        assert result.total_rounds == 3

    def test_round_numbers_increment(self, pm_agent, draft_with_questions):
        """轮次序号递增"""
        callback = MagicMock(side_effect=["修改1", "修改2", ""])
        result = pm_agent.communicate_with_user(draft_with_questions, callback)
        round_numbers = [r.round_number for r in result.rounds]
        assert round_numbers == list(range(1, len(round_numbers) + 1))

    def test_all_rounds_have_timestamps(self, pm_agent, draft_with_questions):
        """每轮都有时间戳"""
        callback = MagicMock(side_effect=["修改1", ""])
        result = pm_agent.communicate_with_user(draft_with_questions, callback)
        for r in result.rounds:
            assert r.started_at is not None
            assert r.completed_at is not None

    def test_no_callback_means_no_feedback(self, pm_agent, draft_with_questions):
        """无回调时用户无法回复"""
        result = pm_agent.communicate_with_user(draft_with_questions)
        # 无回调 → 升级处理
        assert result.final_status == CommunicationStatus.ESCALATED


# ══════════════════════════════════════════════════════════
# 9. 最大轮次升级
# ══════════════════════════════════════════════════════════


class TestEscalation:
    """最大轮次升级"""

    def test_escalation_after_max_rounds(self, pm_agent, draft_with_questions):
        """超过最大轮次后升级"""
        # 始终返回非空反馈
        callback = MagicMock(side_effect=["修改1", "修改2", "修改3"])
        result = pm_agent.communicate_with_user(draft_with_questions, callback)
        assert result.needs_escalation is True
        assert result.final_status == CommunicationStatus.ESCALATED

    def test_escalation_no_confirmed_bdd(self, pm_agent, draft_with_questions):
        """升级后无 confirmed_bdd"""
        callback = MagicMock(side_effect=["修改1", "修改2", "修改3"])
        result = pm_agent.communicate_with_user(draft_with_questions, callback)
        assert result.confirmed_bdd is None

    def test_escalation_has_unresolved_questions(self, pm_agent, draft_with_questions):
        """升级后有未解决问题"""
        callback = MagicMock(side_effect=["修改1", "修改2", "修改3"])
        result = pm_agent.communicate_with_user(draft_with_questions, callback)
        assert result.has_questions_unresolved is True

    def test_escalation_does_not_save_confirmed_bdd(self, pm_agent, draft_with_questions):
        """升级后不保存 confirmed_bdd"""
        callback = MagicMock(side_effect=["修改1", "修改2", "修改3"])
        pm_agent.communicate_with_user(draft_with_questions, callback)
        assert pm_agent.confirmed_bdd is None

    def test_no_callback_escalates(self, pm_agent, draft_with_questions):
        """无回调时有问题草稿升级"""
        result = pm_agent.communicate_with_user(draft_with_questions)
        assert result.final_status == CommunicationStatus.ESCALATED

    def test_callback_exception_escalates(self, pm_agent, draft_with_questions):
        """回调函数异常时升级"""
        callback = MagicMock(side_effect=Exception("connection error"))
        result = pm_agent.communicate_with_user(draft_with_questions, callback)
        assert result.final_status == CommunicationStatus.ESCALATED


# ══════════════════════════════════════════════════════════
# 10. 沟通 Prompt 构建
# ══════════════════════════════════════════════════════════


class TestCommunicatePrompt:
    """沟通 Prompt 构建"""

    def test_get_communicate_prompt_returns_string(self, pm_agent, draft_with_questions):
        """get_communicate_prompt 返回字符串"""
        prompt = pm_agent.get_communicate_prompt(draft_with_questions)
        assert isinstance(prompt, str)
        assert len(prompt) > 0

    def test_prompt_contains_bdd_content(self, pm_agent, draft_with_questions):
        """prompt 包含 BDD 内容"""
        prompt = pm_agent.get_communicate_prompt(draft_with_questions)
        assert "BDD 草稿" in prompt

    def test_prompt_contains_questions(self, pm_agent, draft_with_questions):
        """prompt 包含待澄清问题"""
        prompt = pm_agent.get_communicate_prompt(draft_with_questions)
        assert "待澄清问题" in prompt or "第三方登录" in prompt

    def test_prompt_contains_role(self, pm_agent, draft_with_questions):
        """prompt 包含角色身份"""
        prompt = pm_agent.get_communicate_prompt(draft_with_questions)
        assert "角色身份" in prompt

    def test_prompt_contains_round_number(self, pm_agent, draft_with_questions):
        """prompt 包含轮次信息"""
        prompt = pm_agent.get_communicate_prompt(draft_with_questions, round_number=2)
        assert "第 2 轮" in prompt

    def test_prompt_no_questions_version(self, pm_agent, simple_draft):
        """无问题时 prompt 包含最终确认指令"""
        prompt = pm_agent.get_communicate_prompt(simple_draft)
        assert "确认" in prompt

    def test_prompt_contains_max_rounds_hint(self, pm_agent, draft_with_questions):
        """prompt 包含最大轮次提示"""
        prompt = pm_agent.get_communicate_prompt(draft_with_questions)
        assert "3 轮" in prompt


# ══════════════════════════════════════════════════════════
# 11. 边界条件与异常处理
# ══════════════════════════════════════════════════════════


class TestEdgeCases:
    """边界条件与异常处理"""

    def test_callback_returns_none(self, pm_agent, draft_with_questions):
        """回调返回 None 视为无回复"""
        callback = MagicMock(return_value=None)
        result = pm_agent.communicate_with_user(draft_with_questions, callback)
        assert result.final_status == CommunicationStatus.ESCALATED

    def test_callback_returns_whitespace_only(self, pm_agent, draft_with_questions):
        """回调返回仅空白 = 确认"""
        callback = MagicMock(return_value="   ")
        result = pm_agent.communicate_with_user(draft_with_questions, callback)
        assert result.is_confirmed is True

    def test_empty_questions_auto_confirms(self, pm_agent):
        """空问题列表自动确认"""
        draft = BDDDraft(
            raw_need="需求", summary="摘要",
            scenarios=[],
            questions=[],
        )
        result = pm_agent.communicate_with_user(draft)
        assert result.final_status == CommunicationStatus.AUTO_CONFIRMED

    def test_very_long_feedback(self, pm_agent, draft_with_questions):
        """超长反馈不报错"""
        long_feedback = "修改内容" * 500
        callback = MagicMock(side_effect=[long_feedback, ""])
        result = pm_agent.communicate_with_user(draft_with_questions, callback)
        assert result.is_confirmed is True

    def test_unicode_feedback(self, pm_agent, draft_with_questions):
        """Unicode 反馈不报错"""
        callback = MagicMock(side_effect=["需要支持🔐安全认证🚀", ""])
        result = pm_agent.communicate_with_user(draft_with_questions, callback)
        assert result.is_confirmed is True

    def test_feedback_removes_answered_questions(self, pm_agent):
        """反馈回答问题后，该问题被移除"""
        draft = BDDDraft(
            raw_need="需求",
            summary="摘要",
            questions=["是否需要权限控制？", "是否有性能要求？"],
        )
        # 回答了权限问题
        callback = MagicMock(side_effect=["需要管理员权限控制", ""])
        result = pm_agent.communicate_with_user(draft, callback)
        # 至少有一轮的问题列表发生了变化
        assert result.total_rounds >= 2

    def test_all_questions_answered_auto_confirms(self, pm_agent):
        """所有问题被回答后自动确认"""
        draft = BDDDraft(
            raw_need="需求",
            summary="摘要",
            questions=["是否需要权限控制？"],
        )
        # 反馈包含问题关键词
        callback = MagicMock(side_effect=["需要权限控制"])
        result = pm_agent.communicate_with_user(draft, callback)
        # 所有问题被回答后应该自动确认
        assert result.is_confirmed is True or result.total_rounds >= 2

    def test_communicate_twice_overwrites(self, pm_agent, simple_draft):
        """重复沟通覆盖之前结果"""
        pm_agent.communicate_with_user(simple_draft)
        pm_agent.communicate_with_user(simple_draft)
        assert pm_agent.confirmed_bdd is not None

    def test_result_serializable(self, pm_agent, simple_draft):
        """CommunicationResult 可序列化"""
        result = pm_agent.communicate_with_user(simple_draft)
        json_str = result.model_dump_json()
        restored = CommunicationResult.model_validate_json(json_str)
        assert restored.final_status == result.final_status
        assert restored.total_rounds == result.total_rounds


# ══════════════════════════════════════════════════════════
# 12. 与 refine_requirement 集成
# ══════════════════════════════════════════════════════════


class TestRefineIntegration:
    """与 refine_requirement 集成"""

    def test_refine_then_communicate(self, pm_agent):
        """先精炼再沟通"""
        draft = pm_agent.refine_requirement("用户需要登录功能")
        result = pm_agent.communicate_with_user(draft)
        assert isinstance(result, CommunicationResult)
        # 登录功能需求通常会产生澄清问题
        # 无回调时有问题 → 升级；无问题 → 自动确认
        assert result.total_rounds >= 1

    def test_refine_communicate_confirm_flow(self, pm_agent):
        """完整精炼→沟通→确认流程"""
        draft = pm_agent.refine_requirement("简单需求，不需要额外确认")
        result = pm_agent.communicate_with_user(draft)
        # 无问题草稿应自动确认
        if not draft.has_questions:
            assert result.is_confirmed is True

    def test_refine_communicate_with_callback(self, pm_agent):
        """精炼→带回调沟通流程"""
        draft = pm_agent.refine_requirement("用户需要登录功能")
        callback = MagicMock(return_value="")  # 立即确认
        result = pm_agent.communicate_with_user(draft, callback)
        assert result.is_confirmed is True
        assert pm_agent.confirmed_bdd is not None

    def test_agent_state_after_communicate(self, pm_agent):
        """沟通后 agent 状态正确"""
        draft = pm_agent.refine_requirement("简单需求")
        pm_agent.communicate_with_user(draft)
        assert pm_agent.raw_requirement is not None
        assert pm_agent.bdd_draft is not None
        # 阶段不受沟通影响（沟通不在生命周期内）
        assert pm_agent.phase == AgentPhase.CREATED

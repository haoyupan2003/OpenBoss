"""
P2-026 测试：BDDValidator 单元测试

测试 BDDValidator.verify() 对各种 Given-When-Then 场景的验证能力。
覆盖：
1. BDDValidationResult 数据模型
2. 完全匹配（given/when/then 全部通过）
3. 部分匹配（各段独立验证）
4. 不匹配场景（全错 / 部分错）
5. 关键词提取与匹配逻辑
6. 否定词检测（前置否定排除）
7. min_score 阈值控制
8. 边界条件（空输入、None、单字、纯英文）
9. BDDSpec 和 dict 两种输入格式
10. to_text / summary 可读输出
"""

import pytest

from agent_automation_system.scheduler.bdd_validator import (
    BDDValidationResult,
    BDDValidator,
)
from agent_automation_system.models.task import BDDSpec


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def validator():
    """默认 BDDValidator 实例"""
    return BDDValidator()


@pytest.fixture
def validator_strict():
    """严格模式：min_score=0.6"""
    return BDDValidator(min_score=0.6)


@pytest.fixture
def validator_loose():
    """宽松模式：min_score=0.01"""
    return BDDValidator(min_score=0.01)


@pytest.fixture
def login_bdd():
    """登录场景 BDD"""
    return BDDSpec(
        given="用户已注册账号且未登录",
        when="用户输入正确的用户名和密码并点击登录",
        then="系统返回认证 token 并跳转到首页",
    )


@pytest.fixture
def order_bdd():
    """订单创建 BDD"""
    return BDDSpec(
        given="用户已登录并选择了商品",
        when="用户点击提交订单按钮",
        then="系统创建订单并显示订单编号和支付页面",
    )


@pytest.fixture
def perfect_result():
    """完美匹配的登录结果文本"""
    return (
        "用户已注册账号且未登录，系统验证通过。"
        "用户输入正确的用户名和密码并点击登录按钮后，"
        "系统返回认证 token abc123 并跳转到首页。"
    )


@pytest.fixture
def partial_result():
    """部分匹配的结果"""
    return (
        "系统返回了认证 token。页面跳转到了首页。"
    )


@pytest.fixture
def wrong_result():
    """完全不匹配的结果"""
    return "注册功能正在维护中，请稍后再试。"


@pytest.fixture
def order_result():
    """订单创建执行结果"""
    return (
        "系统验证用户已登录并选择了商品。"
        "用户点击提交订单按钮后，"
        "系统创建订单编号 ORD-001 并显示支付页面。"
    )


# ── BDDValidationResult 模型测试 ──────────────────────────


class TestBDDValidationResult:
    """BDDValidationResult 数据模型"""

    def test_all_passed_true(self):
        r = BDDValidationResult(
            passed=True,
            given_passed=True,
            when_passed=True,
            then_passed=True,
            score=1.0,
            summary="3/3 passed",
        )
        assert r.passed is True
        assert r.all_passed is True
        assert r.partial_score == (3, 3)

    def test_partial_pass(self):
        r = BDDValidationResult(
            given_passed=True,
            when_passed=False,
            then_passed=True,
            score=0.67,
        )
        assert r.passed is False
        assert r.all_passed is False
        assert r.partial_score == (2, 3)

    def test_all_failed(self):
        r = BDDValidationResult(
            given_passed=False,
            when_passed=False,
            then_passed=False,
            score=0.0,
        )
        assert r.passed is False
        assert r.all_passed is False
        assert r.partial_score == (0, 3)

    def test_defaults(self):
        r = BDDValidationResult()
        assert r.passed is False
        assert r.given_passed is False
        assert r.score == 0.0
        assert r.summary == ""


# ── 完全匹配场景 ──────────────────────────────────────────


class TestBDDValidatorFullMatch:
    """完全匹配：所有 3 段通过"""

    def test_perfect_match_with_spec(self, validator, login_bdd, perfect_result):
        """BDDSpec 完美匹配"""
        r = validator.verify(perfect_result, login_bdd)
        assert r.passed is True
        assert r.given_passed is True
        assert r.when_passed is True
        assert r.then_passed is True
        assert r.score == 1.0
        assert "3/3 passed" in r.summary

    def test_perfect_match_with_dict(self, validator, perfect_result):
        """dict 格式完美匹配"""
        bdd_dict = {
            "given": "用户已注册账号且未登录",
            "when": "用户输入正确的用户名和密码并点击登录",
            "then": "系统返回认证 token 并跳转到首页",
        }
        r = validator.verify(perfect_result, bdd_dict)
        assert r.passed is True
        assert r.score == 1.0

    def test_order_full_match(self, validator, order_bdd, order_result):
        """订单场景完美匹配"""
        r = validator.verify(order_result, order_bdd)
        assert r.passed is True
        assert r.given_passed is True
        assert r.when_passed is True
        assert r.then_passed is True

    def test_details_contain_labels(self, validator, login_bdd, perfect_result):
        """详情包含 Given/When/Then 标签"""
        r = validator.verify(perfect_result, login_bdd)
        assert "Given:" in r.given_detail
        assert "When:" in r.when_detail
        assert "Then:" in r.then_detail

    def test_details_contain_scores(self, validator, login_bdd, perfect_result):
        """详情包含匹配分数"""
        r = validator.verify(perfect_result, login_bdd)
        assert "score=" in r.given_detail
        assert "score=" in r.when_detail
        assert "score=" in r.then_detail

    def test_summary_format(self, validator, login_bdd, perfect_result):
        """summary 格式正确"""
        r = validator.verify(perfect_result, login_bdd)
        assert "3/3" in r.summary
        for expected in ["Given", "When", "Then"]:
            assert expected in r.summary


# ── 部分匹配场景 ──────────────────────────────────────────


class TestBDDValidatorPartialMatch:
    """部分匹配：部分段通过"""

    def test_only_then_passed(self, validator, login_bdd, partial_result):
        """仅 Then 匹配"""
        r = validator.verify(partial_result, login_bdd)
        assert r.passed is False
        # partial_result 有 "token" 和 "首页" → Then 应该匹配
        assert r.then_passed is True
        # Given/When 没有关键词
        assert r.given_passed is False
        assert r.when_passed is False
        assert r.score < 1.0

    def test_given_when_missing(self, validator, login_bdd):
        """Given/When 缺失的结果 → 仅少量关键词命中"""
        result = "token 已生成，页面已跳转"
        r = validator.verify(result, login_bdd)
        # 短文本只命中 then 中少数字 → 整体分数不到 0.3
        assert r.then_passed is False
        assert r.passed is False

    def test_two_of_three(self, validator, login_bdd):
        """三中二"""
        result = "用户已注册账号。输入正确的用户名和密码后，系统正常处理。"
        r = validator.verify(result, login_bdd)
        # Given 有 "用户已注册账号"
        # When 有 "输入正确的用户名和密码"
        # Then 没有 token 或首页
        assert r.given_passed is True
        assert r.when_passed is True
        assert r.then_passed is False
        assert round(r.score, 2) == 0.67


# ── 完全不匹配场景 ────────────────────────────────────────


class TestBDDValidatorNoMatch:
    """完全不匹配"""

    def test_completely_wrong(self, validator, login_bdd, wrong_result):
        """完全无关结果"""
        r = validator.verify(wrong_result, login_bdd)
        assert r.passed is False
        assert r.given_passed is False
        assert r.when_passed is False
        assert r.then_passed is False
        assert r.score == 0.0

    def test_empty_result(self, validator, login_bdd):
        """空结果"""
        r = validator.verify("", login_bdd)
        assert r.passed is False
        assert r.score == 0.0

    def test_result_is_none(self, validator, login_bdd):
        """None 结果"""
        r = validator.verify(None, login_bdd)
        assert r.passed is False
        assert r.score == 0.0


# ── 关键词提取测试 ────────────────────────────────────────


class TestBDDValidatorKeywordExtraction:
    """关键词提取逻辑"""

    def test_chinese_keywords(self, validator):
        """中文关键词提取"""
        kw = validator._extract_keywords("用户登录系统后查看订单列表")
        assert "用户" in kw
        assert "登录" in kw
        assert "系统" in kw
        assert "查看" in kw
        assert "订单" in kw
        assert "列表" in kw

    def test_mixed_keywords(self, validator):
        """中英混合"""
        kw = validator._extract_keywords("返回 HTTP 200 状态码和 token")
        assert "返回" in kw  # 中文 2-gram
        assert "http" in kw  # 英文小写
        assert "token" in kw
        # 单字符英文忽略
        assert all(len(w) > 1 for w in kw)

    def test_duplicates_removed(self, validator):
        """去重"""
        kw = validator._extract_keywords("用户用户用户登录登录")
        # "用户" 和 "登录" 应该各出现一次
        user_count = sum(1 for w in kw if w == "用户")
        login_count = sum(1 for w in kw if w == "登录")
        assert user_count == 1
        assert login_count == 1

    def test_single_char_ignored(self, validator):
        """单字被忽略"""
        kw = validator._extract_keywords("a b c 你好 world")
        assert "你好" in kw
        assert "world" in kw
        for w in kw:
            assert len(w) > 1

    def test_empty_text(self, validator):
        """空文本"""
        kw = validator._extract_keywords("")
        assert kw == []

    def test_numbers_only(self, validator):
        """纯数字"""
        kw = validator._extract_keywords("123 456 789")
        assert kw == []


# ─── 否定词检测 ───────────────────────────────────────────


class TestBDDValidatorNegation:
    """否定词上下文检测"""

    def test_positive_match_no_negation(self, validator):
        """正向匹配：没有否定词"""
        text = "用户成功登录系统"
        assert validator._is_negated(text, "登录") is False

    def test_negated_by_bu(self, validator):
        """被「不」否定"""
        text = "用户不能登录系统"
        assert validator._is_negated(text, "登录") is True

    def test_negated_by_wei(self, validator):
        """被「未」否定"""
        text = "用户尚未登录"
        assert validator._is_negated(text, "登录") is True

    def test_negated_by_wufa(self, validator):
        """被「无法」否定"""
        text = "系统无法返回 token"
        assert validator._is_negated(text, "token") is True

    def test_keyword_not_found(self, validator):
        """关键词根本不存在"""
        assert validator._is_negated("some text", "absent") is False

    def test_keyword_at_start(self, validator):
        """关键词在文本开头"""
        # "登录" 在开头，前面没有否定词
        assert validator._is_negated("登录功能正常", "登录") is False

    def test_multiple_negators(self, validator):
        """多个否定词"""
        assert validator._is_negated("不成功不登录", "登录") is True
        assert validator._is_negated("未能正常登录", "登录") is True

    def test_negation_in_verify(self, validator):
        """否定影响 verify 结果"""
        bdd = BDDSpec(
            given="用户已登录",
            when="用户点击按钮",
            then="系统返回数据",
        )
        # 结果中说 "未" 返回数据
        r = validator.verify("系统未返回数据，用户无法登录", bdd)
        # "登录" 被 "未/无法" 否定 → given 不通过
        # "数据" 被 "未" 否定 → then 不通过
        assert r.then_passed is False


# ── min_score 阈值控制 ────────────────────────────────────


class TestBDDValidatorThreshold:
    """min_score 阈值控制"""

    def test_strict_threshold_blocks_partial(self, validator_strict, login_bdd, partial_result):
        """严格阈值阻断部分匹配"""
        r = validator_strict.verify(partial_result, login_bdd)
        # partial_result 含 "token" 和 "首页" → then 的关键词匹配数少
        # strict=0.6 可能让 then 也不通过
        assert r.passed is False

    def test_loose_threshold_allows_partial(self, validator_loose, login_bdd):
        """宽松阈值通过微弱匹配"""
        r = validator_loose.verify("token", login_bdd)
        # "token" 匹配 then 中的一个词，min_score=0.01 应该通过 then
        assert r.then_passed is True

    def test_min_score_validation(self):
        """min_score 参数校验"""
        with pytest.raises(ValueError, match="0.0~1.0"):
            BDDValidator(min_score=-0.1)
        with pytest.raises(ValueError, match="0.0~1.0"):
            BDDValidator(min_score=1.5)

    def test_min_score_boundary(self):
        """min_score 边界值合法"""
        BDDValidator(min_score=0.0)
        BDDValidator(min_score=1.0)

    def test_default_min_score(self, validator):
        """默认 min_score = 0.3"""
        assert validator.min_score == 0.3


# ── 输入格式兼容 ──────────────────────────────────────────


class TestBDDValidatorInputFormats:
    """输入格式兼容性"""

    def test_bdd_spec_input(self, validator):
        """BDDSpec 输入"""
        spec = BDDSpec(given="g", when="w", then="t")
        r = validator.verify("g w t", spec)
        assert r.passed is True

    def test_dict_input(self, validator):
        """dict 输入"""
        d = {"given": "g", "when": "w", "then": "t"}
        r = validator.verify("g w t", d)
        assert r.passed is True

    def test_dict_missing_field(self, validator):
        """dict 缺字段 → 空字符串"""
        d = {"given": "hello", "when": "world"}
        # then 缺 → 空字符串 → verify_then 返回 False
        r = validator.verify("hello world", d)
        assert r.then_passed is False

    def test_none_bdd_raises(self, validator):
        """None bdd_spec 抛异常"""
        with pytest.raises(ValueError, match="cannot be None"):
            validator.verify("text", None)


# ── 单段独立验证 ──────────────────────────────────────────


class TestBDDValidatorIndividualSegments:
    """单段的 verify_given / verify_when / verify_then"""

    def test_verify_given_pass(self, validator):
        passed, detail = validator.verify_given("系统已启动并运行", "系统已启动")
        assert passed is True
        assert "Given:" in detail

    def test_verify_given_fail(self, validator):
        passed, detail = validator.verify_given("系统关闭", "系统已启动")
        assert passed is False

    def test_verify_when_pass(self, validator):
        passed, detail = validator.verify_when("用户点击了提交按钮", "用户点击提交按钮")
        assert passed is True
        assert "When:" in detail

    def test_verify_when_fail(self, validator):
        passed, _ = validator.verify_when("用户取消了操作", "用户点击提交按钮")
        assert passed is False

    def test_verify_then_pass(self, validator):
        passed, detail = validator.verify_then("返回数据包含 id 和 name", "返回数据")
        assert passed is True
        assert "Then:" in detail

    def test_verify_then_fail(self, validator):
        passed, _ = validator.verify_then("无任何响应", "返回数据")
        assert passed is False

    def test_verify_given_empty_expectation(self, validator):
        """空 Given 描述 → 不通过"""
        passed, detail = validator.verify_given("anything", "")
        assert passed is False
        assert "empty" in detail.lower()

    def test_verify_given_empty_result(self, validator):
        """空结果 → 不通过"""
        passed, detail = validator.verify_given("", "系统已启动")
        assert passed is False
        assert "no result" in detail.lower()


# ── 边界与异常 ────────────────────────────────────────────


class TestBDDValidatorEdgeCases:
    """边界条件"""

    def test_single_char_bdd_field(self, validator):
        """BDD 字段只有一个字"""
        spec = BDDSpec(given="启", when="点", then="返")
        r = validator.verify("启动系统 点击按钮 返回数据", spec)
        # 单字被忽略，无关键词 → 默认通过
        assert r.given_passed is True
        assert r.when_passed is True
        assert r.then_passed is True

    def test_english_only_bdd(self, validator):
        """纯英文 BDD"""
        spec = BDDSpec(
            given="user is authenticated",
            when="user clicks submit button",
            then="system returns order ID",
        )
        r = validator.verify(
            "user is authenticated and clicked submit button, order ID is ORD-001",
            spec,
        )
        assert r.given_passed is True
        assert r.when_passed is True
        assert r.then_passed is True

    def test_very_long_result(self, validator):
        """超长结果文本"""
        long_text = "a " * 5000 + "用户已登录" + "b " * 5000
        spec = BDDSpec(given="用户已登录", when="点击", then="返回")
        r = validator.verify(long_text, spec)
        assert r.given_passed is True

    def test_whitespace_only_bdd(self, validator):
        """空白 BDD"""
        spec = BDDSpec(given="   ", when="\t\n", then="")
        r = validator.verify("some result", spec)
        assert r.passed is False  # 空字段全部不通过

    def test_result_with_special_chars(self, validator):
        """结果含特殊字符"""
        spec = BDDSpec(given="用户登录", when="提交表单", then="返回 JSON")
        r = validator.verify(
            '{"status": "ok", "data": {"user": "已登录", "form": "提交成功", "response": "JSON格式"}}',
            spec,
        )
        # 中文和英文都可以匹配
        assert r.passed is True


# ── 真实场景模拟 ──────────────────────────────────────────


class TestBDDValidatorRealisticScenarios:
    """真实测试场景"""

    def test_api_response_validation(self, validator):
        """API 响应验证"""
        spec = BDDSpec(
            given="用户 token 有效",
            when="请求 GET /api/profile",
            then="返回 200 和用户 profile 数据",
        )
        result_text = (
            "验证 token 有效。向 /api/profile 发送 GET 请求。"
            "服务器返回 200 OK，payload 包含用户 profile 数据："
            '{"name":"张三","email":"zhang@test.com"}'
        )
        r = validator.verify(result_text, spec)
        assert r.passed is True

    def test_ui_validation(self, validator):
        """UI 操作验证"""
        spec = BDDSpec(
            given="用户在首页未登录",
            when="点击顶部导航栏的登录按钮",
            then="弹出登录弹窗，包含用户名和密码输入框",
        )
        result_text = (
            "页面加载：首页，用户未登录状态。"
            "检测到点击顶部导航栏的登录按钮操作。"
            "弹窗已弹出：登录弹窗显示用户名输入框和密码输入框。"
        )
        r = validator.verify(result_text, spec)
        assert r.passed is True

    def test_data_processing_validation(self, validator):
        """数据处理验证"""
        spec = BDDSpec(
            given="CSV 文件包含 100 行销售数据",
            when="执行数据清洗脚本",
            then="输出 clean_data.csv 包含 95 行有效数据，去除 5 行异常值",
        )
        result_text = (
            "读取 CSV 文件，共 100 行销售数据。"
            "执行数据清洗脚本完成。"
            "生成 clean_data.csv，包含 95 行有效数据，已去除 5 行异常值。"
        )
        r = validator.verify(result_text, spec)
        assert r.passed is True

    def test_error_scenario_validation(self, validator):
        """错误场景验证（Then 不应该匹配）"""
        spec = BDDSpec(
            given="数据库连接正常",
            when="执行查询",
            then="返回查询结果",
        )
        # 实际结果：数据库连接失败
        result_text = "数据库连接失败，无法执行查询，未返回任何结果"
        r = validator.verify(result_text, spec)
        # "连接" 前面有 "失败" → 否定
        # "查询" 前面有 "无法执行" → 否定
        # "结果" 前面有 "未返回" → 否定
        assert r.passed is False

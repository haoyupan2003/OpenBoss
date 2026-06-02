"""
P1-057: harness/validate-rules.md 加载验证测试

验证 Validator 角色约束文件可被 HarnessLoader 正确加载和解析，
各段落的 RuleType 映射正确，内容完整符合"测试验收标准"定位。
"""

import pytest
from pathlib import Path

from agent_automation_system.harness.harness_loader import HarnessLoader
from agent_automation_system.harness.models import Harness, HarnessRule, RuleType


# ── 固定路径 ──────────────────────────────────────────────
VALIDATE_RULES_PATH = (
    Path(__file__).resolve().parent.parent / "harness" / "validate-rules.md"
)


@pytest.fixture
def loader() -> HarnessLoader:
    return HarnessLoader()


@pytest.fixture
def harness(loader: HarnessLoader) -> Harness:
    """加载 harness/validate-rules.md"""
    assert VALIDATE_RULES_PATH.exists(), f"validate-rules.md not found at {VALIDATE_RULES_PATH}"
    return loader.load_harness(str(VALIDATE_RULES_PATH))


# ══════════════════════════════════════════════════════════
# 1. 基础加载与元数据
# ══════════════════════════════════════════════════════════
class TestBasicLoading:
    """基础加载与元数据验证"""

    def test_file_exists(self):
        """validate-rules.md 文件存在"""
        assert VALIDATE_RULES_PATH.is_file()

    def test_load_without_error(self, loader: HarnessLoader):
        """加载不抛异常"""
        harness = loader.load_harness(str(VALIDATE_RULES_PATH))
        assert isinstance(harness, Harness)

    def test_harness_name(self, harness: Harness):
        """Harness 名称包含 Validator"""
        assert "Validator" in harness.name

    def test_role_name_inferred(self, harness: Harness):
        """角色名称从文件名推断为 validator"""
        assert harness.role_name == "validator"

    def test_has_sections(self, harness: Harness):
        """包含 Role Identity / DO / DON'T / Constraints / Verification 段落"""
        section_titles = [s.title for s in harness.sections]
        assert "Role Identity" in section_titles
        assert "DO" in section_titles
        assert "DON'T" in section_titles
        assert "Constraints" in section_titles
        assert "Verification" in section_titles

    def test_has_rules(self, harness: Harness):
        """解析出规则条目"""
        assert len(harness.rules) > 0


# ══════════════════════════════════════════════════════════
# 2. 段落 RuleType 映射
# ══════════════════════════════════════════════════════════
class TestSectionRuleTypes:
    """各段落 RuleType 映射正确"""

    def test_role_identity_is_custom(self, harness: Harness):
        """Role Identity → CUSTOM"""
        section = next(s for s in harness.sections if s.title == "Role Identity")
        assert section.rule_type == RuleType.CUSTOM

    def test_do_section_type(self, harness: Harness):
        """DO → RuleType.DO"""
        section = next(s for s in harness.sections if s.title == "DO")
        assert section.rule_type == RuleType.DO

    def test_dont_section_type(self, harness: Harness):
        """DON'T → RuleType.DONT"""
        section = next(s for s in harness.sections if s.title == "DON'T")
        assert section.rule_type == RuleType.DONT

    def test_constraints_section_type(self, harness: Harness):
        """Constraints → RuleType.CONSTRAINT"""
        section = next(s for s in harness.sections if s.title == "Constraints")
        assert section.rule_type == RuleType.CONSTRAINT

    def test_verification_section_type(self, harness: Harness):
        """Verification → RuleType.VERIFICATION"""
        section = next(s for s in harness.sections if s.title == "Verification")
        assert section.rule_type == RuleType.VERIFICATION


# ══════════════════════════════════════════════════════════
# 3. 内容完整性
# ══════════════════════════════════════════════════════════
class TestContentCompleteness:
    """内容覆盖测试验收标准的核心职责和约束"""

    def test_role_identity_content(self, harness: Harness):
        """Role Identity 包含 Validator 和 quality 关键词"""
        section = next(s for s in harness.sections if s.title == "Role Identity")
        raw = section.raw_content.lower()
        assert "validator" in raw
        assert "quality" in raw

    def test_do_rules_count(self, harness: Harness):
        """DO 段落至少 6 条"""
        do_rules = harness.get_do_rules()
        assert len(do_rules) >= 6

    def test_do_covers_core_validation(self, harness: Harness):
        """DO 规则覆盖核心验证职责"""
        contents = [r.content.lower() for r in harness.get_do_rules()]
        # 验证测试脚本通过
        assert any("test" in c and "pass" in c for c in contents)
        # 检查 git commit
        assert any("git" in c and "commit" in c for c in contents)
        # 验证 progress.txt
        assert any("progress.txt" in c for c in contents)
        # 验证 task.json
        assert any("task.json" in c for c in contents)
        # 集成测试
        assert any("integration" in c for c in contents)

    def test_dont_rules_count(self, harness: Harness):
        """DON'T 段落至少 4 条"""
        dont_rules = harness.get_dont_rules()
        assert len(dont_rules) >= 4

    def test_dont_covers_never_constraints(self, harness: Harness):
        """DON'T 规则覆盖关键禁止项"""
        contents = [r.content.lower() for r in harness.get_dont_rules()]
        # 不验证自己的工作
        assert any("own work" in c or "independent" in c for c in contents)
        # 不跳过测试
        assert any("test" in c for c in contents)

    def test_constraints_rules_count(self, harness: Harness):
        """Constraints 段落至少 4 条"""
        constraints = harness.get_constraints()
        assert len(constraints) >= 4

    def test_constraints_covers_key_items(self, harness: Harness):
        """Constraints 覆盖关键约束"""
        contents = [r.content.lower() for r in harness.get_constraints()]
        # 任务完成必须测试通过+验证
        assert any("test" in c and "complete" in c for c in contents)
        # exit code 0 = pass
        assert any("exit code" in c for c in contents)
        # 集成测试必须
        assert any("integration" in c for c in contents)

    def test_verification_rules_count(self, harness: Harness):
        """Verification 段落至少 3 条"""
        verifications = harness.get_verification_rules()
        assert len(verifications) >= 3

    def test_verification_covers_test_and_git(self, harness: Harness):
        """Verification 覆盖测试和 git 验证"""
        contents = [r.content.lower() for r in harness.get_verification_rules()]
        assert any("test" in c for c in contents)
        assert any("git" in c and "commit" in c for c in contents)


# ══════════════════════════════════════════════════════════
# 4. to_prompt_text 输出
# ══════════════════════════════════════════════════════════
class TestPromptText:
    """验证 to_prompt_text 输出格式正确"""

    def test_prompt_text_not_empty(self, harness: Harness):
        """prompt 文本非空"""
        prompt = harness.to_prompt_text()
        assert len(prompt) > 0

    def test_prompt_contains_sections(self, harness: Harness):
        """prompt 包含各段落标题"""
        prompt = harness.to_prompt_text()
        assert "## Role Identity" in prompt
        assert "## DO" in prompt
        assert "## DON'T" in prompt
        assert "## Constraints" in prompt
        assert "## Verification" in prompt

    def test_prompt_contains_rule_items(self, harness: Harness):
        """prompt 包含具体规则条目"""
        prompt = harness.to_prompt_text()
        do_rules = harness.get_do_rules()
        if do_rules:
            assert f"- {do_rules[0].content}" in prompt


# ══════════════════════════════════════════════════════════
# 5. 与其他规则文件的差异验证
# ══════════════════════════════════════════════════════════
class TestDistinctFromOtherRules:
    """验证 validate-rules.md 与 main-rules/sub-rules 角色区分明确"""

    def test_different_role_name(self, harness: Harness):
        """角色名称是 validator，不是 master-agent 或 sub-agent"""
        assert harness.role_name == "validator"
        assert harness.role_name != "master-agent"
        assert harness.role_name != "sub-agent"

    def test_validate_rules_has_integration_testing(self, harness: Harness):
        """Validator 规则包含集成测试（区别于 sub-rules 的单元测试）"""
        do_contents = [r.content.lower() for r in harness.get_do_rules()]
        assert any("integration" in c for c in do_contents)

    def test_validate_rules_has_validation_report(self, harness: Harness):
        """Validator 规则包含验证报告输出"""
        do_contents = [r.content.lower() for r in harness.get_do_rules()]
        assert any("report" in c for c in do_contents)

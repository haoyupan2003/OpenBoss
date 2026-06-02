"""
P1-058: harness/pm-rules.md 加载验证测试

验证 Product Manager Agent 专属约束文件可被 HarnessLoader 正确加载和解析，
各段落的 RuleType 映射正确，内容完整符合 PRD 5.1 节 BDD 沟通规则定位。
"""

import pytest
from pathlib import Path

from agent_automation_system.harness.harness_loader import HarnessLoader
from agent_automation_system.harness.models import Harness, HarnessRule, RuleType


# ── 固定路径 ──────────────────────────────────────────────
PM_RULES_PATH = Path(__file__).resolve().parent.parent / "harness" / "pm-rules.md"


@pytest.fixture
def loader() -> HarnessLoader:
    return HarnessLoader()


@pytest.fixture
def harness(loader: HarnessLoader) -> Harness:
    """加载 harness/pm-rules.md"""
    assert PM_RULES_PATH.exists(), f"pm-rules.md not found at {PM_RULES_PATH}"
    return loader.load_harness(str(PM_RULES_PATH))


# ══════════════════════════════════════════════════════════
# 1. 基础加载与元数据
# ══════════════════════════════════════════════════════════
class TestBasicLoading:
    """基础加载与元数据验证"""

    def test_file_exists(self):
        """pm-rules.md 文件存在"""
        assert PM_RULES_PATH.is_file()

    def test_load_without_error(self, loader: HarnessLoader):
        """加载不抛异常"""
        harness = loader.load_harness(str(PM_RULES_PATH))
        assert isinstance(harness, Harness)

    def test_harness_name(self, harness: Harness):
        """Harness 名称包含 Product Manager"""
        assert "Product Manager" in harness.name

    def test_role_name_inferred(self, harness: Harness):
        """角色名称从文件名推断为 product-manager"""
        assert harness.role_name == "product-manager"

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
# 3. 内容完整性（按 PRD 5.1 BDD 沟通规则）
# ══════════════════════════════════════════════════════════
class TestContentCompleteness:
    """内容覆盖 PRD 5.1 节 BDD 沟通和任务拆解核心职责"""

    def test_role_identity_content(self, harness: Harness):
        """Role Identity 包含 requirement refinement 和 BDD 关键词"""
        section = next(s for s in harness.sections if s.title == "Role Identity")
        raw = section.raw_content.lower()
        assert "requirement" in raw
        assert "bdd" in raw or "given" in raw or "behavior" in raw

    def test_do_rules_count(self, harness: Harness):
        """DO 段落至少 6 条"""
        do_rules = harness.get_do_rules()
        assert len(do_rules) >= 6

    def test_do_covers_bdd_communication(self, harness: Harness):
        """DO 规则覆盖 BDD 沟通核心职责"""
        contents = [r.content.lower() for r in harness.get_do_rules()]
        # BDD Given-When-Then
        assert any("given" in c and "when" in c and "then" in c for c in contents)
        # 任务拆解 → task.json
        assert any("task.json" in c for c in contents)
        # 测试脚本
        assert any("test script" in c for c in contents)
        # 与用户迭代确认
        assert any("iterate" in c or "user" in c for c in contents)

    def test_dont_rules_count(self, harness: Harness):
        """DON'T 段落至少 4 条"""
        dont_rules = harness.get_dont_rules()
        assert len(dont_rules) >= 4

    def test_dont_covers_never_constraints(self, harness: Harness):
        """DON'T 规则覆盖关键禁止项"""
        contents = [r.content.lower() for r in harness.get_dont_rules()]
        # 不接受模糊需求
        assert any("ambiguous" in c or "incomplete" in c for c in contents)
        # 不跳过 BDD 格式
        assert any("given" in c or "bdd" in c for c in contents)
        # 不创建无测试的任务
        assert any("test script" in c for c in contents)

    def test_constraints_rules_count(self, harness: Harness):
        """Constraints 段落至少 4 条"""
        constraints = harness.get_constraints()
        assert len(constraints) >= 4

    def test_constraints_covers_key_items(self, harness: Harness):
        """Constraints 覆盖关键约束"""
        contents = [r.content.lower() for r in harness.get_constraints()]
        # 每个任务必须有测试脚本
        assert any("test script" in c for c in contents)
        # task.json 格式
        assert any("task.json" in c for c in contents)
        # BDD Given-When-Then 格式
        assert any("given" in c and "when" in c for c in contents)
        # 任务 ID 格式
        assert any("task-" in c for c in contents)

    def test_verification_rules_count(self, harness: Harness):
        """Verification 段落至少 3 条"""
        verifications = harness.get_verification_rules()
        assert len(verifications) >= 3

    def test_verification_covers_acceptance(self, harness: Harness):
        """Verification 覆盖验收标准和 BDD 格式验证"""
        contents = [r.content.lower() for r in harness.get_verification_rules()]
        assert any("acceptance" in c or "testable" in c for c in contents)
        assert any("given" in c or "bdd" in c for c in contents)


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
    """验证 pm-rules.md 与 main/sub/validate 规则区分明确"""

    def test_different_role_name(self, harness: Harness):
        """角色名称是 product-manager"""
        assert harness.role_name == "product-manager"
        assert harness.role_name != "master-agent"
        assert harness.role_name != "sub-agent"
        assert harness.role_name != "validator"

    def test_pm_rules_has_bdd_focus(self, harness: Harness):
        """PM 规则聚焦 BDD 沟通（区别于其他角色的执行/验证）"""
        do_contents = [r.content.lower() for r in harness.get_do_rules()]
        assert any("given" in c or "bdd" in c for c in do_contents)

    def test_pm_rules_has_task_json_generation(self, harness: Harness):
        """PM 规则包含 task.json 生成职责"""
        do_contents = [r.content.lower() for r in harness.get_do_rules()]
        assert any("task.json" in c for c in do_contents)

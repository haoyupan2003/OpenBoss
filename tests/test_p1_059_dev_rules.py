"""
P1-059: harness/dev-rules.md 加载验证测试

验证 Senior Developer Agent 专属约束文件可被 HarnessLoader 正确加载和解析，
各段落的 RuleType 映射正确，内容完整覆盖编码规范和提交规则。
"""

import pytest
from pathlib import Path

from agent_automation_system.harness.harness_loader import HarnessLoader
from agent_automation_system.harness.models import Harness, HarnessRule, RuleType


# ── 固定路径 ──────────────────────────────────────────────
DEV_RULES_PATH = Path(__file__).resolve().parent.parent / "harness" / "dev-rules.md"


@pytest.fixture
def loader() -> HarnessLoader:
    return HarnessLoader()


@pytest.fixture
def harness(loader: HarnessLoader) -> Harness:
    """加载 harness/dev-rules.md"""
    assert DEV_RULES_PATH.exists(), f"dev-rules.md not found at {DEV_RULES_PATH}"
    return loader.load_harness(str(DEV_RULES_PATH))


# ══════════════════════════════════════════════════════════
# 1. 基础加载与元数据
# ══════════════════════════════════════════════════════════
class TestBasicLoading:
    """基础加载与元数据验证"""

    def test_file_exists(self):
        """dev-rules.md 文件存在"""
        assert DEV_RULES_PATH.is_file()

    def test_load_without_error(self, loader: HarnessLoader):
        """加载不抛异常"""
        harness = loader.load_harness(str(DEV_RULES_PATH))
        assert isinstance(harness, Harness)

    def test_harness_name(self, harness: Harness):
        """Harness 名称包含 Senior Developer"""
        assert "Senior Developer" in harness.name

    def test_role_name_inferred(self, harness: Harness):
        """角色名称从文件名推断为 senior-developer"""
        assert harness.role_name == "senior-developer"

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
# 3. 内容完整性（编码规范 + 提交规则）
# ══════════════════════════════════════════════════════════
class TestContentCompleteness:
    """内容覆盖编码规范和提交规则核心职责"""

    def test_role_identity_content(self, harness: Harness):
        """Role Identity 包含 code implementation 和 TDD 关键词"""
        section = next(s for s in harness.sections if s.title == "Role Identity")
        raw = section.raw_content.lower()
        assert "code" in raw or "implementation" in raw
        assert "tdd" in raw or "test" in raw

    def test_do_rules_count(self, harness: Harness):
        """DO 段落至少 6 条"""
        do_rules = harness.get_do_rules()
        assert len(do_rules) >= 6

    def test_do_covers_tdd_workflow(self, harness: Harness):
        """DO 规则覆盖 TDD 核心工作流"""
        contents = [r.content.lower() for r in harness.get_do_rules()]
        # TDD：先写测试
        assert any("test" in c and ("first" in c or "before" in c) for c in contents)
        # 读任务描述
        assert any("task" in c for c in contents)
        # 提交与更新
        assert any("commit" in c for c in contents)

    def test_do_covers_code_style(self, harness: Harness):
        """DO 规则覆盖编码规范"""
        contents = [r.content.lower() for r in harness.get_do_rules()]
        # 代码风格/命名/文档
        assert any("style" in c or "convention" in c or "naming" in c for c in contents)
        # docstrings/文档
        assert any("docstring" in c or "document" in c for c in contents)

    def test_dont_rules_count(self, harness: Harness):
        """DON'T 段落至少 4 条"""
        dont_rules = harness.get_dont_rules()
        assert len(dont_rules) >= 4

    def test_dont_covers_never_constraints(self, harness: Harness):
        """DON'T 规则覆盖关键禁止项"""
        contents = [r.content.lower() for r in harness.get_dont_rules()]
        # 不超范围实现
        assert any("beyond" in c or "scope" in c or "specification" in c for c in contents)
        # 不跳过测试
        assert any("test" in c for c in contents)
        # 不提交未通过测试的代码
        assert any("commit" in c for c in contents)

    def test_constraints_rules_count(self, harness: Harness):
        """Constraints 段落至少 4 条"""
        constraints = harness.get_constraints()
        assert len(constraints) >= 4

    def test_constraints_covers_key_items(self, harness: Harness):
        """Constraints 覆盖关键约束"""
        contents = [r.content.lower() for r in harness.get_constraints()]
        # 提交格式
        assert any("commit" in c and "task-" in c for c in contents)
        # 单一逻辑变更
        assert any("single" in c or "logical" in c for c in contents)
        # 依赖管理
        assert any("depend" in c for c in contents)

    def test_verification_rules_count(self, harness: Harness):
        """Verification 段落至少 3 条"""
        verifications = harness.get_verification_rules()
        assert len(verifications) >= 3

    def test_verification_covers_acceptance(self, harness: Harness):
        """Verification 覆盖测试通过、提交格式、范围控制"""
        contents = [r.content.lower() for r in harness.get_verification_rules()]
        assert any("test" in c and ("pass" in c or "complet" in c) for c in contents)
        assert any("commit" in c and "task-" in c for c in contents)
        assert any("scope" in c for c in contents)


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
    """验证 dev-rules.md 与 main/sub/validate/pm 规则区分明确"""

    def test_different_role_name(self, harness: Harness):
        """角色名称是 senior-developer"""
        assert harness.role_name == "senior-developer"
        assert harness.role_name != "master-agent"
        assert harness.role_name != "sub-agent"
        assert harness.role_name != "validator"
        assert harness.role_name != "product-manager"

    def test_dev_rules_has_tdd_focus(self, harness: Harness):
        """Dev 规则聚焦 TDD 编码（区别于 PM 的 BDD/Validator 的验证）"""
        do_contents = [r.content.lower() for r in harness.get_do_rules()]
        assert any("tdd" in c or ("test" in c and "first" in c) for c in do_contents)

    def test_dev_rules_has_commit_format(self, harness: Harness):
        """Dev 规则包含 senior-developer 提交格式约束"""
        all_contents = [r.content.lower() for r in harness.rules]
        assert any("senior-developer" in c for c in all_contents)

    def test_dev_rules_no_bdd_orchestration(self, harness: Harness):
        """Dev 规则不包含编排或 BDD 沟通（区别于 main-rules 和 pm-rules）"""
        all_contents = [r.content.lower() for r in harness.rules]
        # 不涉及 Sub-Agent 编排
        assert not any("sub-agent" in c and "dispatch" in c for c in all_contents)
        # 不涉及 Given-When-Then BDD 沟通
        assert not any("given" in c and "when" in c and "then" in c for c in all_contents)

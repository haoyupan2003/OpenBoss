"""
P1-055: harness/main-rules.md 加载验证测试

验证 Master Agent 编排者/老板角色约束文件可被 HarnessLoader 正确加载和解析，
各段落的 RuleType 映射正确，内容完整符合 PRD 6.4.1 规范。
"""

import pytest
from pathlib import Path

from agent_automation_system.harness.harness_loader import HarnessLoader
from agent_automation_system.harness.models import Harness, HarnessRule, RuleType


# ── 固定路径 ──────────────────────────────────────────────
MAIN_RULES_PATH = Path(__file__).resolve().parent.parent / "harness" / "main-rules.md"


@pytest.fixture
def loader() -> HarnessLoader:
    return HarnessLoader()


@pytest.fixture
def harness(loader: HarnessLoader) -> Harness:
    """加载 harness/main-rules.md"""
    assert MAIN_RULES_PATH.exists(), f"main-rules.md not found at {MAIN_RULES_PATH}"
    return loader.load_harness(str(MAIN_RULES_PATH))


# ══════════════════════════════════════════════════════════
# 1. 基础加载与元数据
# ══════════════════════════════════════════════════════════
class TestBasicLoading:
    """基础加载与元数据验证"""

    def test_file_exists(self):
        """main-rules.md 文件存在"""
        assert MAIN_RULES_PATH.is_file()

    def test_load_without_error(self, loader: HarnessLoader):
        """加载不抛异常"""
        harness = loader.load_harness(str(MAIN_RULES_PATH))
        assert isinstance(harness, Harness)

    def test_harness_name(self, harness: Harness):
        """Harness 名称来自 # 一级标题"""
        assert "Master Agent" in harness.name

    def test_role_name_inferred(self, harness: Harness):
        """角色名称从文件名推断为 master-agent"""
        assert harness.role_name == "master-agent"

    def test_has_sections(self, harness: Harness):
        """至少包含 Role Identity / DO / DON'T / Constraints / Verification 段落"""
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
# 3. 内容完整性（按 PRD 6.4.1）
# ══════════════════════════════════════════════════════════
class TestContentCompleteness:
    """内容覆盖 PRD 6.4.1 定义的核心职责和约束"""

    def test_role_identity_content(self, harness: Harness):
        """Role Identity 包含 Orchestrator 和 Sub-Agents 关键词"""
        section = next(s for s in harness.sections if s.title == "Role Identity")
        raw = section.raw_content.lower()
        assert "orchestrator" in raw
        assert "sub-agent" in raw or "sub-agents" in raw

    def test_do_rules_count(self, harness: Harness):
        """DO 段落至少 7 条（PRD Core Responsibilities 7 项 + 补充）"""
        do_rules = harness.get_do_rules()
        assert len(do_rules) >= 7

    def test_do_covers_core_responsibilities(self, harness: Harness):
        """DO 规则覆盖 PRD 核心职责"""
        contents = [r.content.lower() for r in harness.get_do_rules()]
        # 1. 接收需求 + 协调 PM
        assert any("requirements" in c and "product manager" in c for c in contents)
        # 2. 接收 task.json + 分析依赖
        assert any("task.json" in c and "dependencies" in c for c in contents)
        # 3. 决定 Sub-Agent 角色
        assert any("sub-agent" in c and "role" in c for c in contents)
        # 4. 创建 Sub-Agent CLI
        assert any("sub-agent" in c and "cli" in c for c in contents)
        # 5. 监控进度
        assert any("progress" in c and "monitor" in c for c in contents)
        # 6. 处理失败
        assert any("failures" in c or "failure" in c for c in contents)
        # 7. 恢复执行
        assert any("resume" in c for c in contents)

    def test_dont_rules_count(self, harness: Harness):
        """DON'T 段落至少 3 条"""
        dont_rules = harness.get_dont_rules()
        assert len(dont_rules) >= 3

    def test_dont_covers_never_constraints(self, harness: Harness):
        """DON'T 规则覆盖 PRD NEVER 约束"""
        contents = [r.content.lower() for r in harness.get_dont_rules()]
        # NEVER write code / run tests / do data analysis
        assert any("code" in c and "test" in c for c in contents)
        # NEVER execute business logic
        assert any("business logic" in c for c in contents)

    def test_constraints_rules_count(self, harness: Harness):
        """Constraints 段落至少 4 条"""
        constraints = harness.get_constraints()
        assert len(constraints) >= 4

    def test_constraints_covers_key_items(self, harness: Harness):
        """Constraints 覆盖 PRD 关键约束"""
        contents = [r.content.lower() for r in harness.get_constraints()]
        # ALWAYS delegate
        assert any("delegate" in c for c in contents)
        # PAUSE on failure
        assert any("pause" in c for c in contents)
        # Dependency order
        assert any("dependencies" in c and "dispatch" in c for c in contents)

    def test_verification_rules_count(self, harness: Harness):
        """Verification 段落至少 3 条"""
        verifications = harness.get_verification_rules()
        assert len(verifications) >= 3

    def test_verification_covers_progress_and_git(self, harness: Harness):
        """Verification 覆盖进度更新和 git 提交验证"""
        contents = [r.content.lower() for r in harness.get_verification_rules()]
        assert any("progress" in c for c in contents)
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
        """prompt 包含具体规则条目（列表形式）"""
        prompt = harness.to_prompt_text()
        do_rules = harness.get_do_rules()
        if do_rules:
            assert f"- {do_rules[0].content}" in prompt


# ══════════════════════════════════════════════════════════
# 5. MasterAgent 集成加载
# ══════════════════════════════════════════════════════════
class TestMasterAgentIntegration:
    """验证 MasterAgent 可通过 _load_main_rules 加载此文件"""

    def test_load_by_master_agent(self):
        """MasterAgent._load_main_rules 可成功加载"""
        from agent_automation_system.master_agent.master_agent import MasterAgent

        master = MasterAgent()
        master._load_main_rules(str(MAIN_RULES_PATH))
        assert master.main_rules_content is not None
        assert len(master.main_rules_content) > 0

    def test_master_prompt_contains_role(self):
        """MasterAgent prompt 包含角色身份和约束"""
        from agent_automation_system.master_agent.master_agent import MasterAgent

        master = MasterAgent()
        master._load_main_rules(str(MAIN_RULES_PATH))
        prompt = master._build_main_prompt()
        assert "Master Agent" in prompt or "master-agent" in prompt.lower()
        assert "约束规则" in prompt or "DO" in prompt or "Constraints" in prompt

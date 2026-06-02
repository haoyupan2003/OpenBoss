"""
P2-029 测试：CommitMessageFormatter 统一格式化

验证 [task-{id}] {role}: {description} 格式的完整实现。
覆盖：
1. format 基础格式化
2. 标题截断（>50 字符）
3. format_from_task（Task 对象解析）
4. parse 反向解析
5. is_valid_format 校验
6. extract_task_id / extract_role
7. 参数校验（空值/None）
8. PRD §4.7 真实示例
"""

import pytest

from agent_automation_system.git_manager.commit_message import CommitMessageFormatter
from agent_automation_system.models.task import (
    Task,
    TaskComplexity,
    TaskPriority,
    TaskStatus,
)


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def fmt():
    return CommitMessageFormatter()


@pytest.fixture
def sample_task():
    return Task(
        id="task-023",
        title="实现用户登录页面布局和样式",
        description="基于 Figma 设计稿实现登录页面 UI",
        dependencies=[],
        suggested_role="senior-developer",
        priority=TaskPriority.HIGH,
        estimated_complexity=TaskComplexity.MEDIUM,
        status=TaskStatus.PENDING,
    )


# ── format 基础 ───────────────────────────────────────────


class TestFormatBasic:
    """format 基础格式化"""

    def test_simple_format(self, fmt):
        msg = fmt.format("001", "dev", "实现用户登录")
        assert msg == "[task-001] dev: 实现用户登录"

    def test_with_senior_developer_role(self, fmt):
        msg = fmt.format("023", "senior-developer", "实现用户登录页面布局和样式")
        assert msg == "[task-023] senior-developer: 实现用户登录页面布局和样式"

    def test_with_qa_role(self, fmt):
        msg = fmt.format("002", "test-engineer", "编写登录表单 E2E 自动化测试")
        assert msg == "[task-002] test-engineer: 编写登录表单 E2E 自动化测试"

    def test_with_pm_role(self, fmt):
        msg = fmt.format("001", "product-manager", "分解用户认证模块需求")
        assert msg == "[task-001] product-manager: 分解用户认证模块需求"

    def test_long_task_id(self, fmt):
        msg = fmt.format("12345", "dev", "修复 bug")
        assert msg == "[task-12345] dev: 修复 bug"

    def test_strips_whitespace(self, fmt):
        msg = fmt.format("  001  ", "  dev  ", "  实现登录  ")
        assert msg == "[task-001] dev: 实现登录"

    def test_english_description(self, fmt):
        msg = fmt.format("001", "dev", "Implement user login API")
        assert msg == "[task-001] dev: Implement user login API"

    def test_truncate_disabled(self, fmt):
        long_desc = "x" * 60
        msg = fmt.format("001", "dev", long_desc, truncate=False)
        assert len(msg) > 60
        assert long_desc in msg


# ── 标题截断 ──────────────────────────────────────────────


class TestTruncation:
    """标题截断规则"""

    def test_exactly_50_chars_not_truncated(self, fmt):
        desc = "a" * 50
        msg = fmt.format("001", "dev", desc)
        # 50 字符精确不截断
        assert f": {desc}" in msg
        assert "..." not in msg.split(": ")[-1]

    def test_51_chars_truncated(self, fmt):
        desc = "a" * 51
        msg = fmt.format("001", "dev", desc)
        # 截断为 47 + "..."
        desc_part = msg.split(": ")[1]
        assert desc_part.endswith("...")
        assert len(desc_part) == 50  # 47 + 3

    def test_100_chars_truncated(self, fmt):
        desc = "a" * 100
        msg = fmt.format("001", "dev", desc)
        desc_part = msg.split(": ")[1]
        assert desc_part.endswith("...")
        assert len(desc_part) == 50

    def test_chinese_truncation(self, fmt):
        """中文字符截断（按字符数，非字节数）"""
        desc = "这是一个非常长的中文描述文本用于测试 commit message 格式化工具的截断功能是否能够正确处理中文字符"
        msg = fmt.format("001", "dev", desc)
        desc_part = msg.split(": ")[1]
        assert desc_part.endswith("...")
        # 中文按字符计，50 个字符
        assert len(desc_part) == 50


# ── format_from_task ─────────────────────────────────────


class TestFormatFromTask:
    """从 Task 对象生成"""

    def test_basic_task(self, fmt, sample_task):
        msg = fmt.format_from_task(sample_task, role="senior-developer")
        assert msg == "[task-023] senior-developer: 实现用户登录页面布局和样式"

    def test_default_role(self, fmt, sample_task):
        msg = fmt.format_from_task(sample_task)
        assert "[task-023] dev:" in msg

    def test_strips_task_prefix(self, fmt):
        task = Task(
            id="task-999",
            title="修复样式",
            description="D",
            dependencies=[],
            suggested_role="dev",
            priority=TaskPriority.LOW,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        msg = fmt.format_from_task(task)
        assert msg == "[task-999] dev: 修复样式"

    def test_title_takes_priority(self, fmt):
        """title 非空时优先使用 title"""
        task = Task(
            id="task-001",
            title="标题优先",
            description="描述次之",
            dependencies=[],
            suggested_role="dev",
            priority=TaskPriority.LOW,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        msg = fmt.format_from_task(task)
        assert "标题优先" in msg
        assert "描述次之" not in msg

    def test_none_task_raises(self, fmt):
        with pytest.raises(ValueError, match="cannot be None"):
            fmt.format_from_task(None)

    def test_truncates_long_title(self, fmt):
        task = Task(
            id="task-003",
            title="a" * 60,
            description="D",
            dependencies=[],
            suggested_role="dev",
            priority=TaskPriority.LOW,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        msg = fmt.format_from_task(task)
        desc_part = msg.split(": ")[1]
        assert desc_part.endswith("...")


# ── parse 解析 ────────────────────────────────────────────


class TestParse:
    """反向解析"""

    def test_parse_simple(self, fmt):
        r = fmt.parse("[task-001] dev: 实现用户登录")
        assert r is not None
        assert r["task_id"] == "001"
        assert r["role"] == "dev"
        assert r["description"] == "实现用户登录"

    def test_parse_with_hyphen_role(self, fmt):
        r = fmt.parse("[task-023] senior-developer: 实现用户登录页面布局和样式")
        assert r is not None
        assert r["task_id"] == "023"
        assert r["role"] == "senior-developer"

    def test_parse_with_colons_in_description(self, fmt):
        """描述中包含冒号"""
        r = fmt.parse("[task-001] dev: 实现 API: POST /login 接口")
        assert r is not None
        assert r["task_id"] == "001"
        assert r["description"] == "实现 API: POST /login 接口"

    def test_parse_invalid_format(self, fmt):
        assert fmt.parse("not a commit message") is None
        assert fmt.parse("[task-001] missing colon") is None
        assert fmt.parse("task-001: dev: description") is None

    def test_parse_empty_string(self, fmt):
        assert fmt.parse("") is None

    def test_parse_none(self, fmt):
        assert fmt.parse(None) is None

    def test_roundtrip(self, fmt):
        """format → parse 往返一致"""
        original_id = "042"
        original_role = "qa"
        original_desc = "编写集成测试"
        msg = fmt.format(original_id, original_role, original_desc)
        parsed = fmt.parse(msg)
        assert parsed is not None
        assert parsed["task_id"] == original_id
        assert parsed["role"] == original_role
        assert parsed["description"] == original_desc


# ── is_valid_format ──────────────────────────────────────


class TestIsValidFormat:
    """格式校验"""

    def test_valid_format(self, fmt):
        assert fmt.is_valid_format("[task-001] dev: 实现登录") is True

    def test_invalid_format(self, fmt):
        assert fmt.is_valid_format("random text") is False

    def test_empty_string(self, fmt):
        assert fmt.is_valid_format("") is False


# ── extract_task_id / extract_role ────────────────────────


class TestExtract:
    """辅助提取方法"""

    def test_extract_task_id(self, fmt):
        assert fmt.extract_task_id("[task-042] dev: fix") == "042"

    def test_extract_task_id_invalid(self, fmt):
        assert fmt.extract_task_id("not valid") is None

    def test_extract_role(self, fmt):
        assert fmt.extract_role("[task-001] test-engineer: add tests") == "test-engineer"

    def test_extract_role_invalid(self, fmt):
        assert fmt.extract_role("not valid") is None


# ── 参数校验 ──────────────────────────────────────────────


class TestValidation:
    """参数校验"""

    def test_empty_task_id_raises(self, fmt):
        with pytest.raises(ValueError, match="task_id"):
            fmt.format("", "dev", "desc")

    def test_whitespace_task_id_raises(self, fmt):
        with pytest.raises(ValueError, match="task_id"):
            fmt.format("   ", "dev", "desc")

    def test_empty_role_raises(self, fmt):
        with pytest.raises(ValueError, match="role"):
            fmt.format("001", "", "desc")

    def test_whitespace_role_raises(self, fmt):
        with pytest.raises(ValueError, match="role"):
            fmt.format("001", "  ", "desc")

    def test_empty_description_raises(self, fmt):
        with pytest.raises(ValueError, match="description"):
            fmt.format("001", "dev", "")

    def test_whitespace_description_raises(self, fmt):
        with pytest.raises(ValueError, match="description"):
            fmt.format("001", "dev", "   ")


# ── PRD §4.7 真实示例 ────────────────────────────────────


class TestPRDExamples:
    """PRD §4.7 中的示例"""

    def test_prd_example_1(self, fmt):
        """示例：[task-023] senior-developer: 实现用户登录页面布局和样式"""
        msg = fmt.format(
            "023",
            "senior-developer",
            "实现用户登录页面布局和样式",
        )
        assert msg == "[task-023] senior-developer: 实现用户登录页面布局和样式"

    def test_prd_example_2(self, fmt):
        """示例：[task-001] senior-developer: 实现用户登录页面布局和样式"""
        msg = fmt.format(
            "001",
            "senior-developer",
            "实现用户登录页面布局和样式",
        )
        assert msg == "[task-001] senior-developer: 实现用户登录页面布局和样式"

    def test_prd_example_3(self, fmt):
        """示例：[task-002] test-engineer: 编写登录表单 E2E 自动化测试"""
        msg = fmt.format(
            "002",
            "test-engineer",
            "编写登录表单 E2E 自动化测试",
        )
        assert msg == "[task-002] test-engineer: 编写登录表单 E2E 自动化测试"


# ── 全局常量测试 ──────────────────────────────────────────


class TestConstants:
    """常量和类级默认值"""

    def test_format_string(self):
        assert CommitMessageFormatter.FORMAT == "[task-{id}] {role}: {description}"

    def test_max_desc_length(self):
        assert CommitMessageFormatter.MAX_DESC_LENGTH == 50

    def test_truncation_suffix(self):
        assert CommitMessageFormatter.TRUNCATION_SUFFIX == "..."

    def test_parse_pattern_compiled(self, fmt):
        assert fmt.PARSE_PATTERN is not None
        assert hasattr(fmt.PARSE_PATTERN, "match")

    def test_format_from_task_vs_format_equivalence(self, fmt, sample_task):
        """format_from_task 输出应等价于 format(extracted_id, role, title)"""
        from_task = fmt.format_from_task(sample_task, role="senior-developer")
        direct = fmt.format("023", "senior-developer", "实现用户登录页面布局和样式")
        assert from_task == direct

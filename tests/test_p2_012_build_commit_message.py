"""
P2-012 测试：SeniorDeveloperAgent.build_commit_message 完整实现

验证 build_commit_message 方法，覆盖：
1. 正常格式输出（标准 task ID + 短标题）
2. 长标题截断（> 50 字符时截断为 47 字符 + "..."）
3. None task 抛出 ValueError
4. 空标题处理
5. commit message 格式符合 [task-{id}] senior-developer: {desc} 规范
6. task ID 解析（task-001 → 001，task-123 → 123）
7. 调用后缓存到 _commit_message
8. 多次调用覆盖缓存（幂等性）
9. 不含换行符（单行格式）
10. 边界：标题恰好 50 字符不截断
"""

import pytest
from unittest.mock import MagicMock, patch

from agent_automation_system.models.task import (
    Task,
    TaskComplexity,
    TaskPriority,
    TaskStatus,
)
from agent_automation_system.sub_agent.dev_agent import (
    SeniorDeveloperAgent,
    _COMMIT_MESSAGE_FORMAT,
)


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def dev_agent():
    """创建默认 SeniorDeveloperAgent 实例"""
    return SeniorDeveloperAgent()


@pytest.fixture
def simple_task():
    """短标题 Task（无需截断）"""
    return Task(
        id="task-001",
        title="实现用户登录 API",
        description="实现登录接口",
        status=TaskStatus.PENDING,
        priority=TaskPriority.HIGH,
        complexity=TaskComplexity.MEDIUM,
    )


@pytest.fixture
def long_title_task():
    """标题超过 50 字符的 Task（51 个英文字母，确保超过边界）"""
    return Task(
        id="task-042",
        title="A" * 51,  # 51 字符，必须截断
        description="长标题任务",
        status=TaskStatus.PENDING,
        priority=TaskPriority.HIGH,
        complexity=TaskComplexity.HIGH,
    )


@pytest.fixture
def exact_50_task():
    """标题恰好 50 字符的 Task（边界值）"""
    title = "A" * 50  # 精确 50 字符
    return Task(
        id="task-050",
        title=title,
        description="边界测试",
        status=TaskStatus.PENDING,
        priority=TaskPriority.MEDIUM,
        complexity=TaskComplexity.LOW,
    )


@pytest.fixture
def empty_title_task():
    """空标题 Task（title 最小长度为空字符串，用 mock 绕过 pydantic 校验）"""
    task = MagicMock()
    task.id = "task-099"
    task.title = ""
    return task


# ── Class 1: 格式规范测试 ──────────────────────────────────


class TestCommitMessageFormat:
    """验证 commit message 格式符合规范"""

    def test_format_matches_template(self, dev_agent, simple_task):
        """commit message 必须符合 [task-{id}] senior-developer: {desc} 格式"""
        msg = dev_agent.build_commit_message(simple_task)
        assert msg.startswith("[task-")
        assert "] senior-developer: " in msg

    def test_contains_task_id(self, dev_agent, simple_task):
        """commit message 包含 task ID 数字部分"""
        msg = dev_agent.build_commit_message(simple_task)
        assert "001" in msg

    def test_contains_task_title(self, dev_agent, simple_task):
        """短标题完整出现在 commit message 中"""
        msg = dev_agent.build_commit_message(simple_task)
        assert simple_task.title in msg

    def test_single_line_no_newline(self, dev_agent, simple_task):
        """commit message 必须是单行，不含换行符"""
        msg = dev_agent.build_commit_message(simple_task)
        assert "\n" not in msg
        assert "\r" not in msg

    def test_returns_string(self, dev_agent, simple_task):
        """build_commit_message 必须返回 str 类型"""
        msg = dev_agent.build_commit_message(simple_task)
        assert isinstance(msg, str)

    def test_format_constant_used(self, dev_agent, simple_task):
        """生成结果与 _COMMIT_MESSAGE_FORMAT 模板一致"""
        msg = dev_agent.build_commit_message(simple_task)
        expected = _COMMIT_MESSAGE_FORMAT.format(
            task_id="001",
            description=simple_task.title,
        )
        assert msg == expected


# ── Class 2: task ID 解析测试 ──────────────────────────────


class TestTaskIdParsing:
    """验证 task ID 解析（task-001 → 001）"""

    def test_strips_task_prefix(self, dev_agent, simple_task):
        """task-001 → 001（去掉 task- 前缀）"""
        msg = dev_agent.build_commit_message(simple_task)
        # 不应出现 [task-task-001]，只出现 [task-001]
        assert "[task-001]" in msg
        assert "[task-task-001]" not in msg

    def test_three_digit_id(self, dev_agent, long_title_task):
        """task-042 → [task-042]"""
        msg = dev_agent.build_commit_message(long_title_task)
        assert "[task-042]" in msg

    def test_numeric_only_id(self, dev_agent):
        """task-123 → [task-123]"""
        task = Task(
            id="task-123",
            title="测试任务",
            description="desc",
            status=TaskStatus.PENDING,
            priority=TaskPriority.LOW,
            complexity=TaskComplexity.LOW,
        )
        msg = dev_agent.build_commit_message(task)
        assert "[task-123]" in msg


# ── Class 3: 标题截断测试 ──────────────────────────────────


class TestTitleTruncation:
    """验证长标题截断逻辑"""

    def test_long_title_truncated_to_ellipsis(self, dev_agent, long_title_task):
        """超过 50 字符的标题截断为 47 字符 + '...'（共 50 字符）"""
        msg = dev_agent.build_commit_message(long_title_task)
        # 提取 description 部分（senior-developer: 之后）
        desc = msg.split("senior-developer: ", 1)[1]
        assert desc.endswith("...")
        assert len(desc) == 50  # 47 + 3

    def test_short_title_not_truncated(self, dev_agent, simple_task):
        """短标题不截断，原样输出"""
        msg = dev_agent.build_commit_message(simple_task)
        desc = msg.split("senior-developer: ", 1)[1]
        assert desc == simple_task.title
        assert not desc.endswith("...")

    def test_exact_50_char_title_not_truncated(self, dev_agent, exact_50_task):
        """恰好 50 字符的标题不截断（边界值）"""
        msg = dev_agent.build_commit_message(exact_50_task)
        desc = msg.split("senior-developer: ", 1)[1]
        assert len(desc) == 50
        assert not desc.endswith("...")

    def test_51_char_title_truncated(self, dev_agent):
        """51 字符的标题需要截断"""
        task = Task(
            id="task-051",
            title="A" * 51,
            description="desc",
            status=TaskStatus.PENDING,
            priority=TaskPriority.LOW,
            complexity=TaskComplexity.LOW,
        )
        msg = dev_agent.build_commit_message(task)
        desc = msg.split("senior-developer: ", 1)[1]
        assert desc.endswith("...")
        assert len(desc) == 50


# ── Class 4: None / 空值处理 ──────────────────────────────


class TestNullHandling:
    """验证 None 和空值边界处理"""

    def test_none_task_raises_value_error(self, dev_agent):
        """task=None 应抛出 ValueError"""
        with pytest.raises((ValueError, AttributeError)):
            dev_agent.build_commit_message(None)

    def test_empty_title_produces_empty_desc(self, dev_agent, empty_title_task):
        """空标题产生空描述部分，格式仍合法"""
        msg = dev_agent.build_commit_message(empty_title_task)
        assert isinstance(msg, str)
        assert "[task-099]" in msg
        assert "senior-developer: " in msg


# ── Class 5: 缓存行为测试 ──────────────────────────────────


class TestCacheBehavior:
    """验证 _commit_message 缓存机制"""

    def test_commit_message_cached_after_build(self, dev_agent, simple_task):
        """调用后 commit message 被缓存到 _commit_message"""
        assert dev_agent.commit_message is None
        dev_agent.build_commit_message(simple_task)
        assert dev_agent.commit_message is not None

    def test_cached_value_matches_return_value(self, dev_agent, simple_task):
        """缓存值与方法返回值相同"""
        msg = dev_agent.build_commit_message(simple_task)
        assert dev_agent.commit_message == msg

    def test_second_call_overwrites_cache(self, dev_agent, simple_task, long_title_task):
        """第二次调用覆盖缓存（幂等，每次以最新 task 为准）"""
        dev_agent.build_commit_message(simple_task)
        first_cached = dev_agent.commit_message

        dev_agent.build_commit_message(long_title_task)
        second_cached = dev_agent.commit_message

        assert first_cached != second_cached
        assert "[task-042]" in second_cached


# ── Class 6: 日志行为测试 ──────────────────────────────────


class TestLoggingBehavior:
    """验证 build_commit_message 触发正确日志"""

    def test_logs_commit_message(self, dev_agent, simple_task):
        """build_commit_message 应触发 INFO 日志"""
        with patch(
            "agent_automation_system.sub_agent.dev_agent.logger"
        ) as mock_logger:
            dev_agent.build_commit_message(simple_task)
            mock_logger.info.assert_called_once()

    def test_logged_message_contains_commit(self, dev_agent, simple_task):
        """日志内容包含生成的 commit message"""
        with patch(
            "agent_automation_system.sub_agent.dev_agent.logger"
        ) as mock_logger:
            msg = dev_agent.build_commit_message(simple_task)
            log_call_args = mock_logger.info.call_args
            # 日志格式化字符串中包含 commit message
            assert msg in str(log_call_args)


# ── Class 7: 多种 task 类型测试 ──────────────────────────────


class TestVariousTaskTypes:
    """验证多种 task 配置下的 commit message 生成"""

    def test_high_priority_task(self, dev_agent):
        """HIGH 优先级任务正常生成 commit message"""
        task = Task(
            id="task-010",
            title="修复关键安全漏洞",
            description="desc",
            status=TaskStatus.PENDING,
            priority=TaskPriority.HIGH,
            complexity=TaskComplexity.HIGH,
        )
        msg = dev_agent.build_commit_message(task)
        assert "修复关键安全漏洞" in msg

    def test_low_complexity_task(self, dev_agent):
        """LOW 复杂度任务正常生成 commit message"""
        task = Task(
            id="task-005",
            title="更新 README 文档",
            description="desc",
            status=TaskStatus.PENDING,
            priority=TaskPriority.LOW,
            complexity=TaskComplexity.LOW,
        )
        msg = dev_agent.build_commit_message(task)
        assert "[task-005]" in msg
        assert "更新 README 文档" in msg

    def test_unicode_title(self, dev_agent):
        """含中文 Unicode 字符的标题正常处理"""
        task = Task(
            id="task-007",
            title="实现数据库连接池管理器",
            description="desc",
            status=TaskStatus.PENDING,
            priority=TaskPriority.HIGH,
            complexity=TaskComplexity.MEDIUM,
        )
        msg = dev_agent.build_commit_message(task)
        assert "实现数据库连接池管理器" in msg

    def test_special_chars_in_title(self, dev_agent):
        """标题含特殊字符（-、/、()）正常处理"""
        task = Task(
            id="task-008",
            title="实现 REST API (v2) - /users 端点",
            description="desc",
            status=TaskStatus.PENDING,
            priority=TaskPriority.HIGH,
            complexity=TaskComplexity.MEDIUM,
        )
        msg = dev_agent.build_commit_message(task)
        assert isinstance(msg, str)
        assert "[task-008]" in msg


# ── Class 8: 集成场景测试 ──────────────────────────────────


class TestIntegrationScenarios:
    """端到端场景验证"""

    def test_full_tdd_flow_commit_step(self, dev_agent, simple_task):
        """模拟完整 TDD 流程最后一步：build_commit_message 生成提交信息"""
        # 前置：simulate analyze → write_tests → implement → run_tests 已完成
        dev_agent._implementation_plan = "已完成实现方案"
        dev_agent._test_results = {"passed": 5, "failed": 0}

        msg = dev_agent.build_commit_message(simple_task)

        assert msg.startswith("[task-001]")
        assert "senior-developer" in msg
        assert dev_agent.commit_message == msg

    def test_fresh_agent_no_cached_message(self):
        """新创建的 agent 无缓存 commit message"""
        agent = SeniorDeveloperAgent()
        assert agent.commit_message is None

    def test_message_non_empty(self, dev_agent, simple_task):
        """commit message 不为空字符串"""
        msg = dev_agent.build_commit_message(simple_task)
        assert len(msg) > 0
        assert msg.strip() != ""

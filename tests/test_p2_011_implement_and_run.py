"""
P2-011 测试：SeniorDeveloperAgent.implement_code / run_tests 实现

验证 implement_code 和 run_tests 完整实现，覆盖：
1. ImplementResult 数据模型
2. TestRunResult 数据模型
3. implement_code 核心流程
4. run_tests 核心流程
5. 实现摘要构建
6. 代码行数估算
7. 代码骨架生成
8. 测试命令和计数估算
9. 内部辅助方法
10. 边界条件与异常处理
"""

import re
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_automation_system.models.dev_analysis import TaskAnalysisResult
from agent_automation_system.models.dev_implement import ImplementResult, TestRunResult
from agent_automation_system.models.task import (
    BDDSpec,
    Task,
    TaskComplexity,
    TaskPriority,
    TaskStatus,
)
from agent_automation_system.models.test_write import TestCaseInfo, TestWriteResult
from agent_automation_system.sub_agent.dev_agent import (
    SeniorDeveloperAgent,
    _DEFAULT_MAX_IMPLEMENTATION_MINUTES,
)
from agent_automation_system.sub_agent.role_injector import RoleInjector
from agent_automation_system.sub_agent.sub_agent import (
    AgentPhase,
    SubAgentResult,
    SubAgentResultStatus,
)


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def dev_agent():
    """创建默认 SeniorDeveloperAgent 实例"""
    return SeniorDeveloperAgent()


@pytest.fixture
def sample_task():
    """创建示例 Task（含 BDD，MEDIUM 复杂度）"""
    return Task(
        id="task-001",
        title="实现用户登录 API",
        description="实现用户登录接口，支持邮箱和手机号登录",
        bdd=BDDSpec(
            given="用户已注册账号",
            when="提交正确的登录凭证",
            then="返回认证 token 和用户信息",
        ),
        dependencies=[],
        suggested_role="senior-developer",
        priority=TaskPriority.HIGH,
        estimated_complexity=TaskComplexity.MEDIUM,
        status=TaskStatus.PENDING,
    )


@pytest.fixture
def task_without_bdd():
    """创建无 BDD 的 Task"""
    return Task(
        id="task-010",
        title="简单配置修改",
        description="修改配置文件中的默认值",
        priority=TaskPriority.LOW,
        estimated_complexity=TaskComplexity.LOW,
        status=TaskStatus.PENDING,
    )


@pytest.fixture
def high_complexity_task():
    """创建高复杂度 Task"""
    return Task(
        id="task-020",
        title="实现并发任务调度 service",
        description="实现支持并发的任务调度服务，需要线程安全",
        bdd=BDDSpec(
            given="调度器已初始化",
            when="提交多个并发任务",
            then="所有任务按优先级顺序执行",
        ),
        dependencies=["task-001"],
        priority=TaskPriority.HIGH,
        estimated_complexity=TaskComplexity.HIGH,
        status=TaskStatus.PENDING,
    )


# ── 1. ImplementResult 数据模型 ───────────────────────────


class TestImplementResultModel:
    """验证 ImplementResult 数据模型"""

    def test_create_with_required_fields(self):
        """创建 ImplementResult 仅需 task_id"""
        result = ImplementResult(task_id="task-001")
        assert result.task_id == "task-001"
        assert result.files_changed == []
        assert result.implementation_summary == ""
        assert result.lines_added == 0
        assert result.lines_removed == 0
        assert result.status == "completed"

    def test_create_with_all_fields(self):
        """创建 ImplementResult 含全部字段"""
        result = ImplementResult(
            task_id="task-001",
            files_changed=["a.py", "b.py"],
            implementation_summary="实现登录功能",
            lines_added=85,
            lines_removed=5,
            implementation_content="code here",
            status="completed",
        )
        assert result.task_id == "task-001"
        assert len(result.files_changed) == 2
        assert result.lines_added == 85

    def test_has_changes_property(self):
        """has_changes 属性"""
        r1 = ImplementResult(task_id="task-001")
        assert r1.has_changes is False

        r2 = ImplementResult(task_id="task-001", lines_added=10)
        assert r2.has_changes is True

        r3 = ImplementResult(task_id="task-001", files_changed=["a.py"])
        assert r3.has_changes is True

    def test_net_lines_property(self):
        """net_lines 属性"""
        result = ImplementResult(
            task_id="task-001", lines_added=100, lines_removed=20
        )
        assert result.net_lines == 80

    def test_change_count_property(self):
        """change_count 属性"""
        result = ImplementResult(
            task_id="task-001", files_changed=["a.py", "b.py", "c.py"]
        )
        assert result.change_count == 3

    def test_to_text_contains_basic_info(self):
        """to_text 包含基本信息"""
        result = ImplementResult(
            task_id="task-001",
            implementation_summary="实现登录",
            files_changed=["login.py"],
            lines_added=50,
        )
        text = result.to_text()
        assert "task-001" in text
        assert "实现登录" in text
        assert "login.py" in text
        assert "50" in text

    def test_task_id_required(self):
        """task_id 必填"""
        with pytest.raises(Exception):
            ImplementResult()

    def test_lines_cannot_be_negative(self):
        """行数不能为负"""
        with pytest.raises(Exception):
            ImplementResult(task_id="task-001", lines_added=-1)
        with pytest.raises(Exception):
            ImplementResult(task_id="task-001", lines_removed=-1)

    def test_created_at_auto_set(self):
        """created_at 自动设置"""
        result = ImplementResult(task_id="task-001")
        assert result.created_at is not None

    def test_serialization(self):
        """可序列化"""
        result = ImplementResult(
            task_id="task-001",
            files_changed=["a.py"],
            lines_added=10,
        )
        data = result.model_dump()
        assert "task_id" in data
        assert "files_changed" in data
        json_str = result.model_dump_json()
        assert json_str is not None


# ── 2. TestRunResult 数据模型 ─────────────────────────────


class TestTestRunResultModel:
    """验证 TestRunResult 数据模型"""

    def test_create_with_required_fields(self):
        """创建 TestRunResult 仅需 task_id"""
        result = TestRunResult(task_id="task-001")
        assert result.task_id == "task-001"
        assert result.passed is True
        assert result.total == 0
        assert result.passed_count == 0
        assert result.failed_count == 0

    def test_create_with_all_fields(self):
        """创建 TestRunResult 含全部字段"""
        result = TestRunResult(
            task_id="task-001",
            passed=True,
            total=5,
            passed_count=5,
            failed_count=0,
            error_details="",
            test_file_path="tests/test_task_001.py",
            duration_seconds=0.35,
        )
        assert result.total == 5
        assert result.pass_rate == 1.0

    def test_pass_rate_property(self):
        """pass_rate 属性"""
        result = TestRunResult(
            task_id="task-001", total=10, passed_count=8
        )
        assert result.pass_rate == 0.8

    def test_pass_rate_zero_total(self):
        """total 为 0 时 pass_rate 为 1.0"""
        result = TestRunResult(task_id="task-001", total=0)
        assert result.pass_rate == 1.0

    def test_has_failures_property(self):
        """has_failures 属性"""
        r1 = TestRunResult(task_id="task-001", failed_count=0)
        assert r1.has_failures is False

        r2 = TestRunResult(task_id="task-001", failed_count=2)
        assert r2.has_failures is True

    def test_all_passed_property(self):
        """all_passed 属性"""
        r1 = TestRunResult(task_id="task-001", passed=True, failed_count=0)
        assert r1.all_passed is True

        r2 = TestRunResult(task_id="task-001", passed=False, failed_count=1)
        assert r2.all_passed is False

        # passed=True 但有失败也视为未全通过
        r3 = TestRunResult(task_id="task-001", passed=True, failed_count=1)
        assert r3.all_passed is False

    def test_to_text_contains_basic_info(self):
        """to_text 包含基本信息"""
        result = TestRunResult(
            task_id="task-001",
            total=5,
            passed_count=5,
            test_file_path="tests/test_task_001.py",
        )
        text = result.to_text()
        assert "task-001" in text
        assert "5" in text

    def test_to_text_shows_failure(self):
        """to_text 含失败时显示错误"""
        result = TestRunResult(
            task_id="task-001",
            passed=False,
            total=5,
            passed_count=3,
            failed_count=2,
            error_details="AssertionError in test_x",
        )
        text = result.to_text()
        assert "失败" in text or "AssertionError" in text

    def test_task_id_required(self):
        """task_id 必填"""
        with pytest.raises(Exception):
            TestRunResult()

    def test_counts_cannot_be_negative(self):
        """计数不能为负"""
        with pytest.raises(Exception):
            TestRunResult(task_id="task-001", total=-1)
        with pytest.raises(Exception):
            TestRunResult(task_id="task-001", passed_count=-1)
        with pytest.raises(Exception):
            TestRunResult(task_id="task-001", failed_count=-1)

    def test_duration_cannot_be_negative(self):
        """时长不能为负"""
        with pytest.raises(Exception):
            TestRunResult(task_id="task-001", duration_seconds=-1.0)

    def test_created_at_auto_set(self):
        """created_at 自动设置"""
        result = TestRunResult(task_id="task-001")
        assert result.created_at is not None


# ── 3. implement_code 核心流程 ────────────────────────────


class TestImplementCodeCore:
    """验证 implement_code 核心流程"""

    def test_returns_implement_result(self, dev_agent, sample_task):
        """implement_code 返回 ImplementResult"""
        result = dev_agent.implement_code(sample_task)
        assert isinstance(result, ImplementResult)

    def test_result_task_id_matches(self, dev_agent, sample_task):
        """结果 task_id 与输入一致"""
        result = dev_agent.implement_code(sample_task)
        assert result.task_id == sample_task.id

    def test_result_has_files_changed(self, dev_agent, sample_task):
        """结果包含变更文件列表"""
        result = dev_agent.implement_code(sample_task)
        assert isinstance(result.files_changed, list)
        assert len(result.files_changed) > 0

    def test_result_has_implementation_summary(self, dev_agent, sample_task):
        """结果包含实现摘要"""
        result = dev_agent.implement_code(sample_task)
        assert result.implementation_summary != ""

    def test_result_has_lines_added(self, dev_agent, sample_task):
        """结果包含新增行数"""
        result = dev_agent.implement_code(sample_task)
        assert result.lines_added > 0

    def test_result_status_completed(self, dev_agent, sample_task):
        """结果状态为 completed"""
        result = dev_agent.implement_code(sample_task)
        assert result.status == "completed"

    def test_none_task_raises_value_error(self, dev_agent):
        """None 任务抛出 ValueError"""
        with pytest.raises(ValueError, match="task cannot be None"):
            dev_agent.implement_code(None)

    def test_result_has_implementation_content(self, dev_agent, sample_task):
        """结果包含代码骨架内容"""
        result = dev_agent.implement_code(sample_task)
        assert result.implementation_content != ""

    def test_result_created_at_set(self, dev_agent, sample_task):
        """结果 created_at 已设置"""
        result = dev_agent.implement_code(sample_task)
        assert result.created_at is not None

    def test_lines_removed_is_zero(self, dev_agent, sample_task):
        """新实现 lines_removed 为 0"""
        result = dev_agent.implement_code(sample_task)
        assert result.lines_removed == 0


# ── 4. run_tests 核心流程 ────────────────────────────────


class TestRunTestsCore:
    """验证 run_tests 核心流程"""

    def test_returns_test_run_result(self, dev_agent, sample_task):
        """run_tests 返回 TestRunResult"""
        result = dev_agent.run_tests(sample_task)
        assert isinstance(result, TestRunResult)

    def test_result_task_id_matches(self, dev_agent, sample_task):
        """结果 task_id 与输入一致"""
        result = dev_agent.run_tests(sample_task)
        assert result.task_id == sample_task.id

    def test_result_has_test_file_path(self, dev_agent, sample_task):
        """结果包含测试文件路径"""
        result = dev_agent.run_tests(sample_task)
        assert result.test_file_path == "tests/test_task_001.py"

    def test_result_has_total(self, dev_agent, sample_task):
        """结果包含总测试数"""
        result = dev_agent.run_tests(sample_task)
        assert result.total > 0

    def test_result_default_passed(self, dev_agent, sample_task):
        """默认结果为全部通过"""
        result = dev_agent.run_tests(sample_task)
        assert result.passed is True
        assert result.failed_count == 0

    def test_none_task_raises_value_error(self, dev_agent):
        """None 任务抛出 ValueError"""
        with pytest.raises(ValueError, match="task cannot be None"):
            dev_agent.run_tests(None)

    def test_caches_test_results(self, dev_agent, sample_task):
        """结果缓存到 _test_results"""
        dev_agent.run_tests(sample_task)
        assert dev_agent.test_results is not None
        assert isinstance(dev_agent.test_results, dict)

    def test_result_created_at_set(self, dev_agent, sample_task):
        """结果 created_at 已设置"""
        result = dev_agent.run_tests(sample_task)
        assert result.created_at is not None

    def test_passed_count_equals_total(self, dev_agent, sample_task):
        """默认通过数等于总数"""
        result = dev_agent.run_tests(sample_task)
        assert result.passed_count == result.total


# ── 5. 实现摘要构建 ────────────────────────────────────


class TestImplementationSummary:
    """验证 _build_implementation_summary"""

    def test_summary_contains_title(self, dev_agent, sample_task):
        """摘要包含任务标题"""
        summary = dev_agent._build_implementation_summary(sample_task)
        assert sample_task.title in summary

    def test_summary_with_bdd(self, dev_agent, sample_task):
        """有 BDD 时摘要包含 BDD 信息"""
        summary = dev_agent._build_implementation_summary(sample_task)
        assert "Given" in summary or "BDD" in summary

    def test_summary_without_bdd(self, dev_agent, task_without_bdd):
        """无 BDD 时摘要包含描述"""
        summary = dev_agent._build_implementation_summary(task_without_bdd)
        assert "配置文件" in summary or "描述" in summary

    def test_summary_with_dependencies(self, dev_agent, high_complexity_task):
        """有依赖时摘要包含依赖信息"""
        summary = dev_agent._build_implementation_summary(high_complexity_task)
        assert "task-001" in summary or "依赖" in summary


# ── 6. 代码行数估算 ────────────────────────────────────


class TestLinesEstimation:
    """验证 _estimate_lines_added"""

    def test_low_complexity(self, dev_agent, task_without_bdd):
        """LOW 复杂度估算"""
        lines = dev_agent._estimate_lines_added(
            task_without_bdd, ["agent_automation_system/config.py"]
        )
        assert lines > 0
        assert lines <= 30

    def test_medium_complexity(self, dev_agent, sample_task):
        """MEDIUM 复杂度估算"""
        lines = dev_agent._estimate_lines_added(
            sample_task, ["agent_automation_system/api/login_api.py"]
        )
        assert lines > 0
        assert lines >= 20

    def test_high_complexity(self, dev_agent, high_complexity_task):
        """HIGH 复杂度估算"""
        lines = dev_agent._estimate_lines_added(
            high_complexity_task, ["agent_automation_system/services/scheduler_service.py"]
        )
        assert lines > 0
        assert lines >= 40

    def test_more_files_more_lines(self, dev_agent, sample_task):
        """更多文件更多行数"""
        lines1 = dev_agent._estimate_lines_added(sample_task, ["a.py"])
        lines2 = dev_agent._estimate_lines_added(sample_task, ["a.py", "b.py", "c.py"])
        assert lines2 > lines1

    def test_excludes_test_files(self, dev_agent, sample_task):
        """测试文件不计入源文件行数"""
        lines1 = dev_agent._estimate_lines_added(sample_task, ["src/a.py"])
        lines2 = dev_agent._estimate_lines_added(
            sample_task, ["src/a.py", "tests/test_a.py"]
        )
        # 行数相同因为 tests/ 被排除
        assert lines1 == lines2


# ── 7. 代码骨架生成 ────────────────────────────────────


class TestImplementationSkeleton:
    """验证 _build_implementation_skeleton"""

    def test_api_skeleton(self, dev_agent, sample_task):
        """API 任务生成 API 骨架"""
        content = dev_agent._build_implementation_skeleton(
            sample_task, ["agent_automation_system/api/login_api.py"]
        )
        assert "class" in content
        assert "API" in content

    def test_model_skeleton(self, dev_agent):
        """模型任务生成 Model 骨架"""
        task = Task(
            id="task-040",
            title="实现用户数据模型",
            description="创建用户模型类",
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        )
        content = dev_agent._build_implementation_skeleton(
            task, ["agent_automation_system/models/user.py"]
        )
        assert "BaseModel" in content or "class" in content

    def test_service_skeleton(self, dev_agent, high_complexity_task):
        """服务任务生成 Service 骨架"""
        content = dev_agent._build_implementation_skeleton(
            high_complexity_task, ["agent_automation_system/services/scheduler_service.py"]
        )
        assert "class" in content
        assert "Service" in content or "service" in content

    def test_util_skeleton(self, dev_agent):
        """工具任务生成工具函数骨架"""
        task = Task(
            id="task-050",
            title="实现数据验证 validator",
            description="创建验证工具",
            priority=TaskPriority.LOW,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        content = dev_agent._build_implementation_skeleton(
            task, ["agent_automation_system/utils/validator.py"]
        )
        assert "def" in content or "class" in content

    def test_generic_skeleton(self, dev_agent, task_without_bdd):
        """通用任务生成通用骨架"""
        content = dev_agent._build_implementation_skeleton(
            task_without_bdd, ["agent_automation_system/config_modify.py"]
        )
        assert "class" in content or "def" in content

    def test_skeleton_has_docstring(self, dev_agent, sample_task):
        """骨架包含 docstring"""
        content = dev_agent._build_implementation_skeleton(
            sample_task, ["agent_automation_system/api/login_api.py"]
        )
        assert '"""' in content

    def test_skeleton_has_not_implemented(self, dev_agent, sample_task):
        """骨架包含 NotImplementedError"""
        content = dev_agent._build_implementation_skeleton(
            sample_task, ["agent_automation_system/api/login_api.py"]
        )
        assert "NotImplementedError" in content or "TODO" in content

    def test_skeleton_is_valid_python(self, dev_agent, sample_task):
        """骨架是有效 Python 语法"""
        content = dev_agent._build_implementation_skeleton(
            sample_task, ["agent_automation_system/api/login_api.py"]
        )
        compile(content, "<skeleton>", "exec")


# ── 8. 测试命令和计数估算 ────────────────────────────────


class TestTestCommandAndCount:
    """验证 _build_test_command 和 _estimate_test_count"""

    def test_build_test_command(self, dev_agent, sample_task):
        """构建 pytest 命令"""
        cmd = dev_agent._build_test_command(sample_task, "tests/test_task_001.py")
        assert "pytest" in cmd
        assert "test_task_001.py" in cmd

    def test_estimate_test_count_low(self, dev_agent, task_without_bdd):
        """LOW 复杂度测试数"""
        count = dev_agent._estimate_test_count(task_without_bdd)
        assert count >= 2

    def test_estimate_test_count_medium(self, dev_agent, sample_task):
        """MEDIUM 复杂度测试数"""
        count = dev_agent._estimate_test_count(sample_task)
        assert count >= 4

    def test_estimate_test_count_high(self, dev_agent, high_complexity_task):
        """HIGH 复杂度测试数"""
        count = dev_agent._estimate_test_count(high_complexity_task)
        assert count >= 7

    def test_bdd_increases_count(self, dev_agent):
        """BDD 增加测试计数"""
        task_with_bdd = Task(
            id="task-060",
            title="功能 A",
            description="描述",
            bdd=BDDSpec(given="前提", when="动作", then="结果"),
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        )
        task_no_bdd = Task(
            id="task-061",
            title="功能 B",
            description="描述",
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        )
        assert dev_agent._estimate_test_count(task_with_bdd) > dev_agent._estimate_test_count(task_no_bdd)

    def test_api_increases_count(self, dev_agent):
        """API 关键词增加测试计数"""
        task_api = Task(
            id="task-070",
            title="实现 API 接口",
            description="创建接口",
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        )
        task_normal = Task(
            id="task-071",
            title="普通功能",
            description="普通描述",
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        )
        assert dev_agent._estimate_test_count(task_api) > dev_agent._estimate_test_count(task_normal)


# ── 9. 内部辅助方法 ──────────────────────────────────────


class TestInternalHelpers:
    """验证 implement_code / run_tests 内部辅助方法"""

    def test_skeleton_api_method(self, dev_agent):
        """_skeleton_api 生成包含 handle_request 的类"""
        lines = dev_agent._skeleton_api("login_api", sample_task := Task(
            id="task-001",
            title="登录 API",
            description="实现登录",
            priority=TaskPriority.HIGH,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        ))
        content = "\n".join(lines)
        assert "handle_request" in content

    def test_skeleton_model_method(self, dev_agent):
        """_skeleton_model 生成包含 BaseModel 的类"""
        lines = dev_agent._skeleton_model("user", Task(
            id="task-001",
            title="用户模型",
            description="创建模型",
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        ))
        content = "\n".join(lines)
        assert "BaseModel" in content

    def test_skeleton_service_method(self, dev_agent):
        """_skeleton_service 生成包含 execute 的类"""
        lines = dev_agent._skeleton_service("scheduler_service", Task(
            id="task-001",
            title="调度服务",
            description="实现服务",
            priority=TaskPriority.HIGH,
            estimated_complexity=TaskComplexity.HIGH,
            status=TaskStatus.PENDING,
        ))
        content = "\n".join(lines)
        assert "execute" in content

    def test_skeleton_util_method(self, dev_agent):
        """_skeleton_util 生成函数定义"""
        lines = dev_agent._skeleton_util("validate_data", Task(
            id="task-001",
            title="数据验证",
            description="验证工具",
            priority=TaskPriority.LOW,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        ))
        content = "\n".join(lines)
        assert "def validate_data" in content

    def test_skeleton_generic_method(self, dev_agent):
        """_skeleton_generic 生成包含 run 的类"""
        lines = dev_agent._skeleton_generic("my_module", Task(
            id="task-001",
            title="通用模块",
            description="通用功能",
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        ))
        content = "\n".join(lines)
        assert "run" in content

    def test_build_test_command_format(self, dev_agent):
        """_build_test_command 格式正确"""
        cmd = dev_agent._build_test_command(
            Task(
                id="task-099",
                title="测试",
                description="测试",
                priority=TaskPriority.LOW,
                estimated_complexity=TaskComplexity.LOW,
                status=TaskStatus.PENDING,
            ),
            "tests/test_task_099.py",
        )
        assert "pytest" in cmd
        assert "test_task_099.py" in cmd


# ── 10. 边界条件与异常处理 ──────────────────────────────


class TestBoundaryConditions:
    """验证边界条件和异常处理"""

    def test_task_without_bdd_implement(self, dev_agent, task_without_bdd):
        """无 BDD 任务实现不崩溃"""
        result = dev_agent.implement_code(task_without_bdd)
        assert isinstance(result, ImplementResult)
        assert result.task_id == "task-010"

    def test_task_without_bdd_run_tests(self, dev_agent, task_without_bdd):
        """无 BDD 任务运行测试不崩溃"""
        result = dev_agent.run_tests(task_without_bdd)
        assert isinstance(result, TestRunResult)

    def test_multiple_implement_calls_independent(self, dev_agent, sample_task, task_without_bdd):
        """多次 implement_code 调用互不影响"""
        result1 = dev_agent.implement_code(sample_task)
        result2 = dev_agent.implement_code(task_without_bdd)
        assert result1.task_id != result2.task_id

    def test_multiple_run_tests_calls(self, dev_agent, sample_task):
        """多次 run_tests 调用覆盖缓存"""
        result1 = dev_agent.run_tests(sample_task)
        result2 = dev_agent.run_tests(sample_task)
        assert result1.task_id == result2.task_id

    def test_task_with_many_dependencies(self, dev_agent):
        """多依赖任务实现不崩溃"""
        task = Task(
            id="task-080",
            title="集成测试模块",
            description="集成多个模块",
            dependencies=["task-001", "task-002", "task-003"],
            priority=TaskPriority.HIGH,
            estimated_complexity=TaskComplexity.HIGH,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.implement_code(task)
        assert isinstance(result, ImplementResult)

    def test_task_with_special_chars(self, dev_agent):
        """标题含特殊字符不崩溃"""
        task = Task(
            id="task-090",
            title="处理 <特殊> 字符 & 符号",
            description="特殊字符输入",
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.implement_code(task)
        assert isinstance(result, ImplementResult)

    def test_implement_content_is_valid_python(self, dev_agent, sample_task):
        """生成的实现内容是有效 Python 语法"""
        result = dev_agent.implement_code(sample_task)
        compile(result.implementation_content, "<implement>", "exec")

    def test_run_tests_result_serializable(self, dev_agent, sample_task):
        """TestRunResult 可序列化"""
        result = dev_agent.run_tests(sample_task)
        data = result.model_dump()
        assert "task_id" in data
        json_str = result.model_dump_json()
        assert json_str is not None

    def test_implement_result_serializable(self, dev_agent, sample_task):
        """ImplementResult 可序列化"""
        result = dev_agent.implement_code(sample_task)
        data = result.model_dump()
        assert "task_id" in data
        json_str = result.model_dump_json()
        assert json_str is not None

    def test_high_complexity_more_lines(self, dev_agent, high_complexity_task, sample_task):
        """高复杂度任务更多行数"""
        high_result = dev_agent.implement_code(high_complexity_task)
        normal_result = dev_agent.implement_code(sample_task)
        assert high_result.lines_added >= normal_result.lines_added

    def test_high_complexity_more_tests(self, dev_agent, high_complexity_task, sample_task):
        """高复杂度任务更多测试数"""
        high_result = dev_agent.run_tests(high_complexity_task)
        normal_result = dev_agent.run_tests(sample_task)
        assert high_result.total >= normal_result.total

"""
P2-025 测试：TDD 闭环 execute_tdd_workflow 完整实现

验证 analyze → write_tests → implement_code → run_tests → commit/rollback 闭环。
覆盖：
1. TddWorkflowResult 数据模型
2. 完整 TDD 闭环（测试通过 → commit）
3. 测试失败场景（测试失败 → 不 commit）
4. 异常恢复（分析失败/实现失败）
5. 与 GitManager 集成（真实 commit）
6. 与 TestRunner 集成（真实测试执行）
7. 无 test_runner 场景（内置预估逻辑）
8. 无 git_manager 场景（仅构建 commit message）
9. 零值防御（空 task、空 BDD）
10. 性能和日志记录
"""

import os
import time
import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

from agent_automation_system.models.dev_analysis import TaskAnalysisResult
from agent_automation_system.models.dev_implement import (
    ImplementResult,
    TddWorkflowResult,
    TddWorkflowStatus,
    TestRunResult,
)
from agent_automation_system.models.task import (
    BDDSpec,
    Task,
    TaskComplexity,
    TaskPriority,
    TaskStatus,
)
from agent_automation_system.models.test_write import TestCaseInfo, TestWriteResult
from agent_automation_system.sub_agent.dev_agent import SeniorDeveloperAgent
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
def task_with_dependencies():
    """创建有依赖的 Task"""
    return Task(
        id="task-005",
        title="实现订单创建服务",
        description="依赖用户认证和商品查询服务",
        bdd=BDDSpec(
            given="用户已认证并有可用商品",
            when="用户提交有效订单",
            then="创建订单并返回订单 ID",
        ),
        dependencies=["task-001", "task-002"],
        suggested_role="senior-developer",
        priority=TaskPriority.HIGH,
        estimated_complexity=TaskComplexity.HIGH,
        status=TaskStatus.PENDING,
    )


@pytest.fixture
def task_without_bdd():
    """创建无 BDD 的 Task"""
    return Task(
        id="task-010",
        title="简单配置修改",
        description="修改配置文件中的默认值",
        dependencies=[],
        suggested_role="senior-developer",
        priority=TaskPriority.MEDIUM,
        estimated_complexity=TaskComplexity.LOW,
        status=TaskStatus.PENDING,
    )


@pytest.fixture
def mock_git_manager():
    """创建 mock GitManager（commit 默认成功）"""
    git_mgr = MagicMock()
    git_mgr.commit_changes.return_value = {
        "success": True,
        "hexsha": "a3f7b2c1234567890abcdef1234567890abcdef",
        "short_sha": "a3f7b2c",
        "files_committed": ["agent_automation_system/api/login.py", "tests/test_task_001.py"],
        "error": None,
        "retries": 0,
    }
    return git_mgr


@pytest.fixture
def mock_git_manager_failure():
    """创建 mock GitManager（commit 失败）"""
    git_mgr = MagicMock()
    git_mgr.commit_changes.return_value = {
        "success": False,
        "hexsha": None,
        "short_sha": None,
        "files_committed": [],
        "error": "没有变更需要提交",
        "retries": 0,
    }
    return git_mgr


@pytest.fixture
def mock_test_runner_passing():
    """创建 mock TestRunner（所有测试通过）"""
    from agent_automation_system.scheduler.test_runner import TestResult

    runner = MagicMock()
    runner.execute.return_value = TestResult(
        test_file_path="tests/test_task_001.py",
        passed=True,
        total=4,
        passed_count=4,
        failed_count=0,
        error_count=0,
        output="============================= test session starts ==============================\ntests/test_task_001.py::test_submit_valid_credentials_returns_expected PASSED\ntests/test_task_001.py::test_submit_valid_credentials_with_invalid_input_fails PASSED\n============================== 4 passed in 0.35s ==============================",
        error_output="",
        duration_seconds=0.35,
    )
    return runner


@pytest.fixture
def mock_test_runner_failing():
    """创建 mock TestRunner（测试失败）"""
    from agent_automation_system.scheduler.test_runner import TestResult

    runner = MagicMock()
    runner.execute.return_value = TestResult(
        test_file_path="tests/test_task_001.py",
        passed=False,
        total=4,
        passed_count=3,
        failed_count=1,
        error_count=0,
        output="============================= test session starts ==============================\ntests/test_task_001.py::test_submit_valid_credentials_returns_expected FAILED\nFAILED tests/test_task_001.py::test_submit_valid_credentials_returns_expected - assert False\n======================== 3 passed, 1 failed in 0.42s ==========================",
        error_output="",
        duration_seconds=0.42,
    )
    return runner


# ── TddWorkflowResult 模型测试 ────────────────────────────


class TestTddWorkflowResultModel:
    """TddWorkflowResult 数据模型验证"""

    def test_committed_success(self):
        r = TddWorkflowResult(
            task_id="task-001",
            workflow_status=TddWorkflowStatus.COMMITTED,
            commit_hash="abc123",
            duration_seconds=10.0,
        )
        assert r.success is True
        assert r.is_committed is True
        assert r.tests_passed is False  # 无 run_tests 步骤结果

    def test_test_failed(self):
        r = TddWorkflowResult(
            task_id="task-002",
            workflow_status=TddWorkflowStatus.TEST_FAILED,
            step_results={
                "run_tests": {"passed": False, "failed_count": 1},
            },
            error_message="1 test failed",
            duration_seconds=5.0,
        )
        assert r.success is False
        assert r.is_committed is False
        assert r.tests_passed is False

    def test_analyze_failed(self):
        r = TddWorkflowResult(
            task_id="task-003",
            workflow_status=TddWorkflowStatus.ANALYZE_FAILED,
            error_message="Analysis failed",
            duration_seconds=0.5,
        )
        assert r.success is False
        assert r.is_committed is False

    def test_implement_failed(self):
        r = TddWorkflowResult(
            task_id="task-004",
            workflow_status=TddWorkflowStatus.IMPLEMENT_FAILED,
            error_message="Implementation error",
            duration_seconds=3.0,
        )
        assert r.success is False

    def test_defaults(self):
        r = TddWorkflowResult(
            task_id="task-010",
            workflow_status=TddWorkflowStatus.COMMITTED,
        )
        assert r.error_message == ""
        assert r.duration_seconds == 0.0
        assert r.step_results == {}
        assert r.commit_hash is None
        assert isinstance(r.created_at, datetime)

    def test_to_text_committed(self):
        r = TddWorkflowResult(
            task_id="task-001",
            workflow_status=TddWorkflowStatus.COMMITTED,
            commit_hash="a3f7b2c1234567890abcdef1234567890abcdef",
            step_results={
                "analyze": {"status": "completed", "summary": "2 files"},
                "run_tests": {"status": "passed", "summary": "4/4 passed"},
            },
            duration_seconds=12.5,
        )
        text = r.to_text()
        assert "task-001" in text
        assert "COMMITTED" in text
        assert "12.50s" in text
        assert "a3f7b2c" in text

    def test_to_text_test_failed(self):
        r = TddWorkflowResult(
            task_id="task-002",
            workflow_status=TddWorkflowStatus.TEST_FAILED,
            error_message="1 test failed: test_login",
            step_results={
                "run_tests": {"status": "failed", "summary": "3/4 passed"},
            },
            duration_seconds=5.0,
        )
        text = r.to_text()
        assert "TEST_FAILED" in text
        assert "test_login" in text

    def test_step_results_preserve_detail(self):
        r = TddWorkflowResult(
            task_id="task-001",
            workflow_status=TddWorkflowStatus.COMMITTED,
            step_results={
                "analyze": {
                    "status": "completed",
                    "summary": "3 files to create + 1 to modify",
                    "files_to_create": ["a.py", "b.py"],
                    "files_to_modify": ["c.py"],
                    "estimated_effort_min": 30,
                    "risks": ["risk1"],
                    "test_strategy": "TDD",
                    "technical_approach": "API pattern",
                },
                "write_tests": {
                    "status": "completed",
                    "test_file_path": "tests/test_x.py",
                    "test_count": 4,
                },
                "implement": {
                    "status": "completed",
                    "lines_added": 85,
                    "files_changed": ["a.py"],
                },
                "run_tests": {
                    "status": "passed",
                    "total": 4,
                    "passed_count": 4,
                },
                "commit": {
                    "status": "committed",
                    "short_sha": "abc1234",
                },
            },
        )
        assert len(r.step_results) == 5
        assert r.step_results["analyze"]["files_to_create"] == ["a.py", "b.py"]


# ── 完整 TDD 闭环测试 ────────────────────────────────────


class TestTddWorkflowSuccess:
    """TDD 闭环：测试通过 → commit"""

    def test_full_workflow_with_mocks(self, dev_agent, sample_task, mock_git_manager, mock_test_runner_passing):
        """完整闭环：测试通过 → commit 成功"""
        result = dev_agent.execute_tdd_workflow(
            task=sample_task,
            test_runner=mock_test_runner_passing,
            git_manager=mock_git_manager,
        )

        assert result.success is True
        assert result.workflow_status == TddWorkflowStatus.COMMITTED
        assert result.commit_hash == "a3f7b2c1234567890abcdef1234567890abcdef"
        assert result.duration_seconds > 0
        assert result.error_message == ""

        # 验证 5 个步骤都有结果
        assert "analyze" in result.step_results
        assert "write_tests" in result.step_results
        assert "implement" in result.step_results
        assert "run_tests" in result.step_results
        assert "commit" in result.step_results

        # 验证分析步骤
        analyze = result.step_results["analyze"]
        assert analyze["status"] == "completed"
        assert len(analyze["files_to_create"]) >= 1  # 至少有测试文件
        assert analyze["estimated_effort_min"] > 0
        assert len(analyze["risks"]) >= 0
        assert len(analyze["technical_approach"]) > 0

        # 验证测试编写步骤
        write_tests = result.step_results["write_tests"]
        assert write_tests["status"] == "completed"
        assert write_tests["test_count"] >= 2
        assert "tests/" in write_tests["test_file_path"]

        # 验证实现步骤
        implement = result.step_results["implement"]
        assert implement["status"] == "completed"
        assert implement["lines_added"] >= 0
        assert len(implement["files_changed"]) >= 1

        # 验证测试运行步骤
        run_tests = result.step_results["run_tests"]
        assert run_tests["status"] == "passed"
        assert run_tests["executed"] is True
        assert run_tests["total"] > 0
        assert run_tests["failed_count"] == 0

        # 验证 commit 步骤
        commit = result.step_results["commit"]
        assert commit["status"] == "committed"
        assert commit["commit_hash"] is not None

        # 验证 GitManager 被正确调用
        mock_git_manager.commit_changes.assert_called_once()
        call_args = mock_git_manager.commit_changes.call_args
        assert call_args[1]["role"] == "dev"

        # 验证 TestRunner 被正确调用
        mock_test_runner_passing.execute.assert_called_once()

    def test_workflow_marks_all_steps(self, dev_agent, sample_task, mock_git_manager, mock_test_runner_passing):
        """5 个步骤全部标记"""
        result = dev_agent.execute_tdd_workflow(
            task=sample_task,
            test_runner=mock_test_runner_passing,
            git_manager=mock_git_manager,
        )
        assert len(result.step_results) == 5
        for step_name in ["analyze", "write_tests", "implement", "run_tests", "commit"]:
            assert step_name in result.step_results, f"Missing step: {step_name}"

    def test_workflow_without_runner(self, dev_agent, sample_task, mock_git_manager):
        """无 test_runner：使用内置预估逻辑"""
        result = dev_agent.execute_tdd_workflow(
            task=sample_task,
            test_runner=None,
            git_manager=mock_git_manager,
        )

        assert result.success is True
        assert result.workflow_status == TddWorkflowStatus.COMMITTED
        run_tests = result.step_results["run_tests"]
        assert run_tests["executed"] is False  # 未真实执行
        assert run_tests["builtin"] is True  # 标记为内置结果
        assert "summary" in run_tests

    def test_workflow_without_git(self, dev_agent, sample_task, mock_test_runner_passing):
        """无 git_manager：构建 commit message 但不执行"""
        result = dev_agent.execute_tdd_workflow(
            task=sample_task,
            test_runner=mock_test_runner_passing,
            git_manager=None,
        )

        assert result.success is True
        assert result.workflow_status == TddWorkflowStatus.COMMITTED
        assert result.commit_hash is None
        assert result.is_committed is False

        # 验证 commit 步骤仍是 message_built
        commit = result.step_results["commit"]
        assert commit["status"] == "message_built"
        assert "[task-001]" in commit["message"]
        assert "senior-developer" in commit["message"]

    def test_workflow_records_duration(self, dev_agent, sample_task, mock_git_manager, mock_test_runner_passing):
        """验证 duration_seconds 正确记录"""
        result = dev_agent.execute_tdd_workflow(
            task=sample_task,
            test_runner=mock_test_runner_passing,
            git_manager=mock_git_manager,
        )
        assert result.duration_seconds > 0
        assert result.duration_seconds < 5  # 不应超过 5 秒（纯 mock）

    def test_workflow_created_at_is_datetime(self, dev_agent, sample_task, mock_git_manager, mock_test_runner_passing):
        """created_at 是 datetime"""
        result = dev_agent.execute_tdd_workflow(
            task=sample_task,
            test_runner=mock_test_runner_passing,
            git_manager=mock_git_manager,
        )
        assert isinstance(result.created_at, datetime)


class TestTddWorkflowTestFailure:
    """TDD 闭环：测试失败 → 不 commit"""

    def test_test_failure_no_commit(self, dev_agent, sample_task, mock_git_manager, mock_test_runner_failing):
        """测试失败时不执行 commit"""
        result = dev_agent.execute_tdd_workflow(
            task=sample_task,
            test_runner=mock_test_runner_failing,
            git_manager=mock_git_manager,
        )

        assert result.success is False
        assert result.workflow_status == TddWorkflowStatus.TEST_FAILED
        assert result.commit_hash is None
        assert result.is_committed is False

        # 验证 run_tests 记录了失败
        run_tests = result.step_results["run_tests"]
        assert run_tests["status"] == "failed"
        assert run_tests["failed_count"] > 0

        # 验证 GitManager 没有被调用
        mock_git_manager.commit_changes.assert_not_called()

        # 验证错误消息
        assert "failed" in result.error_message.lower()

    def test_test_failure_preserves_analyze_and_implement(self, dev_agent, sample_task, mock_git_manager, mock_test_runner_failing):
        """测试失败但分析和实现步骤完成"""
        result = dev_agent.execute_tdd_workflow(
            task=sample_task,
            test_runner=mock_test_runner_failing,
            git_manager=mock_git_manager,
        )

        assert "analyze" in result.step_results
        assert "write_tests" in result.step_results
        assert "implement" in result.step_results
        assert "run_tests" in result.step_results
        assert "commit" not in result.step_results  # 失败时不记录 commit 步骤

        assert result.step_results["analyze"]["status"] == "completed"
        assert result.step_results["implement"]["status"] == "completed"

    def test_test_failure_without_runner_fails(self, dev_agent, sample_task, mock_git_manager):
        """无 test_runner 场景下，内置逻辑默认 all pass，不应触发 TEST_FAILED"""
        # 内置 run_tests 默认预估 all pass
        result = dev_agent.execute_tdd_workflow(
            task=sample_task,
            test_runner=None,
            git_manager=mock_git_manager,
        )
        # 内置逻辑下默认测试应通过
        assert result.workflow_status == TddWorkflowStatus.COMMITTED

    def test_test_failure_error_message_includes_failure_names(self, dev_agent, sample_task, mock_git_manager):
        """失败错误消息包含失败测试名称"""
        from agent_automation_system.scheduler.test_runner import TestResult

        runner = MagicMock()
        runner.execute.return_value = TestResult(
            test_file_path="tests/test_x.py",
            passed=False,
            total=4,
            passed_count=2,
            failed_count=2,
            output="FAILED tests/test_x.py::test_bad_1\nFAILED tests/test_x.py::test_bad_2\n2 passed, 2 failed",
            duration_seconds=0.1,
        )

        result = dev_agent.execute_tdd_workflow(
            task=sample_task,
            test_runner=runner,
            git_manager=mock_git_manager,
        )

        assert result.workflow_status == TddWorkflowStatus.TEST_FAILED
        assert "2 failed" in result.error_message
        mock_git_manager.commit_changes.assert_not_called()


class TestTddWorkflowExceptionHandling:
    """TDD 闭环：异常恢复"""

    def test_none_task_raises(self, dev_agent):
        """task=None 抛出 ValueError"""
        with pytest.raises(ValueError, match="cannot be None"):
            dev_agent.execute_tdd_workflow(task=None)

    def test_analyze_throws_returns_failed(self, dev_agent, mock_git_manager, mock_test_runner_passing):
        """分析步骤异常 → ANALYZE_FAILED"""
        # 创建一个特殊 task 触发分析异常
        task = Task(
            id="task-999",
            title="T",
            description="D",
            dependencies=[],
            suggested_role="senior-developer",
            priority=TaskPriority.LOW,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )

        # 强制 analyze_task 抛出异常
        with patch.object(dev_agent, 'analyze_task', side_effect=RuntimeError("Analysis boom")):
            result = dev_agent.execute_tdd_workflow(
                task=task,
                test_runner=mock_test_runner_passing,
                git_manager=mock_git_manager,
            )

        assert result.success is False
        assert result.workflow_status == TddWorkflowStatus.ANALYZE_FAILED
        assert "Analysis boom" in result.error_message
        # 验证只有 analyze 步骤
        assert "analyze" in result.step_results
        assert result.step_results["analyze"]["status"] == "failed"
        # 不应该执行后续步骤的 mock
        mock_git_manager.commit_changes.assert_not_called()

    def test_implement_throws_returns_failed(self, dev_agent, sample_task, mock_git_manager, mock_test_runner_passing):
        """实现步骤异常 → IMPLEMENT_FAILED"""
        with patch.object(dev_agent, 'implement_code', side_effect=RuntimeError("Implement boom")):
            result = dev_agent.execute_tdd_workflow(
                task=sample_task,
                test_runner=mock_test_runner_passing,
                git_manager=mock_git_manager,
            )

        assert result.success is False
        assert result.workflow_status == TddWorkflowStatus.IMPLEMENT_FAILED
        assert "Implement boom" in result.error_message
        # analyze 和 write_tests 已完成
        assert result.step_results["analyze"]["status"] == "completed"
        assert result.step_results["write_tests"]["status"] == "completed"
        assert result.step_results["implement"]["status"] == "failed"
        mock_git_manager.commit_changes.assert_not_called()

    def test_test_runner_throws_subprocess_error(self, dev_agent, sample_task, mock_git_manager):
        """TestRunner.execute 抛出异常 → 记录为 run_tests error"""
        runner = MagicMock()
        runner.execute.side_effect = RuntimeError("Subprocess error")

        result = dev_agent.execute_tdd_workflow(
            task=sample_task,
            test_runner=runner,
            git_manager=mock_git_manager,
        )

        assert result.workflow_status == TddWorkflowStatus.TEST_FAILED
        run_tests = result.step_results["run_tests"]
        assert run_tests["status"] == "error"
        assert run_tests["executed"] is False
        assert "Subprocess error" in run_tests["summary"]
        mock_git_manager.commit_changes.assert_not_called()


class TestTddWorkflowGitIntegration:
    """TDD 闭环：GitManager 集成"""

    def test_git_manager_commit_failure_still_returns_committed(self, dev_agent, sample_task, mock_test_runner_passing, mock_git_manager_failure):
        """commit 失败（如无变更）时，仍标记 COMMITTED 但 commit_hash=None"""
        result = dev_agent.execute_tdd_workflow(
            task=sample_task,
            test_runner=mock_test_runner_passing,
            git_manager=mock_git_manager_failure,
        )

        assert result.workflow_status == TddWorkflowStatus.COMMITTED
        assert result.commit_hash is None
        assert result.is_committed is False

        commit = result.step_results["commit"]
        assert commit["status"] == "commit_skipped"
        assert "reason" in commit

    def test_git_manager_receives_correct_params(self, dev_agent, sample_task, mock_git_manager, mock_test_runner_passing):
        """验证 GitManager.commit_changes 接收正确参数"""
        dev_agent.execute_tdd_workflow(
            task=sample_task,
            test_runner=mock_test_runner_passing,
            git_manager=mock_git_manager,
        )

        call_kwargs = mock_git_manager.commit_changes.call_args[1]
        assert call_kwargs["task_id"] == "001"
        assert call_kwargs["role"] == "dev"
        assert len(call_kwargs["description"]) > 0


class TestTddWorkflowWorkflowStatusEnum:
    """TddWorkflowStatus 常量测试"""

    def test_all_status_values(self):
        assert TddWorkflowStatus.COMMITTED == "COMMITTED"
        assert TddWorkflowStatus.TEST_FAILED == "TEST_FAILED"
        assert TddWorkflowStatus.ANALYZE_FAILED == "ANALYZE_FAILED"
        assert TddWorkflowStatus.IMPLEMENT_FAILED == "IMPLEMENT_FAILED"


class TestTddWorkflowEdgeCases:
    """TDD 闭环：边界条件"""

    def test_minimal_title_task(self, dev_agent, mock_git_manager):
        """最小标题 task 也能完成闭环"""
        from agent_automation_system.scheduler.test_runner import TestResult

        runner = MagicMock()
        runner.execute.return_value = TestResult(
            test_file_path="tests/test_empty.py",
            passed=True,
            total=2,
            passed_count=2,
            failed_count=0,
            output="2 passed",
            duration_seconds=0.1,
        )

        task = Task(
            id="task-999",
            title="T",
            description="minimal task",
            dependencies=[],
            suggested_role="senior-developer",
            priority=TaskPriority.LOW,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )

        result = dev_agent.execute_tdd_workflow(
            task=task,
            test_runner=runner,
            git_manager=mock_git_manager,
        )

        assert result.success is True
        assert result.workflow_status == TddWorkflowStatus.COMMITTED

    def test_no_bdd_task(self, dev_agent, task_without_bdd, mock_git_manager, mock_test_runner_passing):
        """无 BDD 的 task 也能完成闭环"""
        result = dev_agent.execute_tdd_workflow(
            task=task_without_bdd,
            test_runner=mock_test_runner_passing,
            git_manager=mock_git_manager,
        )

        assert result.success is True
        assert result.workflow_status == TddWorkflowStatus.COMMITTED
        # 无 BDD 时分析步骤无 BDD 相关风险
        analyze = result.step_results["analyze"]
        assert any("BDD" in r for r in analyze.get("risks", []))

    def test_high_complexity_task(self, dev_agent, task_with_dependencies, mock_git_manager, mock_test_runner_passing):
        """高复杂度有依赖的 task"""
        result = dev_agent.execute_tdd_workflow(
            task=task_with_dependencies,
            test_runner=mock_test_runner_passing,
            git_manager=mock_git_manager,
        )

        assert result.success is True
        analyze = result.step_results["analyze"]
        assert len(analyze["risks"]) >= 2  # 高复杂度 + 有依赖 → 至少 2 个风险
        assert len(analyze["technical_approach"]) > 0
        assert analyze["estimated_effort_min"] >= 30  # HIGH 复杂度

    def test_to_text_includes_all_steps(self, dev_agent, sample_task, mock_git_manager, mock_test_runner_passing):
        """to_text 包含所有步骤"""
        result = dev_agent.execute_tdd_workflow(
            task=sample_task,
            test_runner=mock_test_runner_passing,
            git_manager=mock_git_manager,
        )
        text = result.to_text()
        assert "TDD 闭环结果" in text
        assert "COMMITTED" in text
        assert "analyze" in text
        assert "write_tests" in text
        assert "implement" in text
        assert "run_tests" in text

    def test_test_runner_not_called_when_analyze_fails(self, dev_agent, mock_test_runner_passing, mock_git_manager):
        """分析失败时不执行测试"""
        with patch.object(dev_agent, 'analyze_task', side_effect=RuntimeError("fail")):
            dev_agent.execute_tdd_workflow(
                task=Task(
                    id="task-999", title="X", description="X",
                    dependencies=[], suggested_role="dev",
                    priority=TaskPriority.LOW,
                    estimated_complexity=TaskComplexity.LOW,
                    status=TaskStatus.PENDING,
                ),
                test_runner=mock_test_runner_passing,
                git_manager=mock_git_manager,
            )

        mock_test_runner_passing.execute.assert_not_called()
        mock_git_manager.commit_changes.assert_not_called()

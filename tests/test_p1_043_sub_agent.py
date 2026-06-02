"""
P1-043 单元测试 — SubAgent 基类

覆盖范围：
1. AgentPhase 枚举（9 个阶段值、字符串类型）
2. SubAgentResultStatus 枚举（5 个状态值、字符串类型）
3. SubAgentResult 数据模型（必填/默认字段、is_success/is_terminal/duration_seconds、Pydantic 校验）
4. _VALID_TRANSITIONS 阶段转换表（合法转换、非法转换、终态不可转换）
5. _transition_to 方法（合法/非法转换、错误信息格式）
6. _build_result 辅助方法（字段填充、retries/commit/output 继承、overrides 覆盖）
7. SubAgent 属性（role_name/task/phase/result 初始值）
8. run() 全流程成功路径（CREATED→INITIALIZED→EXECUTING→VERIFYING→COMMITTING→COMPLETED→CLEANED_UP）
9. run() 各阶段失败路径（initialize 失败、execute 返回 FAILED/BLOCKED、verify 失败/阻塞、commit 失败）
10. run() Ephemeral 保护（None task、重复执行）
11. run() cleanup 异常抑制
12. run() 未预期异常处理
"""

import unittest
from datetime import datetime
from unittest.mock import MagicMock

from agent_automation_system.models.task import Task
from agent_automation_system.sub_agent.sub_agent import (
    AgentPhase,
    SubAgent,
    SubAgentResult,
    SubAgentResultStatus,
    _VALID_TRANSITIONS,
    _LifecycleAbort,
)


# ── 测试用具体 SubAgent 实现 ───────────────────────────


class ConcreteSubAgent(SubAgent):
    """用于测试的具体 SubAgent 实现

    通过 flag 控制各阶段的行为（成功/失败/阻塞）。
    """

    def __init__(
        self,
        role_name: str = "test-agent",
        init_raises: Exception | None = None,
        execute_status: SubAgentResultStatus = SubAgentResultStatus.SUCCESS,
        verify_status: SubAgentResultStatus = SubAgentResultStatus.SUCCESS,
        commit_status: SubAgentResultStatus = SubAgentResultStatus.SUCCESS,
        cleanup_raises: Exception | None = None,
    ) -> None:
        super().__init__(role_name)
        self._init_raises = init_raises
        self._execute_status = execute_status
        self._verify_status = verify_status
        self._commit_status = commit_status
        self._cleanup_raises = cleanup_raises

        # 跟踪调用顺序
        self.call_log: list[str] = []

    def initialize(self) -> None:
        self.call_log.append("initialize")
        if self._init_raises:
            raise self._init_raises

    def execute(self, task: Task) -> SubAgentResult:
        self.call_log.append("execute")
        return self._build_result(
            status=self._execute_status,
            output=f"Execute output for {task.id}",
        )

    def verify(self) -> SubAgentResult:
        self.call_log.append("verify")
        return self._build_result(
            status=self._verify_status,
            output="Verify output",
        )

    def commit(self) -> SubAgentResult:
        self.call_log.append("commit")
        return self._build_result(
            status=self._commit_status,
            commit_hash="abc123",
            commit_message="[task-001] test-agent: test commit",
        )

    def cleanup(self) -> None:
        self.call_log.append("cleanup")
        if self._cleanup_raises:
            raise self._cleanup_raises


# ── 辅助 ───────────────────────────────────────────────


def _make_task(task_id: str = "task-001", **kwargs) -> Task:
    """创建测试用 Task"""
    defaults = dict(
        title="Test Task",
        description="A test task",
    )
    defaults.update(kwargs)
    return Task(id=task_id, **defaults)


# ── 测试类 ─────────────────────────────────────────────


class TestAgentPhase(unittest.TestCase):
    """验证 AgentPhase 枚举"""

    def test_phase_count(self):
        """恰好 9 个阶段"""
        self.assertEqual(len(AgentPhase), 9)

    def test_phase_values(self):
        """所有枚举值正确"""
        expected = {
            "CREATED": "created",
            "INITIALIZED": "initialized",
            "EXECUTING": "executing",
            "VERIFYING": "verifying",
            "COMMITTING": "committing",
            "COMPLETED": "completed",
            "FAILED": "failed",
            "BLOCKED": "blocked",
            "CLEANED_UP": "cleaned_up",
        }
        for name, value in expected.items():
            self.assertEqual(AgentPhase[name].value, value)

    def test_phase_is_string(self):
        """枚举值是字符串"""
        self.assertIsInstance(AgentPhase.CREATED, str)


class TestSubAgentResultStatus(unittest.TestCase):
    """验证 SubAgentResultStatus 枚举"""

    def test_status_count(self):
        """恰好 5 个状态"""
        self.assertEqual(len(SubAgentResultStatus), 5)

    def test_status_values(self):
        """所有枚举值正确"""
        expected = {
            "SUCCESS": "success",
            "FAILED": "failed",
            "BLOCKED": "blocked",
            "TIMEOUT": "timeout",
            "RETRY": "retry",
        }
        for name, value in expected.items():
            self.assertEqual(SubAgentResultStatus[name].value, value)

    def test_status_is_string(self):
        """枚举值是字符串"""
        self.assertIsInstance(SubAgentResultStatus.SUCCESS, str)


class TestSubAgentResult(unittest.TestCase):
    """验证 SubAgentResult 数据模型"""

    def test_required_fields(self):
        """必填字段缺失抛 ValidationError"""
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            SubAgentResult()  # 缺少 task_id, status, phase

    def test_minimal_creation(self):
        """最小构造（仅必填字段）"""
        result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.COMPLETED,
        )
        self.assertEqual(result.task_id, "task-001")
        self.assertEqual(result.status, SubAgentResultStatus.SUCCESS)
        self.assertEqual(result.phase, AgentPhase.COMPLETED)
        self.assertEqual(result.role, "dev")  # 默认值
        self.assertIsNone(result.commit_hash)
        self.assertIsNone(result.commit_message)
        self.assertIsNone(result.output)
        self.assertIsNone(result.error)
        self.assertIsNone(result.started_at)
        self.assertIsNone(result.finished_at)
        self.assertEqual(result.retries, 0)
        self.assertEqual(result.metadata, {})

    def test_all_fields(self):
        """所有字段赋值"""
        now = datetime.now()
        result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.COMPLETED,
            role="senior-developer",
            commit_hash="abc123",
            commit_message="[task-001] senior-developer: 实现登录",
            output="创建 3 个文件",
            error=None,
            started_at=now,
            finished_at=now,
            retries=2,
            metadata={"key": "value"},
        )
        self.assertEqual(result.role, "senior-developer")
        self.assertEqual(result.commit_hash, "abc123")
        self.assertEqual(result.retries, 2)
        self.assertEqual(result.metadata["key"], "value")

    def test_is_success_true(self):
        """SUCCESS → is_success=True"""
        result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.COMPLETED,
        )
        self.assertTrue(result.is_success)

    def test_is_success_false(self):
        """FAILED → is_success=False"""
        result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.FAILED,
            phase=AgentPhase.FAILED,
        )
        self.assertFalse(result.is_success)

    def test_is_terminal_success(self):
        """SUCCESS → is_terminal=True"""
        result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.COMPLETED,
        )
        self.assertTrue(result.is_terminal)

    def test_is_terminal_blocked(self):
        """BLOCKED → is_terminal=True"""
        result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.BLOCKED,
            phase=AgentPhase.BLOCKED,
        )
        self.assertTrue(result.is_terminal)

    def test_is_terminal_failed(self):
        """FAILED → is_terminal=False"""
        result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.FAILED,
            phase=AgentPhase.FAILED,
        )
        self.assertFalse(result.is_terminal)

    def test_is_terminal_timeout(self):
        """TIMEOUT → is_terminal=False"""
        result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.TIMEOUT,
            phase=AgentPhase.FAILED,
        )
        self.assertFalse(result.is_terminal)

    def test_is_terminal_retry(self):
        """RETRY → is_terminal=False"""
        result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.RETRY,
            phase=AgentPhase.CREATED,
        )
        self.assertFalse(result.is_terminal)

    def test_duration_seconds(self):
        """duration_seconds 计算"""
        start = datetime(2026, 5, 18, 10, 0, 0)
        end = datetime(2026, 5, 18, 10, 5, 30)
        result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.COMPLETED,
            started_at=start,
            finished_at=end,
        )
        self.assertAlmostEqual(result.duration_seconds, 330.0)

    def test_duration_seconds_none(self):
        """缺少时间 → duration_seconds=None"""
        result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.COMPLETED,
        )
        self.assertIsNone(result.duration_seconds)

    def test_duration_seconds_partial(self):
        """只有 started_at → duration_seconds=None"""
        result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.COMPLETED,
            started_at=datetime.now(),
        )
        self.assertIsNone(result.duration_seconds)

    def test_retries_negative_validation(self):
        """负 retries 抛 ValidationError"""
        from pydantic import ValidationError
        with self.assertRaises(ValidationError):
            SubAgentResult(
                task_id="task-001",
                status=SubAgentResultStatus.SUCCESS,
                phase=AgentPhase.COMPLETED,
                retries=-1,
            )


class TestValidTransitions(unittest.TestCase):
    """验证 _VALID_TRANSITIONS 阶段转换表"""

    def test_created_transitions(self):
        """CREATED → INITIALIZED | FAILED"""
        self.assertEqual(
            _VALID_TRANSITIONS[AgentPhase.CREATED],
            {AgentPhase.INITIALIZED, AgentPhase.FAILED},
        )

    def test_initialized_transitions(self):
        """INITIALIZED → EXECUTING | FAILED | BLOCKED"""
        self.assertEqual(
            _VALID_TRANSITIONS[AgentPhase.INITIALIZED],
            {AgentPhase.EXECUTING, AgentPhase.FAILED, AgentPhase.BLOCKED},
        )

    def test_executing_transitions(self):
        """EXECUTING → VERIFYING | FAILED | BLOCKED"""
        allowed = _VALID_TRANSITIONS[AgentPhase.EXECUTING]
        self.assertIn(AgentPhase.VERIFYING, allowed)
        self.assertIn(AgentPhase.FAILED, allowed)
        self.assertIn(AgentPhase.BLOCKED, allowed)

    def test_verifying_transitions(self):
        """VERIFYING → COMMITTING | FAILED | BLOCKED"""
        self.assertEqual(
            _VALID_TRANSITIONS[AgentPhase.VERIFYING],
            {AgentPhase.COMMITTING, AgentPhase.FAILED, AgentPhase.BLOCKED},
        )

    def test_committing_transitions(self):
        """COMMITTING → COMPLETED | FAILED"""
        self.assertEqual(
            _VALID_TRANSITIONS[AgentPhase.COMMITTING],
            {AgentPhase.COMPLETED, AgentPhase.FAILED},
        )

    def test_completed_transitions(self):
        """COMPLETED → CLEANED_UP"""
        self.assertEqual(
            _VALID_TRANSITIONS[AgentPhase.COMPLETED],
            {AgentPhase.CLEANED_UP},
        )

    def test_failed_transitions(self):
        """FAILED → CLEANED_UP"""
        self.assertEqual(
            _VALID_TRANSITIONS[AgentPhase.FAILED],
            {AgentPhase.CLEANED_UP},
        )

    def test_blocked_transitions(self):
        """BLOCKED → CLEANED_UP"""
        self.assertEqual(
            _VALID_TRANSITIONS[AgentPhase.BLOCKED],
            {AgentPhase.CLEANED_UP},
        )

    def test_cleaned_up_no_transitions(self):
        """CLEANED_UP 是终态，不可转换"""
        self.assertEqual(_VALID_TRANSITIONS[AgentPhase.CLEANED_UP], set())

    def test_all_phases_covered(self):
        """所有阶段都在转换表中"""
        for phase in AgentPhase:
            self.assertIn(phase, _VALID_TRANSITIONS)


class TestTransitionTo(unittest.TestCase):
    """验证 _transition_to 方法"""

    def test_valid_transition(self):
        """合法转换成功"""
        agent = ConcreteSubAgent()
        self.assertEqual(agent.phase, AgentPhase.CREATED)
        agent._transition_to(AgentPhase.INITIALIZED)
        self.assertEqual(agent.phase, AgentPhase.INITIALIZED)

    def test_invalid_transition(self):
        """非法转换抛 RuntimeError"""
        agent = ConcreteSubAgent()
        with self.assertRaises(RuntimeError) as ctx:
            agent._transition_to(AgentPhase.COMPLETED)  # CREATED → COMPLETED 非法
        self.assertIn("Invalid phase transition", str(ctx.exception))
        self.assertIn("created", str(ctx.exception))
        self.assertIn("completed", str(ctx.exception))

    def test_invalid_transition_shows_allowed(self):
        """非法转换错误信息包含合法目标"""
        agent = ConcreteSubAgent()
        with self.assertRaises(RuntimeError) as ctx:
            agent._transition_to(AgentPhase.COMPLETED)
        msg = str(ctx.exception)
        self.assertIn("initialized", msg)  # 合法目标之一

    def test_terminal_phase_no_transition(self):
        """终态不可转换"""
        agent = ConcreteSubAgent()
        agent._phase = AgentPhase.CLEANED_UP
        with self.assertRaises(RuntimeError):
            agent._transition_to(AgentPhase.CREATED)

    def test_chained_transitions(self):
        """连续合法转换"""
        agent = ConcreteSubAgent()
        agent._transition_to(AgentPhase.INITIALIZED)
        agent._transition_to(AgentPhase.EXECUTING)
        agent._transition_to(AgentPhase.VERIFYING)
        agent._transition_to(AgentPhase.COMMITTING)
        agent._transition_to(AgentPhase.COMPLETED)
        agent._transition_to(AgentPhase.CLEANED_UP)
        self.assertEqual(agent.phase, AgentPhase.CLEANED_UP)


class TestBuildResult(unittest.TestCase):
    """验证 _build_result 辅助方法"""

    def test_basic_fields(self):
        """基本字段填充"""
        agent = ConcreteSubAgent()
        task = _make_task()
        agent._task = task
        agent._result = SubAgentResult(
            task_id=task.id,
            status=SubAgentResultStatus.RETRY,
            phase=AgentPhase.CREATED,
            role="test-agent",
            started_at=datetime.now(),
        )
        result = agent._build_result(SubAgentResultStatus.SUCCESS)
        self.assertEqual(result.task_id, "task-001")
        self.assertEqual(result.status, SubAgentResultStatus.SUCCESS)
        self.assertEqual(result.role, "test-agent")
        self.assertIsNotNone(result.finished_at)

    def test_phase_default(self):
        """phase 默认使用当前 phase"""
        agent = ConcreteSubAgent()
        agent._task = _make_task()
        agent._phase = AgentPhase.EXECUTING
        result = agent._build_result(SubAgentResultStatus.SUCCESS)
        self.assertEqual(result.phase, AgentPhase.EXECUTING)

    def test_phase_override(self):
        """显式 phase 参数覆盖"""
        agent = ConcreteSubAgent()
        agent._task = _make_task()
        agent._phase = AgentPhase.EXECUTING
        result = agent._build_result(
            SubAgentResultStatus.SUCCESS, phase=AgentPhase.COMPLETED
        )
        self.assertEqual(result.phase, AgentPhase.COMPLETED)

    def test_inherit_retries(self):
        """继承上次结果的 retries"""
        agent = ConcreteSubAgent()
        agent._task = _make_task()
        agent._result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.RETRY,
            phase=AgentPhase.CREATED,
            retries=3,
        )
        result = agent._build_result(SubAgentResultStatus.SUCCESS)
        self.assertEqual(result.retries, 3)

    def test_inherit_commit_hash(self):
        """继承上次结果的 commit_hash"""
        agent = ConcreteSubAgent()
        agent._task = _make_task()
        agent._result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.COMPLETED,
            commit_hash="abc123",
        )
        result = agent._build_result(SubAgentResultStatus.SUCCESS)
        self.assertEqual(result.commit_hash, "abc123")

    def test_commit_hash_override(self):
        """overrides 覆盖 commit_hash"""
        agent = ConcreteSubAgent()
        agent._task = _make_task()
        agent._result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.COMPLETED,
            commit_hash="old_hash",
        )
        result = agent._build_result(
            SubAgentResultStatus.SUCCESS, commit_hash="new_hash"
        )
        self.assertEqual(result.commit_hash, "new_hash")

    def test_inherit_output(self):
        """继承上次结果的 output"""
        agent = ConcreteSubAgent()
        agent._task = _make_task()
        agent._result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.EXECUTING,
            output="Previous output",
        )
        result = agent._build_result(SubAgentResultStatus.SUCCESS)
        self.assertEqual(result.output, "Previous output")

    def test_output_override(self):
        """overrides 覆盖 output"""
        agent = ConcreteSubAgent()
        agent._task = _make_task()
        agent._result = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.SUCCESS,
            phase=AgentPhase.EXECUTING,
            output="Old",
        )
        result = agent._build_result(
            SubAgentResultStatus.SUCCESS, output="New output"
        )
        self.assertEqual(result.output, "New output")

    def test_no_task_uses_unknown(self):
        """无 task 时 task_id 为 unknown"""
        agent = ConcreteSubAgent()
        result = agent._build_result(SubAgentResultStatus.FAILED)
        self.assertEqual(result.task_id, "unknown")

    def test_no_prior_result(self):
        """无前置结果时 started_at 为 None"""
        agent = ConcreteSubAgent()
        agent._task = _make_task()
        result = agent._build_result(SubAgentResultStatus.SUCCESS)
        self.assertIsNone(result.started_at)


class TestSubAgentProperties(unittest.TestCase):
    """验证 SubAgent 属性初始值"""

    def test_role_name(self):
        """role_name 正确"""
        agent = ConcreteSubAgent(role_name="senior-developer")
        self.assertEqual(agent.role_name, "senior-developer")

    def test_task_initial_none(self):
        """task 初始为 None"""
        agent = ConcreteSubAgent()
        self.assertIsNone(agent.task)

    def test_phase_initial_created(self):
        """phase 初始为 CREATED"""
        agent = ConcreteSubAgent()
        self.assertEqual(agent.phase, AgentPhase.CREATED)

    def test_result_initial_none(self):
        """result 初始为 None"""
        agent = ConcreteSubAgent()
        self.assertIsNone(agent.result)


class TestRunSuccessPath(unittest.TestCase):
    """验证 run() 全流程成功路径"""

    def test_full_lifecycle(self):
        """完整生命周期：5 阶段全部成功"""
        agent = ConcreteSubAgent()
        task = _make_task()
        result = agent.run(task)

        self.assertTrue(result.is_success)
        self.assertEqual(result.status, SubAgentResultStatus.SUCCESS)
        # result.phase 是 commit 阶段创建时的 phase（COMMITTING），
        # agent.phase 才是最终的 CLEANED_UP
        self.assertEqual(agent.phase, AgentPhase.CLEANED_UP)
        self.assertEqual(result.task_id, "task-001")
        self.assertEqual(result.role, "test-agent")

    def test_call_order(self):
        """阶段调用顺序正确"""
        agent = ConcreteSubAgent()
        task = _make_task()
        agent.run(task)

        self.assertEqual(
            agent.call_log,
            ["initialize", "execute", "verify", "commit", "cleanup"],
        )

    def test_phase_transitions(self):
        """最终 phase 为 CLEANED_UP"""
        agent = ConcreteSubAgent()
        task = _make_task()
        agent.run(task)
        self.assertEqual(agent.phase, AgentPhase.CLEANED_UP)

    def test_task_assigned(self):
        """run 后 task 已赋值"""
        agent = ConcreteSubAgent()
        task = _make_task()
        agent.run(task)
        self.assertIs(agent.task, task)

    def test_result_commit_hash(self):
        """成功路径包含 commit_hash"""
        agent = ConcreteSubAgent()
        task = _make_task()
        result = agent.run(task)
        self.assertEqual(result.commit_hash, "abc123")

    def test_result_has_timestamps(self):
        """成功路径包含时间戳"""
        agent = ConcreteSubAgent()
        task = _make_task()
        result = agent.run(task)
        self.assertIsNotNone(result.started_at)
        self.assertIsNotNone(result.finished_at)
        self.assertIsNotNone(result.duration_seconds)


class TestRunInitializeFailure(unittest.TestCase):
    """验证 initialize 失败路径"""

    def test_init_raises_runtime_error(self):
        """initialize 抛 RuntimeError → FAILED"""
        agent = ConcreteSubAgent(init_raises=RuntimeError("tmux not found"))
        task = _make_task()
        result = agent.run(task)

        self.assertEqual(result.status, SubAgentResultStatus.FAILED)
        self.assertIn("tmux not found", result.error)
        self.assertEqual(agent.phase, AgentPhase.CLEANED_UP)

    def test_init_still_calls_cleanup(self):
        """initialize 失败后仍调用 cleanup"""
        agent = ConcreteSubAgent(init_raises=RuntimeError("fail"))
        agent.run(_make_task())
        self.assertIn("cleanup", agent.call_log)

    def test_init_failure_call_order(self):
        """initialize 失败只调用 initialize + cleanup"""
        agent = ConcreteSubAgent(init_raises=RuntimeError("fail"))
        agent.run(_make_task())
        self.assertEqual(agent.call_log, ["initialize", "cleanup"])

    def test_init_failure_phase(self):
        """initialize 失败后 phase → FAILED → CLEANED_UP"""
        agent = ConcreteSubAgent(init_raises=RuntimeError("fail"))
        agent.run(_make_task())
        self.assertEqual(agent.phase, AgentPhase.CLEANED_UP)


class TestRunExecuteFailure(unittest.TestCase):
    """验证 execute 返回失败/阻塞路径"""

    def test_execute_returns_failed(self):
        """execute 返回 FAILED → 生命周期中止"""
        agent = ConcreteSubAgent(execute_status=SubAgentResultStatus.FAILED)
        task = _make_task()
        result = agent.run(task)

        self.assertEqual(result.status, SubAgentResultStatus.FAILED)
        self.assertEqual(agent.phase, AgentPhase.CLEANED_UP)
        self.assertIn("cleanup", agent.call_log)

    def test_execute_returns_blocked(self):
        """execute 返回 BLOCKED → 生命周期中止"""
        agent = ConcreteSubAgent(execute_status=SubAgentResultStatus.BLOCKED)
        task = _make_task()
        result = agent.run(task)

        self.assertEqual(result.status, SubAgentResultStatus.BLOCKED)
        self.assertEqual(agent.phase, AgentPhase.CLEANED_UP)

    def test_execute_blocked_call_order(self):
        """execute BLOCKED 后跳过 verify/commit"""
        agent = ConcreteSubAgent(execute_status=SubAgentResultStatus.BLOCKED)
        agent.run(_make_task())
        self.assertEqual(
            agent.call_log,
            ["initialize", "execute", "cleanup"],
        )

    def test_execute_failed_call_order(self):
        """execute FAILED 后跳过 verify/commit"""
        agent = ConcreteSubAgent(execute_status=SubAgentResultStatus.FAILED)
        agent.run(_make_task())
        self.assertEqual(
            agent.call_log,
            ["initialize", "execute", "cleanup"],
        )


class TestRunVerifyFailure(unittest.TestCase):
    """验证 verify 返回失败/阻塞路径"""

    def test_verify_returns_failed(self):
        """verify 返回 FAILED → 中止"""
        agent = ConcreteSubAgent(verify_status=SubAgentResultStatus.FAILED)
        task = _make_task()
        result = agent.run(task)

        self.assertEqual(result.status, SubAgentResultStatus.FAILED)
        self.assertEqual(agent.phase, AgentPhase.CLEANED_UP)

    def test_verify_returns_blocked(self):
        """verify 返回 BLOCKED → 中止"""
        agent = ConcreteSubAgent(verify_status=SubAgentResultStatus.BLOCKED)
        task = _make_task()
        result = agent.run(task)

        self.assertEqual(result.status, SubAgentResultStatus.BLOCKED)
        self.assertEqual(agent.phase, AgentPhase.CLEANED_UP)

    def test_verify_failed_call_order(self):
        """verify FAILED 后跳过 commit"""
        agent = ConcreteSubAgent(verify_status=SubAgentResultStatus.FAILED)
        agent.run(_make_task())
        self.assertEqual(
            agent.call_log,
            ["initialize", "execute", "verify", "cleanup"],
        )


class TestRunCommitFailure(unittest.TestCase):
    """验证 commit 失败路径"""

    def test_commit_returns_failed(self):
        """commit 返回 FAILED → 中止"""
        agent = ConcreteSubAgent(commit_status=SubAgentResultStatus.FAILED)
        task = _make_task()
        result = agent.run(task)

        self.assertEqual(result.status, SubAgentResultStatus.FAILED)
        self.assertEqual(agent.phase, AgentPhase.CLEANED_UP)

    def test_commit_failed_call_order(self):
        """commit FAILED 后跳到 cleanup"""
        agent = ConcreteSubAgent(commit_status=SubAgentResultStatus.FAILED)
        agent.run(_make_task())
        self.assertEqual(
            agent.call_log,
            ["initialize", "execute", "verify", "commit", "cleanup"],
        )


class TestRunCleanupException(unittest.TestCase):
    """验证 cleanup 异常抑制"""

    def test_cleanup_raises_suppressed(self):
        """cleanup 抛异常不影响最终结果"""
        agent = ConcreteSubAgent(cleanup_raises=RuntimeError("cleanup boom"))
        task = _make_task()
        result = agent.run(task)

        # 主流程仍为 SUCCESS（cleanup 异常被抑制）
        self.assertTrue(result.is_success)
        self.assertEqual(agent.phase, AgentPhase.CLEANED_UP)

    def test_cleanup_exception_with_prior_failure(self):
        """cleanup 异常 + 前置失败：结果仍为 FAILED"""
        agent = ConcreteSubAgent(
            execute_status=SubAgentResultStatus.FAILED,
            cleanup_raises=RuntimeError("cleanup boom"),
        )
        task = _make_task()
        result = agent.run(task)

        self.assertEqual(result.status, SubAgentResultStatus.FAILED)
        self.assertEqual(agent.phase, AgentPhase.CLEANED_UP)


class TestRunEphemeralProtection(unittest.TestCase):
    """验证 Ephemeral 单次执行保护"""

    def test_run_none_task(self):
        """task=None 抛 ValueError"""
        agent = ConcreteSubAgent()
        with self.assertRaises(ValueError) as ctx:
            agent.run(None)
        self.assertIn("cannot be None", str(ctx.exception))

    def test_run_twice_raises(self):
        """重复执行抛 ValueError"""
        agent = ConcreteSubAgent()
        task = _make_task()
        agent.run(task)

        with self.assertRaises(ValueError) as ctx:
            agent.run(_make_task("task-002"))
        self.assertIn("already executed", str(ctx.exception))

    def test_run_twice_preserves_first_result(self):
        """重复执行不覆盖首次结果"""
        agent = ConcreteSubAgent()
        task = _make_task()
        first_result = agent.run(task)

        try:
            agent.run(_make_task("task-002"))
        except ValueError:
            pass

        self.assertIs(agent.result, first_result)
        self.assertEqual(agent.task.id, "task-001")


class TestRunUnexpectedException(unittest.TestCase):
    """验证未预期异常处理"""

    def test_unexpected_exception_in_execute(self):
        """execute 抛未预期异常 → FAILED"""
        class ExplodingAgent(SubAgent):
            def __init__(self):
                super().__init__("exploder")

            def initialize(self):
                pass

            def execute(self, task):
                raise RuntimeError("Unexpected explosion!")

            def verify(self):
                pass

            def commit(self):
                pass

            def cleanup(self):
                pass

        agent = ExplodingAgent()
        task = _make_task()
        result = agent.run(task)

        self.assertEqual(result.status, SubAgentResultStatus.FAILED)
        self.assertIn("Unexpected explosion", result.error)
        self.assertEqual(agent.phase, AgentPhase.CLEANED_UP)


class TestLifecycleAbort(unittest.TestCase):
    """验证 _LifecycleAbort 内部信号"""

    def test_abort_reason(self):
        """reason 属性正确"""
        abort = _LifecycleAbort("test reason")
        self.assertEqual(abort.reason, "test reason")

    def test_abort_is_exception(self):
        """_LifecycleAbort 是 Exception 子类"""
        self.assertTrue(issubclass(_LifecycleAbort, Exception))


if __name__ == "__main__":
    unittest.main()

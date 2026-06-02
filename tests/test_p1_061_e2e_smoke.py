"""
P1-061: 端到端冒烟测试

验证 MasterAgent 完整生命周期流程：
  MasterAgent 启动 → 创建 1 个 Sub-Agent → 执行简单任务 → 更新 progress.txt

使用 mock 隔离 tmux/CLI 外部依赖，验证：
  - 状态流转正确性（IDLE → ANALYZING → PLANNING → DISPATCHING → ... → COMPLETED）
  - Sub-Agent 创建与任务委派
  - 执行结果记录与 task.json 状态更新
  - progress.txt 进度更新
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_automation_system.file_io.progress_manager import ProgressManager
from agent_automation_system.harness.harness_loader import HarnessLoader
from agent_automation_system.master_agent.agent_factory import (
    EphemeralSubAgent,
    SubAgentFactory,
)
from agent_automation_system.master_agent.master_agent import (
    MasterAgent,
    MasterAgentState,
)
from agent_automation_system.models.progress import ProgressEntry, ProgressStatus
from agent_automation_system.models.task import BDDSpec, Task, TaskPriority, TaskStatus
from agent_automation_system.models.task_json import TaskJSON
from agent_automation_system.sub_agent.sub_agent import (
    SubAgentResult,
    SubAgentResultStatus,
)


# ── 测试用简单任务 ──────────────────────────────────────────

def _make_simple_task() -> Task:
    """创建一个简单的测试任务"""
    return Task(
        id="task-001",
        title="Hello World 输出",
        description="实现一个简单的 Hello World 函数并编写测试",
        bdd=BDDSpec(
            given="项目已初始化",
            when="调用 hello() 函数",
            then="返回 'Hello, World!'",
        ),
        test_script="tests/test_hello.py",
        dependencies=[],
        suggested_role="senior-developer",
        priority=TaskPriority.HIGH,
    )


def _make_task_json() -> TaskJSON:
    """创建包含一个简单任务的 TaskJSON"""
    return TaskJSON(
        project_name="冒烟测试项目",
        description="端到端冒烟测试",
        created_by="TestRunner",
        total_tasks=1,
        tasks=[_make_simple_task()],
    )


def _make_mock_sub_agent(role_name: str) -> MagicMock:
    """创建 mock Sub-Agent，模拟成功执行"""
    agent = MagicMock(spec=EphemeralSubAgent)
    agent.role_name = role_name
    agent.run.return_value = SubAgentResult(
        task_id="task-001",
        status=SubAgentResultStatus.SUCCESS,
        phase="completed",
        role=role_name,
        commit_hash="abc1234",
        commit_message="[task-001] senior-developer: Hello World 输出",
    )
    return agent


# ══════════════════════════════════════════════════════════
# 1. MasterAgent 启动流程
# ══════════════════════════════════════════════════════════
class TestMasterAgentStartup:
    """MasterAgent 启动流程验证"""

    def test_initial_state_is_idle(self):
        """初始状态为 IDLE"""
        master = MasterAgent()
        assert master.state == MasterAgentState.IDLE

    def test_startup_without_tmux_or_cli(self):
        """无 tmux/CLI 时启动不报错"""
        master = MasterAgent()
        master.startup()
        assert master.is_started

    def test_startup_with_main_rules(self, tmp_path):
        """启动时加载 main-rules.md"""
        rules_path = Path(__file__).resolve().parent.parent / "harness" / "main-rules.md"
        if not rules_path.exists():
            pytest.skip("main-rules.md not found")

        master = MasterAgent(main_rules_path=str(rules_path))
        master.startup()
        assert master.is_started
        assert master.main_rules_content is not None
        assert len(master.main_rules_content) > 0

    def test_startup_with_mock_tmux(self):
        """启动时使用 mock tmux_manager"""
        mock_tmux = MagicMock()
        mock_tmux.is_available.return_value = True
        mock_tmux.session_exists.return_value = False
        mock_tmux.create_session.return_value = True

        master = MasterAgent(tmux_manager=mock_tmux)
        master.startup()

        assert master.is_started
        mock_tmux.create_session.assert_called_once()

    def test_double_startup_raises(self):
        """重复启动抛 RuntimeError"""
        master = MasterAgent()
        master.startup()
        with pytest.raises(RuntimeError, match="already started"):
            master.startup()


# ══════════════════════════════════════════════════════════
# 2. 接收需求 → 创建 PM Sub-Agent
# ══════════════════════════════════════════════════════════
class TestReceiveRequirementAndPMAgent:
    """接收需求并创建 PM Sub-Agent"""

    def test_receive_requirement_transitions_to_analyzing(self):
        """接收需求后状态转为 ANALYZING"""
        master = MasterAgent()
        master.receive_requirement("实现一个简单功能")
        assert master.state == MasterAgentState.ANALYZING
        assert master.requirement == "实现一个简单功能"

    def test_receive_empty_requirement_raises(self):
        """空需求抛 ValueError"""
        master = MasterAgent()
        with pytest.raises(ValueError, match="cannot be empty"):
            master.receive_requirement("")

    def test_create_pm_agent(self):
        """创建 PM Sub-Agent"""
        mock_pm = _make_mock_sub_agent("product-manager")
        factory = MagicMock(return_value=mock_pm)

        master = MasterAgent(agent_factory=factory)
        master.receive_requirement("实现一个简单功能")
        pm = master.create_pm_agent()

        assert pm is not None
        factory.assert_called_once_with("product-manager")
        assert master.pm_agent is mock_pm

    def test_create_pm_agent_without_requirement_raises(self):
        """无需求时创建 PM Agent 抛 ValueError"""
        master = MasterAgent(agent_factory=MagicMock())
        with pytest.raises(ValueError, match="No requirement"):
            master.create_pm_agent()


# ══════════════════════════════════════════════════════════
# 3. 加载 TaskJSON → 调度准备
# ══════════════════════════════════════════════════════════
class TestLoadTaskJsonAndPlanning:
    """加载 TaskJSON 并准备调度"""

    def _make_master_with_task_json(self) -> tuple[MasterAgent, TaskJSON]:
        """创建已设置 TaskJSON 的 MasterAgent"""
        mock_pm = _make_mock_sub_agent("product-manager")
        factory = MagicMock(return_value=mock_pm)
        master = MasterAgent(agent_factory=factory)
        master.receive_requirement("冒烟测试")
        master.create_pm_agent()

        task_json = _make_task_json()
        master.set_task_json(task_json)
        return master, task_json

    def test_set_task_json_transitions_to_dispatching(self):
        """设置 TaskJSON 后状态转为 DISPATCHING"""
        master, task_json = self._make_master_with_task_json()
        assert master.state == MasterAgentState.DISPATCHING
        assert master.task_json is task_json

    def test_task_json_contains_correct_task(self):
        """TaskJSON 包含正确的任务"""
        master, task_json = self._make_master_with_task_json()
        assert len(task_json.tasks) == 1
        assert task_json.tasks[0].id == "task-001"
        assert task_json.tasks[0].status == TaskStatus.PENDING

    def test_get_dispatchable_tasks_returns_pending(self):
        """可调度任务列表包含 PENDING 任务"""
        master, _ = self._make_master_with_task_json()
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 1
        assert dispatchable[0].id == "task-001"


# ══════════════════════════════════════════════════════════
# 4. 创建 Sub-Agent → 执行任务
# ══════════════════════════════════════════════════════════
class TestCreateSubAgentAndExecute:
    """创建 Sub-Agent 并执行任务"""

    def _make_dispatching_master(self) -> MasterAgent:
        """创建处于 DISPATCHING 状态的 MasterAgent"""
        mock_agent = _make_mock_sub_agent("senior-developer")
        factory = MagicMock(return_value=mock_agent)

        master = MasterAgent(agent_factory=factory)
        master.receive_requirement("冒烟测试")
        master.create_pm_agent()
        master.set_task_json(_make_task_json())
        return master

    def test_create_sub_agent(self):
        """为任务创建 Sub-Agent"""
        master = self._make_dispatching_master()
        task = master.task_json.tasks[0]

        agent = master.create_sub_agent(task)
        assert agent is not None
        assert task.id in master.active_agents

    def test_dispatch_task_returns_result(self):
        """委派任务返回执行结果"""
        master = self._make_dispatching_master()
        task = master.task_json.tasks[0]

        result = master.dispatch_task(task)
        assert result is not None
        assert result.status == SubAgentResultStatus.SUCCESS

    def test_dispatch_task_records_result(self):
        """委派任务后记录执行结果"""
        master = self._make_dispatching_master()
        task = master.task_json.tasks[0]

        master.dispatch_task(task)
        assert "task-001" in master.execution_results
        assert master.execution_results["task-001"].status == SubAgentResultStatus.SUCCESS

    def test_dispatch_task_updates_task_status(self):
        """委派任务后更新 task.json 中的任务状态"""
        master = self._make_dispatching_master()
        task = master.task_json.tasks[0]

        master.dispatch_task(task)
        assert task.status == TaskStatus.COMPLETED

    def test_dispatch_task_removes_from_active(self):
        """任务完成后从活跃列表移除"""
        master = self._make_dispatching_master()
        task = master.task_json.tasks[0]

        master.dispatch_task(task)
        assert task.id not in master.active_agents


# ══════════════════════════════════════════════════════════
# 5. 执行完成 → 更新 progress.txt
# ══════════════════════════════════════════════════════════
class TestProgressUpdateAfterExecution:
    """执行完成后更新 progress.txt"""

    def test_progress_txt_written_after_task_completion(self, tmp_path):
        """任务完成后 progress.txt 包含正确记录"""
        # 准备 progress.txt 路径
        progress_path = tmp_path / "progress.txt"
        pm = ProgressManager(file_path=progress_path)

        # 创建 MasterAgent 并注入 ProgressManager
        mock_agent = _make_mock_sub_agent("senior-developer")
        factory = MagicMock(return_value=mock_agent)

        master = MasterAgent(
            agent_factory=factory,
            progress_manager=pm,
        )
        master.receive_requirement("冒烟测试")
        master.create_pm_agent()
        master.set_task_json(_make_task_json())

        # 手动记录结果并写入 progress
        task = master.task_json.tasks[0]
        master.dispatch_task(task)

        # 写入 progress 条目
        entry = ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.COMPLETED,
            role="senior-developer",
            started=datetime(2026, 5, 19, 12, 0, 0),
            finished=datetime(2026, 5, 19, 12, 5, 0),
            git_sha="abc1234",
            git_msg="[task-001] senior-developer: Hello World 输出",
        )
        pm.write_entry(entry)

        # 验证 progress.txt
        entries = pm.read_progress()
        assert len(entries) == 1
        assert entries[0].task_id == "task-001"
        assert entries[0].status == ProgressStatus.COMPLETED
        assert entries[0].role == "senior-developer"
        assert entries[0].git_sha == "abc1234"

    def test_progress_txt_file_exists_after_write(self, tmp_path):
        """写入后 progress.txt 文件存在"""
        progress_path = tmp_path / "progress.txt"
        pm = ProgressManager(file_path=progress_path)

        entry = ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.COMPLETED,
            role="senior-developer",
        )
        pm.write_entry(entry)

        assert progress_path.exists()

    def test_progress_format_matches_prd(self, tmp_path):
        """progress.txt 格式符合 PRD §6.3 规范"""
        progress_path = tmp_path / "progress.txt"
        pm = ProgressManager(file_path=progress_path)

        entry = ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.COMPLETED,
            role="senior-developer",
            started=datetime(2026, 5, 19, 12, 0, 0),
            finished=datetime(2026, 5, 19, 12, 5, 0),
            git_sha="abc1234",
            git_msg="[task-001] senior-developer: Hello World",
        )
        pm.write_entry(entry)

        content = progress_path.read_text(encoding="utf-8")
        # 验证关键格式元素
        assert "[task-001]" in content
        assert "COMPLETED" in content
        assert "senior-developer" in content
        assert "abc1234" in content


# ══════════════════════════════════════════════════════════
# 6. 完整端到端冒烟流程
# ══════════════════════════════════════════════════════════
class TestEndToEndSmokeFlow:
    """完整端到端冒烟流程验证"""

    def test_full_lifecycle_single_task(self, tmp_path):
        """单任务完整生命周期：启动 → 需求 → PM → 调度 → 执行 → 完成"""
        # 准备
        progress_path = tmp_path / "progress.txt"
        pm = ProgressManager(file_path=progress_path)

        mock_agent = _make_mock_sub_agent("senior-developer")
        factory = MagicMock(return_value=mock_agent)

        master = MasterAgent(
            agent_factory=factory,
            progress_manager=pm,
        )

        # Step 1: 启动
        master.startup()
        assert master.is_started
        assert master.state == MasterAgentState.IDLE

        # Step 2: 接收需求
        master.receive_requirement("实现 Hello World 功能")
        assert master.state == MasterAgentState.ANALYZING

        # Step 3: 创建 PM Agent
        pm_agent = master.create_pm_agent()
        assert master.pm_agent is pm_agent
        factory.assert_called_with("product-manager")

        # Step 4: 设置 TaskJSON（模拟 PM Agent 输出）
        task_json = _make_task_json()
        master.set_task_json(task_json)
        assert master.state == MasterAgentState.DISPATCHING

        # Step 5: 获取可调度任务
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 1

        # Step 6: 委派任务
        result = master.dispatch_task(dispatchable[0])
        assert result is not None
        assert result.status == SubAgentResultStatus.SUCCESS

        # Step 7: 验证任务完成
        assert master.is_all_completed()
        task = master.task_json.tasks[0]
        assert task.status == TaskStatus.COMPLETED

        # Step 8: 写入 progress.txt
        entry = ProgressEntry(
            task_id="task-001",
            status=ProgressStatus.COMPLETED,
            role="senior-developer",
            started=datetime(2026, 5, 19, 12, 0, 0),
            finished=datetime(2026, 5, 19, 12, 5, 0),
            git_sha="abc1234",
            git_msg="[task-001] senior-developer: Hello World 输出",
        )
        pm.write_entry(entry)

        # Step 9: 验证 progress.txt
        entries = pm.read_progress()
        assert len(entries) == 1
        assert entries[0].task_id == "task-001"
        assert entries[0].status == ProgressStatus.COMPLETED

        # Step 10: 验证进度摘要
        summary = master.get_progress_summary()
        assert summary["total"] == 1
        assert summary["completed"] == 1
        assert summary["progress_pct"] == 100.0

    def test_full_lifecycle_with_task_failure(self):
        """单任务失败生命周期：启动 → 调度 → 执行失败 → 记录"""
        # 模拟失败执行的 Agent
        failed_agent = MagicMock(spec=EphemeralSubAgent)
        failed_agent.role_name = "senior-developer"
        failed_agent.run.return_value = SubAgentResult(
            task_id="task-001",
            status=SubAgentResultStatus.FAILED,
            phase="failed",
            role="senior-developer",
            error="Test failed: assertion error",
        )
        factory = MagicMock(return_value=failed_agent)

        master = MasterAgent(
            agent_factory=factory,
            task_max_retries=0,  # 不允许重试
        )

        master.receive_requirement("失败测试")
        master.create_pm_agent()
        master.set_task_json(_make_task_json())

        result = master.dispatch_task(master.task_json.tasks[0])
        assert result.status == SubAgentResultStatus.FAILED
        assert master.task_json.tasks[0].status == TaskStatus.FAILED

    def test_full_lifecycle_with_mock_tmux_and_cli(self):
        """使用 mock tmux 和 CLI 的完整流程"""
        # 使用 side_effect 模拟会话创建后的状态变化
        session_exists_states = [False, True]  # 初始不存在，创建后存在
        mock_tmux = MagicMock()
        mock_tmux.is_available.return_value = True
        mock_tmux.session_exists.side_effect = session_exists_states
        mock_tmux.create_session.return_value = True
        mock_tmux.window_exists.return_value = True

        mock_cli = MagicMock()

        mock_agent = _make_mock_sub_agent("senior-developer")
        factory = MagicMock(return_value=mock_agent)

        master = MasterAgent(
            tmux_manager=mock_tmux,
            cli=mock_cli,
            agent_factory=factory,
        )

        # 启动
        master.startup()
        assert master.is_started
        mock_tmux.create_session.assert_called_once()

        # 执行完整流程
        master.receive_requirement("冒烟测试")
        master.create_pm_agent()
        master.set_task_json(_make_task_json())

        result = master.dispatch_task(master.task_json.tasks[0])
        assert result.status == SubAgentResultStatus.SUCCESS

    def test_state_transitions_complete_lifecycle(self):
        """验证完整生命周期的状态转换链"""
        mock_agent = _make_mock_sub_agent("senior-developer")
        factory = MagicMock(return_value=mock_agent)

        master = MasterAgent(agent_factory=factory)

        # IDLE → ANALYZING
        master.receive_requirement("测试")
        assert master.state == MasterAgentState.ANALYZING

        # ANALYZING → PLANNING → DISPATCHING
        master.create_pm_agent()
        master.set_task_json(_make_task_json())
        assert master.state == MasterAgentState.DISPATCHING

        # DISPATCHING → (dispatch + record) → check all completed
        master.dispatch_task(master.task_json.tasks[0])
        assert master.is_all_completed()

    def test_multiple_tasks_with_dependency(self):
        """两个有依赖关系的任务端到端流程"""
        task1 = Task(
            id="task-001",
            title="编写代码",
            description="实现功能代码",
            dependencies=[],
            suggested_role="senior-developer",
            priority=TaskPriority.HIGH,
        )
        task2 = Task(
            id="task-002",
            title="编写测试",
            description="为代码编写测试",
            dependencies=["task-001"],
            suggested_role="test-engineer",
            priority=TaskPriority.HIGH,
        )
        task_json = TaskJSON(
            project_name="依赖测试",
            total_tasks=2,
            tasks=[task1, task2],
        )

        # 创建成功执行的 mock
        def make_agent(role_name):
            agent = MagicMock(spec=EphemeralSubAgent)
            agent.role_name = role_name
            agent.run.return_value = SubAgentResult(
                task_id="task-001" if role_name == "senior-developer" else "task-002",
                status=SubAgentResultStatus.SUCCESS,
                phase="completed",
                role=role_name,
            )
            return agent

        factory = MagicMock(side_effect=make_agent)
        master = MasterAgent(agent_factory=factory)

        master.receive_requirement("测试依赖")
        master.create_pm_agent()
        master.set_task_json(task_json)

        # 只能调度 task-001（task-002 依赖 task-001）
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 1
        assert dispatchable[0].id == "task-001"

        # 执行 task-001
        master.dispatch_task(task1)
        assert task1.status == TaskStatus.COMPLETED

        # 现在 task-002 可调度
        dispatchable = master.get_dispatchable_tasks()
        assert len(dispatchable) == 1
        assert dispatchable[0].id == "task-002"

        # 执行 task-002
        master.dispatch_task(task2)
        assert task2.status == TaskStatus.COMPLETED
        assert master.is_all_completed()

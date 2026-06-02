"""
Dev Agent 代码实现和测试运行数据模型

基于 PRD V2.0 §4.4 Dev Agent TDD 流程设计。
定义 implement_code 和 run_tests 的结构化返回模型。

TDD 流程：
    Task
      → analyze_task() → TaskAnalysisResult
        → write_tests() → TestWriteResult
          → implement_code() → ImplementResult（本模型之一）
            → run_tests() → TestRunResult（本模型之一）
              → build_commit_message()

设计原则：
    - implement_code 基于分析结果和测试用例生成实现方案和代码骨架
    - run_tests 构建测试命令、收集结果、缓存到 Agent 状态
    - 两个模型均支持 to_text() 便于 prompt 注入和日志记录
"""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ImplementResult(BaseModel):
    """代码实现结果

    由 SeniorDeveloperAgent.implement_code() 生成。
    包含变更文件列表、实现摘要、代码统计等信息。

    Attributes:
        task_id: 关联的任务 ID
        files_changed: 变更的文件路径列表
        implementation_summary: 实现摘要描述
        lines_added: 新增代码行数
        lines_removed: 删除代码行数
        implementation_content: 生成的主要实现文件内容（可选）
        status: 实现状态（pending/implementing/completed/failed）
        created_at: 结果创建时间
    """

    task_id: str = Field(
        ...,
        min_length=1,
        description="关联的任务 ID",
    )
    files_changed: list[str] = Field(
        default_factory=list,
        description="变更的文件路径列表",
    )
    implementation_summary: str = Field(
        default="",
        description="实现摘要描述",
    )
    lines_added: int = Field(
        default=0,
        ge=0,
        description="新增代码行数",
    )
    lines_removed: int = Field(
        default=0,
        ge=0,
        description="删除代码行数",
    )
    implementation_content: str = Field(
        default="",
        description="生成的主要实现文件内容",
    )
    status: str = Field(
        default="completed",
        description="实现状态：pending/implementing/completed/failed",
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="结果创建时间",
    )

    @property
    def has_changes(self) -> bool:
        """是否存在代码变更"""
        return len(self.files_changed) > 0 or self.lines_added > 0

    @property
    def net_lines(self) -> int:
        """净增代码行数"""
        return self.lines_added - self.lines_removed

    @property
    def change_count(self) -> int:
        """变更文件数量"""
        return len(self.files_changed)

    def to_text(self) -> str:
        """生成结构化文本表示

        将实现结果转为可读的文本格式，便于 prompt 注入或日志记录。

        Returns:
            结构化文本
        """
        lines = [
            f"## 代码实现结果：{self.task_id}",
            "",
            f"### 状态",
            f"  {self.status}",
        ]

        if self.implementation_summary:
            lines.append("")
            lines.append("### 实现摘要")
            lines.append(f"  {self.implementation_summary}")

        if self.files_changed:
            lines.append("")
            lines.append("### 变更文件")
            for f in self.files_changed:
                lines.append(f"  - {f}")

        lines.append("")
        lines.append("### 代码统计")
        lines.append(f"  新增：{self.lines_added} 行")
        lines.append(f"  删除：{self.lines_removed} 行")
        lines.append(f"  净增：{self.net_lines} 行")
        lines.append(f"  变更文件：{self.change_count} 个")

        return "\n".join(lines)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "task_id": "task-001",
                    "files_changed": [
                        "agent_automation_system/api/login.py",
                        "tests/test_task_001.py",
                    ],
                    "implementation_summary": "实现用户登录 API，支持邮箱和手机号两种登录方式",
                    "lines_added": 85,
                    "lines_removed": 0,
                    "status": "completed",
                }
            ]
        }
    }


class TestRunResult(BaseModel):
    """测试运行结果

    由 SeniorDeveloperAgent.run_tests() 生成。
    包含测试通过/失败统计、错误详情等信息。

    Attributes:
        task_id: 关联的任务 ID
        passed: 是否全部通过
        total: 总测试数
        passed_count: 通过数
        failed_count: 失败数
        error_details: 错误详情（如有）
        test_file_path: 测试文件路径
        duration_seconds: 测试运行时长（秒）
        created_at: 结果创建时间
    """

    task_id: str = Field(
        ...,
        min_length=1,
        description="关联的任务 ID",
    )
    passed: bool = Field(
        default=True,
        description="是否全部通过",
    )
    total: int = Field(
        default=0,
        ge=0,
        description="总测试数",
    )
    passed_count: int = Field(
        default=0,
        ge=0,
        description="通过数",
    )
    failed_count: int = Field(
        default=0,
        ge=0,
        description="失败数",
    )
    error_details: str = Field(
        default="",
        description="错误详情（如有）",
    )
    test_file_path: str = Field(
        default="",
        description="测试文件路径",
    )
    duration_seconds: float = Field(
        default=0.0,
        ge=0.0,
        description="测试运行时长（秒）",
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="结果创建时间",
    )

    @property
    def pass_rate(self) -> float:
        """通过率（0.0 ~ 1.0）"""
        if self.total == 0:
            return 1.0
        return round(self.passed_count / self.total, 4)

    @property
    def has_failures(self) -> bool:
        """是否存在失败用例"""
        return self.failed_count > 0

    @property
    def all_passed(self) -> bool:
        """是否全部通过"""
        return self.passed and self.failed_count == 0

    def to_text(self) -> str:
        """生成结构化文本表示

        将测试结果转为可读的文本格式，便于 prompt 注入或日志记录。

        Returns:
            结构化文本
        """
        status = "✅ 全部通过" if self.all_passed else "❌ 存在失败"
        lines = [
            f"## 测试运行结果：{self.task_id}",
            "",
            f"### 状态：{status}",
            f"  总数：{self.total}",
            f"  通过：{self.passed_count}",
            f"  失败：{self.failed_count}",
            f"  通过率：{self.pass_rate:.0%}",
        ]

        if self.test_file_path:
            lines.append(f"  测试文件：{self.test_file_path}")

        if self.duration_seconds > 0:
            lines.append(f"  运行时长：{self.duration_seconds:.2f}s")

        if self.has_failures and self.error_details:
            lines.append("")
            lines.append("### 错误详情")
            lines.append(f"  {self.error_details[:200]}")

        return "\n".join(lines)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "task_id": "task-001",
                    "passed": True,
                    "total": 5,
                    "passed_count": 5,
                    "failed_count": 0,
                    "error_details": "",
                    "test_file_path": "tests/test_task_001.py",
                    "duration_seconds": 0.35,
                }
            ]
        }
    }


class TddWorkflowStatus:
    """TDD 闭环流程状态常量（P2-025）"""

    COMMITTED = "COMMITTED"
    TEST_FAILED = "TEST_FAILED"
    ANALYZE_FAILED = "ANALYZE_FAILED"
    IMPLEMENT_FAILED = "IMPLEMENT_FAILED"


class TddWorkflowResult(BaseModel):
    """TDD 闭环完整结果（P2-025）

    由 SeniorDeveloperAgent.execute_tdd_workflow() 生成。
    覆盖从分析到提交的完整 TDD 流程结果。

    Attributes:
        task_id: 关联的任务 ID
        workflow_status: 流程最终状态（COMMITTED / TEST_FAILED / ANALYZE_FAILED / IMPLEMENT_FAILED）
        step_results: 各步骤的结果缓存（analyze / write_tests / implement / run_tests）
        commit_hash: git commit hash（commit 成功时有值）
        error_message: 错误信息（失败时有值）
        duration_seconds: 总耗时（秒）
        created_at: 结果创建时间
    """

    task_id: str = Field(
        ...,
        min_length=1,
        description="关联的任务 ID",
    )
    workflow_status: str = Field(
        ...,
        description="TDD 闭环最终状态：COMMITTED / TEST_FAILED / ANALYZE_FAILED / IMPLEMENT_FAILED",
    )
    step_results: dict[str, Any] = Field(
        default_factory=dict,
        description="各步骤结果摘要",
    )
    commit_hash: Optional[str] = Field(
        default=None,
        description="git commit hash（仅 COMMITTED 时有值）",
    )
    error_message: str = Field(
        default="",
        description="错误信息（失败时有值）",
    )
    duration_seconds: float = Field(
        default=0.0,
        ge=0.0,
        description="总耗时（秒）",
    )
    created_at: datetime = Field(
        default_factory=datetime.now,
        description="结果创建时间",
    )

    @property
    def success(self) -> bool:
        """TDD 闭环是否成功（代码已提交）"""
        return self.workflow_status == TddWorkflowStatus.COMMITTED

    @property
    def tests_passed(self) -> bool:
        """测试是否通过"""
        run_tests = self.step_results.get("run_tests", {})
        return run_tests.get("passed", False)

    @property
    def is_committed(self) -> bool:
        """是否已 git commit"""
        return self.commit_hash is not None and len(self.commit_hash) > 0

    def to_text(self) -> str:
        """生成结构化文本表示"""
        status_icons = {
            TddWorkflowStatus.COMMITTED: "✅",
            TddWorkflowStatus.TEST_FAILED: "❌",
            TddWorkflowStatus.ANALYZE_FAILED: "⚠️",
            TddWorkflowStatus.IMPLEMENT_FAILED: "⚠️",
        }
        icon = status_icons.get(self.workflow_status, "❓")

        lines = [
            f"## TDD 闭环结果：{self.task_id}",
            "",
            f"### 状态：{icon} {self.workflow_status}",
            f"  耗时：{self.duration_seconds:.2f}s",
        ]

        if self.step_results:
            lines.append("")
            lines.append("### 步骤结果")
            for step, result in self.step_results.items():
                if isinstance(result, dict):
                    status = result.get("status", "?")
                    summary = result.get("summary", "")
                    lines.append(f"  - {step}: {status}" + (f" ({summary})" if summary else ""))

        if self.commit_hash:
            lines.append("")
            lines.append(f"### Git Commit: {self.commit_hash[:7]}")

        if self.error_message:
            lines.append("")
            lines.append("### 错误信息")
            lines.append(f"  {self.error_message[:200]}")

        return "\n".join(lines)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "task_id": "task-001",
                    "workflow_status": "COMMITTED",
                    "step_results": {
                        "analyze": {"status": "completed", "files": 2},
                        "write_tests": {"status": "completed", "test_count": 4},
                        "implement": {"status": "completed", "lines_added": 85},
                        "run_tests": {"status": "passed", "total": 4, "passed_count": 4},
                    },
                    "commit_hash": "a3f7b2c1234567890abcdef1234567890abcdef",
                    "error_message": "",
                    "duration_seconds": 12.5,
                }
            ]
        }
    }

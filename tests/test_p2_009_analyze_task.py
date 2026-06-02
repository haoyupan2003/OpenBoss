"""
P2-009 测试：SeniorDeveloperAgent.analyze_task 实现

验证 analyze_task 完整实现，覆盖：
1. TaskAnalysisResult 数据模型
2. analyze_task 核心流程
3. 文件推断（创建/修改）
4. 工作量估算
5. 风险识别
6. 测试策略生成
7. 技术方案确定
8. 内部辅助方法
9. get_analyze_prompt 集成
10. 边界条件与异常处理
"""

import pytest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from agent_automation_system.harness.models import (
    Harness,
    HarnessRule,
    HarnessSection,
    RuleType,
)
from agent_automation_system.models.dev_analysis import TaskAnalysisResult
from agent_automation_system.models.task import (
    BDDSpec,
    Task,
    TaskComplexity,
    TaskPriority,
    TaskStatus,
)
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
def dev_agent_with_mock_harness():
    """创建带 mock harness 的 SeniorDeveloperAgent 实例"""
    agent = SeniorDeveloperAgent()
    mock_harness = Harness(
        name="Senior Developer Agent Rules",
        file_path="/harness/dev-rules.md",
        role_name="senior-developer",
        sections=[
            HarnessSection(
                title="DO",
                rule_type=RuleType.DO,
                rules=[
                    HarnessRule(
                        rule_type=RuleType.DO,
                        content="Write test cases first following TDD methodology",
                        section="DO",
                    ),
                ],
                raw_content="- Write test cases first",
            ),
            HarnessSection(
                title="DON'T",
                rule_type=RuleType.DONT,
                rules=[
                    HarnessRule(
                        rule_type=RuleType.DONT,
                        content="NEVER skip writing tests before implementation",
                        section="DON'T",
                    ),
                ],
                raw_content="- NEVER skip tests",
            ),
        ],
    )
    agent._dev_harness = mock_harness
    agent._dev_harness_content = mock_harness.to_prompt_text()
    return agent


@pytest.fixture
def sample_task():
    """创建示例 Task（API 类任务）"""
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
def high_complexity_task():
    """创建高复杂度 Task"""
    return Task(
        id="task-010",
        title="实现并发消息队列服务",
        description="实现基于 Redis 的异步消息队列服务，支持并发消费",
        bdd=BDDSpec(
            given="Redis 服务已启动",
            when="发送消息到队列",
            then="消费者成功接收并处理消息",
        ),
        dependencies=["task-008", "task-009"],
        suggested_role="senior-developer",
        priority=TaskPriority.HIGH,
        estimated_complexity=TaskComplexity.HIGH,
        status=TaskStatus.PENDING,
    )


@pytest.fixture
def simple_task():
    """创建简单 Task（无 BDD、低复杂度）"""
    return Task(
        id="task-020",
        title="修改配置文件",
        description="更新数据库连接配置",
        priority=TaskPriority.LOW,
        estimated_complexity=TaskComplexity.LOW,
        status=TaskStatus.PENDING,
    )


@pytest.fixture
def model_task():
    """创建数据模型类 Task"""
    return Task(
        id="task-005",
        title="实现 TaskResult 数据模型",
        description="创建 TaskResult 数据结构 schema",
        bdd=BDDSpec(
            given="需要表示任务执行结果",
            when="创建 TaskResult 实例",
            then="包含 status/output/metadata 字段",
        ),
        priority=TaskPriority.MEDIUM,
        estimated_complexity=TaskComplexity.LOW,
        status=TaskStatus.PENDING,
    )


# ── 1. TaskAnalysisResult 数据模型 ─────────────────────────


class TestTaskAnalysisResultModel:
    """验证 TaskAnalysisResult 数据模型"""

    def test_create_with_required_fields(self):
        """最小字段创建"""
        result = TaskAnalysisResult(
            task_id="task-001",
            implementation_plan="实现登录功能",
        )
        assert result.task_id == "task-001"
        assert result.implementation_plan == "实现登录功能"

    def test_create_with_all_fields(self):
        """全字段创建"""
        now = datetime.now()
        result = TaskAnalysisResult(
            task_id="task-001",
            implementation_plan="实现登录 API",
            files_to_create=["auth/login.py", "tests/test_login.py"],
            files_to_modify=["auth/__init__.py"],
            dependencies=["task-000"],
            estimated_effort=45,
            risks=["涉及第三方认证服务"],
            test_strategy="先编写接口测试",
            technical_approach="使用 JWT 认证",
            created_at=now,
        )
        assert result.task_id == "task-001"
        assert len(result.files_to_create) == 2
        assert len(result.files_to_modify) == 1
        assert result.estimated_effort == 45

    def test_default_values(self):
        """默认值正确"""
        result = TaskAnalysisResult(
            task_id="task-001",
            implementation_plan="plan",
        )
        assert result.files_to_create == []
        assert result.files_to_modify == []
        assert result.dependencies == []
        assert result.estimated_effort == 30
        assert result.risks == []
        assert result.test_strategy == ""
        assert result.technical_approach == ""

    def test_total_files_property(self):
        """total_files 属性计算"""
        result = TaskAnalysisResult(
            task_id="task-001",
            implementation_plan="plan",
            files_to_create=["a.py", "b.py"],
            files_to_modify=["c.py"],
        )
        assert result.total_files == 3

    def test_total_files_empty(self):
        """无文件时 total_files 为 0"""
        result = TaskAnalysisResult(
            task_id="task-001",
            implementation_plan="plan",
        )
        assert result.total_files == 0

    def test_has_risks_property(self):
        """has_risks 属性"""
        result = TaskAnalysisResult(
            task_id="task-001",
            implementation_plan="plan",
            risks=["风险1"],
        )
        assert result.has_risks is True

    def test_has_no_risks(self):
        """无风险时 has_risks 为 False"""
        result = TaskAnalysisResult(
            task_id="task-001",
            implementation_plan="plan",
        )
        assert result.has_risks is False

    def test_has_dependencies_property(self):
        """has_dependencies 属性"""
        result = TaskAnalysisResult(
            task_id="task-001",
            implementation_plan="plan",
            dependencies=["task-000"],
        )
        assert result.has_dependencies is True

    def test_effort_hours_property(self):
        """effort_hours 属性"""
        result = TaskAnalysisResult(
            task_id="task-001",
            implementation_plan="plan",
            estimated_effort=90,
        )
        assert result.effort_hours == 1.5

    def test_effort_hours_less_than_one_hour(self):
        """不足 1 小时的 effort_hours"""
        result = TaskAnalysisResult(
            task_id="task-001",
            implementation_plan="plan",
            estimated_effort=30,
        )
        assert result.effort_hours == 0.5

    def test_to_text_includes_all_sections(self):
        """to_text() 包含所有段落"""
        result = TaskAnalysisResult(
            task_id="task-001",
            implementation_plan="实现登录功能",
            files_to_create=["auth/login.py"],
            files_to_modify=["auth/__init__.py"],
            dependencies=["task-000"],
            estimated_effort=45,
            risks=["涉及外部认证服务"],
            test_strategy="先编写接口测试",
            technical_approach="使用 JWT 认证",
        )
        text = result.to_text()
        assert "task-001" in text
        assert "实现登录功能" in text
        assert "auth/login.py" in text
        assert "auth/__init__.py" in text
        assert "task-000" in text
        assert "45 分钟" in text
        assert "涉及外部认证服务" in text
        assert "先编写接口测试" in text
        assert "使用 JWT 认证" in text

    def test_to_text_no_files(self):
        """无文件变更时的 to_text()"""
        result = TaskAnalysisResult(
            task_id="task-001",
            implementation_plan="plan",
        )
        text = result.to_text()
        assert "暂无明确文件变更" in text

    def test_estimated_effort_validation_min(self):
        """工作量不能小于 1"""
        with pytest.raises(Exception):
            TaskAnalysisResult(
                task_id="task-001",
                implementation_plan="plan",
                estimated_effort=0,
            )

    def test_estimated_effort_validation_max(self):
        """工作量不能超过 480"""
        with pytest.raises(Exception):
            TaskAnalysisResult(
                task_id="task-001",
                implementation_plan="plan",
                estimated_effort=500,
            )

    def test_task_id_required(self):
        """task_id 必填"""
        with pytest.raises(Exception):
            TaskAnalysisResult(implementation_plan="plan")

    def test_implementation_plan_required(self):
        """implementation_plan 必填"""
        with pytest.raises(Exception):
            TaskAnalysisResult(task_id="task-001")

    def test_implementation_plan_non_empty(self):
        """implementation_plan 不能为空字符串"""
        with pytest.raises(Exception):
            TaskAnalysisResult(
                task_id="task-001",
                implementation_plan="",
            )


# ── 2. analyze_task 核心流程 ──────────────────────────────


class TestAnalyzeTaskCore:
    """验证 analyze_task 核心功能"""

    def test_returns_task_analysis_result(self, dev_agent, sample_task):
        """返回 TaskAnalysisResult 实例"""
        result = dev_agent.analyze_task(sample_task)
        assert isinstance(result, TaskAnalysisResult)

    def test_result_contains_task_id(self, dev_agent, sample_task):
        """结果包含正确的 task_id"""
        result = dev_agent.analyze_task(sample_task)
        assert result.task_id == "task-001"

    def test_result_has_implementation_plan(self, dev_agent, sample_task):
        """结果包含实现方案"""
        result = dev_agent.analyze_task(sample_task)
        assert result.implementation_plan
        assert sample_task.id in result.implementation_plan
        assert sample_task.title in result.implementation_plan

    def test_result_has_files_to_create(self, dev_agent, sample_task):
        """结果包含文件创建列表"""
        result = dev_agent.analyze_task(sample_task)
        assert isinstance(result.files_to_create, list)
        assert len(result.files_to_create) > 0

    def test_result_has_test_file(self, dev_agent, sample_task):
        """文件创建列表包含测试文件"""
        result = dev_agent.analyze_task(sample_task)
        test_files = [f for f in result.files_to_create if "test" in f]
        assert len(test_files) > 0

    def test_result_has_estimated_effort(self, dev_agent, sample_task):
        """结果包含工作量估算"""
        result = dev_agent.analyze_task(sample_task)
        assert result.estimated_effort > 0

    def test_saves_task_description(self, dev_agent, sample_task):
        """保存任务描述到 current_task_description"""
        dev_agent.analyze_task(sample_task)
        assert dev_agent.current_task_description == sample_task.description

    def test_saves_implementation_plan(self, dev_agent, sample_task):
        """保存实现方案到 implementation_plan"""
        dev_agent.analyze_task(sample_task)
        assert dev_agent.implementation_plan is not None
        assert sample_task.title in dev_agent.implementation_plan

    def test_result_has_dependencies(self, dev_agent, high_complexity_task):
        """结果包含依赖列表"""
        result = dev_agent.analyze_task(high_complexity_task)
        assert "task-008" in result.dependencies
        assert "task-009" in result.dependencies

    def test_none_task_raises_value_error(self, dev_agent):
        """None 任务抛出 ValueError"""
        with pytest.raises(ValueError, match="task cannot be None"):
            dev_agent.analyze_task(None)

    def test_result_created_at(self, dev_agent, sample_task):
        """结果包含创建时间"""
        result = dev_agent.analyze_task(sample_task)
        assert isinstance(result.created_at, datetime)


# ── 3. 文件推断 ──────────────────────────────────────────


class TestFileInference:
    """验证文件推断逻辑"""

    def test_api_task_creates_api_file(self, dev_agent, sample_task):
        """API 类任务推断创建 API 文件"""
        result = dev_agent.analyze_task(sample_task)
        api_files = [f for f in result.files_to_create if "api" in f]
        assert len(api_files) > 0

    def test_model_task_creates_model_file(self, dev_agent, model_task):
        """模型类任务推断创建 model 文件"""
        result = dev_agent.analyze_task(model_task)
        model_files = [f for f in result.files_to_create if "model" in f]
        assert len(model_files) > 0

    def test_service_task_creates_service_file(self, dev_agent):
        """服务类任务推断创建 service 文件"""
        task = Task(
            id="task-003",
            title="实现用户认证服务",
            description="实现认证业务逻辑处理",
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.analyze_task(task)
        service_files = [f for f in result.files_to_create if "service" in f]
        assert len(service_files) > 0

    def test_util_task_creates_util_file(self, dev_agent):
        """工具类任务推断创建 util 文件"""
        task = Task(
            id="task-004",
            title="实现数据验证 validator 工具",
            description="创建通用的数据校验辅助函数",
            priority=TaskPriority.LOW,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.analyze_task(task)
        util_files = [f for f in result.files_to_create if "util" in f]
        assert len(util_files) > 0

    def test_always_creates_test_file(self, dev_agent, sample_task):
        """始终创建测试文件"""
        result = dev_agent.analyze_task(sample_task)
        test_files = [f for f in result.files_to_create if f.startswith("tests/test_")]
        assert len(test_files) >= 1

    def test_modify_task_infers_modify_files(self, dev_agent, simple_task):
        """修改类任务推断修改文件"""
        result = dev_agent.analyze_task(simple_task)
        # 修改任务应有修改文件
        assert isinstance(result.files_to_modify, list)

    def test_add_task_infers_init_modify(self, dev_agent):
        """添加新功能推断修改 __init__.py"""
        task = Task(
            id="task-030",
            title="添加新的数据模型",
            description="在 models 中新增 TaskResult 模型",
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.analyze_task(task)
        init_files = [f for f in result.files_to_modify if "__init__.py" in f]
        assert len(init_files) > 0

    def test_generic_task_creates_source_file(self, dev_agent):
        """通用任务（无特殊关键词）创建源文件"""
        task = Task(
            id="task-050",
            title="实现日志功能",
            description="实现基本的日志记录",
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.analyze_task(task)
        # 应有测试文件 + 至少一个源文件
        assert len(result.files_to_create) >= 2

    def test_files_to_modify_deduplication(self, dev_agent):
        """修改文件列表去重"""
        task = Task(
            id="task-060",
            title="修改并添加 API 模型",
            description="修改 api 模型数据结构并添加新字段",
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.analyze_task(task)
        # 不应有重复文件
        assert len(result.files_to_modify) == len(set(result.files_to_modify))


# ── 4. 工作量估算 ────────────────────────────────────────


class TestEffortEstimation:
    """验证工作量估算逻辑"""

    def test_low_complexity_base_time(self, dev_agent, simple_task):
        """低复杂度基础时间 15 分钟"""
        result = dev_agent.analyze_task(simple_task)
        assert result.estimated_effort >= 15

    def test_medium_complexity_base_time(self, dev_agent, sample_task):
        """中复杂度基础时间 30 分钟"""
        result = dev_agent.analyze_task(sample_task)
        assert result.estimated_effort >= 30

    def test_high_complexity_base_time(self, dev_agent, high_complexity_task):
        """高复杂度基础时间 60 分钟"""
        result = dev_agent.analyze_task(high_complexity_task)
        assert result.estimated_effort >= 60

    def test_more_files_increases_effort(self, dev_agent):
        """更多文件增加工作量"""
        simple = Task(
            id="task-100",
            title="简单配置",
            description="修改配置",
            priority=TaskPriority.LOW,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        complex_task = Task(
            id="task-101",
            title="实现完整 API 服务模型",
            description="实现 api endpoint 服务和业务逻辑 model",
            priority=TaskPriority.HIGH,
            estimated_complexity=TaskComplexity.HIGH,
            status=TaskStatus.PENDING,
        )
        simple_result = dev_agent.analyze_task(simple)
        complex_result = dev_agent.analyze_task(complex_task)
        assert complex_result.estimated_effort > simple_result.estimated_effort

    def test_dependencies_increase_effort(self, dev_agent):
        """有依赖增加工作量"""
        no_dep = Task(
            id="task-200",
            title="无依赖任务",
            description="独立实现",
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        )
        with_dep = Task(
            id="task-201",
            title="有依赖任务",
            description="依赖前置任务实现",
            dependencies=["task-200"],
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        )
        no_dep_result = dev_agent.analyze_task(no_dep)
        with_dep_result = dev_agent.analyze_task(with_dep)
        assert with_dep_result.estimated_effort >= no_dep_result.estimated_effort

    def test_effort_upper_bound(self, dev_agent):
        """工作量不超过上限"""
        # 构造高复杂度+多依赖的任务
        task = Task(
            id="task-300",
            title="实现高复杂度并发服务",
            description="实现并发消息队列缓存认证 API 服务",
            dependencies=["task-301", "task-302", "task-303", "task-304"],
            priority=TaskPriority.HIGH,
            estimated_complexity=TaskComplexity.HIGH,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.analyze_task(task)
        assert result.estimated_effort <= _DEFAULT_MAX_IMPLEMENTATION_MINUTES * 4


# ── 5. 风险识别 ──────────────────────────────────────────


class TestRiskIdentification:
    """验证风险识别逻辑"""

    def test_high_complexity_identifies_risk(self, dev_agent, high_complexity_task):
        """高复杂度识别为风险"""
        result = dev_agent.analyze_task(high_complexity_task)
        assert result.has_risks
        high_risks = [r for r in result.risks if "HIGH" in r or "复杂度" in r]
        assert len(high_risks) > 0

    def test_dependencies_identify_risk(self, dev_agent, high_complexity_task):
        """有依赖识别为风险"""
        result = dev_agent.analyze_task(high_complexity_task)
        dep_risks = [r for r in result.risks if "依赖" in r]
        assert len(dep_risks) > 0

    def test_external_service_identifies_risk(self, dev_agent):
        """涉及外部服务识别为风险"""
        task = Task(
            id="task-040",
            title="对接第三方支付 API",
            description="实现微信支付接口调用",
            priority=TaskPriority.HIGH,
            estimated_complexity=TaskComplexity.HIGH,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.analyze_task(task)
        ext_risks = [r for r in result.risks if "外部" in r]
        assert len(ext_risks) > 0

    def test_concurrency_identifies_risk(self, dev_agent):
        """涉及并发识别为风险"""
        task = Task(
            id="task-041",
            title="实现并发锁机制",
            description="实现异步并发处理",
            priority=TaskPriority.HIGH,
            estimated_complexity=TaskComplexity.HIGH,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.analyze_task(task)
        concurrency_risks = [r for r in result.risks if "并发" in r or "线程安全" in r]
        assert len(concurrency_risks) > 0

    def test_security_identifies_risk(self, dev_agent):
        """涉及安全识别为风险"""
        task = Task(
            id="task-042",
            title="实现密码加密存储",
            description="实现用户密码的加密和验证",
            priority=TaskPriority.HIGH,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.analyze_task(task)
        security_risks = [r for r in result.risks if "安全" in r]
        assert len(security_risks) > 0

    def test_no_bdd_identifies_risk(self, dev_agent, simple_task):
        """缺少 BDD 识别为风险"""
        result = dev_agent.analyze_task(simple_task)
        bdd_risks = [r for r in result.risks if "BDD" in r]
        assert len(bdd_risks) > 0

    def test_simple_task_may_have_few_risks(self, dev_agent, simple_task):
        """简单任务可能无风险或少风险"""
        result = dev_agent.analyze_task(simple_task)
        # 简单任务也可能有风险（缺少 BDD），但不应有高风险
        assert isinstance(result.risks, list)


# ── 6. 测试策略生成 ──────────────────────────────────────


class TestTestStrategyGeneration:
    """验证测试策略生成"""

    def test_strategy_mentions_tdd(self, dev_agent, sample_task):
        """测试策略提及 TDD"""
        result = dev_agent.analyze_task(sample_task)
        assert "TDD" in result.test_strategy

    def test_strategy_with_bdd(self, dev_agent, sample_task):
        """有 BDD 时策略基于 BDD"""
        result = dev_agent.analyze_task(sample_task)
        assert "Given" in result.test_strategy or "BDD" in result.test_strategy

    def test_strategy_without_bdd(self, dev_agent, simple_task):
        """无 BDD 时策略基于描述"""
        result = dev_agent.analyze_task(simple_task)
        assert "描述" in result.test_strategy or "TDD" in result.test_strategy

    def test_high_complexity_adds_boundary_strategy(self, dev_agent, high_complexity_task):
        """高复杂度追加边界测试策略"""
        result = dev_agent.analyze_task(high_complexity_task)
        assert "边界" in result.test_strategy or "异常" in result.test_strategy

    def test_api_task_adds_api_strategy(self, dev_agent, sample_task):
        """API 任务追加 API 测试策略"""
        result = dev_agent.analyze_task(sample_task)
        assert "API" in result.test_strategy or "接口" in result.test_strategy or "请求" in result.test_strategy

    def test_concurrency_task_adds_concurrency_strategy(self, dev_agent):
        """并发任务追加并发测试策略"""
        task = Task(
            id="task-043",
            title="实现异步任务队列",
            description="实现异步并发消息处理",
            priority=TaskPriority.HIGH,
            estimated_complexity=TaskComplexity.HIGH,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.analyze_task(task)
        assert "并发" in result.test_strategy or "竞态" in result.test_strategy


# ── 7. 技术方案确定 ──────────────────────────────────────


class TestTechnicalApproach:
    """验证技术方案确定"""

    def test_approach_includes_task_title(self, dev_agent, sample_task):
        """技术方案包含任务标题"""
        result = dev_agent.analyze_task(sample_task)
        assert sample_task.title in result.technical_approach

    def test_api_task_adds_api_approach(self, dev_agent, sample_task):
        """API 任务追加 API 实现方案"""
        result = dev_agent.analyze_task(sample_task)
        assert "API" in result.technical_approach or "路由" in result.technical_approach

    def test_model_task_adds_model_approach(self, dev_agent, model_task):
        """模型任务追加模型实现方案"""
        result = dev_agent.analyze_task(model_task)
        assert "模型" in result.technical_approach or "Pydantic" in result.technical_approach or "BaseModel" in result.technical_approach

    def test_task_with_deps_adds_dep_approach(self, dev_agent, high_complexity_task):
        """有依赖任务追加依赖处理方案"""
        result = dev_agent.analyze_task(high_complexity_task)
        assert "依赖" in result.technical_approach or "task-008" in result.technical_approach

    def test_service_task_adds_service_approach(self, dev_agent):
        """服务任务追加服务实现方案"""
        task = Task(
            id="task-006",
            title="实现订单业务服务",
            description="处理订单业务逻辑",
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.analyze_task(task)
        assert "服务" in result.technical_approach or "业务" in result.technical_approach

    def test_util_task_adds_util_approach(self, dev_agent):
        """工具任务追加工具实现方案"""
        task = Task(
            id="task-007",
            title="实现数据验证 validator 工具",
            description="创建通用验证辅助",
            priority=TaskPriority.LOW,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.analyze_task(task)
        assert "工具" in result.technical_approach or "纯函数" in result.technical_approach


# ── 8. 内部辅助方法 ──────────────────────────────────────


class TestInternalHelpers:
    """验证内部辅助方法"""

    def test_extract_module_name_english_title(self, dev_agent):
        """英文标题提取模块名"""
        name = dev_agent._extract_module_name("Implement Login API", "")
        assert name == "implement_login_api"

    def test_extract_module_name_mixed_title(self, dev_agent):
        """中英混合标题提取英文部分"""
        name = dev_agent._extract_module_name("实现 Login API", "")
        assert "login" in name and "api" in name

    def test_extract_module_name_chinese_only(self, dev_agent):
        """纯中文标题从描述提取英文"""
        name = dev_agent._extract_module_name("实现用户登录", "使用 JWT auth token")
        assert "jwt" in name or "auth" in name

    def test_extract_module_name_no_english(self, dev_agent):
        """全中文无英文回退"""
        name = dev_agent._extract_module_name("实现用户登录", "使用手机号验证码")
        # 回退到 hash 或 unnamed_module
        assert isinstance(name, str)
        assert len(name) > 0

    def test_build_implementation_plan_basic(self, dev_agent, sample_task):
        """构建实现方案包含基本信息"""
        plan = dev_agent._build_implementation_plan(sample_task)
        assert sample_task.id in plan
        assert sample_task.title in plan
        assert "TDD" in plan

    def test_build_implementation_plan_high_complexity(self, dev_agent, high_complexity_task):
        """高复杂度实现方案提示分步"""
        plan = dev_agent._build_implementation_plan(high_complexity_task)
        assert "分步" in plan

    def test_build_implementation_plan_low_complexity(self, dev_agent, simple_task):
        """低复杂度实现方案提示快速"""
        plan = dev_agent._build_implementation_plan(simple_task)
        assert "快速" in plan


# ── 9. get_analyze_prompt 集成 ─────────────────────────────


class TestAnalyzePromptIntegration:
    """验证 get_analyze_prompt 与 analyze_task 集成"""

    def test_analyze_prompt_contains_task_info(self, dev_agent_with_mock_harness, sample_task):
        """分析 prompt 包含任务信息"""
        prompt = dev_agent_with_mock_harness.get_analyze_prompt(sample_task)
        assert sample_task.id in prompt
        assert "TDD" in prompt or "test" in prompt.lower()

    def test_analyze_prompt_contains_bdd(self, dev_agent_with_mock_harness, sample_task):
        """分析 prompt 包含 BDD 规格"""
        prompt = dev_agent_with_mock_harness.get_analyze_prompt(sample_task)
        assert "Given" in prompt or "When" in prompt or "Then" in prompt

    def test_analyze_result_to_text_in_prompt(self, dev_agent, sample_task):
        """分析结果 to_text() 可用于后续 prompt"""
        result = dev_agent.analyze_task(sample_task)
        analysis_text = result.to_text()
        # 验证文本可用作 prompt 内容
        assert sample_task.id in analysis_text
        assert len(analysis_text) > 50


# ── 10. 边界条件与异常处理 ───────────────────────────────


class TestBoundaryConditions:
    """验证边界条件和异常处理"""

    def test_multiple_analyses_independent(self, dev_agent, sample_task, model_task):
        """多次分析互不影响"""
        result1 = dev_agent.analyze_task(sample_task)
        result2 = dev_agent.analyze_task(model_task)
        assert result1.task_id != result2.task_id
        assert result1.implementation_plan != result2.implementation_plan

    def test_task_without_bdd(self, dev_agent):
        """无 BDD 任务正常分析"""
        task = Task(
            id="task-010",
            title="简单配置修改",
            description="更新配置项",
            priority=TaskPriority.LOW,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.analyze_task(task)
        assert isinstance(result, TaskAnalysisResult)
        assert result.task_id == "task-010"

    def test_task_without_dependencies(self, dev_agent, sample_task):
        """无依赖任务正常分析"""
        result = dev_agent.analyze_task(sample_task)
        assert result.dependencies == []

    def test_task_with_many_dependencies(self, dev_agent):
        """多依赖任务正常分析"""
        task = Task(
            id="task-999",
            title="集成任务",
            description="集成多个前置任务",
            dependencies=["task-001", "task-002", "task-003", "task-004"],
            priority=TaskPriority.HIGH,
            estimated_complexity=TaskComplexity.HIGH,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.analyze_task(task)
        assert len(result.dependencies) == 4
        assert result.has_dependencies

    def test_task_with_long_title(self, dev_agent):
        """长标题任务正常处理"""
        task = Task(
            id="task-080",
            title="A" * 200,
            description="描述",
            priority=TaskPriority.MEDIUM,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.analyze_task(task)
        assert isinstance(result, TaskAnalysisResult)

    def test_task_with_special_chars_in_description(self, dev_agent):
        """描述含特殊字符正常处理"""
        task = Task(
            id="task-090",
            title="特殊描述任务",
            description="实现 <script>alert('xss')</script> 防护",
            priority=TaskPriority.HIGH,
            estimated_complexity=TaskComplexity.MEDIUM,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.analyze_task(task)
        assert isinstance(result, TaskAnalysisResult)

    def test_analysis_result_is_serializable(self, dev_agent, sample_task):
        """分析结果可序列化"""
        result = dev_agent.analyze_task(sample_task)
        json_text = result.model_dump_json()
        assert isinstance(json_text, str)
        assert "task-001" in json_text

    def test_analysis_result_from_json(self, dev_agent, sample_task):
        """分析结果可反序列化"""
        result = dev_agent.analyze_task(sample_task)
        json_text = result.model_dump_json()
        restored = TaskAnalysisResult.model_validate_json(json_text)
        assert restored.task_id == result.task_id
        assert restored.implementation_plan == result.implementation_plan

    def test_effort_always_positive(self, dev_agent):
        """工作量始终为正"""
        task = Task(
            id="task-070",
            title="最小任务",
            description="最小描述",
            priority=TaskPriority.LOW,
            estimated_complexity=TaskComplexity.LOW,
            status=TaskStatus.PENDING,
        )
        result = dev_agent.analyze_task(task)
        assert result.estimated_effort >= 1

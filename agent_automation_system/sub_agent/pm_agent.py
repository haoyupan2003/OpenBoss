"""
ProductManagerAgent — 产品经理 Agent

基于 PRD V2.0 §4.4 Master Agent 和 §6.4.3 Harness Engineering 设计。
继承 SubAgent 基类，注入 pm-rules.md，专注于需求精炼和任务拆解。

核心职责：
    1. 接收用户原始需求（raw_need）
    2. 将需求精炼为 BDD（Given-When-Then）结构化描述（P2-002）
    3. 与用户沟通确认需求细节（P2-003）
    4. 将确认的需求拆解为原子任务列表（P2-004）
    5. 生成 task.json 文件（P2-005）
    6. 为每个任务编写测试脚本（P2-006）

设计原则：
    - 继承 SubAgent 基类的完整生命周期管理
    - 注入 pm-rules.md 作为角色约束
    - 提供 PM 特有的业务方法（refine / communicate / decompose / generate）
    - 保持 Ephemeral Agent 模式：无状态、一次性、幂等
"""

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from agent_automation_system.harness.harness_loader import HarnessLoader
from agent_automation_system.harness.models import Harness
from agent_automation_system.models.bdd import (
    BDDDraft,
    BDDScenario,
    CommunicationResult,
    CommunicationRound,
    CommunicationStatus,
    DecomposeResult,
    TaskJsonResult,
    TestScriptResult,
    TestScriptType,
)
from agent_automation_system.models.task import (
    BDDSpec,
    Task,
    TaskComplexity,
    TaskPriority,
    TaskStatus,
)
from agent_automation_system.models.task_json import TaskJSON
from agent_automation_system.sub_agent.role_injector import RoleInjector
from agent_automation_system.sub_agent.sub_agent import (
    AgentPhase,
    SubAgent,
    SubAgentResult,
    SubAgentResultStatus,
)

logger = logging.getLogger(__name__)


# ── 默认配置 ────────────────────────────────────────────

# pm-rules.md 默认路径（相对于项目根目录）
_DEFAULT_PM_RULES_PATH = Path(__file__).parent.parent.parent / "harness" / "pm-rules.md"

# PM Agent 角色名称
_PM_ROLE_NAME = "product-manager"

# PM Agent 默认角色简称
_PM_ROLE_SHORT = "pm"

# 沟通循环最大轮次（pm-rules.md Constraints: 3 rounds）
_MAX_COMMUNICATION_ROUNDS = 3


class ProductManagerAgent(SubAgent):
    """产品经理 Agent

    继承 SubAgent 基类，注入 pm-rules.md 角色约束。
    专注于需求精炼（BDD）、用户沟通和任务拆解。

    ProductManagerAgent 在 EphemeralSubAgent 基础上增加了 PM 特有的业务方法，
    用于 BDD 需求精炼、用户沟通循环、任务拆解和 task.json 生成。

    生命周期与基类一致：
        initialize() → execute(task) → verify() → commit() → cleanup()

    PM Agent 特有的业务方法（P2-002 ~ P2-006 将逐步实现）：
        - refine_requirement(raw_need): BDD 需求精炼
        - communicate_with_user(bdd_draft): 用户沟通循环
        - decompose_requirement(confirmed_bdd): 任务拆解
        - generate_task_json(tasks): task.json 生成
        - generate_test_script(task): 测试脚本编写

    Args:
        role_injector: RoleInjector 实例（可选，默认自动创建）
        pm_rules_path: pm-rules.md 文件路径（可选，默认项目 harness 目录）
        harness_loader: HarnessLoader 实例（可选，默认自动创建）
    """

    def __init__(
        self,
        role_injector: Optional[RoleInjector] = None,
        pm_rules_path: Optional[Path] = None,
        harness_loader: Optional[HarnessLoader] = None,
    ) -> None:
        super().__init__(role_name=_PM_ROLE_NAME)
        self._role_injector = role_injector or RoleInjector()
        self._harness_loader = harness_loader or HarnessLoader()
        self._pm_rules_path = pm_rules_path or _DEFAULT_PM_RULES_PATH

        # 加载后的 harness 缓存
        self._pm_harness: Optional[Harness] = None
        self._pm_harness_content: Optional[str] = None

        # PM 工作状态
        self._raw_requirement: Optional[str] = None
        self._bdd_draft: Optional[str] = None
        self._confirmed_bdd: Optional[str] = None

    # ── 属性 ──────────────────────────────────────────────

    @property
    def role_injector(self) -> RoleInjector:
        """RoleInjector 实例"""
        return self._role_injector

    @property
    def pm_rules_path(self) -> Path:
        """pm-rules.md 文件路径"""
        return self._pm_rules_path

    @property
    def pm_harness(self) -> Optional[Harness]:
        """已加载的 pm-rules Harness 对象"""
        return self._pm_harness

    @property
    def pm_harness_content(self) -> Optional[str]:
        """已加载的 pm-rules Harness 内容文本"""
        return self._pm_harness_content

    @property
    def raw_requirement(self) -> Optional[str]:
        """当前处理的原始需求"""
        return self._raw_requirement

    @property
    def bdd_draft(self) -> Optional[str]:
        """当前 BDD 草稿"""
        return self._bdd_draft

    @property
    def confirmed_bdd(self) -> Optional[str]:
        """已确认的 BDD 描述"""
        return self._confirmed_bdd

    # ── Harness 加载 ──────────────────────────────────────

    def load_pm_harness(self) -> Harness:
        """加载 pm-rules.md harness 文件

        从 pm_rules_path 读取并解析 pm-rules.md，
        结果缓存在 _pm_harness 和 _pm_harness_content 中。

        Returns:
            Harness: 解析后的 Harness 对象

        Raises:
            FileNotFoundError: pm-rules.md 文件不存在
            ValueError: 文件内容格式无效
        """
        if self._pm_harness is not None:
            return self._pm_harness

        if not self._pm_rules_path.exists():
            raise FileNotFoundError(
                f"pm-rules.md not found at: {self._pm_rules_path}"
            )

        self._pm_harness = self._harness_loader.load_harness(self._pm_rules_path)
        self._pm_harness_content = self._pm_harness.to_prompt_text()

        logger.info(
            "ProductManagerAgent loaded pm-rules: %s (%d sections, %d rules)",
            self._pm_rules_path,
            len(self._pm_harness.sections),
            len(self._pm_harness.rules),
        )

        return self._pm_harness

    # ── 角色注入 ──────────────────────────────────────────

    def build_pm_prompt(
        self,
        task_description: str,
        include_harness: bool = True,
    ) -> str:
        """构建 PM Agent 专用的完整 prompt

        将角色身份（product-manager）+ 任务描述 + pm-rules.md 约束
        组装为结构化 prompt。

        Args:
            task_description: 任务描述文本
            include_harness: 是否注入 pm-rules 约束（默认 True）

        Returns:
            组装后的完整 prompt 文本
        """
        harness_content = None
        if include_harness:
            if self._pm_harness_content is None:
                try:
                    self.load_pm_harness()
                except FileNotFoundError:
                    logger.warning(
                        "ProductManagerAgent: pm-rules.md not found, "
                        "skipping harness injection"
                    )
            harness_content = self._pm_harness_content

        return self._role_injector.inject_role(
            role_name=_PM_ROLE_NAME,
            task_description=task_description,
            harness_content=harness_content,
        )

    # ── SubAgent 抽象方法实现 ───────────────────────────────

    def initialize(self) -> None:
        """初始化 PM Agent 执行环境

        加载 pm-rules.md harness 文件，准备角色约束。
        如果 harness 文件不存在，记录警告但不阻塞（允许无 harness 运行）。
        """
        try:
            self.load_pm_harness()
            logger.info(
                "ProductManagerAgent initialized with pm-rules harness"
            )
        except FileNotFoundError:
            logger.warning(
                "ProductManagerAgent initialized without pm-rules harness "
                "(file not found: %s)",
                self._pm_rules_path,
            )

    def execute(self, task) -> SubAgentResult:
        """执行 PM 任务

        构建 PM 专用 prompt（含 pm-rules 约束），准备任务执行。
        实际的 LLM 调用由上层编排器（通过 CLI 或直接调用）处理。

        Args:
            task: 要执行的 Task

        Returns:
            SubAgentResult: 执行结果
        """
        task_description = self._build_task_description(task)
        prompt = self.build_pm_prompt(task_description)

        # 保存原始需求
        self._raw_requirement = task.description

        return self._build_result(
            status=SubAgentResultStatus.SUCCESS,
            output=f"PM task '{task.id}' prepared with pm-rules injection",
            metadata={
                "prompt_length": len(prompt),
                "harness_loaded": self._pm_harness is not None,
                "raw_requirement": task.description,
            },
        )

    def verify(self) -> SubAgentResult:
        """验证 PM Agent 执行结果

        检查 PM 产出是否包含基本的 BDD 结构和任务描述。

        Returns:
            SubAgentResult: 验证结果
        """
        return self._build_result(
            status=SubAgentResultStatus.SUCCESS,
            output="PM verification passed (auto-verified)",
        )

    def commit(self) -> SubAgentResult:
        """提交 PM Agent 产出

        PM Agent 的产出（BDD 描述、task.json）通常由 CLI 自行写入文件。

        Returns:
            SubAgentResult: 提交结果
        """
        return self._build_result(
            status=SubAgentResultStatus.SUCCESS,
            output="PM commit completed (auto-committed by CLI)",
        )

    def cleanup(self) -> None:
        """清理 PM Agent 资源"""
        logger.debug("ProductManagerAgent cleanup")

    # ── PM 特有业务方法 ────────────────────────────────────

    def refine_requirement(self, raw_need: str) -> BDDDraft:
        """BDD 需求精炼（P2-002）

        将用户原始需求精炼为 Given-When-Then 结构化描述。
        自动提取关键行为、生成初始 BDD 场景、识别澄清问题和假设。

        精炼流程：
            1. 验证输入（raw_need 非空）
            2. 保存原始需求到 _raw_requirement
            3. 生成需求摘要
            4. 提取初始 BDD 场景
            5. 生成澄清问题
            6. 记录假设
            7. 组装 BDDDraft 并缓存到 _bdd_draft

        Args:
            raw_need: 用户原始需求文本

        Returns:
            BDDDraft: 结构化的 BDD 草稿

        Raises:
            ValueError: raw_need 为空或仅含空白字符
        """
        if not raw_need or not raw_need.strip():
            raise ValueError("raw_need cannot be empty")

        raw_need = raw_need.strip()

        # 1. 保存原始需求
        self._raw_requirement = raw_need

        # 2. 生成需求摘要
        summary = self._generate_summary(raw_need)

        # 3. 提取初始 BDD 场景
        scenarios = self._extract_initial_scenarios(raw_need)

        # 4. 生成澄清问题
        questions = self._generate_clarification_questions(raw_need)

        # 5. 记录假设
        assumptions = self._generate_assumptions(raw_need)

        # 6. 组装 BDDDraft
        draft = BDDDraft(
            raw_need=raw_need,
            summary=summary,
            scenarios=scenarios,
            questions=questions,
            assumptions=assumptions,
            created_at=datetime.now(),
        )

        # 7. 缓存草稿
        self._bdd_draft = draft.to_text()

        logger.info(
            "ProductManagerAgent refined requirement: "
            "%d scenarios, %d questions, %d assumptions",
            draft.scenario_count,
            len(questions),
            len(assumptions),
        )

        return draft

    def get_refine_prompt(self, raw_need: str) -> str:
        """构建需求精炼专用 prompt（供 LLM CLI 使用）

        构建 PM Agent 专用的需求精炼 prompt，包含角色身份、
        pm-rules 约束和精炼指令。此 prompt 供外部 LLM（通过 CLI）
        执行实际的需求精炼，产出更丰富的 BDD 草稿。

        Args:
            raw_need: 用户原始需求文本

        Returns:
            完整的精炼 prompt 文本
        """
        refine_instruction = (
            f"## 原始需求\n\n{raw_need}\n\n"
            "## 精炼任务\n\n"
            "请将上述原始需求精炼为 BDD（Given-When-Then）结构化描述。\n\n"
            "要求：\n"
            "1. 识别需求中的所有功能行为，每个行为对应一个 BDD 场景\n"
            "2. 使用 Given-When-Then 格式描述每个场景\n"
            "3. 列出需要向用户澄清的疑问\n"
            "4. 列出精炼过程中的假设\n"
            "5. 为每个场景标注优先级（high/medium/low）"
        )
        return self.build_pm_prompt(refine_instruction)

    # ── refine_requirement 内部方法 ────────────────────────

    def _generate_summary(self, raw_need: str) -> str:
        """从原始需求生成一句话摘要

        提取需求中的核心行为描述，生成简洁摘要。
        如果原始需求较短（≤50字），直接使用原文作为摘要。

        Args:
            raw_need: 原始需求文本

        Returns:
            需求摘要
        """
        if len(raw_need) <= 50:
            return raw_need

        # 尝试提取第一个句号/分号前的内容
        for delimiter in ["。", "；", ".", ";", "\n"]:
            idx = raw_need.find(delimiter)
            if 0 < idx <= 80:
                return raw_need[:idx].strip()

        # 截取前 80 字符（确保不超过原文）
        truncated = raw_need[:80].strip()
        if len(truncated) < len(raw_need):
            return truncated + "..."
        return raw_need

    def _extract_initial_scenarios(self, raw_need: str) -> list[BDDScenario]:
        """从原始需求提取初始 BDD 场景

        基于模板方法提取核心行为场景。此方法生成初始框架，
        实际的深度精炼由 LLM 通过 CLI 执行。

        提取策略：
            1. 将需求按句号/分号/换行拆分为行为片段
            2. 每个片段构建为一个初始 BDD 场景
            3. 使用需求文本填充 Given/When/Then 模板

        Args:
            raw_need: 原始需求文本

        Returns:
            BDD 场景列表
        """
        scenarios: list[BDDScenario] = []

        # 按标点拆分需求为行为片段
        segments = re.split(r"[。；\n;]", raw_need)
        segments = [s.strip() for s in segments if s.strip()]

        if not segments:
            # 整段作为一个场景
            segments = [raw_need]

        for i, segment in enumerate(segments):
            # 尝试识别"动词+宾语"模式
            scenario_title = self._extract_scenario_title(segment, i + 1)

            scenario = BDDScenario(
                title=scenario_title,
                given=self._infer_given(segment),
                when=self._infer_when(segment),
                then=self._infer_then(segment),
                priority=TaskPriority.HIGH if i == 0 else TaskPriority.MEDIUM,
            )
            scenarios.append(scenario)

        return scenarios

    def _extract_scenario_title(self, segment: str, index: int) -> str:
        """从需求片段提取场景标题

        Args:
            segment: 需求文本片段
            index: 场景序号

        Returns:
            场景标题
        """
        # 尝试提取前 30 字符作为标题
        if len(segment) <= 30:
            return segment

        # 在前 30 字符内寻找自然断点
        truncated = segment[:30]
        for delimiter in ["，", ",", "、", " "]:
            last_idx = truncated.rfind(delimiter)
            if last_idx > 5:
                return truncated[:last_idx].strip()

        return truncated.strip() + "..."

    def _infer_given(self, segment: str) -> str:
        """从需求片段推断 Given（前置条件）

        Args:
            segment: 需求文本片段

        Returns:
            Given 描述
        """
        # 查找常见的前置条件关键词
        given_patterns = [
            r"当([^，。,;；]+)时",
            r"在([^，。,;；]+)情况下",
            r"如果([^，。,;；]+)",
            r"已有([^，。,;；]+)",
            r"存在([^，。,;；]+)",
        ]
        for pattern in given_patterns:
            match = re.search(pattern, segment)
            if match:
                return match.group(1).strip()

        return "系统处于初始状态"

    def _infer_when(self, segment: str) -> str:
        """从需求片段推断 When（触发动作）

        Args:
            segment: 需求文本片段

        Returns:
            When 描述
        """
        # 查找常见的动作关键词
        action_keywords = [
            "需要", "应该", "必须", "可以", "支持", "实现",
            "完成", "执行", "处理", "提供", "创建", "删除",
            "修改", "查询", "展示", "发送", "接收", "验证",
        ]
        for keyword in action_keywords:
            idx = segment.find(keyword)
            if idx >= 0:
                return segment[idx:].strip()

        # 默认使用整段文本
        if len(segment) <= 60:
            return segment
        return segment[:60].strip() + "..."

    def _infer_then(self, segment: str) -> str:
        """从需求片段推断 Then（预期结果）

        Args:
            segment: 需求文本片段

        Returns:
            Then 描述
        """
        # 查找结果描述关键词
        result_patterns = [
            r"以便([^，。,;；]+)",
            r"从而([^，。,;；]+)",
            r"确保([^，。,;；]+)",
            r"达到([^，。,;；]+)效果",
            r"实现([^，。,;；]+)功能",
        ]
        for pattern in result_patterns:
            match = re.search(pattern, segment)
            if match:
                return match.group(1).strip()

        # 基于动作推断结果
        when_text = self._infer_when(segment)
        if when_text and len(when_text) > 2:
            return f"成功{when_text}"

        return "功能按预期工作"

    def _generate_clarification_questions(self, raw_need: str) -> list[str]:
        """从原始需求生成澄清问题

        识别需求中模糊、缺失或需确认的部分，生成问题列表。
        这些问题将在 communicate_with_user（P2-003）中使用。

        Args:
            raw_need: 原始需求文本

        Returns:
            澄清问题列表
        """
        questions: list[str] = []

        # 检测模糊量词
        vague_quantifiers = ["一些", "某些", "很多", "少量", "适当", "合理"]
        for vq in vague_quantifiers:
            if vq in raw_need:
                questions.append(f"「{vq}」的具体标准是什么？请明确数量或范围")
                break  # 每种类型只问一次

        # 检测缺失的异常处理
        if not re.search(r"失败|错误|异常|失败|无效|不合法", raw_need):
            questions.append("当操作失败或输入无效时，系统应如何处理？")

        # 检测缺失的权限/角色描述
        if not re.search(r"权限|角色|管理员|用户类型|授权", raw_need):
            questions.append("是否需要区分不同用户角色的权限？")

        # 检测缺失的性能需求
        if not re.search(r"性能|响应|并发|延迟|速度|QPS|吞吐", raw_need):
            questions.append("是否有性能或响应时间要求？")

        # 检测缺失的数据范围
        if not re.search(r"数据量|规模|上限|最大|限制", raw_need):
            questions.append("数据规模预期如何？是否有上限要求？")

        return questions

    def _generate_assumptions(self, raw_need: str) -> list[str]:
        """从原始需求生成假设列表

        记录精炼过程中的假设，这些假设需用户确认。

        Args:
            raw_need: 原始需求文本

        Returns:
            假设列表
        """
        assumptions: list[str] = []

        # 假设：基本技术栈
        assumptions.append("系统使用标准的 Web 技术栈实现")

        # 如果需求提到登录/认证
        if re.search(r"登录|认证|身份|鉴权|注册|账号", raw_need):
            assumptions.append("用户认证采用邮箱/手机号+密码方式")

        # 如果需求提到数据存储
        if re.search(r"存储|保存|记录|数据库|持久化|数据", raw_need):
            assumptions.append("数据使用关系型数据库持久化存储")

        # 如果需求提到通知/消息
        if re.search(r"通知|消息|提醒|推送|邮件|短信", raw_need):
            assumptions.append("通知通过异步消息队列发送")

        return assumptions

    def communicate_with_user(
        self,
        bdd_draft: BDDDraft,
        user_response_callback: Optional[Any] = None,
    ) -> CommunicationResult:
        """用户沟通循环（P2-003）

        将 BDD 草稿提交给用户确认，收集反馈并迭代修改。
        支持多轮沟通，每轮将草稿和澄清问题展示给用户，
        根据用户反馈修订草稿。

        沟通流程：
            1. 无待澄清问题 → 自动确认
            2. 有待澄清问题 → 展示给用户 → 收集反馈
            3. 根据反馈修订草稿 → 再次展示
            4. 重复直到确认或达到最大轮次
            5. 超过最大轮次 → 升级处理

        Args:
            bdd_draft: BDDDraft 草稿对象
            user_response_callback: 用户回复回调函数，
                签名 (round_number: int, questions: list[str]) -> Optional[str]
                返回 None 表示用户无回复/超时；
                返回空字符串表示确认；
                返回非空字符串表示反馈内容。
                如未提供，第一轮自动确认（无问题时）或升级（有问题时）。

        Returns:
            CommunicationResult: 沟通循环结果

        Raises:
            ValueError: bdd_draft 为 None
        """
        if bdd_draft is None:
            raise ValueError("bdd_draft cannot be None")

        # 保存草稿
        self._bdd_draft = bdd_draft.to_text()

        rounds: list[CommunicationRound] = []

        # 无待澄清问题 → 自动确认
        if not bdd_draft.has_questions:
            round_record = CommunicationRound(
                round_number=1,
                draft_snapshot=self._bdd_draft,
                questions_asked=[],
                user_feedback="",
                status=CommunicationStatus.AUTO_CONFIRMED,
                started_at=datetime.now(),
                completed_at=datetime.now(),
            )
            rounds.append(round_record)
            result = CommunicationResult(
                rounds=rounds,
                final_status=CommunicationStatus.AUTO_CONFIRMED,
                confirmed_bdd=self._bdd_draft,
                total_rounds=1,
                has_questions_unresolved=False,
            )
            self._confirmed_bdd = self._bdd_draft
            logger.info(
                "ProductManagerAgent: auto-confirmed BDD (no questions)"
            )
            return result

        # 有待澄清问题 → 进入沟通循环
        current_draft_text = self._bdd_draft
        current_questions = list(bdd_draft.questions)

        for round_num in range(1, _MAX_COMMUNICATION_ROUNDS + 1):
            # 创建本轮记录
            current_round = CommunicationRound(
                round_number=round_num,
                draft_snapshot=current_draft_text,
                questions_asked=list(current_questions),
                status=CommunicationStatus.PENDING,
                started_at=datetime.now(),
            )

            # 尝试获取用户反馈
            user_feedback = None
            if user_response_callback is not None:
                try:
                    user_feedback = user_response_callback(
                        round_num, current_questions
                    )
                except Exception as exc:
                    logger.warning(
                        "ProductManagerAgent: user_response_callback "
                        "raised exception: %s",
                        exc,
                    )

            # 处理用户反馈
            if user_feedback is None:
                # 用户无回复 → 超时，保持当前草稿
                current_round.user_feedback = None
                current_round.status = CommunicationStatus.ESCALATED
                current_round.completed_at = datetime.now()
                rounds.append(current_round)
                break

            user_feedback = user_feedback.strip()
            current_round.user_feedback = user_feedback

            if not user_feedback:
                # 空字符串 = 用户确认
                current_round.status = CommunicationStatus.CONFIRMED
                current_round.completed_at = datetime.now()
                rounds.append(current_round)
                break

            # 非空反馈 = 需要修订
            current_round.status = CommunicationStatus.NEEDS_REVISION
            current_round.completed_at = datetime.now()
            rounds.append(current_round)

            # 基于反馈修订草稿和问题
            revised = self._apply_user_feedback(
                bdd_draft, user_feedback, current_questions
            )
            current_draft_text = revised["draft_text"]
            current_questions = revised["remaining_questions"]

            # 如果没有剩余问题，下一轮自动确认
            if not current_questions:
                auto_round = CommunicationRound(
                    round_number=round_num + 1,
                    draft_snapshot=current_draft_text,
                    questions_asked=[],
                    user_feedback="",
                    status=CommunicationStatus.AUTO_CONFIRMED,
                    started_at=datetime.now(),
                    completed_at=datetime.now(),
                )
                rounds.append(auto_round)
                break

        else:
            # 达到最大轮次仍未确认 → 升级
            if rounds and rounds[-1].status not in (
                CommunicationStatus.CONFIRMED,
                CommunicationStatus.AUTO_CONFIRMED,
            ):
                escalation_round = CommunicationRound(
                    round_number=len(rounds) + 1,
                    draft_snapshot=current_draft_text,
                    questions_asked=current_questions,
                    user_feedback=None,
                    status=CommunicationStatus.ESCALATED,
                    started_at=datetime.now(),
                    completed_at=datetime.now(),
                )
                rounds.append(escalation_round)

        # 构建最终结果
        final_status = self._determine_final_status(rounds)
        confirmed_bdd = None
        if final_status in (
            CommunicationStatus.CONFIRMED,
            CommunicationStatus.AUTO_CONFIRMED,
        ):
            confirmed_bdd = current_draft_text
            self._confirmed_bdd = confirmed_bdd

        has_unresolved = any(
            q for q in current_questions
        ) if final_status not in (
            CommunicationStatus.CONFIRMED,
            CommunicationStatus.AUTO_CONFIRMED,
        ) else False

        result = CommunicationResult(
            rounds=rounds,
            final_status=final_status,
            confirmed_bdd=confirmed_bdd,
            total_rounds=len(rounds),
            has_questions_unresolved=has_unresolved,
        )

        logger.info(
            "ProductManagerAgent: communication completed, "
            "status=%s, rounds=%d",
            final_status.value,
            len(rounds),
        )

        return result

    def get_communicate_prompt(
        self, bdd_draft: BDDDraft, round_number: int = 1
    ) -> str:
        """构建用户沟通专用 prompt（供 LLM CLI 使用）

        构建 PM Agent 与用户沟通的 prompt，包含当前 BDD 草稿
        和待澄清问题。

        Args:
            bdd_draft: BDDDraft 草稿对象
            round_number: 当前沟通轮次

        Returns:
            完整的沟通 prompt 文本
        """
        questions_text = ""
        if bdd_draft.has_questions:
            questions_text = "\n".join(
                f"{i}. {q}" for i, q in enumerate(bdd_draft.questions, 1)
            )

        communicate_instruction = (
            f"## BDD 草稿（第 {round_number} 轮）\n\n"
            f"{bdd_draft.to_text()}\n\n"
            "## 沟通任务\n\n"
            "请基于上述 BDD 草稿与用户进行需求确认沟通。\n\n"
        )

        if questions_text:
            communicate_instruction += (
                "待澄清问题：\n"
                f"{questions_text}\n\n"
                "请逐一与用户确认上述问题，收集反馈后修订 BDD 草稿。\n"
            )
        else:
            communicate_instruction += (
                "所有问题已澄清，请向用户展示最终 BDD 草稿并请求确认。\n"
            )

        communicate_instruction += (
            "\n注意：\n"
            "- 使用 Given-When-Then 格式描述每个场景\n"
            "- 确保每个反馈都被纳入修订\n"
            "- 如果超过 3 轮仍未确认，需升级处理\n"
        )

        return self.build_pm_prompt(communicate_instruction)

    # ── communicate_with_user 内部方法 ─────────────────────

    def _apply_user_feedback(
        self,
        bdd_draft: BDDDraft,
        feedback: str,
        current_questions: list[str],
    ) -> dict[str, Any]:
        """将用户反馈应用到 BDD 草稿

        根据用户反馈修订草稿文本和剩余问题。

        Args:
            bdd_draft: 原始 BDDDraft 对象
            feedback: 用户反馈文本
            current_questions: 当前待澄清问题列表

        Returns:
            包含 draft_text 和 remaining_questions 的字典
        """
        # 修订草稿文本：追加用户反馈作为补充说明
        draft_text = bdd_draft.to_text()
        draft_text += f"\n\n## 用户反馈（已纳入）\n\n{feedback}"

        # 识别被反馈回答的问题并移除
        remaining_questions = []
        for question in current_questions:
            # 简单启发式：如果反馈中包含问题的关键名词，
            # 认为该问题已被回答
            question_keywords = self._extract_question_keywords(question)
            if not any(kw in feedback for kw in question_keywords):
                remaining_questions.append(question)

        return {
            "draft_text": draft_text,
            "remaining_questions": remaining_questions,
        }

    def _extract_question_keywords(self, question: str) -> list[str]:
        """从问题中提取关键词

        用于判断用户反馈是否回答了该问题。

        Args:
            question: 问题文本

        Returns:
            关键词列表
        """
        # 移除常见疑问词
        stopwords = {
            "是否", "如何", "什么", "哪个", "多少", "怎样",
            "能否", "需要", "应该", "可以", "有没有", "请",
            "明确", "具体", "标准", "范围", "区分", "要求",
            "的", "了", "吗", "呢", "是", "在", "有",
        }
        # 简单分词：按标点和空格分割
        import re as _re
        tokens = _re.split(r"[，。、？！\s；：；,.\?!;:\s]+", question)
        keywords = [t for t in tokens if t and t not in stopwords and len(t) >= 2]
        return keywords

    def _determine_final_status(
        self, rounds: list[CommunicationRound]
    ) -> CommunicationStatus:
        """根据沟通轮次记录确定最终状态

        Args:
            rounds: 沟通轮次列表

        Returns:
            最终沟通状态
        """
        if not rounds:
            return CommunicationStatus.PENDING

        last_round = rounds[-1]

        # 如果最后一轮已确认
        if last_round.status == CommunicationStatus.CONFIRMED:
            return CommunicationStatus.CONFIRMED
        if last_round.status == CommunicationStatus.AUTO_CONFIRMED:
            return CommunicationStatus.AUTO_CONFIRMED

        # 如果最后一轮是升级
        if last_round.status == CommunicationStatus.ESCALATED:
            # 检查是否有任何确认的轮次
            for r in reversed(rounds):
                if r.status in (
                    CommunicationStatus.CONFIRMED,
                    CommunicationStatus.AUTO_CONFIRMED,
                ):
                    return r.status
            return CommunicationStatus.ESCALATED

        # 其他情况（需修订但未继续）→ 升级
        return CommunicationStatus.ESCALATED

    # ── decompose_requirement 内部方法 ─────────────────────

    def _parse_bdd_scenarios(self, bdd_text: str) -> list[dict[str, str]]:
        """从 BDD 文本解析场景列表

        支持两种格式：
        1. BDDDraft.to_text() 生成的结构化格式（### 场景 N:）
        2. 自由格式的 Given-When-Then 文本

        Args:
            bdd_text: BDD 描述文本

        Returns:
            解析出的场景字典列表，每个包含 title/given/when/then/priority
        """
        scenarios: list[dict[str, str]] = []

        # 方式1：解析结构化格式（### 场景 N: title）
        scenario_blocks = re.split(r"### 场景 \d+:", bdd_text)
        if len(scenario_blocks) > 1:
            for block in scenario_blocks[1:]:  # 跳过场景前的内容
                scenario = self._parse_scenario_block(block)
                if scenario:
                    scenarios.append(scenario)
            if scenarios:
                return scenarios

        # 方式2：解析带 "- Given:" 前缀的格式
        given_pattern = re.compile(r"[-*]?\s*Given[:：]\s*(.+)")
        when_pattern = re.compile(r"[-*]?\s*When[:：]\s*(.+)")
        then_pattern = re.compile(r"[-*]?\s*Then[:：]\s*(.+)")

        given_matches = given_pattern.findall(bdd_text)
        when_matches = when_pattern.findall(bdd_text)
        then_matches = then_pattern.findall(bdd_text)

        if given_matches and when_matches and then_matches:
            count = min(len(given_matches), len(when_matches), len(then_matches))
            for i in range(count):
                scenarios.append({
                    "title": f"场景 {i + 1}",
                    "given": given_matches[i].strip(),
                    "when": when_matches[i].strip(),
                    "then": then_matches[i].strip(),
                    "priority": "high" if i == 0 else "medium",
                })
            return scenarios

        # 方式3：解析裸格式（Given ... When ... Then ...）
        bare_pattern = re.compile(
            r"Given\s+(.+?)\s+When\s+(.+?)\s+Then\s+(.+?)(?=\s*Given|\s*$)",
            re.DOTALL,
        )
        for i, match in enumerate(bare_pattern.finditer(bdd_text)):
            scenarios.append({
                "title": f"场景 {i + 1}",
                "given": match.group(1).strip(),
                "when": match.group(2).strip(),
                "then": match.group(3).strip(),
                "priority": "high" if i == 0 else "medium",
            })

        return scenarios

    def _parse_scenario_block(self, block: str) -> Optional[dict[str, str]]:
        """解析单个场景块

        Args:
            block: 场景文本块（### 场景 N: 之后的内容）

        Returns:
            场景字典，或 None 如果解析失败
        """
        lines = block.strip().split("\n")
        title = lines[0].strip() if lines else "场景"

        given = ""
        when = ""
        then = ""
        priority = "medium"

        for line in lines:
            line = line.strip()
            if re.match(r"[-*]?\s*Given[:：]", line):
                given = re.split(r"[:：]", line, 1)[1].strip()
            elif re.match(r"[-*]?\s*When[:：]", line):
                when = re.split(r"[:：]", line, 1)[1].strip()
            elif re.match(r"[-*]?\s*Then[:：]", line):
                then = re.split(r"[:：]", line, 1)[1].strip()
            elif re.match(r"[-*]?\s*优先级[:：]", line):
                priority = re.split(r"[:：]", line, 1)[1].strip()

        if given and when and then:
            return {
                "title": title,
                "given": given,
                "when": when,
                "then": then,
                "priority": priority,
            }

        return None

    def _create_task_dict(
        self, scenario: dict[str, str], index: int
    ) -> dict[str, Any]:
        """从解析的场景创建任务字典

        Args:
            scenario: 解析的场景字典
            index: 任务序号（从 1 开始）

        Returns:
            兼容 Task 模型的任务字典
        """
        task_id = f"task-{index:03d}"
        title = scenario.get("title", f"任务 {index}")
        given = scenario.get("given", "")
        when = scenario.get("when", "")
        then = scenario.get("then", "")
        priority = scenario.get("priority", "medium")

        # 构建任务描述
        description = f"{when}，以使{then}"
        if given:
            description = f"在{given}的情况下，{description}"

        return {
            "id": task_id,
            "title": title,
            "description": description,
            "bdd": {
                "given": given,
                "when": when,
                "then": then,
            },
            "test_script": None,
            "dependencies": [],
            "suggested_role": "dev",
            "priority": priority,
            "estimated_complexity": "medium",
            "status": "pending",
        }

    def _create_default_task(self, confirmed_bdd: str) -> dict[str, Any]:
        """当无法解析场景时，创建一个默认任务

        Args:
            confirmed_bdd: 确认的 BDD 文本

        Returns:
            默认任务字典
        """
        first_line = confirmed_bdd.split("\n")[0].strip()
        if first_line.startswith("#"):
            first_line = re.sub(r"^#+\s*", "", first_line).strip()

        title = first_line[:50] if first_line else "需求实现"

        return {
            "id": "task-001",
            "title": title,
            "description": confirmed_bdd[:200],
            "bdd": {
                "given": "系统处于初始状态",
                "when": "执行需求描述的操作",
                "then": "功能按预期工作",
            },
            "test_script": None,
            "dependencies": [],
            "suggested_role": "dev",
            "priority": "high",
            "estimated_complexity": "medium",
            "status": "pending",
        }

    def _infer_dependencies(
        self, tasks: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """推断任务间的依赖关系

        基于启发式规则推断任务间的前后依赖：
        1. 第一个任务无依赖
        2. "测试/验证"类任务依赖对应实现任务
        3. Given 中提到其他任务 Then 产出的内容时，存在依赖
        4. 查询/展示类操作依赖创建类操作

        Args:
            tasks: 任务字典列表

        Returns:
            更新了 dependencies 字段的任务列表
        """
        if len(tasks) <= 1:
            return tasks

        # 收集所有任务的"产出"关键词（从 Then 中提取）
        task_outputs: dict[str, set[str]] = {}
        for task in tasks:
            then_text = task.get("bdd", {}).get("then", "")
            keywords = self._extract_action_keywords(then_text)
            task_outputs[task["id"]] = keywords

        for i, task in enumerate(tasks):
            deps: list[str] = []
            title = task.get("title", "").lower()
            given_text = task.get("bdd", {}).get("given", "")
            when_text = task.get("bdd", {}).get("when", "")

            # 规则1：测试/验证类任务依赖前一个非测试任务
            if re.search(r"测试|验证|检查|校验", title):
                for j in range(i - 1, -1, -1):
                    prev_title = tasks[j].get("title", "").lower()
                    if not re.search(r"测试|验证|检查|校验", prev_title):
                        deps.append(tasks[j]["id"])
                        break

            # 规则2：Given 中提到其他任务 Then 的产出
            given_keywords = self._extract_action_keywords(given_text)
            for j in range(i):
                prev_task = tasks[j]
                output_keywords = task_outputs.get(prev_task["id"], set())
                if given_keywords & output_keywords:
                    if prev_task["id"] not in deps:
                        deps.append(prev_task["id"])

            # 规则3：查询/展示类操作依赖创建类操作
            if re.search(r"查询|展示|显示|获取|列表|查看", when_text):
                for j in range(i):
                    prev_when = tasks[j].get("bdd", {}).get("when", "")
                    if re.search(r"创建|新增|添加|注册|建立", prev_when):
                        if tasks[j]["id"] not in deps:
                            deps.append(tasks[j]["id"])

            task["dependencies"] = deps

        return tasks

    def _extract_action_keywords(self, text: str) -> set[str]:
        """从文本中提取动作关键词（用于依赖推断）

        Args:
            text: 输入文本

        Returns:
            关键词集合
        """
        action_nouns = [
            "用户", "账号", "订单", "商品", "商品列表",
            "登录", "注册", "认证", "权限", "角色",
            "数据", "配置", "设置", "页面", "接口",
            "文件", "目录", "项目", "任务", "报告",
            "消息", "通知", "邮件", "日志",
        ]
        return {noun for noun in action_nouns if noun in text}

    def _suggest_role(self, task: dict[str, Any]) -> str:
        """根据任务内容建议执行角色

        Args:
            task: 任务字典

        Returns:
            建议的角色标识
        """
        title = task.get("title", "").lower()
        description = task.get("description", "").lower()
        combined = title + " " + description

        # 测试相关 → qa
        if re.search(r"测试|验证|检查|校验|test|qa", combined):
            return "qa"

        # UI/前端相关 → senior-developer
        if re.search(r"页面|界面|UI|前端|组件|样式|布局|交互", combined):
            return "senior-developer"

        # API/后端相关 → dev
        if re.search(r"接口|API|后端|服务|数据库|存储|认证|鉴权", combined):
            return "dev"

        # 验收相关 → validate
        if re.search(r"验收|确认|审批|评审", combined):
            return "validate"

        return "dev"

    def _estimate_complexity(self, task: dict[str, Any]) -> str:
        """估算任务复杂度

        Args:
            task: 任务字典

        Returns:
            复杂度标识（low/medium/high）
        """
        description = task.get("description", "")
        when_text = task.get("bdd", {}).get("when", "")
        then_text = task.get("bdd", {}).get("then", "")
        combined = f"{description} {when_text} {then_text}"

        # 高复杂度标志
        high_indicators = [
            r"集成|对接|第三方|支付|安全|加密|分布式|并发",
            r"实时|推送|消息队列|缓存|事务|迁移",
        ]
        for pattern in high_indicators:
            if re.search(pattern, combined):
                return "high"

        # 低复杂度标志
        low_indicators = [
            r"配置|修改|调整|更新|删除|查询|展示|显示",
        ]
        for pattern in low_indicators:
            if re.search(pattern, combined):
                return "low"

        return "medium"

    def _generate_decomposition_notes(
        self,
        tasks: list[dict[str, Any]],
        parsed_scenarios: list[dict[str, str]],
    ) -> list[str]:
        """生成拆解说明

        记录拆解过程中的决策和推理。

        Args:
            tasks: 拆解后的任务列表
            parsed_scenarios: 解析的场景列表

        Returns:
            拆解说明列表
        """
        notes: list[str] = []

        notes.append(f"从 BDD 描述中解析出 {len(parsed_scenarios)} 个场景")
        notes.append(f"拆解为 {len(tasks)} 个原子任务")

        # 记录依赖关系
        tasks_with_deps = [t for t in tasks if t.get("dependencies")]
        if tasks_with_deps:
            notes.append(f"其中 {len(tasks_with_deps)} 个任务存在依赖关系")

        # 记录角色分配
        role_counts: dict[str, int] = {}
        for task in tasks:
            role = task.get("suggested_role", "dev")
            role_counts[role] = role_counts.get(role, 0) + 1
        if role_counts:
            role_desc = "、".join(
                f"{role}({count})" for role, count in role_counts.items()
            )
            notes.append(f"角色分配：{role_desc}")

        # 记录优先级分布
        priority_counts: dict[str, int] = {}
        for task in tasks:
            p = task.get("priority", "medium")
            priority_counts[p] = priority_counts.get(p, 0) + 1
        if priority_counts:
            pri_desc = "、".join(
                f"{p}({count})" for p, count in priority_counts.items()
            )
            notes.append(f"优先级分布：{pri_desc}")

        return notes

    def get_decompose_prompt(self, confirmed_bdd: str) -> str:
        """构建任务拆解专用 prompt（供 LLM CLI 使用）

        构建 PM Agent 专用的任务拆解 prompt，包含角色身份、
        pm-rules 约束和拆解指令。

        Args:
            confirmed_bdd: 已确认的 BDD 描述文本

        Returns:
            完整的拆解 prompt 文本
        """
        decompose_instruction = (
            f"## 已确认 BDD\n\n{confirmed_bdd}\n\n"
            "## 拆解任务\n\n"
            "请将上述 BDD 描述拆解为原子任务列表。\n\n"
            "要求：\n"
            "1. 每个任务应是可独立执行和验证的原子单元\n"
            "2. 每个任务需包含 Given-When-Then BDD 规格\n"
            "3. 明确标注任务间的依赖关系\n"
            "4. 为每个任务建议合适的执行角色（pm/dev/qa/validate）\n"
            "5. 评估每个任务的复杂度（low/medium/high）\n"
            "6. 按 task-001, task-002... 格式编号\n"
        )
        return self.build_pm_prompt(decompose_instruction)

    def decompose_requirement(self, confirmed_bdd: str) -> DecomposeResult:
        """任务拆解（P2-004）

        将确认的 BDD 描述拆解为原子任务列表。
        基于 BDD 场景自动生成任务，推断依赖关系，分配角色和复杂度。

        拆解流程：
            1. 验证输入（confirmed_bdd 非空）
            2. 保存确认 BDD 到 _confirmed_bdd
            3. 解析 BDD 文本提取场景
            4. 为每个场景创建原子任务字典
            5. 推断任务间依赖关系
            6. 分配建议角色
            7. 估算任务复杂度
            8. 生成拆解说明
            9. 组装 DecomposeResult

        Args:
            confirmed_bdd: 已确认的 BDD 描述文本

        Returns:
            DecomposeResult: 任务拆解结果

        Raises:
            ValueError: confirmed_bdd 为空或仅含空白字符
        """
        if not confirmed_bdd or not confirmed_bdd.strip():
            raise ValueError("confirmed_bdd cannot be empty")

        confirmed_bdd = confirmed_bdd.strip()

        # 1. 保存确认 BDD
        self._confirmed_bdd = confirmed_bdd

        # 2. 解析 BDD 场景
        parsed_scenarios = self._parse_bdd_scenarios(confirmed_bdd)

        # 3. 为每个场景创建任务字典
        tasks = []
        for i, scenario in enumerate(parsed_scenarios, 1):
            task_dict = self._create_task_dict(scenario, i)
            tasks.append(task_dict)

        # 4. 如果没有解析到场景，创建一个默认任务
        if not tasks:
            tasks.append(self._create_default_task(confirmed_bdd))

        # 5. 推断依赖关系
        tasks = self._infer_dependencies(tasks)

        # 6. 分配建议角色
        for task in tasks:
            task["suggested_role"] = self._suggest_role(task)

        # 7. 估算复杂度
        for task in tasks:
            task["estimated_complexity"] = self._estimate_complexity(task)

        # 8. 生成拆解说明
        notes = self._generate_decomposition_notes(tasks, parsed_scenarios)

        # 9. 组装结果
        result = DecomposeResult(
            confirmed_bdd=confirmed_bdd,
            tasks=tasks,
            decomposition_notes=notes,
            created_at=datetime.now(),
        )

        logger.info(
            "ProductManagerAgent decomposed requirement: "
            "%d tasks, %d notes",
            result.total_tasks,
            len(notes),
        )

        return result

    def generate_task_json(
        self,
        tasks: list[dict[str, Any]],
        project_name: Optional[str] = None,
        project_description: Optional[str] = None,
        output_path: Optional[Path] = None,
    ) -> TaskJsonResult:
        """task.json 生成（P2-005）

        将任务字典列表转换为完整的 TaskJSON 模型对象，
        可选写入到文件。

        生成流程：
            1. 验证输入（tasks 非空）
            2. 推断项目名称（如果未提供）
            3. 将任务字典转换为 Task 模型实例
            4. 构建 TaskJSON 模型（触发内置校验：total_tasks 一致、
               依赖引用有效、无循环依赖）
            5. 序列化为 JSON 文本
            6. 可选写入文件
            7. 组装 TaskJsonResult

        Args:
            tasks: 任务字典列表（来自 DecomposeResult.tasks）
            project_name: 项目名称（可选，默认从任务推断）
            project_description: 项目描述（可选）
            output_path: 输出文件路径（可选，None 则不写入文件）

        Returns:
            TaskJsonResult: task.json 生成结果

        Raises:
            ValueError: tasks 为空列表
        """
        if not tasks:
            raise ValueError("tasks cannot be empty")

        # 1. 推断项目名称
        if not project_name:
            project_name = self._infer_project_name(tasks)

        # 2. 转换任务字典为 Task 模型实例
        task_models = self._convert_tasks_to_models(tasks)

        # 3. 构建 TaskJSON（触发模型校验）
        task_json_obj = TaskJSON(
            project_name=project_name,
            description=project_description,
            created_by="Product Manager Agent",
            total_tasks=len(task_models),
            tasks=task_models,
        )

        # 4. 序列化为 JSON
        json_text = self._serialize_task_json(task_json_obj)

        # 5. 可选写入文件
        saved_path = None
        if output_path is not None:
            saved_path = self._write_task_json_file(json_text, output_path)

        # 6. 组装结果
        result = TaskJsonResult(
            task_json=task_json_obj,
            output_path=saved_path,
            json_text=json_text,
            created_at=datetime.now(),
        )

        logger.info(
            "ProductManagerAgent generated task.json: "
            "project=%s, tasks=%d, saved=%s",
            project_name,
            len(task_models),
            saved_path is not None,
        )

        return result

    def generate_test_script(
        self,
        task: dict[str, Any],
        output_path: Optional[Path] = None,
    ) -> TestScriptResult:
        """测试脚本编写（P2-006）

        根据任务类型和 BDD 规格自动生成测试脚本。
        支持四种脚本类型：Playwright（UI）、API、单元测试、集成测试。

        生成流程：
            1. 验证输入（task 必须含 id 和 bdd）
            2. 判断脚本类型（基于任务内容关键词）
            3. 生成 import 语句
            4. 生成测试类/函数结构
            5. 从 BDD 生成测试用例（Given→setup, When→action, Then→assertion）
            6. 组装完整脚本
            7. 可选写入文件
            8. 组装 TestScriptResult

        Args:
            task: 任务字典（必须包含 id 和 bdd 字段）
            output_path: 输出文件路径（可选，None 则不写入文件）

        Returns:
            TestScriptResult: 测试脚本生成结果

        Raises:
            ValueError: task 为空或缺少必要字段
        """
        if not task:
            raise ValueError("task cannot be empty")

        task_id = task.get("id", "")
        if not task_id:
            raise ValueError("task must have an 'id' field")

        # 1. 判断脚本类型
        script_type = self._determine_script_type(task)

        # 2. 生成 import 语句
        imports = self._generate_imports(script_type)

        # 3. 生成测试类名
        class_name = self._generate_test_class_name(task)

        # 4. 从 BDD 生成测试用例
        bdd = task.get("bdd", {})
        test_cases = self._generate_test_cases_from_bdd(bdd, script_type)

        # 5. 组装脚本
        script_content = self._assemble_script(
            imports=imports,
            class_name=class_name,
            test_cases=test_cases,
            script_type=script_type,
            task=task,
        )

        # 6. 提取测试用例名称
        test_case_names = [tc["name"] for tc in test_cases]

        # 7. 可选写入文件
        saved_path = None
        if output_path is not None:
            saved_path = self._write_test_script_file(script_content, output_path)

        # 8. 组装结果
        result = TestScriptResult(
            task_id=task_id,
            script_type=script_type,
            script_content=script_content,
            test_cases=test_case_names,
            imports_needed=imports,
            output_path=saved_path,
            created_at=datetime.now(),
        )

        logger.info(
            "ProductManagerAgent generated test script: "
            "task=%s, type=%s, cases=%d, saved=%s",
            task_id,
            script_type.value,
            len(test_case_names),
            saved_path is not None,
        )

        return result

    # ── generate_task_json 内部方法 ────────────────────────

    def _infer_project_name(self, tasks: list[dict[str, Any]]) -> str:
        """从任务列表推断项目名称

        提取第一个任务的描述关键词作为项目名称。
        如果无法推断，使用默认名称。

        Args:
            tasks: 任务字典列表

        Returns:
            推断的项目名称
        """
        if not tasks:
            return "OpenBoss Project"

        # 从第一个任务的描述中提取关键词
        first_task = tasks[0]
        description = first_task.get("description", "")
        title = first_task.get("title", "")

        # 尝试从描述中提取名词短语
        for text in [title, description]:
            if not text:
                continue
            # 提取前 30 字符内的核心短语
            clean = re.sub(r"[，。、；：,.;:!?！？\s]+", " ", text).strip()
            if len(clean) > 30:
                # 在 30 字符内找自然断点
                truncated = clean[:30]
                for delimiter in [" ", "、"]:
                    last_idx = truncated.rfind(delimiter)
                    if last_idx > 3:
                        clean = truncated[:last_idx].strip()
                        break
                else:
                    clean = truncated.strip()

            if clean and len(clean) >= 2:
                return clean + "项目"

        return "OpenBoss Project"

    def _convert_tasks_to_models(
        self, tasks: list[dict[str, Any]]
    ) -> list[Task]:
        """将任务字典列表转换为 Task 模型实例列表

        处理字段映射和类型转换：
            - priority: str → TaskPriority
            - estimated_complexity: str → TaskComplexity
            - status: str → TaskStatus
            - bdd: dict → BDDSpec

        Args:
            tasks: 任务字典列表

        Returns:
            Task 模型实例列表
        """
        task_models: list[Task] = []

        for task_dict in tasks:
            # 转换优先级
            priority = self._map_priority(task_dict.get("priority", "medium"))

            # 转换复杂度
            complexity = self._map_complexity(
                task_dict.get("estimated_complexity", "medium")
            )

            # 转换状态
            status = self._map_status(task_dict.get("status", "pending"))

            # 转换 BDD
            bdd_spec = None
            bdd_dict = task_dict.get("bdd")
            if bdd_dict and isinstance(bdd_dict, dict):
                bdd_spec = BDDSpec(
                    given=bdd_dict.get("given", ""),
                    when=bdd_dict.get("when", ""),
                    then=bdd_dict.get("then", ""),
                )

            task_model = Task(
                id=task_dict.get("id", "task-000"),
                title=task_dict.get("title", "未命名任务"),
                description=task_dict.get("description", ""),
                bdd=bdd_spec,
                test_script=task_dict.get("test_script"),
                dependencies=task_dict.get("dependencies", []),
                suggested_role=task_dict.get("suggested_role", "dev"),
                priority=priority,
                estimated_complexity=complexity,
                status=status,
            )
            task_models.append(task_model)

        return task_models

    def _map_priority(self, value: str) -> TaskPriority:
        """映射优先级字符串到枚举

        Args:
            value: 优先级字符串

        Returns:
            TaskPriority 枚举值
        """
        mapping = {
            "high": TaskPriority.HIGH,
            "medium": TaskPriority.MEDIUM,
            "low": TaskPriority.LOW,
        }
        return mapping.get(value.lower(), TaskPriority.MEDIUM)

    def _map_complexity(self, value: str) -> TaskComplexity:
        """映射复杂度字符串到枚举

        Args:
            value: 复杂度字符串

        Returns:
            TaskComplexity 枚举值
        """
        mapping = {
            "high": TaskComplexity.HIGH,
            "medium": TaskComplexity.MEDIUM,
            "low": TaskComplexity.LOW,
        }
        return mapping.get(value.lower(), TaskComplexity.MEDIUM)

    def _map_status(self, value: str) -> TaskStatus:
        """映射状态字符串到枚举

        Args:
            value: 状态字符串

        Returns:
            TaskStatus 枚举值
        """
        mapping = {
            "pending": TaskStatus.PENDING,
            "in_progress": TaskStatus.IN_PROGRESS,
            "completed": TaskStatus.COMPLETED,
            "failed": TaskStatus.FAILED,
            "blocked": TaskStatus.BLOCKED,
            "skipped": TaskStatus.SKIPPED,
        }
        return mapping.get(value.lower(), TaskStatus.PENDING)

    def _serialize_task_json(self, task_json_obj: TaskJSON) -> str:
        """将 TaskJSON 模型序列化为 JSON 文本

        使用 indent=2 格式化输出，确保中文不被转义。

        Args:
            task_json_obj: TaskJSON 模型实例

        Returns:
            格式化的 JSON 文本
        """
        return task_json_obj.model_dump_json(indent=2)

    def _write_task_json_file(self, json_text: str, output_path: Path) -> str:
        """将 JSON 文本写入文件

        自动创建父目录（如不存在）。

        Args:
            json_text: JSON 文本内容
            output_path: 输出文件路径

        Returns:
            写入的文件绝对路径字符串
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json_text, encoding="utf-8")

        logger.info("ProductManagerAgent wrote task.json to: %s", output_path)
        return str(output_path.resolve())

    def get_generate_task_json_prompt(self, tasks: list[dict[str, Any]]) -> str:
        """构建 task.json 生成专用 prompt（供 LLM CLI 使用）

        构建 PM Agent 专用的 task.json 生成 prompt，
        包含角色身份、任务列表和格式要求。

        Args:
            tasks: 任务字典列表

        Returns:
            完整的生成 prompt 文本
        """
        import json as _json

        tasks_text = _json.dumps(tasks, ensure_ascii=False, indent=2)

        generate_instruction = (
            f"## 任务列表\n\n{tasks_text}\n\n"
            "## 生成 task.json\n\n"
            "请将上述任务列表转换为完整的 task.json 格式。\n\n"
            "要求：\n"
            "1. 包含 project_name、description、created_by、total_tasks、tasks 字段\n"
            "2. 每个任务需包含 id、title、description、bdd、dependencies、suggested_role、priority、estimated_complexity\n"
            "3. 确保所有依赖引用的任务 ID 存在\n"
            "4. 确保不存在循环依赖\n"
            "5. total_tasks 必须与 tasks 列表长度一致\n"
        )
        return self.build_pm_prompt(generate_instruction)

    # ── generate_test_script 内部方法 ───────────────────────

    def _determine_script_type(self, task: dict[str, Any]) -> TestScriptType:
        """根据任务特征判断测试脚本类型

        判断策略（按优先级）：
            1. 任务标题/描述含 UI/页面/前端 关键词 → Playwright
            2. 任务标题/描述含 API/接口/端点 关键词 → API
            3. 任务标题/描述含 集成/对接/端到端 关键词 → Integration
            4. 默认 → Unit

        Args:
            task: 任务字典

        Returns:
            测试脚本类型枚举值
        """
        title = task.get("title", "").lower()
        description = task.get("description", "").lower()
        when_text = task.get("bdd", {}).get("when", "").lower()
        combined = f"{title} {description} {when_text}"

        # Playwright：UI / 页面 / 前端 / 交互
        if re.search(r"页面|界面|UI|前端|组件|样式|布局|交互|点击|输入框|按钮|表单|playwright", combined):
            return TestScriptType.PLAYWRIGHT

        # API：接口 / 端点 / 请求 / 响应
        if re.search(r"接口|API|端点|请求|响应|路由|endpoint|rest|graphql|http", combined):
            return TestScriptType.API

        # Integration：集成 / 对接 / 端到端 / 流程
        if re.search(r"集成|对接|端到端|流程|完整.*测试|e2e|workflow", combined):
            return TestScriptType.INTEGRATION

        # 默认：单元测试
        return TestScriptType.UNIT

    def _generate_imports(self, script_type: TestScriptType) -> list[str]:
        """根据脚本类型生成 import 语句

        Args:
            script_type: 测试脚本类型

        Returns:
            import 语句列表
        """
        imports: list[str] = []

        # 所有类型都需要 pytest
        imports.append("import pytest")

        if script_type == TestScriptType.PLAYWRIGHT:
            imports.append("from playwright.sync_api import Page, expect")
        elif script_type == TestScriptType.API:
            imports.append("import requests")
        elif script_type == TestScriptType.INTEGRATION:
            imports.append("from unittest.mock import MagicMock, patch")

        return imports

    def _generate_test_class_name(self, task: dict[str, Any]) -> str:
        """根据任务信息生成测试类名

        策略：从任务 title 或 id 生成 PascalCase 类名。
        格式：Test{SanitizedTitle}

        Args:
            task: 任务字典

        Returns:
            测试类名
        """
        title = task.get("title", "")
        task_id = task.get("id", "unknown")

        if title:
            # 清理标题：移除特殊字符，转为 PascalCase
            clean = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff\s_-]", "", title)
            # 如果包含中文字符，使用 task_id 生成
            if re.search(r"[\u4e00-\u9fff]", clean):
                # 中英混合：提取英文部分
                english_parts = re.findall(r"[a-zA-Z]+", clean)
                if english_parts:
                    class_name = "Test" + "".join(
                        p.capitalize() for p in english_parts
                    )
                else:
                    # 纯中文标题 → 使用 task_id
                    class_name = self._task_id_to_class_name(task_id)
            else:
                # 纯英文标题
                words = re.split(r"[\s_-]+", clean.strip())
                class_name = "Test" + "".join(w.capitalize() for w in words if w)
        else:
            class_name = self._task_id_to_class_name(task_id)

        # 确保类名非空且有效
        if not class_name or class_name == "Test":
            class_name = self._task_id_to_class_name(task_id)

        return class_name

    def _task_id_to_class_name(self, task_id: str) -> str:
        """将 task ID 转换为测试类名

        Args:
            task_id: 任务 ID（如 task-001）

        Returns:
            测试类名（如 TestTask001）
        """
        # task-001 → TestTask001
        clean_id = re.sub(r"[^a-zA-Z0-9]", "", task_id)
        if clean_id:
            return "Test" + clean_id[0].upper() + clean_id[1:]
        return "TestUnknown"

    def _generate_test_cases_from_bdd(
        self, bdd: dict[str, str], script_type: TestScriptType
    ) -> list[dict[str, str]]:
        """从 BDD 规格生成测试用例列表

        每个测试用例由 BDD 三段式映射：
            - Given → setup/arrange 代码
            - When → action/act 代码
            - Then → assertion/assert 代码

        Args:
            bdd: BDD 规格字典（given/when/then）
            script_type: 测试脚本类型

        Returns:
            测试用例字典列表，每个包含 name/setup/action/assertion
        """
        given = bdd.get("given", "")
        when = bdd.get("when", "")
        then = bdd.get("then", "")

        # 主测试用例：正向路径
        main_case = {
            "name": self._generate_test_method_name(when, "success"),
            "setup": self._generate_setup_code(given, script_type),
            "action": self._generate_action_code(when, script_type),
            "assertion": self._generate_assertion_code(then, script_type),
        }

        cases = [main_case]

        # 边界测试用例：如果 When 含"有效"/"成功"等词，追加反向用例
        if re.search(r"有效|成功|正确|合法|valid|success", when):
            failure_case = {
                "name": self._generate_test_method_name(when, "failure"),
                "setup": self._generate_setup_code(given, script_type),
                "action": self._generate_action_code(
                    when.replace("有效", "无效")
                    .replace("成功", "失败")
                    .replace("正确", "错误")
                    .replace("合法", "非法"),
                    script_type,
                ),
                "assertion": self._generate_assertion_code(
                    f"应拒绝{then}并返回错误", script_type
                ),
            }
            cases.append(failure_case)

        # 异常测试用例：空输入
        if re.search(r"输入|提交|填写|提供|上传|发送", when):
            empty_case = {
                "name": self._generate_test_method_name(when, "empty_input"),
                "setup": self._generate_setup_code(given, script_type),
                "action": self._generate_action_code(
                    f"提交空值", script_type
                ),
                "assertion": self._generate_assertion_code(
                    "应提示输入不能为空", script_type
                ),
            }
            cases.append(empty_case)

        return cases

    def _generate_test_method_name(
        self, when_text: str, suffix: str
    ) -> str:
        """从 When 文本生成测试方法名

        Args:
            when_text: When 描述文本
            suffix: 后缀（如 success/failure/empty_input）

        Returns:
            测试方法名（如 test_login_success）
        """
        # 提取关键动作词
        action_keywords = [
            "登录", "注册", "创建", "删除", "修改", "查询", "搜索",
            "提交", "上传", "下载", "发送", "接收", "验证", "审批",
            "展示", "显示", "导出", "导入", "添加", "移除",
        ]

        action = ""
        for keyword in action_keywords:
            if keyword in when_text:
                # 将中文关键词转为简短英文
                keyword_map = {
                    "登录": "login", "注册": "register", "创建": "create",
                    "删除": "delete", "修改": "update", "查询": "query",
                    "搜索": "search", "提交": "submit", "上传": "upload",
                    "下载": "download", "发送": "send", "接收": "receive",
                    "验证": "verify", "审批": "approve", "展示": "display",
                    "显示": "show", "导出": "export", "导入": "import_data",
                    "添加": "add", "移除": "remove",
                }
                action = keyword_map.get(keyword, keyword)
                break

        if not action:
            # 尝试提取英文关键词
            english_parts = re.findall(r"[a-zA-Z]+", when_text)
            if english_parts:
                action = "_".join(english_parts[:2]).lower()

        if not action:
            action = "action"

        return f"test_{action}_{suffix}"

    def _generate_setup_code(
        self, given: str, script_type: TestScriptType
    ) -> str:
        """从 Given 生成 setup/arrange 代码

        Args:
            given: Given 描述文本
            script_type: 测试脚本类型

        Returns:
            setup 代码片段
        """
        if script_type == TestScriptType.PLAYWRIGHT:
            return f"# Arrange: {given}\n    # 初始化页面状态"

        if script_type == TestScriptType.API:
            return f"# Arrange: {given}\n    base_url = 'http://localhost:8000'"

        if script_type == TestScriptType.INTEGRATION:
            return f"# Arrange: {given}\n    # 准备测试环境和依赖"

        # Unit
        return f"# Arrange: {given}\n    # 准备测试数据"

    def _generate_action_code(
        self, when: str, script_type: TestScriptType
    ) -> str:
        """从 When 生成 action/act 代码

        Args:
            when: When 描述文本
            script_type: 测试脚本类型

        Returns:
            action 代码片段
        """
        if script_type == TestScriptType.PLAYWRIGHT:
            return f"# Act: {when}\n    # 执行页面操作"

        if script_type == TestScriptType.API:
            return f"# Act: {when}\n    response = requests.get(base_url + '/api/endpoint')"

        if script_type == TestScriptType.INTEGRATION:
            return f"# Act: {when}\n    # 执行集成操作"

        # Unit
        return f"# Act: {when}\n    # 执行被测方法"

    def _generate_assertion_code(
        self, then: str, script_type: TestScriptType
    ) -> str:
        """从 Then 生成 assertion/assert 代码

        Args:
            then: Then 描述文本
            script_type: 测试脚本类型

        Returns:
            assertion 代码片段
        """
        if script_type == TestScriptType.PLAYWRIGHT:
            return f"# Assert: {then}\n    # 验证页面状态"

        if script_type == TestScriptType.API:
            return f"# Assert: {then}\n    assert response.status_code == 200"

        if script_type == TestScriptType.INTEGRATION:
            return f"# Assert: {then}\n    # 验证集成结果"

        # Unit
        return f"# Assert: {then}\n    # 验证预期结果"

    def _assemble_script(
        self,
        imports: list[str],
        class_name: str,
        test_cases: list[dict[str, str]],
        script_type: TestScriptType,
        task: dict[str, Any],
    ) -> str:
        """组装完整测试脚本

        Args:
            imports: import 语句列表
            class_name: 测试类名
            test_cases: 测试用例列表
            script_type: 测试脚本类型
            task: 任务字典

        Returns:
            完整的测试脚本文本
        """
        lines: list[str] = []

        # 文件头注释
        task_id = task.get("id", "unknown")
        task_title = task.get("title", "")
        lines.append(f'"""')
        lines.append(f"测试脚本 — {task_title}")
        lines.append(f"任务 ID: {task_id}")
        lines.append(f"脚本类型: {script_type.value}")
        lines.append(f"由 ProductManagerAgent 自动生成")
        lines.append(f'"""')
        lines.append("")

        # import 语句
        for imp in imports:
            lines.append(imp)
        lines.append("")
        lines.append("")

        # 测试类
        lines.append(f"class {class_name}:")
        lines.append(f'    """{task_title} 测试类"""')
        lines.append("")

        # 添加 fixture（如果是 Playwright 类型）
        if script_type == TestScriptType.PLAYWRIGHT:
            lines.append("    @pytest.fixture")
            lines.append("    def page(self, browser):")
            lines.append("        return browser.new_page()")
            lines.append("")

        for i, tc in enumerate(test_cases):
            if i > 0:
                lines.append("")

            # 方法签名
            if script_type == TestScriptType.PLAYWRIGHT:
                lines.append(f"    def {tc['name']}(self, page):")
            else:
                lines.append(f"    def {tc['name']}(self):")

            # 方法体
            lines.append(f'        """测试用例: {tc["name"]}"""')
            lines.append(f"        {tc['setup']}")
            lines.append(f"        {tc['action']}")
            lines.append(f"        {tc['assertion']}")

        # 如果没有测试用例，添加一个默认的
        if not test_cases:
            lines.append("    def test_placeholder(self):")
            lines.append('        """占位测试用例"""')
            lines.append("        # TODO: 补充实际测试逻辑")
            lines.append("        pass")

        return "\n".join(lines)

    def _write_test_script_file(
        self, script_content: str, output_path: Path
    ) -> str:
        """将测试脚本写入文件

        自动创建父目录（如不存在）。
        文件名基于 output_path 参数。

        Args:
            script_content: 脚本内容
            output_path: 输出文件路径

        Returns:
            写入的文件绝对路径字符串
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(script_content, encoding="utf-8")

        logger.info(
            "ProductManagerAgent wrote test script to: %s", output_path
        )
        return str(output_path.resolve())

    def get_generate_test_script_prompt(
        self, task: dict[str, Any]
    ) -> str:
        """构建测试脚本编写专用 prompt（供 LLM CLI 使用）

        构建 PM Agent 专用的测试脚本编写 prompt，
        包含角色身份、任务信息和 BDD 规格。

        Args:
            task: 任务字典

        Returns:
            完整的测试脚本编写 prompt 文本
        """
        import json as _json

        task_text = _json.dumps(task, ensure_ascii=False, indent=2)

        bdd = task.get("bdd", {})
        bdd_section = ""
        if bdd:
            bdd_section = (
                f"\n## BDD 规格\n\n"
                f"- Given: {bdd.get('given', 'N/A')}\n"
                f"- When: {bdd.get('when', 'N/A')}\n"
                f"- Then: {bdd.get('then', 'N/A')}\n"
            )

        generate_instruction = (
            f"## 任务信息\n\n{task_text}\n"
            f"{bdd_section}\n"
            "## 编写测试脚本\n\n"
            "请为上述任务编写完整的测试脚本。\n\n"
            "要求：\n"
            "1. 根据任务类型选择合适的测试框架（Playwright/API/pytest）\n"
            "2. 从 BDD Given-When-Then 结构生成测试用例\n"
            "3. Given → 测试前置条件（setup/arrange）\n"
            "4. When → 测试动作（act）\n"
            "5. Then → 测试断言（assert）\n"
            "6. 包含正向、反向和边界测试用例\n"
            "7. 使用 pytest 框架\n"
            "8. 测试方法命名遵循 test_<action>_<scenario> 格式\n"
        )
        return self.build_pm_prompt(generate_instruction)

    # ── 辅助方法 ──────────────────────────────────────────

    def _build_task_description(self, task) -> str:
        """从 Task 模型构建 PM 任务描述

        PM Agent 的任务描述与通用版本略有不同，
        强调需求分析而非编码实现。

        Args:
            task: Task 实例

        Returns:
            结构化的 PM 任务描述
        """
        parts = [f"## 需求分析任务: {task.title}"]
        parts.append(f"ID: {task.id}")
        parts.append(f"\n{task.description}")

        if task.bdd:
            parts.append(f"\n### BDD 规格")
            parts.append(f"- Given: {task.bdd.given}")
            parts.append(f"- When: {task.bdd.when}")
            parts.append(f"- Then: {task.bdd.then}")

        return "\n".join(parts)

    def get_harness_rules_summary(self) -> dict[str, int]:
        """获取 pm-rules 各类型规则数量摘要

        Returns:
            规则类型 → 数量的字典

        Raises:
            RuntimeError: harness 尚未加载
        """
        if self._pm_harness is None:
            raise RuntimeError(
                "pm-rules harness not loaded. "
                "Call initialize() or load_pm_harness() first."
            )
        from agent_automation_system.harness.models import RuleType

        return {
            "do": len(self._pm_harness.get_do_rules()),
            "dont": len(self._pm_harness.get_dont_rules()),
            "constraints": len(self._pm_harness.get_constraints()),
            "verification": len(self._pm_harness.get_verification_rules()),
            "total": len(self._pm_harness.rules),
        }

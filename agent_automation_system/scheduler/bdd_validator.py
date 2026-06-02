"""
BDDValidator — BDD 行为验证器（P2-022）

验证任务执行结果是否符合 BDD (Given-When-Then) 规范预期。
用作文本匹配引擎，判断 AI 生成/实现的输出是否与预设的 BDD 场景一致。

核心方法：
    - verify(task_result, bdd_spec) → BDDValidationResult
      逐项验证 Given / When / Then 三段是否在结果文本中出现。
    - verify_given / verify_when / verify_then
      各自独立验证单一段落的匹配情况。

设计原则（P2-022 §2.4 BDD + TDD 闭环）：
    - given 对应任务执行的前置条件 → 验证结果中是否提及
    - when  对应操作触发             → 验证结果中是否描述了操作
    - then  对应预期结果             → 验证结果中是否反映了正确产出
    - 匹配策略：多关键词模糊匹配 + 否定词排除

使用方式：
    validator = BDDValidator()
    result = validator.verify("登录接口返回 token: abc123", bdd_spec)
    print(result.passed, result.details)
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class BDDValidationResult:
    """BDD 验证结果

    Attributes:
        passed: 整体是否通过
        given_passed / when_passed / then_passed: 各段是否通过
        given_detail / when_detail / then_detail: 各段详情
        score: 通过率 (0.0 ~ 1.0)
        summary: 可读摘要
    """

    passed: bool = False
    given_passed: bool = False
    when_passed: bool = False
    then_passed: bool = False
    given_detail: str = ""
    when_detail: str = ""
    then_detail: str = ""
    score: float = 0.0
    summary: str = ""

    @property
    def all_passed(self) -> bool:
        return self.given_passed and self.when_passed and self.then_passed

    @property
    def partial_score(self) -> tuple[int, int]:
        passed = sum([self.given_passed, self.when_passed, self.then_passed])
        return passed, 3


class BDDValidator:
    """BDD 行为验证器

    通过文本匹配判断任务执行结果是否符合 BDD 预期。
    应用于 TDD 闭环中的 verify 步骤：确保代码实现确实满足需求规格。
    """

    # 中文否定词（前置否定）
    _NEGATORS = [
        "没有", "未", "不", "无", "尚未", "不会", "无法",
        "不能", "不可", "禁止", "拒绝", "失败", "错误",
    ]

    # 默认最低匹配分数阈值（每个字段）
    DEFAULT_MIN_SCORE = 0.3

    def __init__(self, min_score: float = DEFAULT_MIN_SCORE) -> None:
        """创建 BDDValidator

        Args:
            min_score: 单段匹配最低分数阈值（0.0 ~ 1.0），默认 0.3
        """
        if not 0.0 <= min_score <= 1.0:
            raise ValueError(f"min_score must be 0.0~1.0, got {min_score}")
        self._min_score = min_score

    @property
    def min_score(self) -> float:
        return self._min_score

    def verify(
        self,
        task_result: Optional[str],
        bdd_spec,
    ) -> BDDValidationResult:
        """验证执行结果是否符合 BDD 规范

        对 BDD 的 Given / When / Then 三个维度分别验证，
        每个维度使用多关键词策略匹配 task_result 文本。

        Args:
            task_result: 任务执行结果文本（实现输出、日志、测试输出等）
            bdd_spec: BDDSpec 实例（含 given/when/then 字段），
                      或 dict（含 given/when/then keys）

        Returns:
            BDDValidationResult 包含各维度通过状态和详情

        Raises:
            ValueError: bdd_spec 为 None 或无效类型
        """
        if bdd_spec is None:
            raise ValueError("bdd_spec cannot be None")

        # 统一提取 given / when / then
        given = self._extract_field(bdd_spec, "given")
        when = self._extract_field(bdd_spec, "when")
        then = self._extract_field(bdd_spec, "then")

        result_text = task_result if task_result else ""

        # 分别验证
        given_passed, given_detail = self.verify_given(result_text, given)
        when_passed, when_detail = self.verify_when(result_text, when)
        then_passed, then_detail = self.verify_then(result_text, then)

        passed_count = sum([given_passed, when_passed, then_passed])
        score = round(passed_count / 3, 2)
        passed = given_passed and when_passed and then_passed

        return BDDValidationResult(
            passed=passed,
            given_passed=given_passed,
            when_passed=when_passed,
            then_passed=then_passed,
            given_detail=given_detail,
            when_detail=when_detail,
            then_detail=then_detail,
            score=score,
            summary=f"{passed_count}/3 passed — "
            f"Given={'✓' if given_passed else '✗'} "
            f"When={'✓' if when_passed else '✗'} "
            f"Then={'✓' if then_passed else '✗'}",
        )

    def verify_given(self, result_text: str, given: str) -> tuple[bool, str]:
        """验证前置条件（Given）是否在结果中体现

        Args:
            result_text: 执行结果文本
            given: BDD Given 描述

        Returns:
            (是否通过, 详情字符串)
        """
        return self._verify_segment(result_text, given, "Given")

    def verify_when(self, result_text: str, when: str) -> tuple[bool, str]:
        """验证操作触发（When）是否在结果中体现

        Args:
            result_text: 执行结果文本
            when: BDD When 描述

        Returns:
            (是否通过, 详情字符串)
        """
        return self._verify_segment(result_text, when, "When")

    def verify_then(self, result_text: str, then: str) -> tuple[bool, str]:
        """验证预期结果（Then）是否在结果中体现

        Args:
            result_text: 执行结果文本
            then: BDD Then 描述

        Returns:
            (是否通过, 详情字符串)
        """
        return self._verify_segment(result_text, then, "Then")

    # ─── 内部方法 ────────────────────────────────────

    def _verify_segment(
        self, result_text: str, expectation: str, label: str
    ) -> tuple[bool, str]:
        """通用段验证：多关键词匹配 + 否定排除"""
        if not expectation or not expectation.strip():
            return False, f"{label}: empty BDD field"

        if not result_text:
            return False, f"{label}: no result text to verify against"

        # 提取关键词（2 字以上的中文词 + 英文词）
        keywords = self._extract_keywords(expectation)
        if not keywords:
            return True, f"{label}: no keywords extracted (pass by default)"

        text_lower = result_text.lower()

        matched = 0
        matched_words: list[str] = []
        mismatched_words: list[str] = []

        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in text_lower:
                # 检查否定上下文
                if self._is_negated(text_lower, kw_lower):
                    mismatched_words.append(kw)
                else:
                    matched += 1
                    matched_words.append(kw)
            else:
                mismatched_words.append(kw)

        total = len(keywords)
        score = matched / total if total > 0 else 0.0
        passed = score >= self._min_score

        detail = (
            f"{label}: {matched}/{total} keywords matched "
            f"(score={score:.2f}, threshold={self._min_score})"
        )
        if matched_words:
            detail += f" — matched: {matched_words[:5]}"
        if mismatched_words:
            detail += f" — missing: {mismatched_words[:5]}"

        return passed, detail

    @staticmethod
    def _extract_keywords(text: str) -> list[str]:
        """从 BDD 描述中提取关键词

        策略：
        - 中文：使用 2-gram 滑动窗口分词（"用户登录系统" → ["用户","户登","登录","录系","系统"]）
        - 英文：匹配 2+ 字母的单词
        - 合并去重，保留首次出现顺序
        """
        keywords: list[str] = []
        seen: set[str] = set()

        # 1. 中文 2-gram
        chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
        for i in range(len(chinese_chars) - 1):
            bigram = chinese_chars[i] + chinese_chars[i + 1]
            if bigram not in seen:
                seen.add(bigram)
                keywords.append(bigram)

        # 2. 英文单词（2+ 字母）
        for w in re.findall(r"[a-zA-Z]{2,}", text):
            wl = w.lower()
            if wl not in seen:
                seen.add(wl)
                keywords.append(wl)

        return keywords

    @staticmethod
    def _is_negated(text: str, keyword: str) -> bool:
        """检查关键词是否在否定上下文中出现"""
        idx = text.find(keyword)
        if idx <= 0:
            return False
        # 检查关键词前 10 个字符是否有否定词
        prefix = text[max(0, idx - 10):idx]
        return any(neg in prefix for neg in BDDValidator._NEGATORS)

    @staticmethod
    def _extract_field(bdd_spec, field_name: str) -> str:
        """从 BDDSpec 实例或 dict 中提取字段值"""
        # dict 类型优先检测（避免 getattr 回退到 class attr）
        if isinstance(bdd_spec, dict):
            return bdd_spec.get(field_name, "")
        # Pydantic model / dataclass / 普通对象
        try:
            return getattr(bdd_spec, field_name, "")
        except Exception:
            raise ValueError(
                f"bdd_spec must be BDDSpec or dict with '{field_name}' field"
            )

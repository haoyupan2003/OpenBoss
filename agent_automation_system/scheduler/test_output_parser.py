"""
parse_test_output — pytest 输出解析器

解析 pytest 标准输出，提取结构化测试结果。
"""

import re
from dataclasses import dataclass, field


@dataclass
class TestOutput:
    __test__ = False
    raw_output: str = ""
    passed: bool = False
    total: int = 0
    passed_count: int = 0
    failed_count: int = 0
    error_count: int = 0
    skipped_count: int = 0
    failed_test_names: list[str] = field(default_factory=list)
    error_test_names: list[str] = field(default_factory=list)
    error_details: list[str] = field(default_factory=list)
    summary: str = ""

    @property
    def success(self) -> bool:
        return self.passed and self.failed_count == 0 and self.error_count == 0


def parse_test_output(output: str) -> TestOutput:
    if not output:
        return TestOutput(raw_output="")

    result = TestOutput(raw_output=output)

    # 解析计数行: "X passed, Y failed, Z error, W skipped"
    m = re.search(r"(\d+)\s+passed", output)
    result.passed_count = int(m.group(1)) if m else 0
    m = re.search(r"(\d+)\s+failed", output)
    result.failed_count = int(m.group(1)) if m else 0
    m = re.search(r"(\d+)\s+error", output)
    result.error_count = int(m.group(1)) if m else 0
    m = re.search(r"(\d+)\s+skipped", output)
    result.skipped_count = int(m.group(1)) if m else 0

    result.total = (result.passed_count + result.failed_count +
                    result.error_count + result.skipped_count)
    result.passed = result.failed_count == 0 and result.error_count == 0

    # 解析失败测试名: "FAILED tests/test_a.py::test_fail"
    for m in re.finditer(r"FAILED\s+\S+::(\S+)", output):
        result.failed_test_names.append(m.group(1))

    # 解析错误测试名: "ERROR tests/test_b.py::test_error"
    for m in re.finditer(r"ERROR\s+\S+::(\S+)", output):
        result.error_test_names.append(m.group(1))

    # 解析错误详情: 在 "ERRORS" 或 "FAILURES" 节中提取
    # 先找错误/失败节
    sections = re.split(r"={3,}\s+(?:ERRORS|FAILURES)\s+={3,}", output)
    if len(sections) > 1:
        for sec in sections[1:]:
            # 提取到下一个分割线之前
            end = re.search(r"={3,}", sec)
            block = sec[:end.start()] if end else sec
            # 找测试名和异常行
            m = re.search(r"_{3,}\s+(\S+)", block)
            if not m:
                m = re.search(r"^(\S+)\s+_", block, re.MULTILINE)
            # 找异常类型
            exc = re.findall(r"(?:RuntimeError|ValueError|AssertionError|TypeError|Exception|Error)[: ].*", block)
            if exc:
                result.error_details.append(exc[0].strip())

    # 提取最后一行的摘要（结果行: "X passed in Y.Zs"）
    m = re.search(r"(\d+ (?:passed|failed).*?in\s+[\d.]+s)", output)
    if m:
        result.summary = m.group(1)

    return result

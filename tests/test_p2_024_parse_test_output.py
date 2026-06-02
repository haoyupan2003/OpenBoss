"""
P2-024 测试 — parse_test_output 测试输出解析器

测试内容：
- 解析 passed/failed/error/skipped 计数
- 提取失败测试名称
- 提取错误详情
- 空输出/非标准输出处理
- 多模块输出解析
"""

import pytest

from agent_automation_system.scheduler.test_output_parser import (
    TestOutput,
    parse_test_output,
)


SAMPLE_ALL_PASS = """============================= test session starts ==============================
collecting ... collected 5 items

tests/test_a.py::test_one PASSED                                              [ 20%]
tests/test_a.py::test_two PASSED                                              [ 40%]
tests/test_b.py::test_three PASSED                                            [ 60%]
tests/test_c.py::test_four PASSED                                             [ 80%]
tests/test_c.py::test_five PASSED                                             [100%]

============================== 5 passed in 0.42s ==============================
"""

SAMPLE_WITH_FAILURES = """============================= test session starts ==============================
collecting ... collected 4 items

tests/test_a.py::test_pass PASSED                                             [ 25%]
tests/test_a.py::test_fail FAILED                                             [ 50%]
tests/test_b.py::test_error ERROR                                              [ 75%]
tests/test_c.py::test_skip SKIPPED                                            [100%]

==================================== ERRORS ====================================
________________________ ERROR at setup of test_error _________________________
    def test_error():
>       raise RuntimeError("boom")
E       RuntimeError: boom
=================================== FAILURES ===================================
_______________________________ test_fail _____________________________________
    def test_fail():
>       assert False
E       assert False
=========================== short test summary info ============================
FAILED tests/test_a.py::test_fail
ERROR tests/test_b.py::test_error
SKIPPED [1] tests/test_c.py::test_skip
================== 1 passed, 1 failed, 1 error, 1 skipped in 0.68s ============
"""

SAMPLE_SHORT = """============================= test session starts ==============================
tests/test_d.py::test_ok PASSED
tests/test_d.py::test_bad FAILED
======================== 1 passed, 1 failed in 0.12s ==========================
"""


class TestParseTestOutputCounts:
    """计数解析"""

    def test_all_pass_counts(self):
        r = parse_test_output(SAMPLE_ALL_PASS)
        assert r.passed_count == 5
        assert r.failed_count == 0
        assert r.error_count == 0
        assert r.skipped_count == 0
        assert r.total == 5

    def test_mixed_counts(self):
        r = parse_test_output(SAMPLE_WITH_FAILURES)
        assert r.passed_count == 1
        assert r.failed_count == 1
        assert r.error_count == 1
        assert r.skipped_count == 1
        assert r.total == 4

    def test_small_counts(self):
        r = parse_test_output(SAMPLE_SHORT)
        assert r.passed_count == 1
        assert r.failed_count == 1
        assert r.total == 2


class TestParseTestOutputStatus:
    """passed/success 状态"""

    def test_all_pass_success_true(self):
        r = parse_test_output(SAMPLE_ALL_PASS)
        assert r.passed is True
        assert r.success is True

    def test_failures_success_false(self):
        r = parse_test_output(SAMPLE_WITH_FAILURES)
        assert r.passed is False
        assert r.success is False


class TestParseTestOutputFailures:
    """失败详情"""

    def test_failed_test_names(self):
        r = parse_test_output(SAMPLE_WITH_FAILURES)
        assert "test_fail" in r.failed_test_names
        assert len(r.failed_test_names) == 1

    def test_error_test_names(self):
        r = parse_test_output(SAMPLE_WITH_FAILURES)
        assert "test_error" in r.error_test_names
        assert len(r.error_test_names) == 1

    def test_error_messages_extracted(self):
        r = parse_test_output(SAMPLE_WITH_FAILURES)
        assert len(r.error_details) >= 1
        assert any("RuntimeError" in e for e in r.error_details)


class TestParseTestOutputEdgeCases:
    """边界"""

    def test_empty_string(self):
        r = parse_test_output("")
        assert r.total == 0
        assert r.passed is False

    def test_no_test_output(self):
        r = parse_test_output("random text without test results")
        assert r.total == 0

    def test_no_collection(self):
        output = "ERROR: file not found"
        r = parse_test_output(output)
        assert r.total == 0

    def test_summary_line_preserved(self):
        r = parse_test_output(SAMPLE_ALL_PASS)
        assert "5 passed" in r.summary

    def test_raw_output_stored(self):
        r = parse_test_output(SAMPLE_SHORT)
        assert r.raw_output == SAMPLE_SHORT

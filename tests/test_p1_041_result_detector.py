"""
P1-041 集成验证 — ResultDetector 执行结果检测

验证项：
1. ExecutionStatus 枚举
2. DetectionResult 数据类
3. ResultDetector 构造参数（默认/自定义/None tmux_manager 校验）
4. detect() 完成检测（默认模式 + 自定义模式）
5. detect() 失败检测（默认模式 + 排除模式）
6. detect() 运行中检测
7. detect() 未知状态（无法获取输出）
8. detect_from_output() 直接输出分析
9. 快捷方法 is_completed / is_failed / is_terminal
10. register_completion_pattern / register_failure_pattern 模式注册
11. 只读属性副本
12. 空输出处理
"""

import re
import unittest
from unittest.mock import MagicMock

from agent_automation_system.cli.result_detector import (
    _DEFAULT_COMPLETION_PATTERNS,
    _DEFAULT_EXCLUSION_PATTERNS,
    _DEFAULT_FAILURE_PATTERNS,
    DetectionResult,
    ExecutionStatus,
    ResultDetector,
)


class TestExecutionStatus(unittest.TestCase):
    """验证 ExecutionStatus 枚举"""

    def test_status_values(self):
        """所有枚举值正确"""
        self.assertEqual(ExecutionStatus.COMPLETED.value, "completed")
        self.assertEqual(ExecutionStatus.FAILED.value, "failed")
        self.assertEqual(ExecutionStatus.RUNNING.value, "running")
        self.assertEqual(ExecutionStatus.UNKNOWN.value, "unknown")

    def test_status_count(self):
        """恰好 4 个状态"""
        self.assertEqual(len(ExecutionStatus), 4)

    def test_status_is_string(self):
        """枚举值是字符串"""
        self.assertIsInstance(ExecutionStatus.COMPLETED, str)


class TestDetectionResult(unittest.TestCase):
    """验证 DetectionResult 数据类"""

    def test_default_values(self):
        """默认值为 None / 0"""
        result = DetectionResult(status=ExecutionStatus.RUNNING)
        self.assertEqual(result.status, ExecutionStatus.RUNNING)
        self.assertIsNone(result.matched_pattern)
        self.assertIsNone(result.matched_line)
        self.assertEqual(result.output_lines, 0)
        self.assertIsNone(result.raw_output)

    def test_all_fields(self):
        """所有字段正确赋值"""
        result = DetectionResult(
            status=ExecutionStatus.COMPLETED,
            matched_pattern="claude>",
            matched_line="claude>",
            output_lines=42,
            raw_output="some output\nclaude>",
        )
        self.assertEqual(result.status, ExecutionStatus.COMPLETED)
        self.assertEqual(result.matched_pattern, "claude>")
        self.assertEqual(result.matched_line, "claude>")
        self.assertEqual(result.output_lines, 42)
        self.assertEqual(result.raw_output, "some output\nclaude>")

    def test_is_terminal_completed(self):
        """COMPLETED 是终态"""
        result = DetectionResult(status=ExecutionStatus.COMPLETED)
        self.assertTrue(result.is_terminal)

    def test_is_terminal_failed(self):
        """FAILED 是终态"""
        result = DetectionResult(status=ExecutionStatus.FAILED)
        self.assertTrue(result.is_terminal)

    def test_is_terminal_running(self):
        """RUNNING 不是终态"""
        result = DetectionResult(status=ExecutionStatus.RUNNING)
        self.assertFalse(result.is_terminal)

    def test_is_terminal_unknown(self):
        """UNKNOWN 不是终态"""
        result = DetectionResult(status=ExecutionStatus.UNKNOWN)
        self.assertFalse(result.is_terminal)

    def test_repr(self):
        """repr 格式正确"""
        result = DetectionResult(
            status=ExecutionStatus.COMPLETED,
            matched_pattern="test",
            output_lines=5,
        )
        r = repr(result)
        self.assertIn("completed", r)
        self.assertIn("test", r)


class TestResultDetectorConstructor(unittest.TestCase):
    """验证 ResultDetector 构造"""

    def test_none_tmux_manager(self):
        """None tmux_manager 抛 ValueError"""
        with self.assertRaises(ValueError) as ctx:
            ResultDetector(tmux_manager=None)
        self.assertIn("cannot be None", str(ctx.exception))

    def test_default_params(self):
        """默认参数正确"""
        tmux = MagicMock()
        detector = ResultDetector(tmux_manager=tmux)
        self.assertIs(detector.tmux_manager, tmux)
        self.assertEqual(
            detector.completion_patterns, _DEFAULT_COMPLETION_PATTERNS
        )
        self.assertEqual(
            detector.failure_patterns, _DEFAULT_FAILURE_PATTERNS
        )
        self.assertEqual(
            detector.exclusion_patterns, _DEFAULT_EXCLUSION_PATTERNS
        )
        self.assertEqual(detector.history_lines, 100)

    def test_custom_patterns(self):
        """自定义模式正确设置"""
        tmux = MagicMock()
        detector = ResultDetector(
            tmux_manager=tmux,
            completion_patterns=[r"自定义完成"],
            failure_patterns=[r"自定义失败"],
            exclusion_patterns=[r"自定义排除"],
            history_lines=50,
        )
        self.assertEqual(detector.completion_patterns, [r"自定义完成"])
        self.assertEqual(detector.failure_patterns, [r"自定义失败"])
        self.assertEqual(detector.exclusion_patterns, [r"自定义排除"])
        self.assertEqual(detector.history_lines, 50)

    def test_readonly_properties(self):
        """属性返回只读副本（修改不影响内部）"""
        tmux = MagicMock()
        detector = ResultDetector(tmux_manager=tmux)
        patterns = detector.completion_patterns
        patterns.append("hacked")
        self.assertNotIn("hacked", detector.completion_patterns)


class TestDetectCompleted(unittest.TestCase):
    """验证完成检测"""

    def test_detect_claude_prompt(self):
        """检测 claude> 提示符 → COMPLETED"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = [
            "Some output here",
            "claude>",
        ]
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect("boss", "agent_001")
        self.assertEqual(result.status, ExecutionStatus.COMPLETED)
        self.assertIsNotNone(result.matched_pattern)
        self.assertEqual(result.output_lines, 2)

    def test_detect_claude_space_prompt(self):
        """检测 'claude >' 提示符 → COMPLETED"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = [
            "Working...",
            "claude >",
        ]
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect("boss", "agent_001")
        self.assertEqual(result.status, ExecutionStatus.COMPLETED)

    def test_detect_chinese_completed(self):
        """检测中文完成标志 → COMPLETED"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = [
            "执行中...",
            "任务已完成。",
        ]
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect("boss", "agent_001")
        self.assertEqual(result.status, ExecutionStatus.COMPLETED)

    def test_detect_english_task_completed(self):
        """检测英文 Task completed → COMPLETED"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = [
            "Running tests...",
            "Task completed successfully",
        ]
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect("boss", "agent_001")
        self.assertEqual(result.status, ExecutionStatus.COMPLETED)

    def test_detect_custom_completion_pattern(self):
        """自定义完成模式生效"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = [
            "my custom finish signal",
        ]
        detector = ResultDetector(
            tmux_manager=tmux,
            completion_patterns=[r"custom finish signal"],
        )
        result = detector.detect("boss", "agent_001")
        self.assertEqual(result.status, ExecutionStatus.COMPLETED)
        self.assertEqual(result.matched_pattern, "custom finish signal")


class TestDetectFailed(unittest.TestCase):
    """验证失败检测"""

    def test_detect_error(self):
        """检测 Error: → FAILED"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = [
            "Some output",
            "Error: something went wrong",
        ]
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect("boss", "agent_001")
        self.assertEqual(result.status, ExecutionStatus.FAILED)
        self.assertIsNotNone(result.matched_pattern)

    def test_detect_fatal(self):
        """检测 Fatal: → FAILED"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = [
            "Processing...",
            "Fatal: unrecoverable error",
        ]
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect("boss", "agent_001")
        self.assertEqual(result.status, ExecutionStatus.FAILED)

    def test_detect_exception(self):
        """检测 Exception: → FAILED"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = [
            "Running...",
            "Exception: null pointer",
        ]
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect("boss", "agent_001")
        self.assertEqual(result.status, ExecutionStatus.FAILED)

    def test_detect_segfault(self):
        """检测 Segmentation Fault → FAILED"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = [
            "Segmentation fault (core dumped)",
        ]
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect("boss", "agent_001")
        self.assertEqual(result.status, ExecutionStatus.FAILED)

    def test_detect_permission_denied(self):
        """检测 Permission denied → FAILED"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = [
            "Permission denied: access forbidden",
        ]
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect("boss", "agent_001")
        self.assertEqual(result.status, ExecutionStatus.FAILED)

    def test_failure_priority_over_completion(self):
        """失败优先于完成检测"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = [
            "Error: something failed",
            "claude>",
        ]
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect("boss", "agent_001")
        self.assertEqual(result.status, ExecutionStatus.FAILED)

    def test_exclusion_pattern(self):
        """排除模式命中时不判定失败"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = [
            "error: message format --help",
        ]
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect("boss", "agent_001")
        # 被 exclusion 排除，不算失败
        self.assertNotEqual(result.status, ExecutionStatus.FAILED)

    def test_custom_failure_pattern(self):
        """自定义失败模式生效"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = [
            "my custom error trigger",
        ]
        detector = ResultDetector(
            tmux_manager=tmux,
            failure_patterns=[r"custom error trigger"],
        )
        result = detector.detect("boss", "agent_001")
        self.assertEqual(result.status, ExecutionStatus.FAILED)


class TestDetectRunning(unittest.TestCase):
    """验证运行中检测"""

    def test_running_no_match(self):
        """无完成/失败标志 → RUNNING"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = [
            "Processing data...",
            "Still working on it...",
            "Almost there...",
        ]
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect("boss", "agent_001")
        self.assertEqual(result.status, ExecutionStatus.RUNNING)

    def test_empty_output(self):
        """空输出 → RUNNING"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = ["", "  ", ""]
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect("boss", "agent_001")
        self.assertEqual(result.status, ExecutionStatus.RUNNING)


class TestDetectUnknown(unittest.TestCase):
    """验证未知状态"""

    def test_capture_failure(self):
        """无法捕获输出 → UNKNOWN"""
        tmux = MagicMock()
        tmux.capture_pane_history.side_effect = Exception("tmux error")
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect("boss", "agent_001")
        self.assertEqual(result.status, ExecutionStatus.UNKNOWN)
        self.assertEqual(result.output_lines, 0)

    def test_none_output(self):
        """捕获返回 None → UNKNOWN"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = None
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect("boss", "agent_001")
        self.assertEqual(result.status, ExecutionStatus.UNKNOWN)


class TestDetectFromOutput(unittest.TestCase):
    """验证 detect_from_output 直接输出分析"""

    def test_completed_from_output(self):
        """直接输出分析 → COMPLETED"""
        tmux = MagicMock()
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect_from_output([
            "Some output",
            "claude>",
        ])
        self.assertEqual(result.status, ExecutionStatus.COMPLETED)

    def test_failed_from_output(self):
        """直接输出分析 → FAILED"""
        tmux = MagicMock()
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect_from_output([
            "Error: crash detected",
        ])
        self.assertEqual(result.status, ExecutionStatus.FAILED)

    def test_running_from_output(self):
        """直接输出分析 → RUNNING"""
        tmux = MagicMock()
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect_from_output([
            "Still processing...",
        ])
        self.assertEqual(result.status, ExecutionStatus.RUNNING)

    def test_none_input(self):
        """None 输入 → UNKNOWN"""
        tmux = MagicMock()
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect_from_output(None)
        self.assertEqual(result.status, ExecutionStatus.UNKNOWN)


class TestShortcutMethods(unittest.TestCase):
    """验证快捷方法"""

    def test_is_completed(self):
        """is_completed 正确"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = ["claude>"]
        detector = ResultDetector(tmux_manager=tmux)
        self.assertTrue(detector.is_completed("boss", "w1"))

    def test_is_completed_false(self):
        """is_completed 返回 False"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = ["working..."]
        detector = ResultDetector(tmux_manager=tmux)
        self.assertFalse(detector.is_completed("boss", "w1"))

    def test_is_failed(self):
        """is_failed 正确"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = ["Error: fail"]
        detector = ResultDetector(tmux_manager=tmux)
        self.assertTrue(detector.is_failed("boss", "w1"))

    def test_is_terminal_completed(self):
        """is_terminal 对 COMPLETED 返回 True"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = ["claude>"]
        detector = ResultDetector(tmux_manager=tmux)
        self.assertTrue(detector.is_terminal("boss", "w1"))

    def test_is_terminal_failed(self):
        """is_terminal 对 FAILED 返回 True"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = ["Error: fail"]
        detector = ResultDetector(tmux_manager=tmux)
        self.assertTrue(detector.is_terminal("boss", "w1"))

    def test_is_terminal_running(self):
        """is_terminal 对 RUNNING 返回 False"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = ["still going"]
        detector = ResultDetector(tmux_manager=tmux)
        self.assertFalse(detector.is_terminal("boss", "w1"))


class TestPatternRegistration(unittest.TestCase):
    """验证模式注册"""

    def test_register_completion_pattern(self):
        """注册自定义完成模式"""
        tmux = MagicMock()
        detector = ResultDetector(tmux_manager=tmux)
        initial_count = len(detector.completion_patterns)
        detector.register_completion_pattern(r"✅ 任务完成")
        self.assertEqual(len(detector.completion_patterns), initial_count + 1)
        self.assertIn(r"✅ 任务完成", detector.completion_patterns)

    def test_register_failure_pattern(self):
        """注册自定义失败模式"""
        tmux = MagicMock()
        detector = ResultDetector(tmux_manager=tmux)
        initial_count = len(detector.failure_patterns)
        detector.register_failure_pattern(r"💥 崩溃")
        self.assertEqual(len(detector.failure_patterns), initial_count + 1)
        self.assertIn(r"💥 崩溃", detector.failure_patterns)

    def test_register_empty_pattern(self):
        """注册空模式抛 ValueError"""
        tmux = MagicMock()
        detector = ResultDetector(tmux_manager=tmux)
        with self.assertRaises(ValueError):
            detector.register_completion_pattern("")
        with self.assertRaises(ValueError):
            detector.register_failure_pattern("   ")

    def test_register_invalid_regex(self):
        """注册非法正则抛 ValueError"""
        tmux = MagicMock()
        detector = ResultDetector(tmux_manager=tmux)
        with self.assertRaises(ValueError):
            detector.register_completion_pattern(r"[invalid")
        with self.assertRaises(ValueError):
            detector.register_failure_pattern(r"(?P<name")

    def test_registered_pattern_works(self):
        """注册的模式可以生效检测"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = [
            "✅ 任务完成",
        ]
        detector = ResultDetector(
            tmux_manager=tmux,
            completion_patterns=[],  # 清空默认模式，只使用注册的模式
        )
        detector.register_completion_pattern(r"✅ 任务完成")
        result = detector.detect("boss", "w1")
        self.assertEqual(result.status, ExecutionStatus.COMPLETED)
        self.assertEqual(result.matched_pattern, r"✅ 任务完成")


class TestEdgeCases(unittest.TestCase):
    """验证边界情况"""

    def test_earliest_match_in_latest_lines(self):
        """从末尾搜索，最新输出优先匹配"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = [
            "Error: early error",  # 旧的错误
            "claude>",             # 新的完成
        ]
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect("boss", "w1")
        # 失败优先于完成（检测优先级），且 Error 在前
        # 但搜索从末尾开始，先看到 claude>
        # 不过失败优先级高于完成，先检测失败模式
        # Error: early error 匹配失败模式，即使从末尾搜索
        # 实际上从末尾搜索时先看到 "claude>"，但失败检测优先
        # 失败模式搜索从末尾开始，"claude>" 不匹配失败模式
        # 然后 "Error: early error" 匹配失败模式
        self.assertEqual(result.status, ExecutionStatus.FAILED)

    def test_large_output(self):
        """大量输出正常处理"""
        tmux = MagicMock()
        lines = [f"Processing line {i}..." for i in range(200)]
        lines.append("claude>")
        tmux.capture_pane_history.return_value = lines
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect("boss", "w1")
        self.assertEqual(result.status, ExecutionStatus.COMPLETED)
        self.assertEqual(result.output_lines, 201)

    def test_capture_pane_history_args(self):
        """detect 正确传递 history_lines 参数"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = ["claude>"]
        detector = ResultDetector(tmux_manager=tmux, history_lines=50)
        detector.detect("boss", "w1")
        tmux.capture_pane_history.assert_called_once_with("boss", "w1", lines=50)

    def test_chinese_error_detection(self):
        """中文错误关键词检测"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = [
            "Error: 中文错误信息",
        ]
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect("boss", "w1")
        self.assertEqual(result.status, ExecutionStatus.FAILED)

    def test_mixed_case_error(self):
        """大小写不敏感的错误检测"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = [
            "ERROR: critical issue",
        ]
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect("boss", "w1")
        self.assertEqual(result.status, ExecutionStatus.FAILED)

    def test_raw_output_in_result(self):
        """检测结果包含原始输出"""
        tmux = MagicMock()
        tmux.capture_pane_history.return_value = [
            "line 1",
            "claude>",
        ]
        detector = ResultDetector(tmux_manager=tmux)
        result = detector.detect("boss", "w1")
        self.assertIn("line 1", result.raw_output)
        self.assertIn("claude>", result.raw_output)


if __name__ == "__main__":
    unittest.main()

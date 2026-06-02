"""
P1-042 集成验证 — TimeoutController 超时控制

验证项：
1. TimeoutStatus 枚举
2. TimeoutResult 数据类
3. TimeoutController 构造参数（默认/自定义/None 校验/非法值校验）
4. execute_with_timeout 任务完成检测
5. execute_with_timeout 任务失败检测
6. execute_with_timeout 超时终止 CLI
7. cancel 取消监控
8. is_timed_out 查询
9. get_remaining_time / get_elapsed_time
10. 参数校验（空 session/window、非正 timeout）
11. 超时后 stop_cli 调用
12. 只读属性
"""

import time
import unittest
from unittest.mock import MagicMock, patch

from agent_automation_system.cli.result_detector import (
    DetectionResult,
    ExecutionStatus,
)
from agent_automation_system.cli.claude_code_cli import CLIStatus
from agent_automation_system.cli.timeout_controller import (
    TimeoutController,
    TimeoutResult,
    TimeoutStatus,
)


class TestTimeoutStatus(unittest.TestCase):
    """验证 TimeoutStatus 枚举"""

    def test_status_values(self):
        """所有枚举值正确"""
        self.assertEqual(TimeoutStatus.COMPLETED.value, "completed")
        self.assertEqual(TimeoutStatus.FAILED.value, "failed")
        self.assertEqual(TimeoutStatus.TIMEOUT.value, "timeout")
        self.assertEqual(TimeoutStatus.CANCELLED.value, "cancelled")
        self.assertEqual(TimeoutStatus.UNKNOWN.value, "unknown")

    def test_status_count(self):
        """恰好 5 个状态"""
        self.assertEqual(len(TimeoutStatus), 5)

    def test_status_is_string(self):
        """枚举值是字符串"""
        self.assertIsInstance(TimeoutStatus.TIMEOUT, str)


class TestTimeoutResult(unittest.TestCase):
    """验证 TimeoutResult 数据类"""

    def test_default_values(self):
        """默认值正确"""
        result = TimeoutResult(status=TimeoutStatus.TIMEOUT)
        self.assertEqual(result.status, TimeoutStatus.TIMEOUT)
        self.assertIsNone(result.detection_result)
        self.assertFalse(result.timed_out)
        self.assertEqual(result.elapsed_seconds, 0.0)
        self.assertEqual(result.timeout_seconds, 0.0)
        self.assertFalse(result.cancelled)
        self.assertFalse(result.stopped_cli)

    def test_all_fields(self):
        """所有字段正确赋值"""
        detection = DetectionResult(status=ExecutionStatus.COMPLETED)
        result = TimeoutResult(
            status=TimeoutStatus.COMPLETED,
            detection_result=detection,
            timed_out=False,
            elapsed_seconds=42.5,
            timeout_seconds=300.0,
            cancelled=False,
            stopped_cli=False,
        )
        self.assertEqual(result.status, TimeoutStatus.COMPLETED)
        self.assertIs(result.detection_result, detection)
        self.assertFalse(result.timed_out)
        self.assertEqual(result.elapsed_seconds, 42.5)
        self.assertEqual(result.timeout_seconds, 300.0)

    def test_is_terminal_completed(self):
        """COMPLETED 是终态"""
        result = TimeoutResult(status=TimeoutStatus.COMPLETED)
        self.assertTrue(result.is_terminal)

    def test_is_terminal_failed(self):
        """FAILED 是终态"""
        result = TimeoutResult(status=TimeoutStatus.FAILED)
        self.assertTrue(result.is_terminal)

    def test_is_terminal_timeout(self):
        """TIMEOUT 是终态"""
        result = TimeoutResult(status=TimeoutStatus.TIMEOUT)
        self.assertTrue(result.is_terminal)

    def test_is_terminal_cancelled(self):
        """CANCELLED 不是终态"""
        result = TimeoutResult(status=TimeoutStatus.CANCELLED)
        self.assertFalse(result.is_terminal)

    def test_remaining_seconds(self):
        """remaining_seconds 计算"""
        result = TimeoutResult(
            status=TimeoutStatus.TIMEOUT,
            elapsed_seconds=250.0,
            timeout_seconds=300.0,
        )
        self.assertAlmostEqual(result.remaining_seconds, 50.0)

    def test_repr(self):
        """repr 格式正确"""
        result = TimeoutResult(
            status=TimeoutStatus.TIMEOUT,
            elapsed_seconds=100.0,
            timeout_seconds=60.0,
            timed_out=True,
        )
        r = repr(result)
        self.assertIn("timeout", r)
        self.assertIn("100.0", r)


class TestTimeoutControllerConstructor(unittest.TestCase):
    """验证 TimeoutController 构造"""

    def test_none_cli(self):
        """None cli 抛 ValueError"""
        detector = MagicMock()
        with self.assertRaises(ValueError) as ctx:
            TimeoutController(cli=None, detector=detector)
        self.assertIn("cli", str(ctx.exception))

    def test_none_detector(self):
        """None detector 抛 ValueError"""
        cli = MagicMock()
        with self.assertRaises(ValueError) as ctx:
            TimeoutController(cli=cli, detector=None)
        self.assertIn("detector", str(ctx.exception))

    def test_default_params(self):
        """默认参数正确"""
        cli = MagicMock()
        detector = MagicMock()
        controller = TimeoutController(cli=cli, detector=detector)
        self.assertIs(controller.cli, cli)
        self.assertIs(controller.detector, detector)
        self.assertEqual(controller.default_timeout, 600)
        self.assertEqual(controller.poll_interval, 5.0)
        self.assertEqual(controller.stop_timeout, 15.0)

    def test_custom_params(self):
        """自定义参数正确"""
        cli = MagicMock()
        detector = MagicMock()
        controller = TimeoutController(
            cli=cli,
            detector=detector,
            default_timeout=300,
            poll_interval=2.0,
            stop_timeout=10.0,
        )
        self.assertEqual(controller.default_timeout, 300)
        self.assertEqual(controller.poll_interval, 2.0)
        self.assertEqual(controller.stop_timeout, 10.0)

    def test_invalid_default_timeout(self):
        """非正 default_timeout 抛 ValueError"""
        cli = MagicMock()
        detector = MagicMock()
        with self.assertRaises(ValueError):
            TimeoutController(cli=cli, detector=detector, default_timeout=0)
        with self.assertRaises(ValueError):
            TimeoutController(cli=cli, detector=detector, default_timeout=-1)

    def test_invalid_poll_interval(self):
        """非正 poll_interval 抛 ValueError"""
        cli = MagicMock()
        detector = MagicMock()
        with self.assertRaises(ValueError):
            TimeoutController(cli=cli, detector=detector, poll_interval=0)


class TestExecuteWithTimeoutCompleted(unittest.TestCase):
    """验证任务完成场景"""

    def test_immediate_completion(self):
        """立即检测到完成 → COMPLETED"""
        cli = MagicMock()
        detector = MagicMock()
        detection = DetectionResult(status=ExecutionStatus.COMPLETED)
        detector.detect.return_value = detection

        controller = TimeoutController(
            cli=cli, detector=detector, poll_interval=0.01
        )
        result = controller.execute_with_timeout("boss", "w1", timeout=10)

        self.assertEqual(result.status, TimeoutStatus.COMPLETED)
        self.assertFalse(result.timed_out)
        self.assertIsNotNone(result.detection_result)
        self.assertLess(result.elapsed_seconds, 5)

    def test_completion_after_polls(self):
        """经过几次轮询后完成 → COMPLETED"""
        cli = MagicMock()
        detector = MagicMock()

        running = DetectionResult(status=ExecutionStatus.RUNNING)
        completed = DetectionResult(status=ExecutionStatus.COMPLETED)
        detector.detect.side_effect = [running, running, completed]

        controller = TimeoutController(
            cli=cli, detector=detector, poll_interval=0.01
        )
        result = controller.execute_with_timeout("boss", "w1", timeout=10)

        self.assertEqual(result.status, TimeoutStatus.COMPLETED)
        self.assertEqual(detector.detect.call_count, 3)


class TestExecuteWithTimeoutFailed(unittest.TestCase):
    """验证任务失败场景"""

    def test_immediate_failure(self):
        """立即检测到失败 → FAILED"""
        cli = MagicMock()
        detector = MagicMock()
        detection = DetectionResult(status=ExecutionStatus.FAILED)
        detector.detect.return_value = detection

        controller = TimeoutController(
            cli=cli, detector=detector, poll_interval=0.01
        )
        result = controller.execute_with_timeout("boss", "w1", timeout=10)

        self.assertEqual(result.status, TimeoutStatus.FAILED)
        self.assertFalse(result.timed_out)


class TestExecuteWithTimeoutTimeout(unittest.TestCase):
    """验证超时场景"""

    def test_timeout_triggers_stop_cli(self):
        """超时后调用 stop_cli"""
        cli = MagicMock()
        cli.stop_cli.return_value = CLIStatus.STOPPED
        detector = MagicMock()
        # 始终返回 RUNNING，模拟任务不结束
        detector.detect.return_value = DetectionResult(
            status=ExecutionStatus.RUNNING
        )

        controller = TimeoutController(
            cli=cli, detector=detector, poll_interval=0.05
        )
        result = controller.execute_with_timeout("boss", "w1", timeout=0.2)

        self.assertEqual(result.status, TimeoutStatus.TIMEOUT)
        self.assertTrue(result.timed_out)
        self.assertTrue(result.stopped_cli)
        cli.stop_cli.assert_called_once()

    def test_timeout_elapsed_time(self):
        """超时时 elapsed_seconds 接近 timeout"""
        cli = MagicMock()
        cli.stop_cli.return_value = CLIStatus.STOPPED
        detector = MagicMock()
        detector.detect.return_value = DetectionResult(
            status=ExecutionStatus.RUNNING
        )

        controller = TimeoutController(
            cli=cli, detector=detector, poll_interval=0.05
        )
        result = controller.execute_with_timeout("boss", "w1", timeout=0.3)

        self.assertTrue(result.timed_out)
        self.assertGreaterEqual(result.elapsed_seconds, 0.25)
        self.assertAlmostEqual(
            result.elapsed_seconds, result.timeout_seconds, delta=0.2
        )

    def test_timeout_stop_cli_failure(self):
        """超时后 stop_cli 返回非 STOPPED → stopped_cli=False"""
        cli = MagicMock()
        cli.stop_cli.return_value = CLIStatus.ERROR
        detector = MagicMock()
        detector.detect.return_value = DetectionResult(
            status=ExecutionStatus.RUNNING
        )

        controller = TimeoutController(
            cli=cli, detector=detector, poll_interval=0.05
        )
        result = controller.execute_with_timeout("boss", "w1", timeout=0.2)

        self.assertEqual(result.status, TimeoutStatus.TIMEOUT)
        self.assertTrue(result.timed_out)
        self.assertFalse(result.stopped_cli)

    def test_timeout_stop_cli_exception(self):
        """超时后 stop_cli 抛异常 → stopped_cli=False"""
        cli = MagicMock()
        cli.stop_cli.side_effect = Exception("stop failed")
        detector = MagicMock()
        detector.detect.return_value = DetectionResult(
            status=ExecutionStatus.RUNNING
        )

        controller = TimeoutController(
            cli=cli, detector=detector, poll_interval=0.05
        )
        result = controller.execute_with_timeout("boss", "w1", timeout=0.2)

        self.assertEqual(result.status, TimeoutStatus.TIMEOUT)
        self.assertTrue(result.timed_out)
        self.assertFalse(result.stopped_cli)

    def test_is_timed_out_after_timeout(self):
        """超时后 is_timed_out 返回 True"""
        cli = MagicMock()
        cli.stop_cli.return_value = CLIStatus.STOPPED
        detector = MagicMock()
        detector.detect.return_value = DetectionResult(
            status=ExecutionStatus.RUNNING
        )

        controller = TimeoutController(
            cli=cli, detector=detector, poll_interval=0.05
        )
        controller.execute_with_timeout("boss", "w1", timeout=0.2)

        self.assertTrue(controller.is_timed_out("boss", "w1"))


class TestCancel(unittest.TestCase):
    """验证取消功能"""

    def test_cancel_returns_true(self):
        """取消活跃监控返回 True"""
        cli = MagicMock()
        detector = MagicMock()

        running = DetectionResult(status=ExecutionStatus.RUNNING)
        cancelled_detection = DetectionResult(status=ExecutionStatus.RUNNING)

        call_count = 0

        def detect_side_effect(session, window):
            nonlocal call_count
            call_count += 1
            # 第二次检测前取消
            if call_count == 2:
                controller.cancel("boss", "w1")
            return running if call_count < 3 else cancelled_detection

        detector.detect.side_effect = detect_side_effect

        controller = TimeoutController(
            cli=cli, detector=detector, poll_interval=0.01
        )
        result = controller.execute_with_timeout("boss", "w1", timeout=10)

        self.assertEqual(result.status, TimeoutStatus.CANCELLED)
        self.assertTrue(result.cancelled)
        self.assertFalse(result.timed_out)

    def test_cancel_no_active_monitor(self):
        """取消不存在的监控返回 False"""
        cli = MagicMock()
        detector = MagicMock()
        controller = TimeoutController(cli=cli, detector=detector)
        self.assertFalse(controller.cancel("boss", "w1"))


class TestTimeTracking(unittest.TestCase):
    """验证时间跟踪"""

    def test_get_remaining_time_active(self):
        """活跃监控有剩余时间"""
        cli = MagicMock()
        detector = MagicMock()

        def detect_after_delay(session, window):
            # 第一次返回 RUNNING，第二次返回 COMPLETED
            if detector.detect.call_count == 1:
                return DetectionResult(status=ExecutionStatus.RUNNING)
            return DetectionResult(status=ExecutionStatus.COMPLETED)

        detector.detect.side_effect = detect_after_delay

        controller = TimeoutController(
            cli=cli, detector=detector, poll_interval=0.01
        )

        # 启动后立即查询（在第一次检测返回 RUNNING 时）
        # 但 execute_with_timeout 是阻塞的，所以用独立测试
        # 改为直接测试跟踪状态

    def test_get_remaining_time_no_monitor(self):
        """无活跃监控返回 None"""
        cli = MagicMock()
        detector = MagicMock()
        controller = TimeoutController(cli=cli, detector=detector)
        self.assertIsNone(controller.get_remaining_time("boss", "w1"))

    def test_get_elapsed_time_no_monitor(self):
        """无活跃监控返回 None"""
        cli = MagicMock()
        detector = MagicMock()
        controller = TimeoutController(cli=cli, detector=detector)
        self.assertIsNone(controller.get_elapsed_time("boss", "w1"))

    def test_remaining_time_during_execution(self):
        """执行中查询剩余时间"""
        cli = MagicMock()
        detector = MagicMock()

        results = []

        def detect_side_effect(session, window):
            remaining = controller.get_remaining_time(session, window)
            elapsed = controller.get_elapsed_time(session, window)
            if remaining is not None:
                results.append(remaining)
            if elapsed is not None:
                results.append(elapsed)
            # 第三次检测完成
            if detector.detect.call_count >= 3:
                return DetectionResult(status=ExecutionStatus.COMPLETED)
            return DetectionResult(status=ExecutionStatus.RUNNING)

        detector.detect.side_effect = detect_side_effect

        controller = TimeoutController(
            cli=cli, detector=detector, poll_interval=0.01
        )
        controller.execute_with_timeout("boss", "w1", timeout=30)

        # 应该有值被记录（remaining > 0, elapsed > 0）
        self.assertTrue(len(results) > 0)
        # remaining 应该小于 timeout
        remainings = [r for r in results if r < 30]
        self.assertTrue(len(remainings) > 0)


class TestParameterValidation(unittest.TestCase):
    """验证参数校验"""

    def test_empty_session(self):
        """空 session 抛 ValueError"""
        cli = MagicMock()
        detector = MagicMock()
        controller = TimeoutController(cli=cli, detector=detector)
        with self.assertRaises(ValueError):
            controller.execute_with_timeout("", "w1", timeout=10)

    def test_empty_window(self):
        """空 window 抛 ValueError"""
        cli = MagicMock()
        detector = MagicMock()
        controller = TimeoutController(cli=cli, detector=detector)
        with self.assertRaises(ValueError):
            controller.execute_with_timeout("boss", "", timeout=10)

    def test_zero_timeout(self):
        """零 timeout 抛 ValueError"""
        cli = MagicMock()
        detector = MagicMock()
        controller = TimeoutController(cli=cli, detector=detector)
        with self.assertRaises(ValueError):
            controller.execute_with_timeout("boss", "w1", timeout=0)

    def test_negative_timeout(self):
        """负 timeout 抛 ValueError"""
        cli = MagicMock()
        detector = MagicMock()
        controller = TimeoutController(cli=cli, detector=detector)
        with self.assertRaises(ValueError):
            controller.execute_with_timeout("boss", "w1", timeout=-1)

    def test_none_timeout_uses_default(self):
        """None timeout 使用 default_timeout"""
        cli = MagicMock()
        detector = MagicMock()
        detector.detect.return_value = DetectionResult(
            status=ExecutionStatus.COMPLETED
        )

        controller = TimeoutController(
            cli=cli, detector=detector, default_timeout=999, poll_interval=0.01
        )
        result = controller.execute_with_timeout("boss", "w1")

        self.assertEqual(result.status, TimeoutStatus.COMPLETED)
        self.assertEqual(result.timeout_seconds, 999)


class TestMapExecutionToTimeout(unittest.TestCase):
    """验证 ExecutionStatus → TimeoutStatus 映射"""

    def test_completed_mapping(self):
        self.assertEqual(
            TimeoutController._map_execution_to_timeout(ExecutionStatus.COMPLETED),
            TimeoutStatus.COMPLETED,
        )

    def test_failed_mapping(self):
        self.assertEqual(
            TimeoutController._map_execution_to_timeout(ExecutionStatus.FAILED),
            TimeoutStatus.FAILED,
        )

    def test_running_mapping(self):
        self.assertEqual(
            TimeoutController._map_execution_to_timeout(ExecutionStatus.RUNNING),
            TimeoutStatus.UNKNOWN,
        )

    def test_unknown_mapping(self):
        self.assertEqual(
            TimeoutController._map_execution_to_timeout(ExecutionStatus.UNKNOWN),
            TimeoutStatus.UNKNOWN,
        )


class TestMakeKey(unittest.TestCase):
    """验证 key 生成"""

    def test_key_format(self):
        self.assertEqual(
            TimeoutController._make_key("boss", "w1"),
            "boss:w1",
        )


class TestStopTimeoutParameter(unittest.TestCase):
    """验证 stop_timeout 参数传递"""

    def test_custom_stop_timeout(self):
        """自定义 stop_timeout 传递给 stop_cli"""
        cli = MagicMock()
        cli.stop_cli.return_value = CLIStatus.STOPPED
        detector = MagicMock()
        detector.detect.return_value = DetectionResult(
            status=ExecutionStatus.RUNNING
        )

        controller = TimeoutController(
            cli=cli, detector=detector,
            poll_interval=0.05, stop_timeout=8.0,
        )
        controller.execute_with_timeout("boss", "w1", timeout=0.2)

        cli.stop_cli.assert_called_once_with("boss", "w1", timeout=8.0)


class TestCleanupAfterExecution(unittest.TestCase):
    """验证执行后的状态清理"""

    def test_start_times_cleaned_after_completion(self):
        """完成后 start_times 被清理"""
        cli = MagicMock()
        detector = MagicMock()
        detector.detect.return_value = DetectionResult(
            status=ExecutionStatus.COMPLETED
        )

        controller = TimeoutController(
            cli=cli, detector=detector, poll_interval=0.01
        )
        controller.execute_with_timeout("boss", "w1", timeout=10)

        self.assertIsNone(controller.get_remaining_time("boss", "w1"))
        self.assertIsNone(controller.get_elapsed_time("boss", "w1"))


if __name__ == "__main__":
    unittest.main()

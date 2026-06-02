"""
P2-023 测试 — TestRunner 测试执行器

测试内容：
- execute 基本执行（pytest）
- 解析输出（passed/failed/errors）
- 脚本不存在处理
- 超时处理
- 自定义参数
- TestResult 属性
"""

import pytest
import os
import tempfile
from pathlib import Path

from agent_automation_system.scheduler.test_runner import (
    TestRunner,
    TestResult,
    TestRunnerError,
)


@pytest.fixture
def tmp_test_file():
    d = tempfile.mkdtemp()
    path = Path(d) / "test_sample.py"
    path.write_text("def test_pass():\n    assert True\n")
    yield str(path)
    import shutil
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def tmp_failing_test_file():
    d = tempfile.mkdtemp()
    path = Path(d) / "test_fail.py"
    path.write_text("def test_fail():\n    assert False\n")
    yield str(path)
    import shutil
    shutil.rmtree(d, ignore_errors=True)


class TestTestRunnerExecute:
    """execute 基本执行"""

    def test_execute_passing_test(self, tmp_test_file):
        runner = TestRunner()
        result = runner.execute(tmp_test_file)
        assert result.passed is True
        assert result.total == 1
        assert result.passed_count == 1
        assert result.failed_count == 0

    def test_execute_failing_test(self, tmp_failing_test_file):
        runner = TestRunner()
        result = runner.execute(tmp_failing_test_file)
        assert result.passed is False
        assert result.failed_count >= 1

    def test_execute_returns_test_file_path(self, tmp_test_file):
        runner = TestRunner()
        result = runner.execute(tmp_test_file)
        assert result.test_file_path == tmp_test_file

    def test_execute_has_output(self, tmp_test_file):
        runner = TestRunner()
        result = runner.execute(tmp_test_file)
        assert len(result.output) > 0

    def test_execute_has_duration(self, tmp_test_file):
        runner = TestRunner()
        result = runner.execute(tmp_test_file)
        assert result.duration_seconds > 0


class TestTestRunnerFileNotFound:
    """文件不存在处理"""

    def test_missing_file_raises(self):
        runner = TestRunner()
        with pytest.raises(TestRunnerError, match="not found"):
            runner.execute("/nonexistent/test_file.py")


class TestTestRunnerTimeout:
    """超时处理"""

    def test_custom_timeout(self, tmp_test_file):
        runner = TestRunner(timeout=300)
        result = runner.execute(tmp_test_file)
        assert result.passed is True

    def test_very_short_timeout(self):
        d = tempfile.mkdtemp()
        path = Path(d) / "test_slow.py"
        path.write_text("import time\ndef test_slow():\n    time.sleep(30)\n    assert True\n")
        runner = TestRunner(timeout=2)
        with pytest.raises(TestRunnerError, match="timed out"):
            runner.execute(str(path))
        import shutil
        shutil.rmtree(d, ignore_errors=True)


class TestTestRunnerArgs:
    """自定义参数"""

    def test_verbose_flag(self, tmp_test_file):
        runner = TestRunner(args=["-v"])
        result = runner.execute(tmp_test_file)
        assert result.passed is True

    def test_extra_args_passed_to_pytest(self, tmp_test_file):
        runner = TestRunner(args=["-q", "--tb=short"])
        result = runner.execute(tmp_test_file)
        assert result.passed is True


class TestTestResultProperties:
    """TestResult 属性"""

    def test_result_success_property(self, tmp_test_file):
        runner = TestRunner()
        result = runner.execute(tmp_test_file)
        assert result.success is True

    def test_result_error_count(self, tmp_failing_test_file):
        runner = TestRunner()
        result = runner.execute(tmp_failing_test_file)
        assert result.error_count >= 0

    def test_result_summary_contains_counts(self, tmp_test_file):
        runner = TestRunner()
        result = runner.execute(tmp_test_file)
        assert "passed" in result.summary.lower()
        assert str(result.total) in result.summary


class TestTestRunnerDefaultConfig:
    """默认配置"""

    def test_default_timeout(self):
        runner = TestRunner()
        assert runner.timeout == 60

    def test_default_args(self):
        runner = TestRunner()
        assert "-q" in runner.args


class TestTestRunnerMultipleTests:
    """多测试执行"""

    def test_execute_directory(self, tmp_test_file):
        runner = TestRunner()
        test_dir = str(Path(tmp_test_file).parent)
        result = runner.execute(test_dir)
        assert result.total >= 1

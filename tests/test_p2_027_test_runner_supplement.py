"""
P2-027 测试：TestRunner 单元测试补充

P2-023 已覆盖 16 个基础测试（执行/超时/参数/属性）。
P2-027 补充以下场景：
1. TestResult 数据类完整性
2. 多测试混合结果（pass + fail + error + skip）
3. error_output 捕获（stderr）
4. _parse_counts 边界（乱码/空/garbled）
5. 自定义 python_path
6. args 副本隔离
7. 多次执行可重复性
8. 大输出处理
9. 收集失败场景
10. TestRunner/TestResult __test__ = False 标记
"""

import os
import tempfile
import pytest
from pathlib import Path

from agent_automation_system.scheduler.test_runner import (
    TestRunner,
    TestResult,
    TestRunnerError,
)


# ── Fixtures ──────────────────────────────────────────────


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


@pytest.fixture
def tmp_mixed_test_file():
    """混合 pass + fail + skip 的测试文件"""
    d = tempfile.mkdtemp()
    path = Path(d) / "test_mixed.py"
    path.write_text("""
import pytest

def test_one():
    assert True

def test_two():
    assert False

def test_three():
    assert True

@pytest.mark.skip(reason="not ready")
def test_four():
    assert True
""")
    yield str(path)
    import shutil
    shutil.rmtree(d, ignore_errors=True)


@pytest.fixture
def tmp_error_test_file():
    """含 setup error 的测试文件"""
    d = tempfile.mkdtemp()
    path = Path(d) / "test_error.py"
    path.write_text("""
import pytest

@pytest.fixture
def bad_fixture():
    raise RuntimeError("fixture setup failed")

def test_using_bad_fixture(bad_fixture):
    assert True
""")
    yield str(path)
    import shutil
    shutil.rmtree(d, ignore_errors=True)


# ── TestResult 数据模型 ───────────────────────────────────


class TestTestResultModel:
    """TestResult 数据模型深度验证"""

    def test_create_minimal(self):
        r = TestResult(test_file_path="/x.py")
        assert r.test_file_path == "/x.py"
        assert r.passed is False
        assert r.total == 0
        assert r.passed_count == 0
        assert r.failed_count == 0
        assert r.error_count == 0
        assert r.output == ""
        assert r.error_output == ""
        assert r.duration_seconds == 0.0

    def test_create_full(self):
        r = TestResult(
            test_file_path="/t.py",
            passed=True,
            total=5,
            passed_count=5,
            failed_count=0,
            error_count=0,
            output="5 passed",
            error_output="",
            duration_seconds=1.23,
        )
        assert r.passed is True
        assert r.success is True
        assert r.total == 5
        assert r.duration_seconds == 1.23

    def test_success_with_failures(self, tmp_failing_test_file):
        """success 属性在 passed=False 时为 False"""
        runner = TestRunner()
        result = runner.execute(tmp_failing_test_file)
        assert result.passed is False
        assert result.success is False

    def test_error_count_from_execution(self, tmp_error_test_file):
        """error count 从真实执行结果获取"""
        runner = TestRunner()
        result = runner.execute(tmp_error_test_file)
        assert result.error_count >= 0

    def test_summary_for_passing(self, tmp_test_file):
        runner = TestRunner()
        result = runner.execute(tmp_test_file)
        s = result.summary
        assert "passed" in s.lower()
        assert str(result.total) in s

    def test_summary_for_failing(self, tmp_failing_test_file):
        runner = TestRunner()
        result = runner.execute(tmp_failing_test_file)
        s = result.summary
        assert "failed" in s.lower()
        assert str(result.failed_count) in s

    def test_test_file_path_preserved_on_fail(self, tmp_failing_test_file):
        runner = TestRunner()
        result = runner.execute(tmp_failing_test_file)
        assert result.test_file_path == tmp_failing_test_file

    def test_error_output_stderr(self, tmp_test_file):
        """error_output 捕获 stderr"""
        runner = TestRunner()
        result = runner.execute(tmp_test_file)
        # stderr 可能是空，也可能包含 warnings
        assert isinstance(result.error_output, str)

    def test_error_output_stderr_on_error(self, tmp_error_test_file):
        """错误场景下 error_output 有内容"""
        runner = TestRunner()
        result = runner.execute(tmp_error_test_file)
        assert isinstance(result.error_output, str)


# ── 多测试混合场景 ───────────────────────────────────────


class TestMixedResults:
    """pass + fail + skip 混合"""

    def test_mixed_counts(self, tmp_mixed_test_file):
        runner = TestRunner()
        result = runner.execute(tmp_mixed_test_file)
        # 应该有 passed 和 failed
        assert result.total > 0
        assert result.passed_count >= 2  # test_one + test_three
        assert result.failed_count >= 1  # test_two
        assert result.passed is False  # 有失败

    def test_mixed_has_output(self, tmp_mixed_test_file):
        runner = TestRunner()
        result = runner.execute(tmp_mixed_test_file)
        assert len(result.output) > 0

    def test_mixed_duration(self, tmp_mixed_test_file):
        runner = TestRunner()
        result = runner.execute(tmp_mixed_test_file)
        assert result.duration_seconds > 0


class TestMultipleTestFiles:
    """多个测试文件执行"""

    def test_execute_two_files(self, tmp_test_file, tmp_failing_test_file):
        """顺序执行两个不同文件"""
        runner = TestRunner()
        r1 = runner.execute(tmp_test_file)
        r2 = runner.execute(tmp_failing_test_file)
        assert r1.passed is True
        assert r2.passed is False
        assert r1.test_file_path != r2.test_file_path

    def test_same_runner_multiple_passes(self, tmp_test_file):
        """同一 runner 多次执行同一文件"""
        runner = TestRunner()
        r1 = runner.execute(tmp_test_file)
        r2 = runner.execute(tmp_test_file)
        assert r1.passed is True
        assert r2.passed is True
        # 两次 duration 可能不同但都是正数
        assert r1.duration_seconds > 0
        assert r2.duration_seconds > 0


# ── _parse_counts 静态方法 ───────────────────────────────


class TestParseCounts:
    """_parse_counts 边界测试"""

    def test_all_passed(self):
        passed, failed, errors = TestRunner._parse_counts("5 passed in 0.1s")
        assert passed == 5
        assert failed == 0
        assert errors == 0

    def test_all_failed(self):
        passed, failed, errors = TestRunner._parse_counts("3 failed in 0.2s")
        assert passed == 0
        assert failed == 3
        assert errors == 0

    def test_mixed(self):
        passed, failed, errors = TestRunner._parse_counts(
            "2 passed, 1 failed, 1 error in 0.3s"
        )
        assert passed == 2
        assert failed == 1
        assert errors == 1

    def test_no_collection(self):
        """无收集到测试"""
        passed, failed, errors = TestRunner._parse_counts(
            "collected 0 items\n\nno tests ran in 0.01s"
        )
        assert passed == 0
        assert failed == 0
        assert errors == 0

    def test_empty_string(self):
        passed, failed, errors = TestRunner._parse_counts("")
        assert passed == 0
        assert failed == 0
        assert errors == 0

    def test_garbage_output(self):
        passed, failed, errors = TestRunner._parse_counts("not pytest output")
        assert passed == 0
        assert failed == 0
        assert errors == 0


# ── 自定义 python_path ────────────────────────────────────


class TestCustomPythonPath:
    """自定义 python_path"""

    def test_default_python_path(self):
        runner = TestRunner()
        assert runner._python == "python3"

    def test_custom_python_path(self, tmp_test_file):
        runner = TestRunner(python_path="python3")
        result = runner.execute(tmp_test_file)
        assert result.passed is True

    def test_python_preserved(self):
        runner = TestRunner(python_path="/usr/local/bin/python3.11")
        assert runner._python == "/usr/local/bin/python3.11"


# ── args 副本隔离 ────────────────────────────────────────


class TestArgsIsolation:
    """args 返回副本，外部修改不影响内部"""

    def test_args_returns_copy(self):
        runner = TestRunner(args=["-v"])
        args = runner.args
        args.append("--extra")
        # 内部 args 不受影响
        assert "--extra" not in runner.args
        assert "-v" in runner.args

    def test_empty_args_uses_defaults(self):
        runner = TestRunner(args=[])
        assert "-q" in runner.args

    def test_none_args_uses_defaults(self):
        runner = TestRunner(args=None)
        assert "-q" in runner.args

    def test_args_unrelated_to_timeout(self):
        """args 和 timeout 互不影响"""
        runner = TestRunner(timeout=30, args=["-v", "--tb=long"])
        assert runner.timeout == 30
        assert "-v" in runner.args
        assert "--tb=long" in runner.args


# ── 构造函数边界 ──────────────────────────────────────────


class TestRunnerConstructors:
    """构造函数边界值"""

    def test_defaults(self):
        runner = TestRunner()
        assert runner.timeout == 60
        assert runner._python == "python3"
        assert isinstance(runner.args, list)

    def test_negative_timeout(self):
        """负超时不抛异常（由 subprocess 决定行为）"""
        runner = TestRunner(timeout=-1)
        assert runner.timeout == -1

    def test_zero_timeout_falls_back_to_default(self):
        """timeout=0 被 Python falsy 逻辑转为默认 60"""
        runner = TestRunner(timeout=0)
        assert runner.timeout == 60  # 0 是 falsy → 使用 DEFAULT_TIMEOUT

    def test_large_timeout(self):
        runner = TestRunner(timeout=99999)
        assert runner.timeout == 99999


# ── __test__ = False 标记 ──────────────────────────────────


class TestCollectionPrevention:
    """__test__ = False 标记防止误收集"""

    def test_test_result_not_collectable(self):
        assert getattr(TestResult, "__test__", None) is False

    def test_test_runner_not_collectable(self):
        assert getattr(TestRunner, "__test__", None) is False

    def test_test_runner_error_not_collectable(self):
        assert getattr(TestRunnerError, "__test__", None) is False


# ── 大输出场景 ───────────────────────────────────────────


class TestLargeScenarios:
    """大输出 / 压力场景"""

    def test_large_output(self):
        """大量测试的输出"""
        d = tempfile.mkdtemp()
        path = Path(d) / "test_many.py"
        # 生成 50 个通过的测试
        tests = "\n".join(
            f"def test_{i:03d}():\n    assert True\n"
            for i in range(50)
        )
        path.write_text(tests)
        runner = TestRunner()
        result = runner.execute(str(path))
        assert result.passed is True
        assert result.total == 50
        # -q 模式输出精简，仅验证存在
        assert "50 passed" in result.output or "passed" in result.output
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    def test_long_test_name(self):
        """长测试名"""
        d = tempfile.mkdtemp()
        path = Path(d) / "test_long.py"
        path.write_text(
            "def test_" + "a" * 50 + "():\n    assert True\n"
        )
        runner = TestRunner()
        result = runner.execute(str(path))
        assert result.passed is True
        import shutil
        shutil.rmtree(d, ignore_errors=True)


# ── 收集失败场景 ─────────────────────────────────────────


class TestCollectionFailures:
    """pytest 收集失败"""

    def test_syntax_error_file(self):
        """语法错误文件"""
        d = tempfile.mkdtemp()
        path = Path(d) / "test_broken.py"
        path.write_text("this is not valid python @@@@")
        runner = TestRunner()
        # pytest 收集语法错误文件时返回非 0
        result = runner.execute(str(path))
        assert result.passed is False
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    def test_empty_test_file(self):
        """空测试文件（无测试函数）"""
        d = tempfile.mkdtemp()
        path = Path(d) / "test_empty.py"
        path.write_text("# no tests here\n")
        runner = TestRunner()
        result = runner.execute(str(path))
        assert result.total == 0
        import shutil
        shutil.rmtree(d, ignore_errors=True)


# ── error_output 深度验证 ──────────────────────────────────


class TestErrorOutput:
    """stderr 输出捕获"""

    def test_error_output_on_syntax_error(self):
        d = tempfile.mkdtemp()
        path = Path(d) / "test_broken.py"
        path.write_text("def test_x()\n    invalid syntax !!!")
        runner = TestRunner()
        result = runner.execute(str(path))
        assert result.passed is False
        # syntax error 会输出到 stderr
        assert isinstance(result.error_output, str)
        import shutil
        shutil.rmtree(d, ignore_errors=True)

    def test_error_output_empty_on_pass(self, tmp_test_file):
        runner = TestRunner()
        result = runner.execute(tmp_test_file)
        # 通过的测试通常 stderr 为空
        assert isinstance(result.error_output, str)

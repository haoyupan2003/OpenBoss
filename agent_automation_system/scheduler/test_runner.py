"""
TestRunner — 测试执行器

调用 pytest 执行测试脚本，解析输出返回结构化结果。
由 DevAgent 在 TDD 第三步（run_tests）调用。

使用方式：
    runner = TestRunner()
    result = runner.execute("tests/test_task_001.py")
    print(result.passed, result.total, result.failed_count)
"""

import logging
import re
import subprocess
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class TestRunnerError(Exception):
    __test__ = False
    pass


@dataclass
class TestResult:
    __test__ = False
    test_file_path: str
    passed: bool = False
    total: int = 0
    passed_count: int = 0
    failed_count: int = 0
    error_count: int = 0
    output: str = ""
    error_output: str = ""
    duration_seconds: float = 0.0

    @property
    def success(self) -> bool:
        return self.passed and self.failed_count == 0

    @property
    def summary(self) -> str:
        return (
            f"{self.total} tests: {self.passed_count} passed, "
            f"{self.failed_count} failed, {self.error_count} errors "
            f"in {self.duration_seconds:.2f}s"
        )


class TestRunner:
    __test__ = False
    DEFAULT_TIMEOUT = 60
    DEFAULT_ARGS = ["-q", "--tb=short"]

    def __init__(
        self,
        timeout: int | None = None,
        args: list[str] | None = None,
        python_path: str = "python3",
    ) -> None:
        self._timeout = timeout or self.DEFAULT_TIMEOUT
        self._args = list(args) if args else list(self.DEFAULT_ARGS)
        self._python = python_path

    @property
    def timeout(self) -> int:
        return self._timeout

    @property
    def args(self) -> list[str]:
        return list(self._args)

    def execute(self, test_path: str) -> TestResult:
        import os
        if not os.path.exists(test_path):
            raise TestRunnerError(f"Test file not found: {test_path}")

        cmd = [self._python, "-m", "pytest"] + self._args + [test_path]
        start = time.time()

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self._timeout,
            )
        except subprocess.TimeoutExpired:
            raise TestRunnerError(
                f"Test execution timed out after {self._timeout}s"
            )

        elapsed = time.time() - start
        stdout = proc.stdout
        stderr = proc.stderr

        passed_count, failed_count, error_count = self._parse_counts(stdout)
        total = passed_count + failed_count + error_count

        return TestResult(
            test_file_path=test_path,
            passed=proc.returncode == 0,
            total=total,
            passed_count=passed_count,
            failed_count=failed_count,
            error_count=error_count,
            output=stdout,
            error_output=stderr,
            duration_seconds=elapsed,
        )

    @staticmethod
    def _parse_counts(output: str) -> tuple[int, int, int]:
        m = re.search(r"(\d+)\s+passed", output)
        passed = int(m.group(1)) if m else 0
        m = re.search(r"(\d+)\s+failed", output)
        failed = int(m.group(1)) if m else 0
        m = re.search(r"(\d+)\s+error", output)
        errors = int(m.group(1)) if m else 0
        return passed, failed, errors

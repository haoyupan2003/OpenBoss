"""
LogManager 单元测试

覆盖 LogManager 的所有公共方法、内部逻辑和边界场景：
- write_log: 级别过滤、自动路由、ERROR/CRITICAL 双写、手动指定 category
- 便利方法: debug / info / warning / error / critical
- _infer_category: master / 非 master / ERROR 且无 agent
- read_logs: 正常读取、文件不存在、指定日期
- get_log_path: 路径格式验证
- LogLevel: 枚举值、比较运算符
- LogCategory: 枚举值
- auto_create_dir: 自动创建日志目录
- round-trip: 写入后读取一致性
"""

import re
from datetime import datetime
from pathlib import Path

import pytest

from agent_automation_system.file_io.log_manager import LogCategory, LogLevel, LogManager


# ─── Fixtures ──────────────────────────────────────


@pytest.fixture
def tmp_log_dir(tmp_path: Path) -> Path:
    """创建临时日志目录"""
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    return log_dir


@pytest.fixture
def log_manager(tmp_log_dir: Path) -> LogManager:
    """创建使用临时目录的 LogManager 实例（min_level=DEBUG，捕获所有级别）"""
    return LogManager(log_dir=tmp_log_dir, min_level=LogLevel.DEBUG)


@pytest.fixture
def default_log_manager(tmp_log_dir: Path) -> LogManager:
    """创建使用默认 min_level=INFO 的 LogManager"""
    return LogManager(log_dir=tmp_log_dir, min_level=LogLevel.INFO)


# ─── write_log 测试 ────────────────────────────────


class TestWriteLog:
    """write_log() 方法测试"""

    def test_write_returns_path(self, log_manager, tmp_log_dir):
        """写入日志返回文件路径"""
        result = log_manager.write_log(LogLevel.INFO, "master", "测试消息")
        assert result is not None
        assert isinstance(result, Path)

    def test_write_below_min_level_returns_none(self, default_log_manager):
        """低于最低级别的日志不写入，返回 None"""
        result = default_log_manager.write_log(LogLevel.DEBUG, "master", "debug 消息")
        assert result is None

    def test_write_at_min_level(self, default_log_manager):
        """等于最低级别的日志正常写入"""
        result = default_log_manager.write_log(LogLevel.INFO, "master", "info 消息")
        assert result is not None

    def test_write_creates_main_agent_log(self, log_manager, tmp_log_dir):
        """master agent 日志写入 main_agent 文件"""
        log_manager.write_log(LogLevel.INFO, "master", "调度消息")

        date_str = datetime.now().strftime("%Y-%m-%d")
        log_path = tmp_log_dir / f"main_agent_{date_str}.log"
        assert log_path.exists()

        content = log_path.read_text(encoding="utf-8")
        assert "调度消息" in content
        assert "[INFO]" in content
        assert "[master]" in content

    def test_write_creates_sub_agent_log(self, log_manager, tmp_log_dir):
        """非 master agent 日志写入 sub_agent_exec 文件"""
        log_manager.write_log(LogLevel.INFO, "dev-agent-001", "执行消息")

        date_str = datetime.now().strftime("%Y-%m-%d")
        log_path = tmp_log_dir / f"sub_agent_exec_{date_str}.log"
        assert log_path.exists()

        content = log_path.read_text(encoding="utf-8")
        assert "执行消息" in content
        assert "[dev-agent-001]" in content

    def test_write_error_dual_writes(self, log_manager, tmp_log_dir):
        """ERROR 级别同时写入来源文件和 error 文件（非 master agent）"""
        # dev-agent-001 的 ERROR: _infer_category 返回 SUB_AGENT（含 agent），
        # 因此主文件是 sub_agent_exec，双写到 error
        log_manager.write_log(LogLevel.ERROR, "dev-agent-001", "发生错误")

        date_str = datetime.now().strftime("%Y-%m-%d")
        sub_path = tmp_log_dir / f"sub_agent_exec_{date_str}.log"
        error_path = tmp_log_dir / f"error_{date_str}.log"

        assert sub_path.exists()
        assert error_path.exists()

        sub_content = sub_path.read_text(encoding="utf-8")
        error_content = error_path.read_text(encoding="utf-8")

        assert "发生错误" in sub_content
        assert "发生错误" in error_content

    def test_write_critical_dual_writes(self, log_manager, tmp_log_dir):
        """CRITICAL 级别同时写入来源文件和 error 文件"""
        log_manager.write_log(LogLevel.CRITICAL, "dev-agent-002", "严重错误")

        date_str = datetime.now().strftime("%Y-%m-%d")
        sub_path = tmp_log_dir / f"sub_agent_exec_{date_str}.log"
        error_path = tmp_log_dir / f"error_{date_str}.log"

        assert sub_path.exists()
        assert error_path.exists()

        sub_content = sub_path.read_text(encoding="utf-8")
        error_content = error_path.read_text(encoding="utf-8")

        assert "严重错误" in sub_content
        assert "严重错误" in error_content

    def test_write_error_no_dual_when_error_category(self, log_manager, tmp_log_dir):
        """手动指定 category=ERROR 时不双写"""
        log_manager.write_log(
            LogLevel.ERROR, "system", "系统错误", category=LogCategory.ERROR
        )

        date_str = datetime.now().strftime("%Y-%m-%d")
        error_path = tmp_log_dir / f"error_{date_str}.log"

        assert error_path.exists()
        content = error_path.read_text(encoding="utf-8")
        # 只写一次（不应重复）
        assert content.count("系统错误") == 1

    def test_write_info_no_error_file(self, log_manager, tmp_log_dir):
        """INFO 级别不写入 error 文件"""
        log_manager.write_log(LogLevel.INFO, "master", "普通消息")

        date_str = datetime.now().strftime("%Y-%m-%d")
        error_path = tmp_log_dir / f"error_{date_str}.log"
        assert not error_path.exists()

    def test_write_with_manual_category(self, log_manager, tmp_log_dir):
        """手动指定 category 覆盖自动推断"""
        log_manager.write_log(
            LogLevel.INFO, "dev-agent-001", "手动路由", category=LogCategory.MAIN_AGENT
        )

        date_str = datetime.now().strftime("%Y-%m-%d")
        main_path = tmp_log_dir / f"main_agent_{date_str}.log"
        sub_path = tmp_log_dir / f"sub_agent_exec_{date_str}.log"

        assert main_path.exists()
        assert not sub_path.exists()

        content = main_path.read_text(encoding="utf-8")
        assert "手动路由" in content

    def test_write_multiple_logs_append(self, log_manager, tmp_log_dir):
        """多次写入追加到同一文件"""
        log_manager.write_log(LogLevel.INFO, "master", "第一条")
        log_manager.write_log(LogLevel.INFO, "master", "第二条")

        lines = log_manager.read_logs(LogCategory.MAIN_AGENT)
        assert len(lines) == 2
        assert "第一条" in lines[0]
        assert "第二条" in lines[1]

    def test_write_log_format(self, log_manager):
        """日志行格式：YYYY-MM-DD HH:MM:SS [LEVEL] [agent_id] Message"""
        log_manager.write_log(LogLevel.WARNING, "test-agent", "格式验证")

        lines = log_manager.read_logs(LogCategory.SUB_AGENT)
        assert len(lines) == 1

        pattern = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[WARNING\] \[test-agent\] 格式验证$"
        assert re.match(pattern, lines[0])


# ─── 便利方法测试 ────────────────────────────────────


class TestConvenienceMethods:
    """debug/info/warning/error/critical 便利方法测试"""

    def test_debug_method(self, log_manager):
        """debug() 写入 DEBUG 级别日志"""
        log_manager.debug("master", "调试信息")
        lines = log_manager.read_logs(LogCategory.MAIN_AGENT)
        assert len(lines) == 1
        assert "[DEBUG]" in lines[0]
        assert "调试信息" in lines[0]

    def test_info_method(self, log_manager):
        """info() 写入 INFO 级别日志"""
        log_manager.info("master", "信息消息")
        lines = log_manager.read_logs(LogCategory.MAIN_AGENT)
        assert len(lines) == 1
        assert "[INFO]" in lines[0]

    def test_warning_method(self, log_manager):
        """warning() 写入 WARNING 级别日志"""
        log_manager.warning("master", "警告消息")
        lines = log_manager.read_logs(LogCategory.MAIN_AGENT)
        assert len(lines) == 1
        assert "[WARNING]" in lines[0]

    def test_error_method(self, log_manager):
        """error() 写入 ERROR 级别日志"""
        # master + ERROR: _infer_category 返回 ERROR（master 不含 "agent"）
        log_manager.error("master", "错误消息")
        error_lines = log_manager.read_logs(LogCategory.ERROR)
        assert len(error_lines) == 1
        assert "[ERROR]" in error_lines[0]
        assert "错误消息" in error_lines[0]

    def test_critical_method(self, log_manager):
        """critical() 写入 CRITICAL 级别日志"""
        # master + CRITICAL: _infer_category 返回 ERROR
        log_manager.critical("master", "严重消息")
        error_lines = log_manager.read_logs(LogCategory.ERROR)
        assert len(error_lines) == 1
        assert "[CRITICAL]" in error_lines[0]
        assert "严重消息" in error_lines[0]

    def test_convenience_passes_category_kwarg(self, log_manager):
        """便利方法支持 **kwargs 传递 category"""
        log_manager.info("dev-agent", "手动路由", category=LogCategory.MAIN_AGENT)
        lines = log_manager.read_logs(LogCategory.MAIN_AGENT)
        assert len(lines) == 1
        assert "手动路由" in lines[0]


# ─── _infer_category 测试 ───────────────────────────


class TestInferCategory:
    """_infer_category() 推断逻辑测试"""

    def test_master_routes_to_main_agent(self):
        """agent_id='master' 路由到 main_agent"""
        result = LogManager._infer_category(LogLevel.INFO, "master")
        assert result == LogCategory.MAIN_AGENT

    def test_master_prefix_routes_to_main_agent(self):
        """agent_id 以 'master-' 开头路由到 main_agent"""
        result = LogManager._infer_category(LogLevel.INFO, "master-orchestrator")
        assert result == LogCategory.MAIN_AGENT

    def test_non_master_routes_to_sub_agent(self):
        """非 master agent 路由到 sub_agent_exec"""
        result = LogManager._infer_category(LogLevel.INFO, "dev-agent-001")
        assert result == LogCategory.SUB_AGENT

    def test_arbitrary_id_routes_to_sub_agent(self):
        """任意非 master ID 路由到 sub_agent_exec"""
        result = LogManager._infer_category(LogLevel.INFO, "worker-01")
        assert result == LogCategory.SUB_AGENT

    def test_error_level_without_agent_in_id(self):
        """ERROR 级别且 agent_id 不含 'agent' 路由到 error"""
        result = LogManager._infer_category(LogLevel.ERROR, "system")
        assert result == LogCategory.ERROR

    def test_critical_level_without_agent_in_id(self):
        """CRITICAL 级别且 agent_id 不含 'agent' 路由到 error"""
        result = LogManager._infer_category(LogLevel.CRITICAL, "system")
        assert result == LogCategory.ERROR

    def test_error_level_with_agent_in_id(self):
        """ERROR 级别但 agent_id 含 'agent' 仍走 sub_agent_exec"""
        result = LogManager._infer_category(LogLevel.ERROR, "dev-agent-001")
        assert result == LogCategory.SUB_AGENT

    def test_error_level_master_with_agent(self):
        """master 含 'agent' 吗？不含，但 master 规则优先"""
        # 注意：_infer_category 先检查 ERROR 无 agent，再检查 master
        # "master" 不含 "agent" 字样，ERROR 级别时走 error 路由
        result = LogManager._infer_category(LogLevel.ERROR, "master")
        assert result == LogCategory.ERROR


# ─── read_logs 测试 ─────────────────────────────────


class TestReadLogs:
    """read_logs() 方法测试"""

    def test_read_existing_logs(self, log_manager):
        """读取已存在的日志"""
        log_manager.write_log(LogLevel.INFO, "master", "测试消息1")
        log_manager.write_log(LogLevel.INFO, "master", "测试消息2")

        lines = log_manager.read_logs(LogCategory.MAIN_AGENT)
        assert len(lines) == 2
        assert "测试消息1" in lines[0]
        assert "测试消息2" in lines[1]

    def test_read_nonexistent_logs(self, log_manager):
        """读取不存在的日志返回空列表"""
        lines = log_manager.read_logs(LogCategory.MAIN_AGENT)
        assert lines == []

    def test_read_with_date(self, log_manager, tmp_log_dir):
        """指定日期读取日志"""
        # 创建一个特定日期的日志文件
        old_log_path = tmp_log_dir / "main_agent_2025-01-15.log"
        old_log_path.write_text("2025-01-15 10:00:00 [INFO] [master] 旧日志\n", encoding="utf-8")

        lines = log_manager.read_logs(LogCategory.MAIN_AGENT, date="2025-01-15")
        assert len(lines) == 1
        assert "旧日志" in lines[0]

    def test_read_different_categories(self, log_manager):
        """读取不同类别的日志互不干扰"""
        log_manager.write_log(LogLevel.INFO, "master", "主日志")
        log_manager.write_log(LogLevel.INFO, "dev-agent-001", "子日志")

        main_lines = log_manager.read_logs(LogCategory.MAIN_AGENT)
        sub_lines = log_manager.read_logs(LogCategory.SUB_AGENT)

        assert len(main_lines) == 1
        assert len(sub_lines) == 1
        assert "主日志" in main_lines[0]
        assert "子日志" in sub_lines[0]

    def test_read_returns_lines_without_newline(self, log_manager):
        """read_logs 返回的行不包含换行符"""
        log_manager.write_log(LogLevel.INFO, "master", "无换行测试")
        lines = log_manager.read_logs(LogCategory.MAIN_AGENT)
        assert all(line.endswith("无换行测试") for line in lines)


# ─── get_log_path 测试 ─────────────────────────────


class TestGetLogPath:
    """get_log_path() 方法测试"""

    def test_main_agent_path_format(self, log_manager, tmp_log_dir):
        """main_agent 日志路径格式"""
        path = log_manager.get_log_path(LogCategory.MAIN_AGENT)
        date_str = datetime.now().strftime("%Y-%m-%d")
        assert path == tmp_log_dir / f"main_agent_{date_str}.log"

    def test_sub_agent_path_format(self, log_manager, tmp_log_dir):
        """sub_agent_exec 日志路径格式"""
        path = log_manager.get_log_path(LogCategory.SUB_AGENT)
        date_str = datetime.now().strftime("%Y-%m-%d")
        assert path == tmp_log_dir / f"sub_agent_exec_{date_str}.log"

    def test_error_path_format(self, log_manager, tmp_log_dir):
        """error 日志路径格式"""
        path = log_manager.get_log_path(LogCategory.ERROR)
        date_str = datetime.now().strftime("%Y-%m-%d")
        assert path == tmp_log_dir / f"error_{date_str}.log"


# ─── LogLevel 测试 ─────────────────────────────────


class TestLogLevel:
    """LogLevel 枚举和比较运算符测试"""

    def test_log_level_values(self):
        """LogLevel 枚举值正确"""
        assert LogLevel.DEBUG.value == "DEBUG"
        assert LogLevel.INFO.value == "INFO"
        assert LogLevel.WARNING.value == "WARNING"
        assert LogLevel.ERROR.value == "ERROR"
        assert LogLevel.CRITICAL.value == "CRITICAL"

    def test_log_level_ordering(self):
        """LogLevel 级别排序正确"""
        assert LogLevel.DEBUG < LogLevel.INFO
        assert LogLevel.INFO < LogLevel.WARNING
        assert LogLevel.WARNING < LogLevel.ERROR
        assert LogLevel.ERROR < LogLevel.CRITICAL

    def test_log_level_comparison_operators(self):
        """比较运算符工作正常"""
        assert LogLevel.DEBUG <= LogLevel.INFO
        assert LogLevel.CRITICAL >= LogLevel.ERROR
        assert LogLevel.INFO > LogLevel.DEBUG
        assert LogLevel.WARNING >= LogLevel.WARNING
        assert LogLevel.WARNING <= LogLevel.WARNING

    def test_log_level_is_str_enum(self):
        """LogLevel 继承自 str 和 Enum"""
        assert isinstance(LogLevel.INFO, str)
        assert LogLevel.INFO == "INFO"

    def test_log_level_comparison_with_non_level(self):
        """与非 LogLevel 比较返回 NotImplemented"""
        result = LogLevel.INFO.__lt__("INFO")
        assert result is NotImplemented


# ─── LogCategory 测试 ──────────────────────────────


class TestLogCategory:
    """LogCategory 枚举测试"""

    def test_log_category_values(self):
        """LogCategory 枚举值正确"""
        assert LogCategory.MAIN_AGENT.value == "main_agent"
        assert LogCategory.SUB_AGENT.value == "sub_agent_exec"
        assert LogCategory.ERROR.value == "error"

    def test_log_category_is_str_enum(self):
        """LogCategory 继承自 str 和 Enum"""
        assert isinstance(LogCategory.MAIN_AGENT, str)
        assert LogCategory.MAIN_AGENT == "main_agent"


# ─── auto_create_dir 测试 ───────────────────────────


class TestAutoCreateDir:
    """自动创建日志目录测试"""

    def test_auto_create_dir_enabled(self, tmp_path: Path):
        """auto_create_dir=True 时自动创建目录"""
        log_dir = tmp_path / "auto_created" / "logs"
        assert not log_dir.exists()

        mgr = LogManager(log_dir=log_dir, auto_create_dir=True)
        mgr.write_log(LogLevel.INFO, "master", "自动创建目录")

        assert log_dir.exists()

    def test_auto_create_dir_disabled(self, tmp_path: Path):
        """auto_create_dir=False 时不自动创建目录（写入失败）"""
        log_dir = tmp_path / "no_create" / "logs"
        assert not log_dir.exists()

        mgr = LogManager(log_dir=log_dir, auto_create_dir=False)
        # 目录不存在时应抛出 FileNotFoundError
        with pytest.raises(FileNotFoundError):
            mgr.write_log(LogLevel.INFO, "master", "不创建目录")


# ─── 级别过滤测试 ───────────────────────────────────


class TestLevelFiltering:
    """min_level 级别过滤测试"""

    def test_filter_debug_when_min_info(self, default_log_manager):
        """min_level=INFO 时 DEBUG 不写入"""
        result = default_log_manager.write_log(LogLevel.DEBUG, "master", "被过滤")
        assert result is None

    def test_filter_debug_convenience_method(self, default_log_manager):
        """min_level=INFO 时 debug() 不写入"""
        result = default_log_manager.debug("master", "被过滤")
        assert result is None

    def test_allow_info_when_min_info(self, default_log_manager):
        """min_level=INFO 时 INFO 正常写入"""
        result = default_log_manager.info("master", "允许写入")
        assert result is not None

    def test_allow_warning_when_min_info(self, default_log_manager):
        """min_level=INFO 时 WARNING 正常写入"""
        result = default_log_manager.warning("master", "警告写入")
        assert result is not None

    def test_min_level_debug_passes_all(self, log_manager):
        """min_level=DEBUG 时所有级别都写入"""
        for level in LogLevel:
            result = log_manager.write_log(level, "master", f"{level.value} 消息")
            assert result is not None


# ─── round-trip 一致性测试 ────────────────────────────


class TestRoundTrip:
    """写入后读取一致性测试"""

    def test_roundtrip_single_entry(self, log_manager):
        """单条日志写入后读取一致"""
        log_manager.write_log(LogLevel.INFO, "master", "一致性测试")
        lines = log_manager.read_logs(LogCategory.MAIN_AGENT)

        assert len(lines) == 1
        assert "[INFO]" in lines[0]
        assert "[master]" in lines[0]
        assert "一致性测试" in lines[0]

    def test_roundtrip_multiple_entries(self, log_manager):
        """多条日志写入后读取一致"""
        log_manager.write_log(LogLevel.INFO, "master", "第一条")
        log_manager.write_log(LogLevel.WARNING, "master", "第二条")
        # master + ERROR: _infer_category 返回 ERROR（master 不含 "agent"）
        log_manager.write_log(LogLevel.ERROR, "master", "第三条")

        main_lines = log_manager.read_logs(LogCategory.MAIN_AGENT)
        error_lines = log_manager.read_logs(LogCategory.ERROR)

        # main_agent: info + warning = 2（ERROR 被 _infer_category 路由到 error）
        assert len(main_lines) == 2
        # error: 1 条（master ERROR 直接写入 error）
        assert len(error_lines) == 1
        assert "第三条" in error_lines[0]

    def test_roundtrip_cross_category(self, log_manager):
        """跨类别写入后分别读取一致"""
        log_manager.info("master", "主日志1")
        log_manager.info("dev-agent-001", "子日志1")
        # master + ERROR: _infer_category → ERROR（不含 "agent"）
        log_manager.error("master", "主错误")
        # dev-agent-002 + ERROR: _infer_category → SUB_AGENT（含 "agent"），双写到 ERROR
        log_manager.error("dev-agent-002", "子错误")

        main_lines = log_manager.read_logs(LogCategory.MAIN_AGENT)
        sub_lines = log_manager.read_logs(LogCategory.SUB_AGENT)
        error_lines = log_manager.read_logs(LogCategory.ERROR)

        # main_agent: 只有 info = 1
        assert len(main_lines) == 1
        # sub_agent_exec: info + error = 2
        assert len(sub_lines) == 2
        # error: master error（直接路由） + dev-agent-002 error（双写） = 2
        assert len(error_lines) == 2

    def test_roundtrip_log_format_consistency(self, log_manager):
        """写入后读取的日志行格式一致"""
        log_manager.write_log(LogLevel.WARNING, "test-agent", "格式测试")
        lines = log_manager.read_logs(LogCategory.SUB_AGENT)

        assert len(lines) == 1
        line = lines[0]
        # 格式: YYYY-MM-DD HH:MM:SS [LEVEL] [agent_id] Message
        pattern = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \[WARNING\] \[test-agent\] 格式测试$"
        assert re.match(pattern, line), f"日志格式不匹配: {line}"

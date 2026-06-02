"""
MemoryManager 单元测试

覆盖 MemoryManager 的所有公共方法和边界场景：
- read: 空文件、文件不存在、单/多 section
- append: 新增、同标题替换+tags 合并、自动设 updated_at
- search: 按标题/内容/tags 搜索、大小写敏感
- read_section: 精确匹配、不存在
- replace_section: 替换不合并 tags、不存在时追加
- delete_section: 存在/不存在
- get_all_titles: 正常/空文件
- _parse_entries: Markdown 格式兼容、tags/updated_at 解析
- 写入-读取一致性
"""

from datetime import datetime
from pathlib import Path

import pytest

from agent_automation_system.file_io.memory_manager import MemoryManager
from agent_automation_system.models.memory_entry import MemoryEntry


# ─── Fixtures ──────────────────────────────────────


@pytest.fixture
def tmp_data_dir(tmp_path: Path) -> Path:
    """创建临时 data 目录"""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    return data_dir


@pytest.fixture
def memory_manager(tmp_data_dir: Path) -> MemoryManager:
    """创建使用临时目录的 MemoryManager 实例"""
    return MemoryManager(file_path=tmp_data_dir / "memory.md")


@pytest.fixture
def sample_entry() -> MemoryEntry:
    """返回一个基础 MemoryEntry"""
    return MemoryEntry(
        title="Current State",
        content="正在实现 MemoryManager 单元测试",
        tags=["core", "testing"],
        updated_at=datetime(2026, 5, 16, 16, 0, 0),
    )


@pytest.fixture
def learning_entry() -> MemoryEntry:
    """返回一个经验教训条目"""
    return MemoryEntry(
        title="Learnings",
        content="Pydantic v2 使用 model_copy() 进行不可变更新",
        tags=["pydantic", "v2"],
        updated_at=datetime(2026, 5, 16, 15, 30, 0),
    )


@pytest.fixture
def result_entry() -> MemoryEntry:
    """返回一个关键结果条目"""
    return MemoryEntry(
        title="Key Results",
        content="MemoryManager 实现完成，通过全部功能测试",
        tags=["milestone"],
    )


# ─── read 测试 ──────────────────────────────────────


class TestRead:
    """read() 方法测试"""

    def test_read_nonexistent_file(self, memory_manager):
        """文件不存在返回空列表"""
        assert memory_manager.read() == []

    def test_read_empty_file(self, memory_manager):
        """空文件返回空列表"""
        memory_manager.file_path.write_text("", encoding="utf-8")
        assert memory_manager.read() == []

    def test_read_only_header(self, memory_manager):
        """只含一级标题（无 section）返回空列表"""
        content = "# Project Memory\n\n_Last updated: 2026-05-16 10:00:00_\n\n"
        memory_manager.file_path.write_text(content, encoding="utf-8")
        assert memory_manager.read() == []

    def test_read_single_section(self, memory_manager, sample_entry):
        """正确读取单个 section"""
        memory_manager.append(sample_entry)
        result = memory_manager.read()
        assert len(result) == 1
        assert result[0].title == "Current State"

    def test_read_multiple_sections(
        self, memory_manager, sample_entry, learning_entry
    ):
        """正确读取多个 section"""
        memory_manager.append(sample_entry)
        memory_manager.append(learning_entry)
        result = memory_manager.read()
        assert len(result) == 2
        titles = [e.title for e in result]
        assert "Current State" in titles
        assert "Learnings" in titles


# ─── append 测试 ────────────────────────────────────


class TestAppend:
    """append() 方法测试"""

    def test_append_new_entry(self, memory_manager, sample_entry):
        """追加新 section"""
        memory_manager.append(sample_entry)
        result = memory_manager.read()
        assert len(result) == 1
        assert result[0].title == "Current State"
        assert "正在实现" in result[0].content

    def test_append_same_title_replaces_content(self, memory_manager, sample_entry):
        """同标题 append 替换内容"""
        memory_manager.append(sample_entry)

        updated = MemoryEntry(
            title="Current State",
            content="已完成 MemoryManager 测试",
            tags=["done"],
        )
        memory_manager.append(updated)

        result = memory_manager.read()
        assert len(result) == 1
        assert "已完成" in result[0].content

    def test_append_same_title_merges_tags(self, memory_manager, sample_entry):
        """同标题 append 合并 tags"""
        memory_manager.append(sample_entry)

        updated = MemoryEntry(
            title="Current State",
            content="新内容",
            tags=["done", "core"],  # core 重复
        )
        memory_manager.append(updated)

        result = memory_manager.read()
        assert len(result) == 1
        tags = result[0].tags
        assert "core" in tags
        assert "done" in tags
        assert "testing" in tags  # 保留旧 tag
        # 不应有重复
        assert tags.count("core") == 1

    def test_append_auto_sets_updated_at(self, memory_manager):
        """append 时未设 updated_at 自动填充"""
        entry = MemoryEntry(title="Auto Time", content="测试自动时间")
        assert entry.updated_at is None

        memory_manager.append(entry)
        result = memory_manager.read()
        assert len(result) == 1
        assert result[0].updated_at is not None

    def test_append_preserves_explicit_updated_at(self, memory_manager):
        """append 时已有 updated_at 不被覆盖"""
        explicit_time = datetime(2026, 1, 1, 0, 0, 0)
        entry = MemoryEntry(
            title="Fixed Time",
            content="固定时间",
            updated_at=explicit_time,
        )
        memory_manager.append(entry)
        result = memory_manager.read()
        assert result[0].updated_at == explicit_time

    def test_append_creates_parent_directory(self, tmp_path: Path):
        """自动创建父目录"""
        deep_path = tmp_path / "deep" / "nested" / "memory.md"
        mgr = MemoryManager(file_path=deep_path)
        mgr.append(MemoryEntry(title="Test", content="Hello"))
        assert deep_path.exists()


# ─── search 测试 ────────────────────────────────────


class TestSearch:
    """search() 方法测试"""

    def test_search_by_title(self, memory_manager, sample_entry, learning_entry):
        """按标题搜索（不区分大小写）"""
        memory_manager.append(sample_entry)
        memory_manager.append(learning_entry)

        results = memory_manager.search("current")
        assert len(results) == 1
        assert results[0].title == "Current State"

    def test_search_by_content(self, memory_manager, sample_entry, learning_entry):
        """按内容搜索"""
        memory_manager.append(sample_entry)
        memory_manager.append(learning_entry)

        results = memory_manager.search("pydantic")
        assert len(results) == 1
        assert results[0].title == "Learnings"

    def test_search_by_tag(self, memory_manager, sample_entry, learning_entry):
        """按 tag 搜索"""
        memory_manager.append(sample_entry)
        memory_manager.append(learning_entry)

        results = memory_manager.search("core")
        assert len(results) == 1
        assert results[0].title == "Current State"

    def test_search_case_insensitive_by_default(
        self, memory_manager, sample_entry
    ):
        """默认不区分大小写"""
        memory_manager.append(sample_entry)

        results = memory_manager.search("CURRENT")
        assert len(results) == 1

    def test_search_case_sensitive(self, memory_manager, sample_entry):
        """区分大小写搜索"""
        memory_manager.append(sample_entry)

        # 大写搜索，case_sensitive=True，应不匹配 "Current State" 中的 "CURRENT"
        results = memory_manager.search("CURRENT", case_sensitive=True)
        assert len(results) == 0

        # 精确大小写匹配
        results = memory_manager.search("Current", case_sensitive=True)
        assert len(results) == 1

    def test_search_no_match(self, memory_manager, sample_entry):
        """无匹配结果返回空列表"""
        memory_manager.append(sample_entry)
        results = memory_manager.search("nonexistent_keyword_xyz")
        assert results == []

    def test_search_empty_file(self, memory_manager):
        """空文件搜索返回空列表"""
        results = memory_manager.search("anything")
        assert results == []

    def test_search_matches_multiple(
        self, memory_manager, sample_entry, learning_entry, result_entry
    ):
        """关键词匹配多个条目"""
        memory_manager.append(sample_entry)
        memory_manager.append(learning_entry)
        memory_manager.append(result_entry)

        # "core" 在 sample_entry 的 tags 和 result_entry 无，只有 1 个
        # "pydantic" 只在 learning_entry
        # "v2" 在 learning_entry 的 tags
        results = memory_manager.search("v2")
        assert len(results) == 1

        # 搜索中文关键词
        results = memory_manager.search("MemoryManager")
        assert len(results) >= 2  # sample_entry 和 result_entry 都含此词


# ─── read_section 测试 ──────────────────────────────


class TestReadSection:
    """read_section() 方法测试"""

    def test_read_existing_section(self, memory_manager, sample_entry):
        """读取已存在的 section"""
        memory_manager.append(sample_entry)
        result = memory_manager.read_section("Current State")
        assert result is not None
        assert result.title == "Current State"

    def test_read_nonexistent_section(self, memory_manager, sample_entry):
        """读取不存在的 section 返回 None"""
        memory_manager.append(sample_entry)
        result = memory_manager.read_section("Nonexistent")
        assert result is None

    def test_read_section_exact_match(self, memory_manager):
        """精确标题匹配（非模糊）"""
        memory_manager.append(
            MemoryEntry(title="Test", content="A")
        )
        memory_manager.append(
            MemoryEntry(title="Test Extended", content="B")
        )

        result = memory_manager.read_section("Test")
        assert result is not None
        assert result.content == "A"


# ─── replace_section 测试 ──────────────────────────


class TestReplaceSection:
    """replace_section() 方法测试"""

    def test_replace_existing_section(self, memory_manager, sample_entry):
        """替换已有 section"""
        memory_manager.append(sample_entry)

        replacement = MemoryEntry(
            title="Current State",
            content="替换后的内容",
            tags=["replaced"],
        )
        memory_manager.replace_section(replacement)

        result = memory_manager.read_section("Current State")
        assert result is not None
        assert result.content == "替换后的内容"
        assert result.tags == ["replaced"]  # 不合并，直接替换

    def test_replace_does_not_merge_tags(self, memory_manager, sample_entry):
        """replace_section 不合并 tags（与 append 区别）"""
        memory_manager.append(sample_entry)

        replacement = MemoryEntry(
            title="Current State",
            content="新内容",
            tags=["new-tag"],
        )
        memory_manager.replace_section(replacement)

        result = memory_manager.read_section("Current State")
        assert result.tags == ["new-tag"]
        assert "core" not in result.tags  # 旧 tag 被替换掉

    def test_replace_appends_if_not_exists(self, memory_manager):
        """section 不存在时追加"""
        memory_manager.replace_section(
            MemoryEntry(title="New Section", content="新增内容")
        )
        result = memory_manager.read()
        assert len(result) == 1
        assert result[0].title == "New Section"

    def test_replace_auto_sets_updated_at(self, memory_manager):
        """替换时未设 updated_at 自动填充"""
        memory_manager.append(MemoryEntry(title="Test", content="旧"))

        memory_manager.replace_section(
            MemoryEntry(title="Test", content="新")
        )
        result = memory_manager.read_section("Test")
        assert result.updated_at is not None


# ─── delete_section 测试 ────────────────────────────


class TestDeleteSection:
    """delete_section() 方法测试"""

    def test_delete_existing_section(
        self, memory_manager, sample_entry, learning_entry
    ):
        """删除已存在的 section"""
        memory_manager.append(sample_entry)
        memory_manager.append(learning_entry)

        result = memory_manager.delete_section("Current State")
        assert result is True

        remaining = memory_manager.read()
        assert len(remaining) == 1
        assert remaining[0].title == "Learnings"

    def test_delete_nonexistent_section(self, memory_manager, sample_entry):
        """删除不存在的 section 返回 False"""
        memory_manager.append(sample_entry)
        result = memory_manager.delete_section("Nonexistent")
        assert result is False

    def test_delete_from_empty_file(self, memory_manager):
        """空文件中删除返回 False"""
        result = memory_manager.delete_section("Anything")
        assert result is False

    def test_delete_last_section(self, memory_manager, sample_entry):
        """删除最后一个 section 后文件为空"""
        memory_manager.append(sample_entry)
        memory_manager.delete_section("Current State")
        assert memory_manager.read() == []


# ─── get_all_titles 测试 ────────────────────────────


class TestGetAllTitles:
    """get_all_titles() 方法测试"""

    def test_get_titles_from_multiple_sections(
        self, memory_manager, sample_entry, learning_entry
    ):
        """获取多个 section 的标题"""
        memory_manager.append(sample_entry)
        memory_manager.append(learning_entry)

        titles = memory_manager.get_all_titles()
        assert "Current State" in titles
        assert "Learnings" in titles
        assert len(titles) == 2

    def test_get_titles_from_empty_file(self, memory_manager):
        """空文件返回空列表"""
        assert memory_manager.get_all_titles() == []


# ─── 解析器边界场景 ──────────────────────────────────


class TestParserEdgeCases:
    """_parse_entries 解析器边界场景测试"""

    def test_parse_tags_with_backticks(self, memory_manager):
        """正确解析 Tags 行（反引号格式）"""
        content = (
            "# Project Memory\n\n"
            "_Last updated: 2026-05-16 10:00:00_\n\n"
            "## Test Section\n"
            "Tags: `tag1` `tag2` `tag3`\n"
            "_Updated: 2026-05-16 10:00:00_\n"
            "内容文本\n"
        )
        memory_manager.file_path.write_text(content, encoding="utf-8")
        result = memory_manager.read()

        assert len(result) == 1
        assert result[0].tags == ["tag1", "tag2", "tag3"]

    def test_parse_updated_at_line(self, memory_manager):
        """正确解析 _Updated: YYYY-MM-DD HH:MM:SS_ 行"""
        content = (
            "# Project Memory\n\n"
            "_Last updated: 2026-05-16 10:00:00_\n\n"
            "## Test\n"
            "_Updated: 2026-05-16 12:30:45_\n"
            "内容\n"
        )
        memory_manager.file_path.write_text(content, encoding="utf-8")
        result = memory_manager.read()

        assert len(result) == 1
        assert result[0].updated_at == datetime(2026, 5, 16, 12, 30, 45)

    def test_parse_multiline_content(self, memory_manager):
        """正确解析多行内容"""
        content = (
            "# Project Memory\n\n"
            "_Last updated: 2026-05-16 10:00:00_\n\n"
            "## Notes\n"
            "第一行\n"
            "第二行\n"
            "\n"
            "第四行（空行后）\n"
        )
        memory_manager.file_path.write_text(content, encoding="utf-8")
        result = memory_manager.read()

        assert len(result) == 1
        assert "第一行" in result[0].content
        assert "第二行" in result[0].content

    def test_parse_section_with_no_content(self, memory_manager):
        """解析空内容的 section"""
        content = (
            "# Project Memory\n\n"
            "_Last updated: 2026-05-16 10:00:00_\n\n"
            "## Empty Section\n\n"
            "## Next Section\n"
            "有内容\n"
        )
        memory_manager.file_path.write_text(content, encoding="utf-8")
        result = memory_manager.read()

        assert len(result) == 2
        assert result[0].title == "Empty Section"
        assert result[0].content == ""

    def test_parse_skip_one_level_header(self, memory_manager):
        """一级标题（# ）不应被解析为 section"""
        content = (
            "# Project Memory\n\n"
            "_Last updated: 2026-05-16 10:00:00_\n\n"
            "## Real Section\n"
            "内容\n"
        )
        memory_manager.file_path.write_text(content, encoding="utf-8")
        result = memory_manager.read()

        assert len(result) == 1
        assert result[0].title == "Real Section"

    def test_parse_chinese_content(self, memory_manager):
        """正确解析中文内容"""
        entry = MemoryEntry(
            title="架构决策",
            content="采用主从架构，Master Agent 负责调度",
            tags=["架构", "决策"],
        )
        memory_manager.append(entry)
        result = memory_manager.read()

        assert len(result) == 1
        assert result[0].title == "架构决策"
        assert "主从架构" in result[0].content
        assert "架构" in result[0].tags


# ─── 写入-读取一致性 ─────────────────────────────────


class TestRoundTrip:
    """写入后读取一致性测试"""

    def test_roundtrip_basic_entry(self, memory_manager, sample_entry):
        """基础条目的写入-读取一致性"""
        memory_manager.append(sample_entry)
        result = memory_manager.read()

        assert len(result) == 1
        assert result[0].title == sample_entry.title
        assert result[0].content == sample_entry.content
        assert set(result[0].tags) == set(sample_entry.tags)

    def test_roundtrip_multiple_entries(
        self, memory_manager, sample_entry, learning_entry, result_entry
    ):
        """多个条目的写入-读取一致性"""
        memory_manager.append(sample_entry)
        memory_manager.append(learning_entry)
        memory_manager.append(result_entry)

        result = memory_manager.read()
        assert len(result) == 3

        result_map = {e.title: e for e in result}
        assert "Current State" in result_map
        assert "Learnings" in result_map
        assert "Key Results" in result_map

    def test_roundtrip_minimal_entry(self, memory_manager):
        """最简条目（仅 title）的写入-读取一致性"""
        minimal = MemoryEntry(title="Minimal")
        memory_manager.append(minimal)
        result = memory_manager.read()

        assert len(result) == 1
        assert result[0].title == "Minimal"
        assert result[0].content == ""
        assert result[0].tags == []

    def test_roundtrip_entry_with_multiline_markdown(self, memory_manager):
        """含多行 Markdown 内容的写入-读取一致性"""
        entry = MemoryEntry(
            title="Workflow",
            content="- Step 1: 初始化\n- Step 2: 执行\n- Step 3: 验证",
        )
        memory_manager.append(entry)
        result = memory_manager.read()

        assert "Step 1" in result[0].content
        assert "Step 3" in result[0].content

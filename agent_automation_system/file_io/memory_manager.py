"""
MemoryManager - memory.md 读写器

基于 PRD V2.0 §6.1 memory.md 格式规范。
提供 memory.md 文件的读取、追加、搜索操作。

文件格式为 Markdown，按 section 组织：

    # Project Memory

    ## Current State
    当前工作状态描述...

    ## Learnings
    经验教训内容...

    ## Key Results
    关键结果...
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from agent_automation_system.models.memory_entry import MemoryEntry


class MemoryManager:
    """memory.md 文件管理器

    负责 memory.md 文件的读取、写入和搜索。
    memory.md 是 Agent 之间的共享知识库，
    用于记录项目上下文、经验教训、关键决策等。

    Args:
        file_path: memory.md 文件路径，默认 data/memory.md
    """

    # 文件头模板
    HEADER_TEMPLATE = "# Project Memory\n\n_Last updated: {updated_at}_\n\n"

    # section 标题正则：## Title {#optional-id} 或 ## Title
    SECTION_PATTERN = re.compile(r"^##\s+(.+?)(?:\s+\{#[\w-]+\})?\s*$")

    def __init__(self, file_path: Optional[Path] = None):
        self.file_path = file_path or Path("data/memory.md")

    def read(self) -> list[MemoryEntry]:
        """读取 memory.md 并解析为 MemoryEntry 列表

        Returns:
            MemoryEntry 列表，按文件中的顺序排列。
            如果文件不存在，返回空列表。
        """
        if not self.file_path.exists():
            return []

        content = self.file_path.read_text(encoding="utf-8")
        return self._parse_entries(content)

    def append(self, entry: MemoryEntry) -> None:
        """追加一个 section 到 memory.md

        如果同标题的 section 已存在，则更新其内容和 updated_at。
        如果不存在，则在文件末尾追加新 section。

        Args:
            entry: 要追加的 MemoryEntry 对象
        """
        entries = self.read()

        # 设置更新时间
        if entry.updated_at is None:
            entry = entry.model_copy(update={"updated_at": datetime.now()})

        # 查找是否已存在同标题 section
        replaced = False
        for i, existing in enumerate(entries):
            if existing.title == entry.title:
                # 合并 tags
                merged_tags = list(set(existing.tags + entry.tags))
                entries[i] = entry.model_copy(update={"tags": merged_tags})
                replaced = True
                break

        if not replaced:
            entries.append(entry)

        self._write_file(entries)

    def search(self, keyword: str, case_sensitive: bool = False) -> list[MemoryEntry]:
        """搜索 memory.md 中包含关键词的条目

        在标题、内容和标签中搜索匹配的条目。

        Args:
            keyword: 搜索关键词
            case_sensitive: 是否区分大小写，默认 False

        Returns:
            匹配的 MemoryEntry 列表
        """
        entries = self.read()
        results: list[MemoryEntry] = []

        search_keyword = keyword if case_sensitive else keyword.lower()

        for entry in entries:
            title = entry.title if case_sensitive else entry.title.lower()
            content = entry.content if case_sensitive else entry.content.lower()
            tags = (
                entry.tags
                if case_sensitive
                else [t.lower() for t in entry.tags]
            )

            if (
                search_keyword in title
                or search_keyword in content
                or any(search_keyword in tag for tag in tags)
            ):
                results.append(entry)

        return results

    def read_section(self, title: str) -> Optional[MemoryEntry]:
        """读取指定标题的 section

        Args:
            title: section 标题（精确匹配）

        Returns:
            MemoryEntry 或 None
        """
        entries = self.read()
        for entry in entries:
            if entry.title == title:
                return entry
        return None

    def replace_section(self, entry: MemoryEntry) -> None:
        """替换指定标题的 section 内容

        与 append 不同，此方法直接替换内容，不合并 tags。
        如果 section 不存在，则追加。

        Args:
            entry: 要替换的 MemoryEntry 对象
        """
        entries = self.read()

        if entry.updated_at is None:
            entry = entry.model_copy(update={"updated_at": datetime.now()})

        replaced = False
        for i, existing in enumerate(entries):
            if existing.title == entry.title:
                entries[i] = entry
                replaced = True
                break

        if not replaced:
            entries.append(entry)

        self._write_file(entries)

    def delete_section(self, title: str) -> bool:
        """删除指定标题的 section

        Args:
            title: section 标题

        Returns:
            是否成功删除（True/False）
        """
        entries = self.read()
        original_len = len(entries)
        entries = [e for e in entries if e.title != title]

        if len(entries) < original_len:
            self._write_file(entries)
            return True
        return False

    def get_all_titles(self) -> list[str]:
        """获取所有 section 标题

        Returns:
            标题列表
        """
        entries = self.read()
        return [e.title for e in entries]

    # ─── 内部方法 ───────────────────────────────────

    def _write_file(self, entries: list[MemoryEntry]) -> None:
        """将条目列表写入 memory.md 文件

        Args:
            entries: MemoryEntry 列表
        """
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

        updated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines: list[str] = []

        # 文件头
        lines.append(self.HEADER_TEMPLATE.format(updated_at=updated_at))

        # 各 section
        for entry in entries:
            # section 标题
            lines.append(f"## {entry.title}\n")

            # tags（如有）
            if entry.tags:
                tag_str = " ".join(f"`{t}`" for t in entry.tags)
                lines.append(f"Tags: {tag_str}\n")

            # updated_at（如有）
            if entry.updated_at is not None:
                ts = entry.updated_at.strftime("%Y-%m-%d %H:%M:%S")
                lines.append(f"_Updated: {ts}_\n")

            # 内容
            if entry.content:
                lines.append(f"{entry.content}\n")

            # section 之间空行分隔
            lines.append("\n")

        self.file_path.write_text("".join(lines), encoding="utf-8")

    @staticmethod
    def _parse_entries(content: str) -> list[MemoryEntry]:
        """解析 memory.md 内容为 MemoryEntry 列表

        逐行扫描，以 ## 标题作为新 section 起始。

        Args:
            content: 文件文本内容

        Returns:
            MemoryEntry 列表
        """
        entries: list[dict] = []
        current: Optional[dict] = None
        current_lines: list[str] = []

        for line in content.splitlines():
            # 检测 section 标题
            section_match = MemoryManager.SECTION_PATTERN.match(line)
            if section_match:
                # 保存上一个 section
                if current is not None:
                    current["content"] = "\n".join(current_lines).strip()
                    entries.append(current)
                current = {"title": section_match.group(1).strip()}
                current_lines = []
                continue

            # 跳过一级标题和文件头
            if current is None:
                continue

            # 跳过空行（保留在内容中）
            stripped = line.strip()

            # 解析 Tags 行
            if stripped.startswith("Tags:"):
                tag_text = stripped[len("Tags:"):].strip()
                tags = re.findall(r"`([^`]+)`", tag_text)
                current["tags"] = tags
                continue

            # 解析 Updated 行
            if stripped.startswith("_Updated:") and stripped.endswith("_"):
                ts_text = stripped[len("_Updated:"):-1].strip()
                try:
                    current["updated_at"] = datetime.strptime(
                        ts_text, "%Y-%m-%d %H:%M:%S"
                    )
                except ValueError:
                    pass
                continue

            # 普通内容行
            current_lines.append(line)

        # 保存最后一个 section
        if current is not None:
            current["content"] = "\n".join(current_lines).strip()
            entries.append(current)

        # 构建 MemoryEntry 对象
        result: list[MemoryEntry] = []
        for fields in entries:
            try:
                result.append(MemoryEntry(**fields))
            except Exception:
                pass

        return result

"""
MemoryEntry - memory.md 条目数据模型

基于 PRD V2.0 §6.1 memory.md 格式规范。
定义 memory.md 文件中的条目结构。

memory.md 采用 Markdown 格式，按 section 组织：
    ## Section Name
    section 内容（自由 Markdown 文本）

    ## Another Section
    另一段内容
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MemoryEntry(BaseModel):
    """memory.md 中单个 section 的数据模型

    每个 MemoryEntry 对应 memory.md 中的一个 ## 标题段落。

    Attributes:
        title: section 标题（对应 ## 后的文本）
        content: section 内容（Markdown 格式文本）
        updated_at: 最后更新时间
        tags: 可选标签列表，用于 search 时快速过滤
    """

    title: str = Field(
        ...,
        min_length=1,
        description="section 标题",
    )
    content: str = Field(
        default="",
        description="section 内容（Markdown 格式）",
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description="最后更新时间",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="标签列表，用于搜索过滤",
    )

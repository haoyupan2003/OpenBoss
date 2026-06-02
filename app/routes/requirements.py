"""
需求提交 API（P3-006）

POST /api/requirements — 接收用户原始需求
存储需求记录，返回需求 ID + 状态（pending → processing → task_json_ready）
"""

import logging
import uuid
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["requirements"])


# ── 数据模型 ──────────────────────────────────────────────


class RequirementRequest(BaseModel):
    """需求提交请求"""
    raw_need: str = Field(..., min_length=1, max_length=5000, description="用户原始需求描述")
    title: Optional[str] = Field(None, max_length=200, description="需求标题（可选）")


class RequirementResponse(BaseModel):
    """需求记录响应"""
    id: str
    title: Optional[str]
    raw_need: str
    status: str  # pending / processing / task_json_ready / failed
    created_at: str
    task_json_path: Optional[str] = None
    error: Optional[str] = None


# ── 内存存储 ──────────────────────────────────────────────


class RequirementStore:
    """需求内存存储（后续可替换为持久化存储）"""

    def __init__(self):
        self._items: dict[str, dict] = {}

    def add(self, raw_need: str, title: Optional[str] = None) -> str:
        rid = f"req-{uuid.uuid4().hex[:8]}"
        self._items[rid] = {
            "id": rid,
            "title": title,
            "raw_need": raw_need,
            "status": "pending",
            "created_at": datetime.now().isoformat(),
            "task_json_path": None,
            "error": None,
        }
        return rid

    def get(self, rid: str) -> Optional[dict]:
        return self._items.get(rid)

    def list_all(self) -> list[dict]:
        return sorted(self._items.values(), key=lambda x: x["created_at"], reverse=True)

    def update_status(self, rid: str, status: str, task_json_path: Optional[str] = None, error: Optional[str] = None):
        item = self._items.get(rid)
        if item:
            item["status"] = status
            if task_json_path:
                item["task_json_path"] = task_json_path
            if error:
                item["error"] = error


# 全局存储实例
_store = RequirementStore()


# ── 路由 ─────────────────────────────────────────────────


@router.post("/requirements", status_code=201)
async def submit_requirement(req: RequirementRequest):
    """提交原始需求（触发 PM Agent 流程）

    接收用户自然语言需求描述，存入需求队列。
    PM Agent 将被 Master Agent 调度处理该需求。
    """
    rid = _store.add(req.raw_need, req.title)
    logger.info("Requirement submitted: %s (%s)", rid, (req.title or req.raw_need[:30]))
    return RequirementResponse(**_store.get(rid))


@router.get("/requirements")
async def list_requirements():
    """列出所有已提交的需求"""
    return {"requirements": [RequirementResponse(**r).model_dump() for r in _store.list_all()]}


@router.get("/requirements/{req_id}")
async def get_requirement(req_id: str):
    """获取指定需求状态"""
    item = _store.get(req_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Requirement '{req_id}' not found")
    return RequirementResponse(**item)

"""
BDD 确认 API（P3-007）

POST /api/bdd/confirm — 用户确认 BDD 描述
GET  /api/bdd/{req_id}   — 查看 BDD 状态
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.routes.requirements import _store as req_store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/bdd", tags=["bdd"])


# ── 数据模型 ──────────────────────────────────────────────


class BDDConfirmRequest(BaseModel):
    req_id: str = Field(..., description="需求 ID")
    given: Optional[str] = Field(None, description="Given 前置条件")
    when: Optional[str] = Field(None, description="When 操作触发")
    then: Optional[str] = Field(None, description="Then 预期结果")
    confirmed: bool = Field(True, description="是否确认")
    feedback: Optional[str] = Field(None, max_length=1000, description="用户反馈/修改意见")


class BDDFeedbackRequest(BaseModel):
    """BDD 修改反馈请求（P3-008）"""
    req_id: str = Field(..., description="需求 ID")
    feedback: str = Field(..., min_length=1, max_length=1000, description="修改意见/反馈")
    given: Optional[str] = Field(None, description="修改后的 Given")
    when: Optional[str] = Field(None, description="修改后的 When")
    then: Optional[str] = Field(None, description="修改后的 Then")


class BDDStatusResponse(BaseModel):
    req_id: str
    status: str  # pending / draft / confirmed / rejected
    bdd: Optional[dict] = None
    feedback: Optional[str] = None
    confirmed_at: Optional[str] = None


# ── 内存存储 ──────────────────────────────────────────────

_bdd_records: dict[str, dict] = {}


def _ensure_record(req_id: str) -> dict:
    req = req_store.get(req_id)
    if req is None:
        raise HTTPException(status_code=404, detail=f"Requirement '{req_id}' not found")
    if req_id not in _bdd_records:
        _bdd_records[req_id] = {
            "status": "pending", "bdd": None, "feedback": None,
            "confirmed_at": None, "feedback_history": [],
        }
    return _bdd_records[req_id]


# ── 路由 ─────────────────────────────────────────────────


@router.post("/confirm")
async def confirm_bdd(req: BDDConfirmRequest):
    """确认 BDD 描述（用户确认 PM Agent 生成的 Given-When-Then）"""
    record = _ensure_record(req.req_id)

    if req.confirmed:
        record["status"] = "confirmed"
        record["bdd"] = {"given": req.given, "when": req.when, "then": req.then}
        record["confirmed_at"] = datetime.now().isoformat()
        record["feedback"] = None
        req_store.update_status(req.req_id, "bdd_confirmed")
        logger.info("BDD confirmed for %s", req.req_id)
    else:
        record["status"] = "rejected"
        record["feedback"] = req.feedback
        logger.info("BDD rejected for %s: %s", req.req_id, req.feedback)

    return BDDStatusResponse(req_id=req.req_id, **record)


@router.get("/{req_id}")
async def get_bdd_status(req_id: str):
    """获取 BDD 确认状态"""
    record = _ensure_record(req_id)
    return BDDStatusResponse(req_id=req_id, **record)


@router.post("/feedback")
async def submit_bdd_feedback(req: BDDFeedbackRequest):
    """提交 BDD 修改意见（P3-008）

    用户对 PM Agent 生成的 BDD 提出修改意见。
    支持仅文字反馈，或附带修改后的 Given/When/Then。
    每次反馈记录到历史。
    """
    record = _ensure_record(req.req_id)

    feedback_entry = {
        "feedback": req.feedback,
        "given": req.given,
        "when": req.when,
        "then": req.then,
        "submitted_at": datetime.now().isoformat(),
    }
    record.setdefault("feedback_history", []).append(feedback_entry)
    record["status"] = "draft"
    record["feedback"] = req.feedback
    if req.given or req.when or req.then:
        record["bdd"] = {"given": req.given, "when": req.when, "then": req.then}
    req_store.update_status(req.req_id, "bdd_feedback_received")

    logger.info("BDD feedback for %s: %s...", req.req_id, req.feedback[:50])
    return {
        "req_id": req.req_id,
        "status": "draft",
        "feedback": req.feedback,
        "feedback_count": len(record["feedback_history"]),
    }

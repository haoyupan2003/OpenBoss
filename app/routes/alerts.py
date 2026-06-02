"""
告警历史 API（P3-011）

GET /api/alerts — 返回历史告警记录
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["alerts"])

# 内存告警存储
_alerts: list[dict] = []


def add_alert(level: str, message: str, task_id: Optional[str] = None, source: str = "system"):
    _alerts.append({
        "id": f"alert-{len(_alerts) + 1:04d}",
        "level": level,
        "message": message,
        "task_id": task_id,
        "source": source,
        "created_at": datetime.now().isoformat(),
    })
    # 保留最近 200 条
    if len(_alerts) > 200:
        _alerts.pop(0)


@router.get("/alerts")
async def get_alerts(
    level: Optional[str] = Query(None, description="按级别过滤：error / warning / info"),
    task_id: Optional[str] = Query(None, description="按任务 ID 过滤"),
    limit: int = Query(50, ge=1, le=200, description="返回条数"),
):
    """获取历史告警记录"""
    results = _alerts
    if level:
        results = [a for a in results if a["level"] == level]
    if task_id:
        results = [a for a in results if a.get("task_id") == task_id]
    return {
        "alerts": results[-limit:],
        "total": len(results),
        "stored": len(_alerts),
    }

"""
Agent 状态 API（P3-003）

GET /api/agents — 返回所有 Agent 实时状态
数据来源：progress.txt（ProgressManager）
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from agent_automation_system.file_io.progress_manager import ProgressManager
from agent_automation_system.models.progress import ProgressEntry

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["agents"])

# 默认 progress.txt 路径
_DEFAULT_PROGRESS_PATH = Path("data/progress.txt")


def _get_progress_manager(path: Optional[Path] = None) -> ProgressManager:
    return ProgressManager(file_path=path or _DEFAULT_PROGRESS_PATH)


def _entry_to_dict(entry: ProgressEntry) -> dict:
    """将 ProgressEntry 转为 API 响应格式"""
    return {
        "task_id": entry.task_id,
        "status": entry.status.value,
        "role": entry.role,
        "started": entry.started.isoformat() if entry.started else None,
        "finished": entry.finished.isoformat() if entry.finished else None,
        "git_sha": entry.git_sha or None,
        "git_msg": entry.git_msg or None,
        "error": entry.error or None,
        "retry": entry.retry,
    }


def _summarize_agents(entries: list[ProgressEntry]) -> list[dict]:
    """按 role 聚合 Agent 状态摘要"""
    by_role: dict[str, dict] = {}
    for e in entries:
        role = e.role or "unknown"
        if role not in by_role:
            by_role[role] = {
                "role": role,
                "total": 0,
                "completed": 0,
                "failed": 0,
                "in_progress": 0,
                "blocked": 0,
                "last_active_dt": None,
                "last_active": None,
            }
        agg = by_role[role]
        agg["total"] += 1
        if e.status.value == "COMPLETED":
            agg["completed"] += 1
        elif e.status.value == "FAILED":
            agg["failed"] += 1
        elif e.status.value in ("IN_PROGRESS", "in_progress"):
            agg["in_progress"] += 1
        elif e.status.value in ("BLOCKED", "blocked"):
            agg["blocked"] += 1
        finished = e.finished
        if finished and (agg["last_active_dt"] is None or finished > agg["last_active_dt"]):
            agg["last_active_dt"] = finished
            agg["last_active"] = finished.isoformat()

    result = sorted(by_role.values(), key=lambda x: x["role"])
    for r in result:
        r.pop("last_active_dt", None)
    return result


# ── 路由 ─────────────────────────────────────────────────


@router.get("/agents")
async def get_agents(
    role: Optional[str] = Query(None, description="按角色过滤"),
    status: Optional[str] = Query(None, description="按状态过滤"),
):
    """获取所有 Agent 实时状态

    从 progress.txt 读取所有记录，返回每个 Agent 的执行状态。

    Query Params:
        role: 角色过滤（如 dev, qa, pm）
        status: 状态过滤（如 COMPLETED, FAILED）
    """
    try:
        pm = _get_progress_manager()
        entries = pm.read_progress()
    except FileNotFoundError:
        return {
            "agents": [],
            "summary": {"total": 0, "completed": 0, "failed": 0},
            "by_role": [],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read agent status: {e}")

    # 过滤
    if role:
        entries = [e for e in entries if e.role == role]
    if status:
        entries = [e for e in entries if e.status.value == status]

    # 构建响应
    agent_list = [_entry_to_dict(e) for e in entries]

    return {
        "agents": agent_list,
        "summary": {
            "total": len(entries),
            "completed": sum(1 for e in entries if e.status.value == "COMPLETED"),
            "failed": sum(1 for e in entries if e.status.value == "FAILED"),
            "in_progress": sum(1 for e in entries if e.status.value in ("IN_PROGRESS", "in_progress")),
            "blocked": sum(1 for e in entries if e.status.value in ("BLOCKED", "blocked")),
        },
        "by_role": _summarize_agents(entries),
    }


@router.get("/agents/{task_id}")
async def get_agent_detail(task_id: str):
    """获取指定 Agent（task）的详细信息"""
    try:
        pm = _get_progress_manager()
        entry = pm.get_entry(task_id)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="progress.txt not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read agent detail: {e}")

    if entry is None:
        raise HTTPException(status_code=404, detail=f"Agent '{task_id}' not found")

    return _entry_to_dict(entry)

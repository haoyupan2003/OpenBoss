"""
任务进度 API（P3-004）

GET /api/tasks — 合并 task.json + progress.txt 返回统一任务视图
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from agent_automation_system.file_io.progress_manager import ProgressManager
from agent_automation_system.file_io.task_file_manager import TaskFileManager
from agent_automation_system.models.task import TaskStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["tasks"])

_DEFAULT_TASK_PATH = Path("data/task.json")
_DEFAULT_PROGRESS_PATH = Path("data/progress.txt")


def _get_managers():
    return (
        TaskFileManager(file_path=_DEFAULT_TASK_PATH),
        ProgressManager(file_path=_DEFAULT_PROGRESS_PATH),
    )


def _merge_task_progress(task, progress_map: dict) -> dict:
    """合并单个 task 与其 progress 条目"""
    entry = progress_map.get(task.id)
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "priority": task.priority.value if task.priority else "medium",
        "complexity": task.estimated_complexity.value if task.estimated_complexity else "medium",
        "suggested_role": task.suggested_role,
        "dependencies": task.dependencies,
        "status": task.status.value,
        "progress": {
            "status": entry.status.value,
            "role": entry.role,
            "started": entry.started.isoformat() if entry.started else None,
            "finished": entry.finished.isoformat() if entry.finished else None,
            "git_sha": entry.git_sha or None,
            "git_msg": entry.git_msg or None,
            "error": entry.error or None,
        } if entry else None,
    }


# ── 路由 ─────────────────────────────────────────────────


@router.get("/tasks")
async def get_tasks(
    status: Optional[str] = Query(None, description="按状态过滤"),
    role: Optional[str] = Query(None, description="按角色过滤（仅看有 progress 的 task）"),
):
    """获取所有任务进度（合并 task.json + progress.txt）

    Query Params:
        status: 状态过滤（PENDING / COMPLETED / FAILED / IN_PROGRESS / BLOCKED）
        role: 角色过滤
    """
    try:
        tfm, pm = _get_managers()
        task_json = tfm.read_tasks()
        progress_entries = pm.read_progress()
    except FileNotFoundError:
        return {"tasks": [], "summary": {"total": 0, "completed": 0, "failed": 0, "pending": 0, "in_progress": 0, "blocked": 0}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read tasks: {e}")

    # progress 索引
    progress_map = {e.task_id: e for e in progress_entries}

    tasks = [_merge_task_progress(t, progress_map) for t in task_json.tasks]

    # 过滤
    if role:
        tasks = [t for t in tasks if t["progress"] and t["progress"]["role"] == role]
    if status:
        tasks = [t for t in tasks if t["status"] == status]

    return {
        "project_name": task_json.project_name,
        "tasks": tasks,
        "summary": {
            "total": len(tasks),
            "completed": sum(1 for t in tasks if t["status"] == "completed"),
            "failed": sum(1 for t in tasks if t["status"] == "failed"),
            "pending": sum(1 for t in tasks if t["status"] == "pending"),
            "in_progress": sum(1 for t in tasks if t["status"] == "in_progress"),
            "blocked": sum(1 for t in tasks if t["status"] == "blocked"),
        },
    }


@router.get("/tasks/{task_id}")
async def get_task_detail(task_id: str):
    """获取单个任务完整详情（P3-005 增强：执行历史 + 依赖关系）"""
    try:
        tfm, pm = _get_managers()
        task_json = tfm.read_tasks()
        progress_entries = pm.read_progress()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Data files not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read data: {e}")

    task = next((t for t in task_json.tasks if t.id == task_id), None)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

    # 最新 progress
    entry = next((e for e in progress_entries if e.task_id == task_id), None)

    # 依赖分析
    depends_on = task.dependencies or []
    dependent_tasks = [t.id for t in task_json.tasks if task_id in (t.dependencies or [])]

    # 依赖任务的状态
    dep_details = []
    for dep_id in depends_on:
        dep_task = next((t for t in task_json.tasks if t.id == dep_id), None)
        dep_entry = next((e for e in progress_entries if e.task_id == dep_id), None)
        dep_details.append({
            "id": dep_id,
            "title": dep_task.title if dep_task else "?",
            "status": dep_entry.status.value if dep_entry else (dep_task.status.value if dep_task else "?"),
        })

    # 被依赖任务
    blocked_details = []
    for bid in dependent_tasks:
        btask = next((t for t in task_json.tasks if t.id == bid), None)
        blocked_details.append({"id": bid, "title": btask.title if btask else "?"})

    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "priority": task.priority.value if task.priority else "medium",
        "complexity": task.estimated_complexity.value if task.estimated_complexity else "medium",
        "suggested_role": task.suggested_role,
        "status": task.status.value,
        "retry_count": task.retry_count,
        "dependencies": {
            "depends_on": dep_details,
            "blocks": blocked_details,
        },
        "execution": {
            "role": entry.role,
            "status": entry.status.value,
            "started": entry.started.isoformat() if entry.started else None,
            "finished": entry.finished.isoformat() if entry.finished else None,
            "duration_seconds": (entry.finished - entry.started).total_seconds() if entry.started and entry.finished else None,
            "git_sha": entry.git_sha or None,
            "git_msg": entry.git_msg or None,
            "error": entry.error or None,
            "retry": entry.retry,
        } if entry else None,
    }

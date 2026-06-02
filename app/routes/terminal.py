"""
终端输出 API（P3-009）

GET /api/terminal/{agent_id} — 返回 tmux 终端实时输出
集成 TmuxManager 获取 pane 内容
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from agent_automation_system.tmux_manager.tmux_manager import TmuxManager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/terminal", tags=["terminal"])

# 默认 tmux session 名称
_DEFAULT_SESSION = "openboss"


def _get_tmux() -> Optional[TmuxManager]:
    """获取 TmuxManager（不抛异常）"""
    try:
        mgr = TmuxManager()
        if mgr.is_available:
            return mgr
    except Exception:
        pass
    return None


@router.get("/{agent_id}")
async def get_terminal_output(
    agent_id: str,
    lines: int = Query(50, ge=1, le=500, description="返回行数"),
    session: str = Query(_DEFAULT_SESSION, description="tmux 会话名"),
):
    """获取 Agent 终端实时输出

    从 tmux pane 捕获最近 N 行输出。
    如果 tmux 不可用，返回 offline 状态。

    Args:
        agent_id: Agent 标识（如 agent_dev_001）
        lines: 返回行数（默认 50，最大 500）
        session: tmux 会话名（默认 openboss）
    """
    mgr = _get_tmux()
    if mgr is None:
        return {
            "agent_id": agent_id,
            "output": [],
            "available": False,
            "message": "tmux not available on this host",
        }

    window_name = agent_id
    sessions = mgr.list_sessions()

    if session not in sessions:
        return {
            "agent_id": agent_id,
            "output": [],
            "available": True,
            "session": session,
            "message": f"session '{session}' not found",
        }

    try:
        windows = mgr.list_windows(session)
        if window_name not in windows:
            return {
                "agent_id": agent_id,
                "output": [],
                "available": True,
                "session": session,
                "message": f"window '{window_name}' not found in session '{session}'",
            }

        output_lines = mgr.capture_pane_history(session, window_name, lines=lines)
        return {
            "agent_id": agent_id,
            "output": output_lines,
            "available": True,
            "session": session,
            "lines": len(output_lines),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to capture terminal: {e}")


@router.get("/{agent_id}/status")
async def get_terminal_status(agent_id: str, session: str = Query(_DEFAULT_SESSION)):
    """获取 Agent 终端状态（轻量）"""
    mgr = _get_tmux()
    if mgr is None:
        return {"agent_id": agent_id, "available": False}

    sessions = mgr.list_sessions()
    has_session = session in sessions
    has_window = False
    if has_session:
        windows = mgr.list_windows(session)
        has_window = agent_id in windows

    return {
        "agent_id": agent_id,
        "available": True,
        "session_exists": has_session,
        "window_exists": has_window,
    }


class CommandRequest(BaseModel):
    """终端指令请求"""
    command: str = Field(..., min_length=1, max_length=2000, description="要发送的指令")


@router.post("/{agent_id}/command")
async def send_terminal_command(
    agent_id: str,
    req: CommandRequest,
    session: str = Query(_DEFAULT_SESSION, description="tmux 会话名"),
):
    """向 Agent 终端发送指令（P3-010）

    通过 tmux send-keys 向指定 Agent 窗口发送命令。
    """
    mgr = _get_tmux()
    if mgr is None:
        return {"agent_id": agent_id, "sent": False, "message": "tmux not available"}

    sessions = mgr.list_sessions()
    if session not in sessions:
        return {"agent_id": agent_id, "sent": False, "message": f"session '{session}' not found"}

    windows = mgr.list_windows(session)
    if agent_id not in windows:
        return {"agent_id": agent_id, "sent": False, "message": f"window '{agent_id}' not found"}

    try:
        mgr.send_command(session, agent_id, req.command)
        return {"agent_id": agent_id, "sent": True, "command": req.command[:100]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to send command: {e}")

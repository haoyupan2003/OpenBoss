"""
WebSocket ConnectionManager（P3-002）

多客户端实时推送管理器。
集成到 FastAPI 应用中，支持：
- connect / disconnect 生命周期
- broadcast 全员广播
- send_personal 单播
- 连接计数 + 客户端元数据
"""

import json
import logging
from typing import Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """WebSocket 连接管理器

    Args:
        max_connections: 最大连接数（0 = 无限制），默认 0
    """

    def __init__(self, max_connections: int = 0) -> None:
        if max_connections < 0:
            raise ValueError("max_connections must be >= 0")
        self._connections: dict[str, WebSocket] = {}
        self._metadata: dict[str, dict[str, Any]] = {}
        self._max = max_connections
        self._counter = 0

    # ── 属性 ──────────────────────────────────────────

    @property
    def active_count(self) -> int:
        """当前活跃连接数"""
        return len(self._connections)

    @property
    def max_connections(self) -> int:
        return self._max

    @property
    def is_full(self) -> bool:
        return self._max > 0 and self.active_count >= self._max

    @property
    def client_ids(self) -> list[str]:
        """所有已连接客户端 ID 列表"""
        return list(self._connections.keys())

    # ── 连接管理 ──────────────────────────────────────

    async def connect(self, websocket: WebSocket, client_id: str = "") -> str:
        """接受 WebSocket 连接

        Args:
            websocket: WebSocket 连接对象
            client_id: 客户端标识（空则自动生成）

        Returns:
            分配的 client_id

        Raises:
            ValueError: 连接数已达上限
        """
        if self.is_full:
            await websocket.close(code=1013, reason="max connections reached")
            raise ValueError(f"Connection limit reached ({self._max})")

        await websocket.accept()

        cid = client_id or self._generate_id()
        self._connections[cid] = websocket
        self._metadata[cid] = {"connected_at": str(websocket.client)}
        logger.info("WebSocket connected: %s (%d active)", cid, self.active_count)
        return cid

    def disconnect(self, client_id: str) -> None:
        """移除连接"""
        self._connections.pop(client_id, None)
        self._metadata.pop(client_id, None)
        logger.info("WebSocket disconnected: %s (%d active)", client_id, self.active_count)

    def is_connected(self, client_id: str) -> bool:
        """检查客户端是否在线"""
        return client_id in self._connections

    # ── 消息发送 ──────────────────────────────────────

    async def broadcast(self, message: dict[str, Any]) -> int:
        """向所有已连接客户端广播消息

        Args:
            message: 消息 dict（自动序列化为 JSON）

        Returns:
            成功发送的客户端数量
        """
        disconnected: list[str] = []
        sent = 0

        payload = json.dumps(message, default=str, ensure_ascii=False)
        for cid, ws in list(self._connections.items()):
            try:
                await ws.send_text(payload)
                sent += 1
            except Exception:
                disconnected.append(cid)

        # 清理断开的连接
        for cid in disconnected:
            self.disconnect(cid)

        return sent

    async def send_personal(self, message: dict[str, Any], client_id: str) -> bool:
        """向指定客户端发送消息

        Args:
            message: 消息 dict
            client_id: 目标客户端 ID

        Returns:
            是否发送成功
        """
        ws = self._connections.get(client_id)
        if ws is None:
            return False

        try:
            payload = json.dumps(message, default=str, ensure_ascii=False)
            await ws.send_text(payload)
            return True
        except Exception:
            self.disconnect(client_id)
            return False

    async def broadcast_except(
        self, message: dict[str, Any], exclude_id: str
    ) -> int:
        """向除指定客户端外的所有人广播

        Args:
            message: 消息 dict
            exclude_id: 排除的客户端 ID

        Returns:
            成功发送的客户端数量
        """
        disconnected: list[str] = []
        sent = 0
        payload = json.dumps(message, default=str, ensure_ascii=False)

        for cid, ws in list(self._connections.items()):
            if cid == exclude_id:
                continue
            try:
                await ws.send_text(payload)
                sent += 1
            except Exception:
                disconnected.append(cid)

        for cid in disconnected:
            self.disconnect(cid)

        return sent

    # ── 内部 ──────────────────────────────────────────

    def _generate_id(self) -> str:
        self._counter += 1
        return f"ws-{self._counter:04d}"

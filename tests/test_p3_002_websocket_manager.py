"""
P3-002 测试：ConnectionManager WebSocket 连接管理

验证多客户端 WebSocket 连接管理器的核心行为：
1. 连接/断开生命周期
2. 广播 / 单播 / 排除广播
3. 最大连接数限制
4. 断线自动清理
5. 集成到 FastAPI WebSocket 端点
"""

import json
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.websocket import ConnectionManager
from app.main import app


# ── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def manager():
    return ConnectionManager(max_connections=10)


@pytest.fixture
def unlimited_manager():
    return ConnectionManager(max_connections=0)


def _mock_ws():
    ws = AsyncMock()
    ws.client = "test-client"
    return ws


# ── 属性 ──────────────────────────────────────────────────


class TestProperties:
    """基本属性"""

    def test_default_max_connections(self):
        m = ConnectionManager()
        assert m.max_connections == 0
        assert m.is_full is False

    def test_custom_max(self, manager):
        assert manager.max_connections == 10

    def test_active_count_starts_zero(self, manager):
        assert manager.active_count == 0

    def test_is_full_false_when_empty(self, manager):
        assert manager.is_full is False

    def test_client_ids_empty_initially(self, manager):
        assert manager.client_ids == []

    def test_negative_max_raises(self):
        with pytest.raises(ValueError, match="max_connections"):
            ConnectionManager(max_connections=-1)


# ── 连接管理 ──────────────────────────────────────────────


class TestConnectDisconnect:
    """connect / disconnect 生命周期"""

    @pytest.mark.asyncio
    async def test_connect_accepts_and_returns_id(self, manager):
        ws = _mock_ws()
        cid = await manager.connect(ws)
        assert cid.startswith("ws-")
        assert manager.active_count == 1
        ws.accept.assert_called_once()

    @pytest.mark.asyncio
    async def test_connect_with_custom_id(self, manager):
        ws = _mock_ws()
        cid = await manager.connect(ws, client_id="agent-dev-001")
        assert cid == "agent-dev-001"
        assert manager.is_connected("agent-dev-001")

    @pytest.mark.asyncio
    async def test_disconnect_removes_client(self, manager):
        ws = _mock_ws()
        cid = await manager.connect(ws)
        manager.disconnect(cid)
        assert manager.active_count == 0
        assert manager.is_connected(cid) is False

    @pytest.mark.asyncio
    async def test_disconnect_idempotent(self, manager):
        """重复 disconnect 不报错"""
        manager.disconnect("nonexistent")
        assert manager.active_count == 0

    @pytest.mark.asyncio
    async def test_is_connected(self, manager):
        ws = _mock_ws()
        cid = await manager.connect(ws)
        assert manager.is_connected(cid) is True
        assert manager.is_connected("nonexistent") is False

    @pytest.mark.asyncio
    async def test_multiple_connections(self, manager):
        for i in range(5):
            cid = await manager.connect(_mock_ws(), client_id=f"client-{i}")
            assert cid == f"client-{i}"
        assert manager.active_count == 5
        assert len(manager.client_ids) == 5

    @pytest.mark.asyncio
    async def test_max_connections_reached(self):
        m = ConnectionManager(max_connections=2)
        await m.connect(_mock_ws())
        await m.connect(_mock_ws())
        assert m.is_full is True

        ws3 = _mock_ws()
        with pytest.raises(ValueError, match="limit"):
            await m.connect(ws3)
        ws3.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_unlimited_never_full(self, unlimited_manager):
        for _ in range(100):
            await unlimited_manager.connect(_mock_ws())
        assert unlimited_manager.active_count == 100
        assert unlimited_manager.is_full is False


# ── 广播 ──────────────────────────────────────────────────


class TestBroadcast:
    """broadcast 广播"""

    @pytest.mark.asyncio
    async def test_broadcast_to_all(self, manager):
        ws1 = _mock_ws()
        ws2 = _mock_ws()
        c1 = await manager.connect(ws1, "c1")
        c2 = await manager.connect(ws2, "c2")

        sent = await manager.broadcast({"type": "update", "data": "hello"})
        assert sent == 2

        # 两个都收到
        ws1.send_text.assert_called_once()
        ws2.send_text.assert_called_once()

        payload1 = ws1.send_text.call_args[0][0]
        assert '"type": "update"' in payload1
        assert '"data": "hello"' in payload1

    @pytest.mark.asyncio
    async def test_broadcast_removes_dead_connections(self, manager):
        ws1 = _mock_ws()
        ws2 = _mock_ws()
        ws2.send_text.side_effect = RuntimeError("disconnected")
        await manager.connect(ws1, "c1")
        await manager.connect(ws2, "c2")

        sent = await manager.broadcast({"type": "ping"})
        # ws1 成功，ws2 断线被移除
        assert sent == 1
        assert manager.active_count == 1
        assert manager.is_connected("c1") is True
        assert manager.is_connected("c2") is False

    @pytest.mark.asyncio
    async def test_broadcast_empty_returns_zero(self, manager):
        sent = await manager.broadcast({"type": "ping"})
        assert sent == 0

    @pytest.mark.asyncio
    async def test_broadcast_message_json(self, manager):
        ws = _mock_ws()
        await manager.connect(ws, "c1")
        await manager.broadcast({"key": "value", "num": 42})
        payload = ws.send_text.call_args[0][0]
        parsed = json.loads(payload)
        assert parsed == {"key": "value", "num": 42}


# ── 单播 ──────────────────────────────────────────────────


class TestSendPersonal:
    """send_personal 单播"""

    @pytest.mark.asyncio
    async def test_send_to_specific_client(self, manager):
        ws1 = _mock_ws()
        ws2 = _mock_ws()
        await manager.connect(ws1, "c1")
        await manager.connect(ws2, "c2")

        ok = await manager.send_personal({"type": "private"}, "c1")
        assert ok is True
        ws1.send_text.assert_called_once()
        ws2.send_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_to_nonexistent(self, manager):
        ok = await manager.send_personal({"type": "x"}, "ghost")
        assert ok is False

    @pytest.mark.asyncio
    async def test_send_personal_removes_on_error(self, manager):
        ws = _mock_ws()
        ws.send_text.side_effect = RuntimeError("broken pipe")
        await manager.connect(ws, "c1")

        ok = await manager.send_personal({"type": "x"}, "c1")
        assert ok is False
        assert manager.active_count == 0


# ── 排除广播 ──────────────────────────────────────────────


class TestBroadcastExcept:
    """broadcast_except 排除广播"""

    @pytest.mark.asyncio
    async def test_excludes_specified_client(self, manager):
        ws1 = _mock_ws()
        ws2 = _mock_ws()
        ws3 = _mock_ws()
        await manager.connect(ws1, "c1")
        await manager.connect(ws2, "c2")
        await manager.connect(ws3, "c3")

        sent = await manager.broadcast_except({"type": "update"}, "c2")
        assert sent == 2
        ws1.send_text.assert_called_once()
        ws3.send_text.assert_called_once()
        ws2.send_text.assert_not_called()

    @pytest.mark.asyncio
    async def test_excludes_dead_connections(self, manager):
        ws1 = _mock_ws()
        ws2 = _mock_ws()
        ws2.send_text.side_effect = RuntimeError("dead")
        await manager.connect(ws1, "c1")
        await manager.connect(ws2, "c2")

        sent = await manager.broadcast_except({"type": "x"}, "c1")
        assert sent == 0  # c2 失败了
        assert manager.active_count == 1


# ── FastAPI 集成 ──────────────────────────────────────────


class TestWebSocketEndpoint:
    """FastAPI WebSocket 端点集成"""

    @pytest.mark.asyncio
    async def test_ws_endpoint_registered(self):
        """WebSocket 路由已注册"""
        ws_routes = [r for r in app.routes if hasattr(r, "path") and "/ws" in r.path]
        assert len(ws_routes) >= 1

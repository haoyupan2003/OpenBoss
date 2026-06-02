"""
P3-001 测试：FastAPI 应用骨架

验证 Web API 核心功能：
1. 应用实例创建
2. 路由注册（root / health / ping）
3. CORS 配置
4. 响应格式与状态码
5. OpenAPI 文档可访问
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app, settings


@pytest.fixture
async def client():
    """创建异步测试客户端"""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


# ── 应用实例 ──────────────────────────────────────────────


class TestAppInstance:
    """应用实例属性"""

    def test_title(self):
        assert app.title == "OpenBoss Agent System"

    def test_version(self):
        assert app.version == "0.2.0"

    def test_has_routes(self):
        assert len(app.routes) >= 5  # 3 custom + OpenAPI + docs

    def test_cors_middleware_registered(self):
        middlewares = [m.cls.__name__ for m in app.user_middleware]
        assert "CORSMiddleware" in middlewares

    def test_lifespan_registered(self):
        assert app.router.lifespan_context is not None


# ── 路由响应 ──────────────────────────────────────────────


class TestRoutes:
    """三个端点"""

    @pytest.mark.asyncio
    async def test_root_returns_info(self, client):
        resp = await client.get("/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["app"] == "OpenBoss Agent System"
        assert data["version"] == "0.2.0"
        assert data["status"] == "running"

    @pytest.mark.asyncio
    async def test_health_returns_200(self, client):
        resp = await client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"

    @pytest.mark.asyncio
    async def test_health_content_type(self, client):
        resp = await client.get("/health")
        assert "application/json" in resp.headers["content-type"]

    @pytest.mark.asyncio
    async def test_ping(self, client):
        resp = await client.get("/api/ping")
        assert resp.status_code == 200
        assert resp.json() == {"ping": "pong"}

    @pytest.mark.asyncio
    async def test_404_for_unknown_route(self, client):
        resp = await client.get("/nonexistent")
        assert resp.status_code == 404


# ── OpenAPI 文档 ──────────────────────────────────────────


class TestOpenAPI:
    """API 文档端点"""

    @pytest.mark.asyncio
    async def test_openapi_json(self, client):
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert schema["info"]["title"] == "OpenBoss Agent System"
        assert "/" in schema["paths"]
        assert "/health" in schema["paths"]
        assert "/api/ping" in schema["paths"]

    @pytest.mark.asyncio
    async def test_docs_accessible(self, client):
        resp = await client.get("/docs")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_redoc_accessible(self, client):
        resp = await client.get("/redoc")
        assert resp.status_code == 200


# ── CORS 配置 ─────────────────────────────────────────────


class TestCORSConfig:
    """CORS 中间件配置"""

    def test_cors_origins_configured(self):
        assert len(settings.CORS_ORIGINS) >= 2

    def test_cors_includes_localhost_vite(self):
        assert "http://localhost:5173" in settings.CORS_ORIGINS

    def test_cors_includes_localhost_react(self):
        assert "http://localhost:3000" in settings.CORS_ORIGINS


# ── Settings ──────────────────────────────────────────────


class TestSettings:
    """配置默认值"""

    def test_host_default(self):
        assert settings.HOST == "127.0.0.1"

    def test_port_default(self):
        assert settings.PORT == 8080

    def test_app_title(self):
        assert "OpenBoss" in settings.APP_TITLE

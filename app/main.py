"""
OpenBoss Web API — FastAPI 应用骨架（P3-001）

基于 PRD V2.0 §4.1 Web 管理面板：
- 仅监听 localhost，不暴露公网
- CORS 允许本地前端开发
- 路由模块化注册
- health check 端点

启动方式：
    uvicorn app.main:app --host 127.0.0.1 --port 8080 --reload
"""

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.websocket import ConnectionManager
from app.routes.alerts import router as alerts_router
from app.routes.agents import router as agents_router
from app.routes.bdd import router as bdd_router
from app.routes.requirements import router as requirements_router
from app.routes.tasks import router as tasks_router
from app.routes.terminal import router as terminal_router


# ── 配置 ────────────────────────────────────────────────


class Settings:
    """应用配置（可通过环境变量覆盖）"""

    APP_TITLE: str = "OpenBoss Agent System"
    APP_VERSION: str = "0.2.0"
    APP_DESCRIPTION: str = "主从架构分布式 Agent 自动化执行系统 — Web API"

    # 安全：默认仅监听 localhost（PRD §4.4.2）
    HOST: str = "127.0.0.1"
    PORT: int = 8080

    # CORS：仅允许本地前端
    CORS_ORIGINS: list[str] = [
        "http://localhost:5173",   # Vite dev
        "http://localhost:3000",   # React dev
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ]


settings = Settings()


# ── 生命周期 ─────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """应用启动/关闭钩子"""
    # startup
    app.state.started = True
    # 初始化 WebSocket 连接管理器（P3-002）
    app.state.ws_manager = ConnectionManager(max_connections=50)
    yield
    # shutdown
    app.state.started = False


# ── 应用实例 ─────────────────────────────────────────────


app = FastAPI(
    title=settings.APP_TITLE,
    version=settings.APP_VERSION,
    description=settings.APP_DESCRIPTION,
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由（P3-003+）
app.include_router(alerts_router)
app.include_router(agents_router)
app.include_router(bdd_router)
app.include_router(requirements_router)
app.include_router(tasks_router)
app.include_router(terminal_router)


# ── 路由 ─────────────────────────────────────────────────


@app.get("/", tags=["health"])
async def root():
    """根路径 — API 信息"""
    return {
        "app": settings.APP_TITLE,
        "version": settings.APP_VERSION,
        "status": "running",
    }


@app.get("/health", tags=["health"])
async def health_check():
    """健康检查端点"""
    return JSONResponse(
        content={
            "status": "healthy",
            "app": settings.APP_TITLE,
            "version": settings.APP_VERSION,
        },
        status_code=200,
    )


@app.get("/api/ping", tags=["health"])
async def ping():
    """轻量 ping"""
    return {"ping": "pong"}


# ── WebSocket ─────────────────────────────────────────────


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 连接端点 — Agent 状态实时推送"""
    manager: ConnectionManager = app.state.ws_manager
    client_id = await manager.connect(websocket)
    try:
        # 发送欢迎消息
        await manager.send_personal(
            {"type": "connected", "client_id": client_id}, client_id
        )
        # 保持连接，接收客户端消息
        while True:
            data = await websocket.receive_text()
            # echo back（后续替换为实际业务逻辑）
            await manager.send_personal(
                {"type": "echo", "data": data}, client_id
            )
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect(client_id)

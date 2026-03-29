"""Artemis Platform API — central hub for all Artemis modules."""
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from artemis.core.registry import registry
from artemis.core.settings import get_settings
from artemis.routers.agent import router as agent_router
from artemis.routers.dashboard import router as dashboard_router
from artemis.routers.modules import router as modules_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await registry.initialize()
    yield
    await registry.shutdown()


app = FastAPI(
    title="Artemis Personal OS Platform",
    description="Central hub that orchestrates Artemis-compatible modules",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins if isinstance(settings.cors_origins, list) else [settings.cors_origins],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(modules_router)
app.include_router(dashboard_router)
app.include_router(agent_router)


@app.get("/health")
async def health():
    healthy = sum(1 for m in registry.list_modules() if m.healthy)
    total = len(registry.list_modules())
    return {
        "status": "healthy",
        "service": "artemis",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "modules": {"healthy": healthy, "total": total},
    }


@app.get("/ready")
async def ready():
    return {"status": "ready"}

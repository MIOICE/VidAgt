from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.database import create_schema, engine
from app.core.redis import close_redis
from app.services.object_storage import object_storage


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.work_dir.mkdir(parents=True, exist_ok=True)
    if settings.auto_create_tables:
        await create_schema()
    await object_storage.ensure_bucket()
    yield
    await close_redis()
    await engine.dispose()


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Evidence-grounded multimodal video understanding agent.",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix=settings.api_prefix)


@app.get("/", tags=["system"])
async def root() -> dict[str, str]:
    return {"name": settings.app_name, "docs": "/docs", "health": "/api/v1/health/ready"}

from fastapi import APIRouter

from app.api.routes import analyses, health, tasks, uploads, videos

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(uploads.router)
api_router.include_router(videos.router)
api_router.include_router(tasks.router)
api_router.include_router(analyses.router)


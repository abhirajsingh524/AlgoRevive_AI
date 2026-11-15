from fastapi import APIRouter
from app.api.v1 import analysis, auth, bottlenecks, health, projects, repositories, ws

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(projects.router)
api_router.include_router(repositories.router)
api_router.include_router(analysis.router)
api_router.include_router(bottlenecks.router)
api_router.include_router(ws.router)

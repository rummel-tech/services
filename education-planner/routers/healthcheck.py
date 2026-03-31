"""Health check endpoints."""

from fastapi import APIRouter

router = APIRouter(tags=['health'])


@router.get('/health')
async def health() -> dict:
    return {'status': 'healthy', 'service': 'education-planner'}


@router.get('/ready')
async def ready() -> dict:
    return {'status': 'ready', 'database': 'connected'}

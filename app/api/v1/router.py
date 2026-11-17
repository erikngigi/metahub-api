from fastapi import APIRouter, Depends

from app.controllers import (
    health_controller,
    metadata_controller,
    tmdb_controller,
    tvmaze_controller,
)
from app.core.security import require_api_key

api_router = APIRouter(prefix="/api/v1")

# Public routes (health checks)
api_router.include_router(health_controller.router)

# Everything on this router requires a valid X-API-Key.
protected_router = APIRouter(dependencies=[Depends(require_api_key)])
protected_router.include_router(tmdb_controller.router)
protected_router.include_router(tvmaze_controller.router)
protected_router.include_router(metadata_controller.router)

api_router.include_router(protected_router)

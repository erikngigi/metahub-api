from fastapi import APIRouter, Depends

from app.api.deps import get_providers
from app.core.config import Settings, get_settings
from app.core.security import require_api_key
from app.providers.base import BaseProvider

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health(settings: Settings = Depends(get_settings)) -> dict:
    return {"status": "ok", "app": settings.app_name, "environment": settings.environment}


@router.get("/providers/status", dependencies=[Depends(require_api_key)])
async def providers_status(providers: list[BaseProvider] = Depends(get_providers)) -> dict:
    return {"providers": [{"name": p.name, "configured": p.is_configured} for p in providers]}

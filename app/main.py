from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.staticfiles import StaticFiles

from app.core.config import get_settings

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
FAVICON_PATH = STATIC_DIR / "meta-tags.ico"


settings = get_settings()
app = FastAPI(docs_url=None, title=settings.app_name)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/docs", include_in_schema=False)
async def swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title=f"{settings.app_name} - Docs",
        swagger_favicon_url="/static/meta-tags.ico",
    )


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "environment": settings.environment}

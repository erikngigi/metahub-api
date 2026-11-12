import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.http_client import HttpClient
from app.core.logging import setup_logging
from app.exceptions.handlers import register_exception_handlers
from app.providers.tmdb_provider import TmdbProvider

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
FAVICON_PATH = STATIC_DIR / "favicon.ico"


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings)

    http = HttpClient(settings)
    providers = [TmdbProvider(http, settings)]

    for provider in providers:
        if not provider.is_configured:
            logger.warning("Provider %r has no API key configured", provider.name)

    app.state.http_client = http
    app.state.providers = providers
    logger.info("Started in %s mode with providers: %s", settings.environment, [p.name for p in providers])

    yield

    await http.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    is_prod = settings.environment == "production"

    app = FastAPI(
        title=settings.app_name,
        version="1.0.0",
        lifespan=lifespan,
        # Hide interactive docs in production
        docs_url=None,
        redoc_url=None if is_prod else "/redoc",
        openapi_url=None if is_prod else "/openapi.json",
    )
    register_exception_handlers(app)
    app.include_router(api_router)

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/favicon.ico", include_in_schema=False)
    async def favicon() -> FileResponse:
        return FileResponse(FAVICON_PATH)

    if not settings.is_production:

        @app.get("/docs", include_in_schema=False)
        async def swagger_ui() -> HTMLResponse:
            return get_swagger_ui_html(
                openapi_url=app.openapi_url,
                title=f"{settings.app_name} - Docs",
                swagger_favicon_url="/static/favicon.ico",
            )

    return app


app = create_app()

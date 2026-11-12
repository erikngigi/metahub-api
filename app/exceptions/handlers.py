import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.exceptions.errors import AggregatorError, AuthenticationError, ProviderError

logger = logging.getLogger(__name__)


def _error_response(
    status_code: int,
    code: str,
    message: str,
    *,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    body = {"error": {"code": code, "message": message, **extra}}
    return JSONResponse(status_code=status_code, content=body, headers=headers)


async def aggregator_error_handler(request: Request, exc: AggregatorError) -> JSONResponse:
    level = logging.ERROR if exc.status_code >= 500 else logging.WARNING
    logger.log(level, "%s on %s %s: %s", exc.code, request.method, request.url.path, exc)

    extra: dict[str, Any] = {}
    if isinstance(exc, ProviderError):
        extra["provider"] = exc.provider

    headers = {"WWW-Authenticate": "ApiKey"} if isinstance(exc, AuthenticationError) else None
    return _error_response(exc.status_code, exc.code, exc.message, headers=headers, **extra)


async def request_validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Only loc and msg are returned. FastAPI's "input" and "ctx" fields can echo
    # client data back or contain values that aren't JSON serialisable.
    details = [
        {
            "field": ".".join(str(part) for part in err["loc"]),
            "message": err["msg"],
        }
        for err in exc.errors()
    ]
    logger.info("Request validation failed on %s: %s", request.url.path, details)
    return _error_response(422, "validation_error", "Request validation failed", details=details)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    # Covers framework-level errors such as 404 (unknown route) and 405.
    return _error_response(
        exc.status_code,
        f"http_{exc.status_code}",
        str(exc.detail),
        headers=getattr(exc, "headers", None),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Full traceback goes to the log; the client only sees a generic message.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return _error_response(500, "internal_error", "An unexpected error occurred")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AggregatorError, aggregator_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)

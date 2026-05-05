from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request, Response, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware

from app.api.auth import require_api_key
from app.api.errors import register_error_handlers
from app.api.routes_health import router as health_router
from app.api.routes_ops import router as ops_router
from app.api.routes_renders import router as renders_router
from app.api.routes_templates import router as templates_router
from app.core.config import get_settings
from app.core.logging import build_request_log_fields, setup_logging
from app.core.rate_limit import RateLimitMiddleware
from app.core.redis import close_arq_pool, create_arq_pool
from app.core.request_limits import RequestBodyLimitMiddleware
from app.db.session import (
    DatabaseConfigurationError,
    DatabaseConnectionError,
    create_tables,
    dispose_engine,
    verify_database_connection,
    verify_database_migrations,
)

logger = structlog.get_logger(__name__)


async def _prepare_database() -> None:
    settings = get_settings()
    try:
        if settings.database_auto_create:
            await create_tables()
            await logger.ainfo("database_auto_create_complete")
            return

        await verify_database_connection()
        await verify_database_migrations()
        await logger.ainfo("database_migrations_verified")
    except (DatabaseConfigurationError, DatabaseConnectionError) as exc:
        await logger.aerror("database_startup_failed", error=str(exc))
        raise


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(log_level=settings.log_level, json_output=not settings.debug)
    await _prepare_database()

    if settings.render_mode == "async":
        await create_arq_pool()
        await logger.ainfo("redis_pool_created", redis_url=settings.redis_url)

    await logger.ainfo(
        "startup",
        app_name=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        environment=settings.environment,
        render_mode=settings.render_mode,
        database_auto_create=settings.database_auto_create,
    )
    yield

    if settings.render_mode == "async":
        await close_arq_pool()

    await dispose_engine()
    await logger.ainfo("shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        lifespan=lifespan,
    )

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)
    app.add_middleware(RateLimitMiddleware)

    allow_credentials = "*" not in settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=allow_credentials,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_id_middleware(
        request: Request,
        call_next: Callable[[Request], Coroutine[Any, Any, Response]],
    ) -> Response:
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        start_time = time.perf_counter()
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - start_time) * 1000
            await logger.aexception(
                "request_failed",
                **build_request_log_fields(
                    request_id=request_id,
                    method=request.method,
                    path=request.url.path,
                    status_code=500,
                    duration_ms=duration_ms,
                ),
            )
            structlog.contextvars.clear_contextvars()
            raise

        duration_ms = (time.perf_counter() - start_time) * 1000
        response.headers["X-Request-ID"] = request_id
        await logger.ainfo(
            "request_completed",
            **build_request_log_fields(
                request_id=request_id,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=duration_ms,
            ),
        )
        structlog.contextvars.clear_contextvars()
        return response

    app.add_middleware(RequestBodyLimitMiddleware)

    register_error_handlers(app)

    app.include_router(health_router)
    app.include_router(health_router, prefix="/v1")
    protected_dependencies = [Security(require_api_key)]
    app.include_router(
        renders_router,
        prefix="/v1",
        dependencies=protected_dependencies,
    )
    app.include_router(
        templates_router,
        prefix="/v1",
        dependencies=protected_dependencies,
    )
    app.include_router(
        ops_router,
        prefix="/v1",
        dependencies=protected_dependencies,
    )

    return app


app = create_app()

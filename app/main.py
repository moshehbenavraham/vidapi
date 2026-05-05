from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_error_handlers
from app.api.routes_health import router as health_router
from app.api.routes_renders import router as renders_router
from app.api.routes_templates import router as templates_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.rate_limit import RateLimitMiddleware
from app.core.redis import close_arq_pool, create_arq_pool
from app.db.session import create_tables, dispose_engine

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    setup_logging(log_level=settings.log_level, json_output=not settings.debug)
    await create_tables()

    if settings.render_mode == "async":
        await create_arq_pool()
        await logger.ainfo("redis_pool_created", redis_url=settings.redis_url)

    await logger.ainfo(
        "startup",
        app_name=settings.app_name,
        version=settings.app_version,
        debug=settings.debug,
        render_mode=settings.render_mode,
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
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    register_error_handlers(app)

    app.include_router(health_router)
    app.include_router(health_router, prefix="/v1")
    app.include_router(renders_router, prefix="/v1")
    app.include_router(templates_router, prefix="/v1")

    return app


app = create_app()

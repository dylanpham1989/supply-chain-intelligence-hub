"""FastAPI application entrypoint."""

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from redis.asyncio import Redis
from starlette.exceptions import HTTPException as StarletteHTTPException

from ai.embeddings.hf_embedder import get_embedder
from app.api.health import router as health_router
from app.api.v1.router import api_router
from app.core import metrics
from app.core.config import settings
from app.core.errors import AppError
from app.core.logging import configure_logging, get_logger
from app.db.session import engine
from app.middleware.access_log import AccessLogMiddleware
from app.middleware.metrics import MetricsMiddleware
from app.middleware.request_context import RequestContextMiddleware

log = get_logger(__name__)

EMBEDDER_WARM_TIMEOUT_S = 60.0
METRICS_PATH = "/metrics"
# Probed and scraped every few seconds. Logged only when they answer with an error.
QUIET_PATHS = (METRICS_PATH, "/health", "/health/live", "/health/ready")

HTTP_ERROR_CODES = {
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    429: "rate_limited",
}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(env=settings.env, level="DEBUG" if settings.debug else "INFO")

    redis: Redis = Redis.from_url(settings.redis_url, decode_responses=True)

    app.state.engine = engine
    app.state.redis = redis
    app.state.queue = await create_pool(RedisSettings.from_dsn(settings.redis_url))

    # Answering a question embeds it, so the model loads here rather than inside
    # whichever request happens to be first. A failure is not fatal: health, auth
    # and every endpoint that does not retrieve still work, and the first
    # question pays for the load instead.
    try:
        await asyncio.wait_for(get_embedder().warm(), timeout=EMBEDDER_WARM_TIMEOUT_S)
    except Exception as exc:
        log.warning("embedder.warm_failed", error=str(exc))
    log.info("app.startup", env=settings.env, vector_backend=settings.vector_backend)

    try:
        yield
    finally:
        await app.state.queue.aclose()
        await redis.aclose()
        await engine.dispose()
        log.info("app.shutdown")


def create_app() -> FastAPI:
    # CI generates the frontend types off this, but prod does not need to publish it.
    expose_schema = settings.env in ("local", "test", "staging")

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs" if expose_schema else None,
        redoc_url=None,
        openapi_url="/openapi.json" if expose_schema else None,
        lifespan=lifespan,
    )

    # Starlette runs the last added middleware first, so the request id is bound
    # before anything else can log, and the access line is written by the layer
    # that sees the real status even when a handler raises.
    app.add_middleware(MetricsMiddleware, skip_paths=(METRICS_PATH,))
    app.add_middleware(AccessLogMiddleware, quiet_paths=QUIET_PATHS)
    app.add_middleware(RequestContextMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    if expose_schema:

        @app.get("/", include_in_schema=False)
        async def root() -> RedirectResponse:
            return RedirectResponse(url="/docs")

    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        log.warning(
            "request.failed",
            code=exc.code,
            status=exc.status_code,
            path=request.url.path,
            **exc.extra,
        )
        # No stack trace to the client; it goes to the log instead.
        return JSONResponse(
            status_code=exc.status_code,
            content={"code": exc.code, "message": exc.message},
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        # Same envelope as everything else, so a client branches on one shape.
        fields = [
            {"field": ".".join(str(p) for p in err["loc"][1:]), "problem": err["msg"]}
            for err in exc.errors()
        ]
        return JSONResponse(
            status_code=422,
            content={"code": "validation_error", "message": "Request is invalid", "fields": fields},
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "code": HTTP_ERROR_CODES.get(exc.status_code, "error"),
                "message": str(exc.detail),
            },
        )

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        log.exception("request.unhandled", path=request.url.path, error=str(exc))
        # The traceback goes to the log, never to the caller.
        return JSONResponse(
            status_code=500,
            content={"code": "internal_error", "message": "Internal server error"},
        )

    app.include_router(api_router, prefix=settings.api_prefix)
    app.include_router(health_router)

    @app.get(METRICS_PATH, include_in_schema=False)
    async def prometheus_metrics() -> Response:
        # Pool depth is read here rather than polled, so it costs nothing
        # between scrapes.
        metrics.observe_pool(app.state.engine)
        payload, content_type = metrics.render()
        return Response(content=payload, media_type=content_type)

    return app


app = create_app()

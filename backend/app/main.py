import time
import uuid
from typing import Callable
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.errors import (
    AppException,
    app_exception_handler,
    generic_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.core.logging import get_logger, request_id_ctx, setup_logging

setup_logging()
logger = get_logger("main")

app = FastAPI(
    title="AlgoRevive AI",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request ID middleware
@app.middleware("http")
async def request_id_middleware(request: Request, call_next: Callable[[Request], Response]) -> Response:
    req_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    token = request_id_ctx.set(req_id)
    start_time = time.perf_counter()
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        duration_ms = (time.perf_counter() - start_time) * 1000
        logger.info(
            f"{request.method} {request.url.path} - status={response.status_code} duration={duration_ms:.2f}ms"
        )
        return response
    finally:
        request_id_ctx.reset(token)


# Exception handlers
app.add_exception_handler(AppException, app_exception_handler)
app.add_exception_handler(StarletteHTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, generic_exception_handler)

# Include API v1 router
app.include_router(api_router, prefix="/api/v1")


# Root-level health endpoints (mirrors /api/v1/health for standard container probes)
@app.get("/health", tags=["health"])
def root_health() -> dict[str, str]:
    return {"status": "ok"}

"""FastAPI application entry point and centralized error handling."""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder

from app.config import get_settings
from app.exceptions.custom_exceptions import ResourceConflictError, ResourceNotFoundError
from app.routers import auth, reports, repositories


settings = get_settings()
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.app_name,
    version="2.0.0",
    description=(
        "AI-powered multi-agent code review platform. "
        "Upload a project ZIP to receive structured findings, ML risk prediction, "
        "and a professional review report."
    ),
)

# CORS — allow frontend origins (localhost, 127.0.0.1 on any port) during development
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
        "http://127.0.0.1:8000",
    ],
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(repositories.router)
app.include_router(reports.router)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log each completed request and log unexpected request failures."""
    try:
        response = await call_next(request)
    except Exception:
        logger.exception("Unhandled request error: %s %s", request.method, request.url.path)
        raise
    logger.info("%s %s returned %s", request.method, request.url.path, response.status_code)
    return response


@app.exception_handler(ResourceNotFoundError)
async def handle_not_found(_: Request, error: ResourceNotFoundError) -> JSONResponse:
    """Return a consistent JSON body for missing resources."""
    return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(error)})


@app.exception_handler(ResourceConflictError)
async def handle_conflict(_: Request, error: ResourceConflictError) -> JSONResponse:
    """Return a consistent JSON body for duplicate or conflicting data."""
    return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(error)})


@app.exception_handler(RequestValidationError)
async def handle_validation_error(_: Request, error: RequestValidationError) -> JSONResponse:
    """Return validation details when request data does not match a schema."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": jsonable_encoder(error.errors())},
    )


@app.exception_handler(Exception)
async def handle_unexpected_error(_: Request, error: Exception) -> JSONResponse:
    """Log unexpected errors without exposing internal details to API clients."""
    logger.exception("Unexpected application error", exc_info=error)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected server error occurred."},
    )


@app.get("/", tags=["Health"])
def root_health_check() -> dict[str, str]:
    """Return a small confirmation that the API process is running."""
    return {
        "message": "AI Multi-Agent Code Review Platform v2.0 is running.",
        "docs": "/docs",
        "features": "multi-agent LLM review, static analysis, ML risk prediction, structured findings",
    }
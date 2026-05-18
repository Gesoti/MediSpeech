"""FastAPI application factory."""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import engine
from app.routes import audio, auth, cases, reports, transcription
from app.utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for startup and shutdown."""
    # Startup — schema is managed by Alembic migrations, not create_all
    logger.info("Starting MediSpeech API")

    yield

    # Shutdown
    logger.info("Shutting down MediSpeech API")
    await engine.dispose()
    from app.utils.tracing import flush as flush_langfuse
    flush_langfuse()
    logger.info("Database connections closed")


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        lifespan=lifespan,
    )

    # Add CORS middleware — allow_credentials must be False when origins are not "*"
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Health check endpoint
    @app.get("/health")
    async def health_check() -> dict:  # type: ignore[misc]
        """Health check endpoint."""
        return {
            "status": "healthy",
            "service": "medispeech-api",
            "version": settings.api_version,
        }

    # Register routers
    app.include_router(auth.router)
    app.include_router(cases.router)
    app.include_router(audio.router)
    app.include_router(transcription.router)
    app.include_router(reports.router)

    return app


app = create_app()

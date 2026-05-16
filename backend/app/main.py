"""FastAPI application factory."""
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import Base, engine
from app.routes import audio, cases, reports, transcription
from app.utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for startup and shutdown."""
    # Startup
    logger.info("Starting MediSpeech API")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables created")

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

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
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
    app.include_router(cases.router)
    app.include_router(audio.router)
    app.include_router(transcription.router)
    app.include_router(reports.router)

    return app


app = create_app()

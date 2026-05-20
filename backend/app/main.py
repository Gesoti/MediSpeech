"""FastAPI application factory."""
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi

from app.config import settings
from app.db import engine, init_db
from app.routes import audio, auth, cases, reports, transcription
from app.utils.logger import get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Lifespan context manager for startup and shutdown."""
    logger.info("Starting MediSpeech API")
    await init_db()

    yield

    # Shutdown
    logger.info("Shutting down MediSpeech API")
    await engine.dispose()
    from app.utils.tracing import flush as flush_langfuse
    flush_langfuse()
    logger.info("Database connections closed")


_TAGS: list[dict[str, str]] = [
    {
        "name": "auth",
        "description": "Register a new user and obtain a JWT bearer token for all other endpoints.",
    },
    {
        "name": "cases",
        "description": "Veterinary cases — each case groups an audio recording, transcription, and report.",
    },
    {
        "name": "audio",
        "description": (
            "Upload audio files and trigger transcription. "
            "Use `/upload` for a single-shot file or `/upload/stream` for SSE streaming."
        ),
    },
    {
        "name": "transcriptions",
        "description": "Read and edit the raw transcription text produced by the Whisper service.",
    },
    {
        "name": "reports",
        "description": (
            "Generate, stream, save and finalise structured clinical reports. "
            "`/stream/{transcription_id}` returns SSE tokens from the LLM. "
            "Call `/stream/{transcription_id}/save` afterwards to persist the result."
        ),
    },
]


def create_app() -> FastAPI:
    """Create and configure FastAPI application."""
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
        description=(
            "MediSpeech backend — veterinary clinical documentation via audio transcription and LLM report generation.\n\n"
            "**Authentication:** all endpoints except `/api/auth/*` require `Authorization: Bearer <token>`.\n\n"
            "**Typical flow:**\n"
            "1. `POST /api/auth/register` or `/login` → get token\n"
            "2. `POST /api/cases` → create a case\n"
            "3. `POST /api/audio/{case_id}/upload` → upload audio, triggers Whisper transcription\n"
            "4. `POST /api/reports/stream/{transcription_id}` → stream LLM report (SSE)\n"
            "5. `POST /api/reports/stream/{transcription_id}/save` → persist the report\n"
            "6. `POST /api/reports/{report_id}/finalize` → mark report as final"
        ),
        openapi_tags=_TAGS,
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

    def custom_openapi() -> dict:  # type: ignore[return]
        if app.openapi_schema:
            return app.openapi_schema
        schema = get_openapi(
            title=app.title,
            version=app.version,
            description=app.description,
            openapi_version=app.openapi_version,
            tags=_TAGS,
            routes=app.routes,
        )
        schema.setdefault("components", {}).setdefault("securitySchemes", {})["BearerAuth"] = {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
        }
        for path_item in schema.get("paths", {}).values():
            for operation in path_item.values():
                if isinstance(operation, dict) and operation.get("tags") != ["auth"]:
                    operation.setdefault("security", [{"BearerAuth": []}])
        app.openapi_schema = schema
        return schema

    app.openapi = custom_openapi  # type: ignore[method-assign]

    return app


app = create_app()

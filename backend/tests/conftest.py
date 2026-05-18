"""Test configuration and fixtures."""
import asyncio
import tempfile
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import Base, get_db
from app.routes import audio, cases, reports, transcription


@pytest.fixture(autouse=True)
def patch_audio_storage(tmp_path, monkeypatch):
    """Redirect audio storage to a temp directory so tests don't need /audio."""
    monkeypatch.setattr(settings, "audio_storage_path", str(tmp_path))


@pytest.fixture(scope="function")
def test_engine():
    """Create test database engine."""
    async def setup():
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        return engine
    
    engine = asyncio.run(setup())
    yield engine
    
    async def cleanup():
        await engine.dispose()
    
    asyncio.run(cleanup())


@pytest.fixture
def client(test_engine):
    """Create test client with test database."""
    # Create session factory for test engine
    TestSessionLocal = sessionmaker(
        test_engine, class_=AsyncSession, expire_on_commit=False
    )
    
    app = FastAPI(
        title=settings.api_title,
        version=settings.api_version,
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
    async def health_check():  # type: ignore[misc]
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
    
    # Override dependency with test session factory
    async def override_get_db():  # type: ignore[misc]
        async with TestSessionLocal() as session:
            yield session
    
    app.dependency_overrides[get_db] = override_get_db
    
    return TestClient(app)




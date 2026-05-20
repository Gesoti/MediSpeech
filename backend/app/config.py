"""Application configuration using pydantic-settings."""
import os

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRET = "dev-secret-change-in-production"


class Settings(BaseSettings):
    """Application settings from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, env_ignore_empty=True)

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/medispeech"

    # API
    api_host: str = "localhost"
    api_port: int = 8000
    api_title: str = "MediSpeech API"
    api_version: str = "0.1.0"

    # Logging
    log_level: str = "INFO"

    # Microservice URLs
    transcription_service_url: str = "http://localhost:8001"
    llm_service_url: str = "http://localhost:8002"

    # Audio storage
    audio_storage_path: str = "/audio"

    # JWT authentication
    jwt_secret: str = _DEV_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24  # 24 hours

    @field_validator("jwt_secret")
    @classmethod
    def jwt_secret_must_be_strong(cls, v: str) -> str:
        if os.getenv("ENV", "development").lower() == "development":
            return v
        if v == _DEV_SECRET:
            raise ValueError("JWT_SECRET must be changed from the default in non-development environments")
        if len(v) < 32:
            raise ValueError("JWT_SECRET must be at least 32 characters")
        return v

    # CORS
    allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Langfuse observability
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str = "pk-lf-dev"
    langfuse_secret_key: str = "sk-lf-dev"


settings = Settings()

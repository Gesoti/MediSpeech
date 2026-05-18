"""Application configuration using pydantic-settings."""
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # CORS
    allowed_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]

    # Langfuse observability
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str = "pk-lf-dev"
    langfuse_secret_key: str = "sk-lf-dev"


settings = Settings()

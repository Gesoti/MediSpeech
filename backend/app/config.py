"""Application configuration using pydantic-settings."""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings from environment variables."""

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/medispeech"

    # API
    api_host: str = "localhost"
    api_port: int = 8000
    api_title: str = "MediSpeech API"
    api_version: str = "0.1.0"

    # Logging
    log_level: str = "INFO"

    # Model paths
    whisper_model_path: str = "/models/whisper-base"
    llm_model_path: str = "/models/biogpt"

    # Langfuse observability
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str = "pk-lf-dev"
    langfuse_secret_key: str = "sk-lf-dev"


settings = Settings()

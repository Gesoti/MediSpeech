import os
from pydantic_settings import BaseSettings, SettingsConfigDict

DOTENV = os.path.join(os.path.dirname(__file__), ".env")

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=DOTENV, case_sensitive=False, env_ignore_empty=True, extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8002
    biogpt_model: str = "microsoft/BioGPT"
    langfuse_host: str = "http://localhost:3000"
    langfuse_public_key: str = "pk-lf-dev"
    langfuse_secret_key: str = "sk-lf-dev"


settings = Settings()

"""Application settings loaded from environment variables or a local .env file."""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr


class Settings(BaseSettings):
    """Settings that can be changed without editing application code."""

    app_name: str = "Price Intelligence Tracker API"
    database_url: str = "sqlite:///./price_tracker.db"
    backend_api_url: str = "http://127.0.0.1:8000"
    rewalto_api_key: SecretStr | None = None

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

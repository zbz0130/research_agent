from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings shared by the API and its future workers."""

    app_name: str = "TraceLab API"
    version: str = "0.1.0"
    cors_origins: str = "http://localhost:8000,http://localhost:3000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="TRACELAB_",
        extra="ignore",
    )

    def parsed_cors_origins(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

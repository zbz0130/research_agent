from functools import lru_cache

from pydantic import PrivateAttr, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings shared by the API and its future workers."""

    app_name: str = "许愿机 API"
    brand_name: str = "许愿机"
    brand_name_en: str = "WishForge"
    version: str = "0.1.0"
    cors_origins: str = "http://localhost:8000,http://localhost:3000"
    storage_path: str = "data/wishforge.db"

    # Providers are deliberately separated by responsibility. A paper-search
    # credential must never be accidentally used by the experiment runner.
    paper_provider: str = "semantic_scholar"
    # Community sources (X/知乎/Reddit) are deliberately separate from
    # academic search.  The first version ships a demo provider; production
    # connectors can be configured later without reusing paper credentials.
    community_provider: str = "demo"
    explanation_provider: str = "openai"
    experiment_provider: str = "local"
    explanation_model: str = "gpt-4.1-mini"
    explanation_base_url: str = "https://api.openai.com/v1"
    demo_mode: bool = True
    paper_api_key: SecretStr | None = None
    community_api_key: SecretStr | None = None
    explanation_api_key: SecretStr | None = None
    experiment_api_key: SecretStr | None = None

    # Keys entered through the local web UI are intentionally process-local.
    # This private marker lets the status endpoint explain whether a value
    # came from .env or from the in-memory runtime overlay without exposing it.
    _runtime_api_key_slots: set[str] = PrivateAttr(default_factory=set)
    # Non-secret provider settings entered through the local web UI are also
    # process-local.  Keep the original values so a future reset operation can
    # restore the environment-backed configuration without re-reading secrets.
    _runtime_provider_slots: set[str] = PrivateAttr(default_factory=set)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="WISHFORGE_",
        env_ignore_empty=True,
        extra="ignore",
    )

    def parsed_cors_origins(self) -> list[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()

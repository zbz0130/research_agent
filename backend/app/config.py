import os
from functools import lru_cache
from pathlib import Path

from pydantic import PrivateAttr, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = None if os.getenv("WISHFORGE_DESKTOP_SIDECAR") == "1" else PROJECT_ROOT / ".env"


class Settings(BaseSettings):
    """Runtime settings shared by the API and its future workers."""

    app_name: str = "许愿机 API"
    brand_name: str = "许愿机"
    brand_name_en: str = "WishForge"
    version: str = "0.2.2"
    cors_origins: str = "http://localhost:8000,http://localhost:3000"
    storage_path: str = "data/wishforge.db"

    # Providers are deliberately separated by responsibility. A paper-search
    # credential must never be accidentally used by the experiment runner.
    paper_provider: str = "multi_source"
    paper_base_url: str | None = None
    paper_model: str | None = None
    paper_enabled: bool = True
    # Community sources are deliberately separate from academic search.  The
    # public Hacker News provider is the default real-time source; X and
    # Reddit remain opt-in because their official APIs require credentials.
    community_provider: str = "hacker_news"
    community_base_url: str | None = "https://hacker-news.firebaseio.com/v0"
    community_model: str | None = None
    community_enabled: bool = True
    explanation_provider: str = "openai"
    explanation_enabled: bool = True
    experiment_provider: str = "local"
    experiment_base_url: str | None = None
    experiment_model: str | None = None
    experiment_enabled: bool = False
    explanation_model: str = "gpt-4.1-mini"
    explanation_base_url: str = "https://api.openai.com/v1"
    explanation_timeout_seconds: float = 90.0
    # A release build must never silently replace failed live retrieval with
    # fixtures. Demo mode remains available for local demos and tests only.
    demo_mode: bool = False
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
        # Resolve from the repository root instead of the process working
        # directory, so starting Uvicorn from ``backend`` still loads the
        # same local configuration file.
        env_file=ENV_FILE,
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

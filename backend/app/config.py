"""Application settings loaded from environment."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Core
    environment: str = "development"
    log_level: str = "INFO"

    # Database
    database_url: str
    database_url_sync: str | None = None

    # Redis / Celery
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # MinIO
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "jobhunter"
    minio_use_ssl: bool = False

    # Auth
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    jwt_access_ttl_min: int = 15
    jwt_refresh_ttl_days: int = 7

    # Encryption
    master_encryption_key: str

    # LLM
    anthropic_api_key: str = ""
    llm_model_scoring: str = "claude-haiku-4-5-20251001"
    llm_model_generation: str = "claude-sonnet-4-6"

    # Frontend
    vite_api_base_url: str = "http://localhost:8000/api/v1"

    # Observability
    sentry_dsn: str = ""

    # Bootstrap
    bootstrap_admin_email: str = ""
    bootstrap_admin_password: str = ""

    # Rate limits
    rate_limit_global_per_min: int = Field(default=100)
    rate_limit_llm_per_min: int = Field(default=10)

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def database_url_sync_effective(self) -> str:
        return self.database_url_sync or self.database_url


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]

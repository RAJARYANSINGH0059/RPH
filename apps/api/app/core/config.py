"""Application settings. All secrets come from environment variables."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "PS05-X API"
    app_version: str = "0.1.0"
    environment: str = Field(default="development", alias="APP_ENV")
    database_url: str = Field(default=f"sqlite:///{API_ROOT / 'ps05x.db'}", alias="DATABASE_URL")
    jwt_secret: str = Field(default="dev-only-change-me", alias="JWT_SECRET")
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = Field(default=480, alias="ACCESS_TOKEN_MINUTES")
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")
    storage_dir: str = Field(default=str(API_ROOT / "data"), alias="STORAGE_DIR")
    max_upload_bytes: int = Field(default=25 * 1024 * 1024, alias="MAX_UPLOAD_BYTES")
    max_pdf_pages: int = Field(default=200, alias="MAX_PDF_PAGES")

    # Demo accounts (configured via env; never committed)
    demo_analyst_email: str = Field(default="analyst@demo.local", alias="DEMO_ANALYST_EMAIL")
    demo_analyst_password: str = Field(default="", alias="DEMO_ANALYST_PASSWORD")
    demo_supervisor_email: str = Field(default="supervisor@demo.local", alias="DEMO_SUPERVISOR_EMAIL")
    demo_supervisor_password: str = Field(default="", alias="DEMO_SUPERVISOR_PASSWORD")
    demo_admin_email: str = Field(default="admin@demo.local", alias="DEMO_ADMIN_EMAIL")
    demo_admin_password: str = Field(default="", alias="DEMO_ADMIN_PASSWORD")

    # Connectors (optional)
    enable_rdap: bool = Field(default=False, alias="ENABLE_RDAP")
    enable_dns: bool = Field(default=False, alias="ENABLE_DNS")
    urlhaus_auth_key: str = Field(default="", alias="URLHAUS_AUTH_KEY")
    threatfox_auth_key: str = Field(default="", alias="THREATFOX_AUTH_KEY")
    misp_url: str = Field(default="", alias="MISP_URL")
    misp_key: str = Field(default="", alias="MISP_KEY")
    connector_timeout_seconds: float = Field(default=6.0, alias="CONNECTOR_TIMEOUT_SECONDS")

    # Benchmark namespace (sealed truth). Analyst API never reads this.
    benchmark_store_dir: str = Field(default=str(API_ROOT / "data" / "sealed"), alias="BENCHMARK_STORE_DIR")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
